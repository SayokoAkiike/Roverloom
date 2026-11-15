"""One wheel-model step as a problem in generalized velocities, built from a dumped solver input.

Generalized velocity q has 12 entries: the body's linear velocity v (3, cm/s), its angular velocity
w (3, rad/s), and the six wheels' spins (rad/s). The mass matrix M is block diagonal: M_body I3, the
body's world inertia restricted to its free axes, and each wheel's spin inertia I_w.

One step, in Chaos's order: q* is q after gravity, normal loads, and known pushes for dt. The
solver then adds impulses dt x through constraint rows G, so q' = q* + M^-1 G^T dt x, where x holds,
per wheel, its tangential ground force (F_f, F_l) and its motor or brake torque tau:

- contact rows, wheel i in contact: u_f = f.v + (r x f).w - R spin_i and u_l = l.v + (r x l).w,
  the end-of-step slip of the wheel's contact point against the ground;
- motor row, wheel i: s = spin_i - target_i.

The ground's force acts on the body at r and on the wheel's rim as -F_f R; the motor's torque acts
on the wheel. As in WheelModel.cpp, the motor's reaction on the body is not modeled.

Units: cm, kg, s.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

Vec = list[float]
Mat = list[list[float]]
COAST, BRAKE = 2, 1


def dot(a: Vec, b: Vec) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def cross(a: Vec, b: Vec) -> Vec:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def matvec(m: Mat, v: Vec) -> Vec:
    return [dot(row, v) for row in m]


def invert3(m: Mat) -> Mat:
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return [
        [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
        [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
        [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det],
    ]


def cholesky_solve(a: Mat, b: Vec) -> Vec:
    """Solve a x = b for symmetric positive definite a."""
    n = len(a)
    low = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = a[i][j] - sum(low[i][k] * low[j][k] for k in range(j))
            if i == j:
                if s <= 0:
                    raise ValueError("matrix is not positive definite")
                low[i][i] = math.sqrt(s)
            else:
                low[i][j] = s / low[j][j]
    y = [0.0] * n
    for i in range(n):
        y[i] = (b[i] - sum(low[i][k] * y[k] for k in range(i))) / low[i][i]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (y[i] - sum(low[k][i] * x[k] for k in range(i + 1, n))) / low[i][i]
    return x


@dataclass
class Problem:
    dt: float
    radius: float
    wheel_inertia: float
    mass: float
    inertia: Mat  # Body world inertia on its free axes
    inv_inertia: Mat
    q_star: Vec
    rows: list[Vec]  # 3 per wheel: contact f, contact l, motor; zero rows where absent
    offsets: Vec  # w = G q - offsets
    friction_limit: Vec  # mu Fz per wheel, 0 out of contact
    torque_limit: Vec  # per wheel, 0 when coasting
    in_contact: list[bool]
    forward: list[Vec]
    lateral: list[Vec]
    arms: list[tuple[Vec, Vec]]  # r x f, r x l per wheel
    raw: dict[str, Any] = field(default_factory=dict)
    # Optional full mass matrix and its inverse, for models that couple the body and the wheels.
    dense_mass: Mat | None = None
    dense_inv: Mat | None = None

    @property
    def wheels(self) -> int:
        return len(self.in_contact)

    def inv_mass_apply(self, impulse: Vec) -> Vec:
        """M^-1 applied to a generalized impulse."""
        if self.dense_inv is not None:
            return matvec(self.dense_inv, impulse)
        out = [x / self.mass for x in impulse[:3]]
        out += matvec(self.inv_inertia, impulse[3:6])
        out += [x / self.wheel_inertia for x in impulse[6:]]
        return out

    def mass_apply(self, velocity: Vec) -> Vec:
        if self.dense_mass is not None:
            return matvec(self.dense_mass, velocity)
        out = [x * self.mass for x in velocity[:3]]
        out += matvec(self.inertia, velocity[3:6])
        out += [x * self.wheel_inertia for x in velocity[6:]]
        return out

    def impulse(self, x: Vec) -> Vec:
        """G^T dt x."""
        out = [0.0] * 12
        for row, value in zip(self.rows, x, strict=True):
            if value:
                for k in range(12):
                    out[k] += row[k] * value * self.dt
        return out

    def velocity_after(self, x: Vec) -> Vec:
        return [
            a + b for a, b in zip(self.q_star, self.inv_mass_apply(self.impulse(x)), strict=True)
        ]

    def slips(self, q: Vec) -> Vec:
        """w = G q - offsets, 3 per wheel."""
        return [dot(row, q) - c for row, c in zip(self.rows, self.offsets, strict=True)]

    def dual(self) -> tuple[Mat, Vec]:
        """A = dt G M^-1 G^T and b = G q* - offsets, so that w = A x + b."""
        columns = [self.inv_mass_apply(row) for row in self.rows]
        a = [[self.dt * dot(ri, cj) for cj in columns] for ri in self.rows]
        return a, self.slips(self.q_star)


def build(data: dict[str, Any]) -> Problem:
    """The step as WheelModel.cpp builds it, from one dumped line."""
    p, body, dt = data["params"], data["body"], data["dt"]
    inv_i, com = body["inv_inertia"], body["com"]
    force = list(body["ext"])
    torque = [0.0, 0.0, 0.0]
    limits, torques, contact, fwd, lat, arms = [], [], [], [], [], []
    for w in data["wheels"]:
        fz = max(0.0, p["spring"] * w["comp"] + p["damper"] * w["comp_rate"]) if w["hit"] else 0.0
        limits.append(p["friction"] * fz)
        contact.append(bool(w["hit"]))
        if w["hit"]:
            load = [fz * n for n in w["normal"]]
            force = [f + q for f, q in zip(force, load, strict=True)]
            torque = [
                t + q for t, q in zip(torque, cross(_sub(w["point"], com), load), strict=True)
            ]
        mode = w["mode"]
        torques.append(0.0 if mode == COAST else float(p["brake"] if mode == BRAKE else p["motor"]))
    v_known = [
        v + dt * (a + f * body["inv_mass"])
        for v, a, f in zip(body["v"], body["acc"], force, strict=True)
    ]
    w_known = [w + dt * t for w, t in zip(body["w"], matvec(inv_i, torque), strict=True)]
    rows, offsets = [], []
    for i, w in enumerate(data["wheels"]):
        r = _sub(w["point"], com)
        f, lv = w["forward"], w["lateral"]
        af, al = cross(r, f), cross(r, lv)
        fwd.append(f)
        lat.append(lv)
        arms.append((af, al))
        spin_row = [0.0] * 6
        if w["hit"]:
            spin_row[i] = -p["radius"]
            rows.append([*f, *af, *spin_row])
            rows.append([*lv, *al, *([0.0] * 6)])
        else:
            rows += [[0.0] * 12, [0.0] * 12]
        offsets += [0.0, 0.0]
        motor = [0.0] * 12
        if w["mode"] != COAST:
            motor[6 + i] = 1.0
        rows.append(motor)
        offsets.append(0.0 if w["mode"] == BRAKE else (w["target"] if w["mode"] != COAST else 0.0))
    q_star = [*v_known, *w_known, *(w["spin"] for w in data["wheels"])]
    singular = abs(_det3(inv_i)) < 1e-30
    return Problem(
        dt=dt,
        radius=p["radius"],
        wheel_inertia=p["inertia"],
        mass=1.0 / body["inv_mass"],
        inertia=[[0.0] * 3 for _ in range(3)] if singular else invert3(inv_i),
        inv_inertia=inv_i,
        q_star=q_star,
        rows=rows,
        offsets=offsets,
        friction_limit=limits,
        torque_limit=torques,
        in_contact=contact,
        forward=fwd,
        lateral=lat,
        arms=arms,
        raw=data,
    )


def _sub(a: Vec, b: Vec) -> Vec:
    return [x - y for x, y in zip(a, b, strict=True)]


def _det3(m: Mat) -> float:
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


def project(x: Vec, problem: Problem) -> Vec:
    """Onto every friction disk and torque interval."""
    out = list(x)
    for i in range(problem.wheels):
        limit = problem.friction_limit[i]
        size = math.hypot(out[3 * i], out[3 * i + 1])
        if size > limit:
            scale = limit / size if size > 0 else 0.0
            out[3 * i] *= scale
            out[3 * i + 1] *= scale
        lim = problem.torque_limit[i]
        out[3 * i + 2] = min(max(out[3 * i + 2], -lim), lim)
    return out


def evaluate(problem: Problem, x: Vec) -> dict[str, Any]:
    """Every check on one solution x, from the end-of-step velocities it gives."""
    q = problem.velocity_after(x)
    w = problem.slips(q)
    a, _ = problem.dual()
    natural_force = natural_torque = 0.0
    stick_slip = 0.0
    slide_angle = 0.0
    circle = torque = 0.0
    friction_power = motor_power = 0.0
    net_force = [0.0, 0.0, 0.0]
    net_torque = [0.0, 0.0, 0.0]
    for i in range(problem.wheels):
        f = (x[3 * i], x[3 * i + 1])
        tau = x[3 * i + 2]
        limit, lim = problem.friction_limit[i], problem.torque_limit[i]
        if lim > 0:
            torque = max(torque, (abs(tau) - lim) / lim)
            rho = 1.0 / a[3 * i + 2][3 * i + 2]
            trial = min(max(tau - rho * w[3 * i + 2], -lim), lim)
            natural_torque = max(natural_torque, abs(tau - trial) / lim)
            motor_power += tau * q[6 + i]
        if not problem.in_contact[i] or limit <= 0:
            continue
        u = (w[3 * i], w[3 * i + 1])
        size = math.hypot(*f)
        circle = max(circle, (size - limit) / limit)
        rho = 1.0 / max(a[3 * i][3 * i], a[3 * i + 1][3 * i + 1])
        tx, ty = f[0] - rho * u[0], f[1] - rho * u[1]
        ts = math.hypot(tx, ty)
        if ts > limit:
            tx, ty = tx * limit / ts, ty * limit / ts
        natural_force = max(natural_force, math.hypot(f[0] - tx, f[1] - ty) / limit)
        if size < limit * (1 - 1e-9):
            stick_slip = max(stick_slip, math.hypot(*u))
        elif math.hypot(*u) > 1e-9:
            cross_z = f[0] * u[1] - f[1] * u[0]
            slide_angle = max(
                slide_angle, math.degrees(math.atan2(abs(cross_z), -(f[0] * u[0] + f[1] * u[1])))
            )
        friction_power += f[0] * u[0] + f[1] * u[1]
        for c in range(3):
            net_force[c] += f[0] * problem.forward[i][c] + f[1] * problem.lateral[i][c]
            net_torque[c] += f[0] * problem.arms[i][0][c] + f[1] * problem.arms[i][1][c]
    kinetic = 0.5 * dot(q, problem.mass_apply(q)) - 0.5 * dot(
        problem.q_star, problem.mass_apply(problem.q_star)
    )
    change = [a - b for a, b in zip(q, problem.q_star, strict=True)]
    dissipation = 0.5 * dot(change, problem.mass_apply(change))
    work = problem.dt * (friction_power + motor_power)
    return {
        "natural_force": natural_force,
        "natural_torque": natural_torque,
        "stick_slip_cmps": stick_slip,
        "slide_angle_deg": slide_angle,
        "circle_excess": circle,
        "torque_excess": torque,
        "net_force": net_force,
        "net_torque": net_torque,
        "velocity": q[:3],
        "angular_velocity": q[3:6],
        "spins": q[6:],
        "friction_power": friction_power,
        "motor_power": motor_power,
        "numerical_dissipation": dissipation,
        # Kinetic energy change = dt (friction + motor power) - dissipation, exactly, for any x.
        "energy_identity_error": kinetic - (work - dissipation),
        "kinetic_change": kinetic,
    }
