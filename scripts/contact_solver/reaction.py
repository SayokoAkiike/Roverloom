"""The motor's reaction on the body: the current model against a coupled one, in the stand-in rig.

    python -m contact_solver.reaction --out <file.json>   (run from scripts/)

Research only; no Unreal model changes. See docs/results/unreal-wheel-model/motor-reaction.md.

- current: as WheelModel.cpp. Each wheel's spin has inertia I_w on its own, and the motor turns
  only it.
- coupled: the same generalized velocities, with each spin taken as relative to the body, as a
  motor turns it, and kinetic energy 0.5 I_w (sigma_i + a_i . w)^2. The mass matrix then couples
  the body's rotation to each spin about the axle a_i, and the motor's reaction on the body
  follows from it. Contact slip is unchanged, because it already uses the body's velocity at the
  contact point and the relative spin.

Both use method D, and both integrate position from the solved velocities in Chaos's order.
Angular momentum about the center of mass, of body and wheels, is L = I w + sum I_w (sigma_i +
a_i . w) a_i; its change over a step is checked against the ground's external torque times dt.
"""

from __future__ import annotations

import argparse
import json
import math
from typing import Any

from .methods import primal_active_set
from .problem import Problem, build, cholesky_solve, cross, dot, matvec
from .simulate import (
    DAMPER,
    MASS,
    MOUNTS,
    PRINCIPAL,
    RADIUS,
    REST,
    SPRING,
    integrate,
    rotate,
    world_inverse_inertia,
)

WHEEL_INERTIA = 0.4 * 15 * RADIUS**2

SCENARIOS: dict[str, dict[str, Any]] = {
    "start": {"slope": 0.0, "forward": 50.0, "yaw": 0.0, "seconds": 3.0, "from": 0.5},
    "stop": {
        "slope": 0.0,
        "forward": 50.0,
        "yaw": 0.0,
        "seconds": 3.0,
        "from": 0.5,
        "brake_at": 1.5,
    },
    "climb_start": {"slope": 10.0, "forward": 50.0, "yaw": 0.0, "seconds": 3.0, "from": 0.5},
    "turn": {"slope": 0.0, "forward": 0.0, "yaw": 28.178, "seconds": 3.0, "from": 0.5},
    # No ground: released 3 m up, the motors spin the wheels up from 0.1 s.
    "airborne": {
        "slope": 0.0,
        "forward": 50.0,
        "yaw": 0.0,
        "seconds": 0.8,
        "from": 0.1,
        "start_z": 300.0,
    },
}


def couple(problem: Problem, axles: list[list[float]]) -> None:
    """Replace the block mass matrix with the coupled one, and redo q* with it."""
    inertia = problem.inertia
    m = [[0.0] * 12 for _ in range(12)]
    for k in range(3):
        m[k][k] = problem.mass
    for a in range(3):
        for b in range(3):
            m[3 + a][3 + b] = inertia[a][b] + sum(WHEEL_INERTIA * ax[a] * ax[b] for ax in axles)
    for i, ax in enumerate(axles):
        for a in range(3):
            m[3 + a][6 + i] = m[6 + i][3 + a] = WHEEL_INERTIA * ax[a]
        m[6 + i][6 + i] = WHEEL_INERTIA
    inverse_columns = [
        cholesky_solve(m, [1.0 if r == c else 0.0 for r in range(12)]) for c in range(12)
    ]
    inv = [[inverse_columns[c][r] for c in range(12)] for r in range(12)]
    start = [
        *problem.raw["body"]["v"],
        *problem.raw["body"]["w"],
        *(w["spin"] for w in problem.raw["wheels"]),
    ]
    # Known generalized impulse over the step, from the block model's q*: gravity, loads, pushes.
    known = problem.mass_apply([a - b for a, b in zip(problem.q_star, start, strict=True)])
    problem.dense_mass, problem.dense_inv = m, inv
    problem.q_star = [a + b for a, b in zip(start, matvec(inv, known), strict=True)]


def momentum(
    inertia: list[list[float]], omega: list[float], spins: list[float], axles: list[list[float]]
) -> list[float]:
    out = matvec(inertia, omega)
    for s, ax in zip(spins, axles, strict=True):
        absolute = s + dot(ax, omega)
        out = [o + WHEEL_INERTIA * absolute * a for o, a in zip(out, ax, strict=True)]
    return out


def world_inertia(orient: list[float]) -> list[list[float]]:
    axes = [rotate(orient, e) for e in ([1, 0, 0], [0, 1, 0], [0, 0, 1])]
    return [
        [sum(axes[a][r] * axes[a][c] * PRINCIPAL[a] for a in range(3)) for c in range(3)]
        for r in range(3)
    ]


def run(model: str, scenario: str, rate: int) -> dict[str, Any]:
    spec = SCENARIOS[scenario]
    dt = 1.0 / rate
    slope = math.radians(spec["slope"])
    gravity = [-371.0 * math.sin(slope), 0.0, -371.0 * math.cos(slope)]
    pos, orient = [0.0, 0.0, spec.get("start_z", 70.0)], [1.0, 0.0, 0.0, 0.0]
    vel, omega, spins = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0] * 6
    rows = []
    for step in range(int(round(spec["seconds"] * rate))):
        t = step * dt
        driving = t >= spec["from"]
        braking = spec.get("brake_at") is not None and t >= spec["brake_at"]
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
                    "mode": 1 if braking else 0,
                    "target": 0.0 if braking else target,
                    "spin": spins[i],
                }
            )
        data = {
            "dt": dt,
            "params": {
                "radius": RADIUS,
                "inertia": WHEEL_INERTIA,
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
        axles = [list(right_axis) for _ in range(6)]
        if model == "coupled":
            couple(problem, axles)
        result = primal_active_set(problem)
        x = result["x"]
        q = problem.velocity_after(x)
        # External torque about the center of mass, from every ground force this step.
        torque = [0.0, 0.0, 0.0]
        for i, w in enumerate(wheels):
            if not problem.in_contact[i]:
                continue
            fz = max(0.0, SPRING * w["comp"] + DAMPER * w["comp_rate"])
            total = [
                fz * w["normal"][k] + x[3 * i] * w["forward"][k] + x[3 * i + 1] * w["lateral"][k]
                for k in range(3)
            ]
            arm = [w["point"][k] - pos[k] for k in range(3)]
            torque = [torque[k] + cross(arm, total)[k] for k in range(3)]
        inertia = world_inertia(orient)
        before = momentum(inertia, omega, spins, axles)
        after = momentum(inertia, q[3:6], q[6:], axles)
        balance = [after[k] - before[k] - dt * torque[k] for k in range(3)]
        vel, omega, spins = q[0:3], q[3:6], q[6:]
        pos = [pos[k] + dt * vel[k] for k in range(3)]
        orient = integrate(orient, omega, dt)
        w0, x0, y0, z0 = orient
        pitch = math.degrees(math.asin(max(-1.0, min(1.0, 2 * (w0 * y0 - z0 * x0)))))
        roll = math.degrees(math.atan2(2 * (w0 * x0 + y0 * z0), 1 - 2 * (x0 * x0 + y0 * y0)))
        rows.append(
            {
                "t": (step + 1) * dt,
                "pitch": pitch,
                "roll": roll,
                "forward": dot(vel, rotate(orient, [1, 0, 0])),
                "yaw_rate": math.degrees(omega[2]),
                "pitch_rate": math.degrees(dot(omega, rotate(orient, [0, 1, 0]))),
                "balance": math.sqrt(dot(balance, balance)),
                "natural": result["natural"],
            }
        )
    return {"model": model, "scenario": scenario, "rate": rate, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    runs = [run(m, s, r) for s in SCENARIOS for m in ("current", "coupled") for r in (60, 120)]
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(runs, handle)
    for r in runs:
        rows = r["rows"]
        pitch = max(abs(x["pitch"]) for x in rows)
        rate = max(abs(x["pitch_rate"]) for x in rows)
        peak = max(x["forward"] for x in rows)
        balance = max(x["balance"] for x in rows)
        print(
            f"{r['scenario']} {r['model']} {r['rate']}: max |pitch| {pitch:.4f} deg, "
            f"max |pitch rate| {rate:.3f} deg/s, peak forward {peak:.3f} cm/s, "
            f"end yaw rate {rows[-1]['yaw_rate']:.4f} deg/s, max L balance {balance:.3e}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
