"""Re-solve one dumped wheel-model step offline, to study the contact solver. Not gated; no scoring.

A run with -WheelDumpAt=<seconds> writes <scenario>_solver_input.json. This script rebuilds the same
problem as WheelModel.cpp and solves it two ways:

- pgs: a port of SolveWheels's projected Gauss-Seidel, with its objective tracked every pass;
- qp: the same step as one convex problem over every wheel's tangential force F and motor or brake
  torque tau, solved by accelerated projected gradient (FISTA with restart).

The convex problem: with x = (F_f, F_l, tau) for each wheel in contact, end-of-step slips are
w = A x + b, where w holds each wheel's contact slip u = (v_f - omega' R, v_l) and its spin error
s = omega' - target. A is symmetric positive semidefinite, so minimizing 0.5 x'Ax + b'x subject
to |F| <= mu Fz and |tau| <= limit gives stick (u = 0) or sliding against u, and a torque below its
limit (s = 0) or at it. The natural residual |x - P(x - rho w)| is zero only at that minimum.

Plain Python, so it runs in the project environment with nothing added.

    python scripts/wheel_solver_lab.py path/to/c3_solver_input.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

COAST, BRAKE = 2, 1
Vec = list[float]
Mat = list[list[float]]


def sub(a: Vec, b: Vec) -> Vec:
    return [x - y for x, y in zip(a, b, strict=True)]


def dot(a: Vec, b: Vec) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def cross(a: Vec, b: Vec) -> Vec:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def matvec(m: Mat, v: Vec) -> Vec:
    return [dot(row, v) for row in m]


def build(data: dict[str, Any]) -> dict[str, Any]:
    """The step's coupling and known velocities, as WheelModel.cpp builds them."""
    p, body, dt = data["params"], data["body"], data["dt"]
    inv_i, com = body["inv_inertia"], body["com"]
    force = list(body["ext"])
    torque = [0.0, 0.0, 0.0]
    wheels = [x for x in data["wheels"] if x["hit"]]
    for x in wheels:
        x["fz"] = max(0.0, p["spring"] * x["comp"] + p["damper"] * x["comp_rate"])
        x["limit"] = p["friction"] * x["fz"]
        load = [x["fz"] * n for n in x["normal"]]
        force = [f + q for f, q in zip(force, load, strict=True)]
        torque = [t + q for t, q in zip(torque, cross(sub(x["point"], com), load), strict=True)]
    v_known = [
        v + dt * (a + f * body["inv_mass"])
        for v, a, f in zip(body["v"], body["acc"], force, strict=True)
    ]
    w_known = [w + dt * t for w, t in zip(body["w"], matvec(inv_i, torque), strict=True)]
    dirs, arms, angular, known = [], [], [], []
    for x in wheels:
        r = sub(x["point"], com)
        at_contact = [a + b for a, b in zip(v_known, cross(w_known, r), strict=True)]
        for d in (x["forward"], x["lateral"]):
            arm = cross(r, d)
            dirs.append(d)
            arms.append(arm)
            angular.append(matvec(inv_i, arm))
            known.append(dot(d, at_contact))
    n = len(dirs)
    k = [
        [dot(dirs[a], dirs[b]) * body["inv_mass"] + dot(arms[a], angular[b]) for b in range(n)]
        for a in range(n)
    ]
    return {"p": p, "dt": dt, "wheels": wheels, "k": k, "known": known, "arms": arms, "dirs": dirs}


def torque_limit(p: dict[str, float], wheel: dict[str, Any]) -> float:
    if wheel["mode"] == COAST:
        return 0.0
    return float(p["brake"] if wheel["mode"] == BRAKE else p["motor"])


def target(wheel: dict[str, Any]) -> float:
    return 0.0 if wheel["mode"] == BRAKE else float(wheel["target"])


def qp_matrix(m: dict[str, Any]) -> tuple[Mat, Vec]:
    """A and b for x = (F_f, F_l, tau) per wheel."""
    p, dt, k, wheels = m["p"], m["dt"], m["k"], m["wheels"]
    r, inertia = p["radius"], p["inertia"]
    n = 3 * len(wheels)
    a = [[0.0] * n for _ in range(n)]
    b = [0.0] * n
    for i, wi in enumerate(wheels):
        for j in range(len(wheels)):
            for di in range(2):
                for dj in range(2):
                    a[3 * i + di][3 * j + dj] = dt * k[2 * i + di][2 * j + dj]
        a[3 * i][3 * i] += dt * r * r / inertia
        a[3 * i][3 * i + 2] = a[3 * i + 2][3 * i] = -dt * r / inertia
        a[3 * i + 2][3 * i + 2] = dt / inertia
        b[3 * i] = m["known"][2 * i] - wi["spin"] * r
        b[3 * i + 1] = m["known"][2 * i + 1]
        b[3 * i + 2] = wi["spin"] - target(wi)
    return a, b


def project(x: Vec, m: dict[str, Any]) -> Vec:
    out = list(x)
    for i, wheel in enumerate(m["wheels"]):
        size = math.hypot(out[3 * i], out[3 * i + 1])
        if size > wheel["limit"]:
            scale = wheel["limit"] / size if size > 0 else 0.0
            out[3 * i] *= scale
            out[3 * i + 1] *= scale
        lim = torque_limit(m["p"], wheel)
        out[3 * i + 2] = min(max(out[3 * i + 2], -lim), lim)
    return out


def natural(x: Vec, a: Mat, b: Vec, m: dict[str, Any]) -> dict[str, float]:
    """Largest |x - P(x - rho w)| per block: force over mu Fz, torque over its limit."""
    rho = 1.0 / max(a[i][i] for i in range(len(a)))
    w = [q + c for q, c in zip(matvec(a, x), b, strict=True)]
    r = sub(x, project([xi - rho * wi for xi, wi in zip(x, w, strict=True)], m))
    force = max(
        math.hypot(r[3 * i], r[3 * i + 1]) / max(wh["limit"], 1e-300)
        for i, wh in enumerate(m["wheels"])
    )
    torques = [
        abs(r[3 * i + 2]) / torque_limit(m["p"], wh)
        for i, wh in enumerate(m["wheels"])
        if torque_limit(m["p"], wh) > 0
    ]
    return {"force": force, "torque": max(torques, default=0.0)}


def objective(x: Vec, a: Mat, b: Vec) -> float:
    return 0.5 * dot(x, matvec(a, x)) + dot(b, x)


def largest_eigenvalue(a: Mat) -> float:
    v = [1.0] * len(a)
    value = 0.0
    for _ in range(500):
        w = matvec(a, v)
        value = math.sqrt(dot(w, w))
        v = [q / value for q in w]
    return value


def solve_qp(m: dict[str, Any], iterations: int, stop: float = 0.0) -> tuple[Vec, int]:
    a, b = qp_matrix(m)
    step = 1.0 / largest_eigenvalue(a)
    x = [0.0] * len(b)
    y, t = list(x), 1.0
    best = objective(x, a, b)
    done = 0
    for _ in range(iterations):
        gradient = [q + c for q, c in zip(matvec(a, y), b, strict=True)]
        nxt = project([yi - step * g for yi, g in zip(y, gradient, strict=True)], m)
        value = objective(nxt, a, b)
        if value > best:  # Restart momentum when the objective rises.
            y, t = list(x), 1.0
            continue
        best = value
        t_next = 0.5 * (1 + math.sqrt(1 + 4 * t * t))
        y = [n + ((t - 1) / t_next) * (n - o) for n, o in zip(nxt, x, strict=True)]
        x, t = nxt, t_next
        done += 1
        if stop > 0 and done % 10 == 0 and natural(x, a, b, m)["force"] <= stop:
            break
    return x, done


def local_friction(av: Vec, w: Mat, limit: float) -> list[float]:
    """Port of SolveContactFriction."""

    def at(lam: float) -> list[float]:
        d00, d11 = w[0][0] + lam, w[1][1] + lam
        det = d00 * d11 - w[0][1] * w[0][1]
        return [-(d11 * av[0] - w[0][1] * av[1]) / det, -(d00 * av[1] - w[0][1] * av[0]) / det]

    stick = at(0.0)
    if math.hypot(*stick) <= limit:
        return stick
    if limit <= 0:
        return [0.0, 0.0]
    low, high = 0.0, math.hypot(*av) / limit
    for _ in range(100):
        mid = 0.5 * (low + high)
        if math.hypot(*at(mid)) > limit:
            low = mid
        else:
            high = mid
    edge = at(high)
    size = math.hypot(*edge)
    return [edge[0] * limit / size, edge[1] * limit / size]


def solve_pgs(
    m: dict[str, Any], passes: int, order: str, stop: float = 0.0
) -> tuple[Vec, list[float]]:
    """Port of SolveWheels's pass loop. Returns x per wheel and the objective after each pass.

    With stop > 0, ends at the first pass whose natural residual is at or below it.
    """
    p, dt, k, wheels = m["p"], m["dt"], m["k"], m["wheels"]
    r, inertia = p["radius"], p["inertia"]
    n = len(wheels)
    vel = list(m["known"])
    solved = [0.0] * (2 * n)
    taus = [0.0] * n
    a, b = qp_matrix(m)
    trace = []
    for step in range(passes):
        indices = list(range(n))
        if order == "reverse" or (order == "alternate" and step % 2):
            indices.reverse()
        for i in indices:
            wl = wheels[i]
            lo, la = 2 * i, 2 * i + 1
            kl, kc, kt = k[lo][lo], k[lo][la], k[la][la]
            old = solved[lo], solved[la]
            free_l = vel[lo] - dt * (kl * old[0] + kc * old[1])
            free_t = vel[la] - dt * (kc * old[0] + kt * old[1])
            omega, tgt, lim = wl["spin"], target(wl), torque_limit(p, wl)
            spin_free = wl["mode"] == COAST
            tau = 0.0
            if not spin_free:
                w2 = [[dt * kl, dt * kc], [dt * kc, dt * kt]]
                force = local_friction([free_l - tgt * r, free_t], w2, wl["limit"])
                tau = inertia * (tgt - omega) / dt + force[0] * r
                spin_free = abs(tau) > lim
            if spin_free:
                tau = 0.0 if wl["mode"] == COAST else min(max(tau, -lim), lim)
                w2 = [[dt * (kl + r * r / inertia), dt * kc], [dt * kc, dt * kt]]
                free = [free_l - omega * r - dt * tau * r / inertia, free_t]
                force = local_friction(free, w2, wl["limit"])
            for row in range(len(vel)):
                vel[row] += dt * (
                    k[row][lo] * (force[0] - old[0]) + k[row][la] * (force[1] - old[1])
                )
            solved[lo], solved[la] = force
            taus[i] = tau
        x = []
        for i in range(n):
            x += [solved[2 * i], solved[2 * i + 1], taus[i]]
        trace.append(objective(x, a, b))
        if stop > 0 and natural(x, a, b, m)["force"] <= stop:
            break
    return x, trace


def net(x: Vec, m: dict[str, Any]) -> tuple[Vec, Vec]:
    forces = [x[3 * i + d] for i in range(len(m["wheels"])) for d in range(2)]
    total = [sum(f * d[c] for f, d in zip(forces, m["dirs"], strict=True)) for c in range(3)]
    turn = [sum(f * a[c] for f, a in zip(forces, m["arms"], strict=True)) for c in range(3)]
    return total, turn


def distance(a: Vec, b: Vec) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("dump", type=Path)
    parser.add_argument("--qp-iterations", type=int, default=100000)
    args = parser.parse_args()
    m = build(json.loads(args.dump.read_text(encoding="utf-8")))
    a, b = qp_matrix(m)
    reference, _ = solve_qp(m, args.qp_iterations)
    ref_force, ref_torque = net(reference, m)
    best = objective(reference, a, b)
    report: dict[str, Any] = {
        "wheels_in_contact": len(m["wheels"]),
        "qp": {"objective": best, "natural": natural(reference, a, b, m), "tau": reference[2::3]},
    }
    for passes in (200, 2000, 20000):
        for order in ("forward", "reverse", "alternate"):
            x, trace = solve_pgs(m, passes, order)
            force, torque = net(x, m)
            rises = sum(1 for p, q in zip(trace, trace[1:], strict=False) if q > p + 1e-12 * abs(p))
            report[f"pgs_{order}_{passes}"] = {
                "objective_gap": trace[-1] - best,
                "objective_rises": rises,
                "natural": natural(x, a, b, m),
                "net_force_vs_qp": distance(force, ref_force),
                "net_torque_vs_qp": distance(torque, ref_torque),
                "wheel_force_vs_qp_max": max(
                    math.hypot(x[3 * i] - reference[3 * i], x[3 * i + 1] - reference[3 * i + 1])
                    for i in range(len(m["wheels"]))
                ),
                "tau": x[2::3],
            }
    # Work to reach a natural residual of 1e-8 of mu Fz: PGS passes by order, FISTA iterations.
    to_target: dict[str, Any] = {}
    for order in ("forward", "reverse", "alternate"):
        _, trace = solve_pgs(m, 20000, order, stop=1e-8)
        to_target[f"pgs_{order}"] = len(trace) if len(trace) < 20000 else None
    _, iterations = solve_qp(m, 100000, stop=1e-8)
    to_target["fista"] = iterations if iterations < 100000 else None
    report["work_to_1e-8"] = to_target
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
