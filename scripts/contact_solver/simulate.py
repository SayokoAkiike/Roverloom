"""Short trajectories of the six-wheel rig in Python, one per solver, for time step and drift.

    python -m contact_solver.simulate --out <file.json>   (run from scripts/)

A stand-in for the Unreal rig, not a copy of it: pathfinder_6w's 853.5 kg box, six wheels with the
same suspension, rays down the body's axis to a flat plane (a slope tilts gravity instead), and
Chaos's step order: v += dt (g + F / M), w += dt I^-1 T, then position and orientation. There is no
sleep. Each solver sees the problems its own trajectory produces, so differences grow from the
solve, not from the setup.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from multiprocessing import Pool
from pathlib import Path
from typing import Any

from .compare import METHODS, remember, warm_start
from .problem import build, cross, dot, evaluate

MASS, GRAVITY = 853.5, 371.0
SIZE = (200.0, 150.0, 40.0)
MOUNTS = [(x, y, -20.0) for y in (-103.7, 103.7) for x in (97.6, 0.0, -97.6)]
RADIUS, REST = 25.0, 30.0
SPRING = MASS * GRAVITY / 6 / 5.0
DAMPER = 2 * 0.7 * math.sqrt(SPRING * MASS / 6)
PRINCIPAL = [
    MASS / 12 * (SIZE[1] ** 2 + SIZE[2] ** 2),
    MASS / 12 * (SIZE[0] ** 2 + SIZE[2] ** 2),
    MASS / 12 * (SIZE[0] ** 2 + SIZE[1] ** 2),
]
SETTLE = 0.5

SCENARIOS = {
    "straight": {"slope": 0.0, "forward": 50.0, "yaw": 0.0, "seconds": 3.0},
    "turn": {"slope": 0.0, "forward": 0.0, "yaw": 28.178, "seconds": 4.0},
    "climb10": {"slope": 10.0, "forward": 50.0, "yaw": 0.0, "seconds": 3.0},
    "hold10": {"slope": 10.0, "forward": 0.0, "yaw": 0.0, "seconds": 3.0},
}


def rotate(q: list[float], v: list[float]) -> list[float]:
    w, x, y, z = q
    u = [x, y, z]
    t = [2 * c for c in cross(u, v)]
    return [v[k] + w * t[k] + cross(u, t)[k] for k in range(3)]


def integrate(q: list[float], omega: list[float], dt: float) -> list[float]:
    """q + dt/2 (0, omega) q, normalized, as Chaos integrates rotation."""
    w, x, y, z = q
    ox, oy, oz = omega
    d = [
        -ox * x - oy * y - oz * z,
        ox * w + oy * z - oz * y,
        oy * w + oz * x - ox * z,
        oz * w + ox * y - oy * x,
    ]
    out = [a + 0.5 * dt * b for a, b in zip(q, d, strict=True)]
    n = math.sqrt(sum(c * c for c in out))
    return [c / n for c in out]


def world_inverse_inertia(q: list[float]) -> list[list[float]]:
    axes = [rotate(q, e) for e in ([1, 0, 0], [0, 1, 0], [0, 0, 1])]
    return [
        [sum(axes[a][r] * axes[a][c] / PRINCIPAL[a] for a in range(3)) for c in range(3)]
        for r in range(3)
    ]


def run(job: tuple[str, str, int]) -> dict[str, Any]:
    method, scenario, rate = job
    spec = SCENARIOS[scenario]
    _, solve, warm = METHODS[method]
    dt = 1.0 / rate
    slope = math.radians(spec["slope"])
    gravity = [-GRAVITY * math.sin(slope), 0.0, -GRAVITY * math.cos(slope)]
    pos, orient = [0.0, 0.0, 70.0], [1.0, 0.0, 0.0, 0.0]
    vel, omega, spins = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0] * 6
    last = None
    states, solve_times, residuals, sliding = [], [], [], []
    steps = int(round(spec["seconds"] * rate))
    for step in range(steps):
        t = step * dt
        driving = t >= SETTLE
        turn = math.radians(spec["yaw"] if driving else 0.0) * 103.7
        forward = spec["forward"] if driving else 0.0
        up = rotate(orient, [0, 0, 1])
        fwd_axis, right_axis = rotate(orient, [1, 0, 0]), rotate(orient, [0, 1, 0])
        wheels = []
        for i, mount in enumerate(MOUNTS):
            offset = rotate(orient, list(mount))
            m = [pos[k] + offset[k] for k in range(3)]
            reach = REST + RADIUS
            hit = up[2] > 1e-6 and 0 <= m[2] / up[2] <= reach
            dist = m[2] / up[2] if hit else reach
            point = [m[k] - dist * up[k] for k in range(3)]
            v_mount = [vel[k] + cross(omega, offset)[k] for k in range(3)]
            normal = [0.0, 0.0, 1.0]
            f = [fwd_axis[k] - dot(fwd_axis, normal) * normal[k] for k in range(3)]
            fn = math.sqrt(dot(f, f))
            f = [c / fn for c in f]
            lat = [right_axis[k] - dot(right_axis, normal) * normal[k] for k in range(3)]
            lat = [lat[k] - dot(lat, f) * f[k] for k in range(3)]
            ln = math.sqrt(dot(lat, lat))
            lat = [c / ln for c in lat]
            target = (forward + turn if i < 3 else forward - turn) / RADIUS
            wheels.append(
                {
                    "hit": hit,
                    "comp": reach - dist,
                    "comp_rate": -dot(v_mount, up),
                    "point": point,
                    "normal": normal,
                    "forward": f,
                    "lateral": lat,
                    "mode": 0,
                    "target": target,
                    "spin": spins[i],
                }
            )
        data = {
            "dt": dt,
            "params": {
                "radius": RADIUS,
                "inertia": 0.4 * 15 * RADIUS**2,
                "spring": SPRING,
                "damper": DAMPER,
                "friction": 0.6,
                "motor": 6e5,
                "brake": 2e6,
            },
            "body": {
                "inv_mass": 1 / MASS,
                "inv_inertia": world_inverse_inertia(orient),
                "com": pos,
                "v": vel,
                "w": omega,
                "acc": gravity,
                "ext": [0.0, 0.0, 0.0],
            },
            "wheels": wheels,
        }
        problem = build(data)
        start = warm_start(problem, last) if warm else None
        begin = time.perf_counter()
        result = solve(problem, start)
        solve_times.append(time.perf_counter() - begin)
        last = remember(problem, result["x"])
        checks = evaluate(problem, result["x"])
        residuals.append(max(checks["natural_force"], checks["natural_torque"]))
        x = result["x"]
        sliding.append(
            [
                problem.in_contact[i]
                and math.hypot(x[3 * i], x[3 * i + 1]) >= problem.friction_limit[i] * (1 - 1e-6)
                for i in range(6)
            ]
        )
        # Apply the forces as the rig does, then integrate in Chaos's order.
        force = [0.0, 0.0, 0.0]
        torque = [0.0, 0.0, 0.0]
        for i, w in enumerate(wheels):
            if not problem.in_contact[i]:
                continue
            fz = max(0.0, SPRING * w["comp"] + DAMPER * w["comp_rate"])
            total = [
                fz * w["normal"][k] + x[3 * i] * w["forward"][k] + x[3 * i + 1] * w["lateral"][k]
                for k in range(3)
            ]
            force = [force[k] + total[k] for k in range(3)]
            arm = [w["point"][k] - pos[k] for k in range(3)]
            torque = [torque[k] + cross(arm, total)[k] for k in range(3)]
        inv_i = data["body"]["inv_inertia"]
        vel = [vel[k] + dt * (gravity[k] + force[k] / MASS) for k in range(3)]
        omega = [omega[k] + dt * dot(inv_i[k], torque) for k in range(3)]
        pos = [pos[k] + dt * vel[k] for k in range(3)]
        orient = integrate(orient, omega, dt)
        spins = checks["spins"]
        yaw = math.degrees(
            math.atan2(
                2 * (orient[0] * orient[3] + orient[1] * orient[2]),
                1 - 2 * (orient[2] ** 2 + orient[3] ** 2),
            )
        )
        states.append({"t": (step + 1) * dt, "pos": pos, "yaw": yaw, "vel": vel, "omega": omega})
    switches = sum(
        1 for a, b in zip(sliding, sliding[1:], strict=False) for i in range(6) if a[i] != b[i]
    )
    times = sorted(solve_times)
    return {
        "method": method,
        "scenario": scenario,
        "rate": rate,
        "states": states,
        "max_natural": max(residuals),
        "median_natural": sorted(residuals)[len(residuals) // 2],
        "slide_switches": switches,
        "solve_seconds": {
            "median": times[len(times) // 2],
            "p95": times[int(0.95 * (len(times) - 1))],
            "p99": times[int(0.99 * (len(times) - 1))],
            "max": times[-1],
        },
        "finite": all(math.isfinite(c) for s in states for c in s["pos"] + s["vel"]),
    }


def at(states: list[dict[str, Any]], t: float) -> dict[str, Any]:
    return min(states, key=lambda s: abs(s["t"] - t))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--methods", nargs="*", default=list(METHODS))
    args = parser.parse_args()
    jobs = [(m, s, r) for m in args.methods for s in SCENARIOS for r in (60, 120)]
    with Pool(args.workers) as pool:
        runs = pool.map(run, jobs)
    by_key = {(r["method"], r["scenario"], r["rate"]): r for r in runs}
    report: dict[str, Any] = {}
    for (method, scenario, rate), r in by_key.items():
        ref = by_key.get(("D", scenario, rate))
        drift = None
        if ref:
            drift = max(math.dist(s["pos"], at(ref["states"], s["t"])["pos"]) for s in r["states"])
        other = by_key.get((method, scenario, 120 if rate == 60 else 60))
        timestep = None
        if other and rate == 60:
            timestep = max(
                math.dist(s["pos"], at(other["states"], s["t"])["pos"]) for s in r["states"]
            )
        end = r["states"][-1]
        report[f"{method}/{scenario}/{rate}"] = {
            "max_position_gap_to_D_cm": drift,
            "max_position_gap_60_vs_120_cm": timestep,
            "end_pos": end["pos"],
            "end_yaw": end["yaw"],
            "end_vel": end["vel"],
            "end_omega": end["omega"],
            "max_natural": r["max_natural"],
            "median_natural": r["median_natural"],
            "slide_switches": r["slide_switches"],
            "solve_seconds": r["solve_seconds"],
            "finite": r["finite"],
        }
    args.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"{len(report)} runs written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
