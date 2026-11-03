"""Solvers for one step, all on the same problem and judged by the same checks.

The dual problem, over x = (F_f, F_l, tau) per wheel:

    minimize 0.5 x'Ax + b'x  subject to  |F_i| <= mu Fz_i,  |tau_i| <= L_i,

with A = dt G M^-1 G^T positive semidefinite. Its minimizers can differ in x (forces are not
unique) but all give the same end-of-step velocities q'. The primal problem, over q' (12
unknowns):

    minimize 0.5 (q' - q*)'M(q' - q*) + sum_i dt mu Fz_i |u_i(q')| + sum_i dt L_i |s_i(q')|,

is strictly convex because M is positive definite, so q' is unique. Its two nonsmooth terms are
the friction disks and torque limits; they are what make the problem hard, whatever its size.

- block_gauss_seidel: methods A, B, and E. Each wheel's block (F, tau) is minimized exactly,
  with the others fixed, as WheelModel.cpp does. Order, warm start, and a regularization gamma
  diag(A) are options. It stops when the largest velocity change in a pass falls below a
  tolerance, or at a pass limit; the natural residual is reported separately.
- fista: method C. Accelerated projected gradient on the dual, restarted when the objective
  rises. It stops on the natural residual.
- primal_newton: method D. The primal with each norm smoothed as sqrt(|z|^2 + eps^2) - eps,
  minimized by damped Newton for a falling sequence of eps. Forces come from the gradient of
  each smoothed term, so they lie strictly inside each disk and are unique for each eps. It
  stops on the Newton decrement at the last eps, and the natural residual of the forces is
  reported.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from .problem import Mat, Problem, Vec, cholesky_solve, dot, matvec, project


def disk_block(g: Vec, b: Mat, limit: float) -> tuple[Vec, bool]:
    """Minimize 0.5 F'BF + g'F over |F| <= limit, for 2 x 2 B positive definite."""

    def at(lam: float) -> Vec:
        d00, d11 = b[0][0] + lam, b[1][1] + lam
        det = d00 * d11 - b[0][1] * b[1][0]
        return [-(d11 * g[0] - b[0][1] * g[1]) / det, -(d00 * g[1] - b[1][0] * g[0]) / det]

    stick = at(0.0)
    if math.hypot(*stick) <= limit:
        return stick, False
    if limit <= 0:
        return [0.0, 0.0], True
    low, high = 0.0, math.hypot(*g) / limit
    for _ in range(100):
        mid = 0.5 * (low + high)
        if math.hypot(*at(mid)) > limit:
            low = mid
        else:
            high = mid
    edge = at(high)
    size = math.hypot(*edge)
    return [edge[0] * limit / size, edge[1] * limit / size], True


def wheel_block(g: Vec, b: Mat, limit: float, torque_limit: float) -> Vec:
    """Exact minimum of the 3 x 3 block (F_f, F_l, tau): first with tau free, then at its limit."""
    if torque_limit <= 0:
        force, _ = disk_block(g[:2], [row[:2] for row in b[:2]], limit)
        return [*force, 0.0]
    btt = b[2][2]
    # Tau free: eliminate it, which is the motor holding its target.
    reduced_g = [g[k] - b[k][2] * g[2] / btt for k in range(2)]
    reduced_b = [[b[k][m] - b[k][2] * b[2][m] / btt for m in range(2)] for k in range(2)]
    force, _ = disk_block(reduced_g, reduced_b, limit)
    tau = -(g[2] + b[2][0] * force[0] + b[2][1] * force[1]) / btt
    if abs(tau) <= torque_limit:
        return [*force, tau]
    tau = math.copysign(torque_limit, tau)
    shifted = [g[k] + b[k][2] * tau for k in range(2)]
    force, _ = disk_block(shifted, [row[:2] for row in b[:2]], limit)
    return [*force, tau]


def natural_residual(problem: Problem, a: Mat, b: Vec, x: Vec) -> float:
    w = [p + q for p, q in zip(matvec(a, x), b, strict=True)]
    worst = 0.0
    for i in range(problem.wheels):
        limit = problem.friction_limit[i]
        if problem.in_contact[i] and limit > 0:
            rho = 1.0 / max(a[3 * i][3 * i], a[3 * i + 1][3 * i + 1])
            tx, ty = x[3 * i] - rho * w[3 * i], x[3 * i + 1] - rho * w[3 * i + 1]
            ts = math.hypot(tx, ty)
            if ts > limit:
                tx, ty = tx * limit / ts, ty * limit / ts
            worst = max(worst, math.hypot(x[3 * i] - tx, x[3 * i + 1] - ty) / limit)
        lim = problem.torque_limit[i]
        if lim > 0:
            rho = 1.0 / a[3 * i + 2][3 * i + 2]
            trial = min(max(x[3 * i + 2] - rho * w[3 * i + 2], -lim), lim)
            worst = max(worst, abs(x[3 * i + 2] - trial) / lim)
    return worst


def block_gauss_seidel(
    problem: Problem,
    passes: int = 200,
    tolerance: float = 1e-7,
    order: str = "forward",
    start: Vec | None = None,
    gamma: float = 0.0,
    stop_natural: float = 0.0,
) -> dict[str, Any]:
    """Methods A, B, and E.

    The stop rule is WheelModel.cpp's: the largest |dF| times its body-only diagonal entry, dt K,
    in a pass, below tolerance. With stop_natural > 0 it stops instead when the natural residual
    of the unregularized problem falls to that value, checked every 5 passes.
    """
    a, b = problem.dual()
    unregularized = a
    spin_term = problem.dt * problem.radius**2 / problem.wheel_inertia
    if gamma:
        a = [
            [v + (gamma * a[i][i] if i == j else 0.0) for j, v in enumerate(row)]
            for i, row in enumerate(a)
        ]
    n = problem.wheels
    x = project(list(start), problem) if start else [0.0] * (3 * n)
    for i in range(n):
        if not problem.in_contact[i]:
            x[3 * i] = x[3 * i + 1] = 0.0
    w = [p + q for p, q in zip(matvec(a, x), b, strict=True)]
    active = [i for i in range(n) if problem.in_contact[i] or problem.torque_limit[i] > 0]
    used, change = 0, 0.0
    for step in range(passes):
        indices = (
            list(reversed(active))
            if order == "reverse" or (order == "alternate" and step % 2)
            else active
        )
        change = 0.0
        for i in indices:
            s = slice(3 * i, 3 * i + 3)
            old = x[s]
            block = [row[s] for row in a[s]]
            g = [w[3 * i + k] - dot(block[k], old) for k in range(3)]
            limit = problem.friction_limit[i] if problem.in_contact[i] else 0.0
            if limit <= 0:
                tl = problem.torque_limit[i]
                tau = min(max(-g[2] / block[2][2], -tl), tl) if tl > 0 else 0.0
                new = [0.0, 0.0, tau]
            else:
                new = wheel_block(g, block, limit, problem.torque_limit[i])
            delta = [p - q for p, q in zip(new, old, strict=True)]
            for k in range(3):
                if delta[k]:
                    column = 3 * i + k
                    for row in range(len(w)):
                        w[row] += a[row][column] * delta[k]
            x[s] = new
            body_long = unregularized[3 * i][3 * i] - (spin_term if problem.in_contact[i] else 0.0)
            change = max(
                change,
                abs(delta[0]) * body_long,
                abs(delta[1]) * unregularized[3 * i + 1][3 * i + 1],
            )
        used = step + 1
        if stop_natural > 0:
            if used % 5 == 0 and natural_residual(problem, unregularized, b, x) <= stop_natural:
                break
        elif change < tolerance:
            break
    residual = natural_residual(problem, unregularized, b, x)
    return {
        "x": x,
        "iterations": used,
        "last_change": change,
        "stopped": residual <= stop_natural if stop_natural > 0 else change < tolerance,
        "natural": residual,
    }


def fista(problem: Problem, iterations: int = 100000, tolerance: float = 1e-8) -> dict[str, Any]:
    """Method C."""
    a, b = problem.dual()
    v = [1.0] * len(b)
    value = 0.0
    for _ in range(300):
        u = matvec(a, v)
        value = math.sqrt(dot(u, u))
        v = [q / value for q in u] if value else v
    step = 1.0 / value
    x = [0.0] * len(b)
    y, t = list(x), 1.0

    def objective(z: Vec) -> float:
        return 0.5 * dot(z, matvec(a, z)) + dot(b, z)

    best = objective(x)
    used = 0
    residual = natural_residual(problem, a, b, x)
    for k in range(iterations):
        gradient = [p + q for p, q in zip(matvec(a, y), b, strict=True)]
        nxt = project([yi - step * gi for yi, gi in zip(y, gradient, strict=True)], problem)
        current = objective(nxt)
        used = k + 1
        if current > best:
            y, t = list(x), 1.0
            continue
        best = current
        t_next = 0.5 * (1 + math.sqrt(1 + 4 * t * t))
        y = [p + ((t - 1) / t_next) * (p - q) for p, q in zip(nxt, x, strict=True)]
        x, t = nxt, t_next
        if used % 10 == 0:
            residual = natural_residual(problem, a, b, x)
            if residual <= tolerance:
                break
    residual = natural_residual(problem, a, b, x)
    return {"x": x, "iterations": used, "stopped": residual <= tolerance, "natural": residual}


def primal_newton(
    problem: Problem,
    eps_final: float = 1e-9,
    eps_start: float = 10.0,
    shrink: float = 0.1,
    max_newton: int = 60,
) -> dict[str, Any]:
    """Method D. eps is a slip speed in cm/s; motor rows use eps / R in rad/s.

    Each eps stage runs damped Newton until its predicted decrease is below 1e-8 of the smoothing's
    own size, sum(weight eps). The line search compares objective changes computed without
    cancellation, because the objective itself is many orders larger than the changes near the end.
    The result is the stage whose forces have the smallest natural residual.
    """
    dt, r = problem.dt, problem.radius
    terms = []  # (rows, offsets, weight, eps scale, wheel, kind)
    for i in range(problem.wheels):
        if problem.in_contact[i] and problem.friction_limit[i] > 0:
            rows = [problem.rows[3 * i], problem.rows[3 * i + 1]]
            terms.append(
                (
                    rows,
                    problem.offsets[3 * i : 3 * i + 2],
                    dt * problem.friction_limit[i],
                    1.0,
                    i,
                    "contact",
                )
            )
        if problem.torque_limit[i] > 0:
            rows = [problem.rows[3 * i + 2]]
            terms.append(
                (
                    rows,
                    [problem.offsets[3 * i + 2]],
                    dt * problem.torque_limit[i],
                    1.0 / r,
                    i,
                    "motor",
                )
            )
    q_star = problem.q_star
    mass = _mass_matrix(problem)

    def residuals(q: Vec) -> list[Vec]:
        return [
            [dot(row, q) - c for row, c in zip(rows, offs, strict=True)] for rows, offs, *_ in terms
        ]

    def change(q: Vec, step: Vec, alpha: float, eps: float) -> float:
        """phi(q + alpha step) - phi(q), without subtracting two large numbers."""
        d = [a - b for a, b in zip(q, q_star, strict=True)]
        md = problem.mass_apply(step)
        total = alpha * dot(d, md) + 0.5 * alpha * alpha * dot(step, md)
        new_q = [a + alpha * b for a, b in zip(q, step, strict=True)]
        for (_, _, weight, scale, *_), z0, z1 in zip(
            terms, residuals(q), residuals(new_q), strict=True
        ):
            e = eps * scale
            s0, s1 = math.sqrt(dot(z0, z0) + e * e), math.sqrt(dot(z1, z1) + e * e)
            total += weight * (dot(z1, z1) - dot(z0, z0)) / (s0 + s1)
        return total

    def forces(q: Vec, eps: float) -> Vec:
        x = [0.0] * (3 * problem.wheels)
        for (_, _, weight, scale, i, kind), z in zip(terms, residuals(q), strict=True):
            e = eps * scale
            s = math.sqrt(dot(z, z) + e * e)
            if kind == "contact":
                x[3 * i], x[3 * i + 1] = -weight * z[0] / s / dt, -weight * z[1] / s / dt
            else:
                x[3 * i + 2] = -weight * z[0] / s / dt
        return x

    a, b = problem.dual()
    q = list(q_star)
    eps = max(eps_start, eps_final)
    newton_steps = 0
    best: dict[str, Any] | None = None
    while True:
        size = sum(weight * eps * scale for _, _, weight, scale, _, _ in terms)
        for _ in range(max_newton):
            d = [p - c for p, c in zip(q, q_star, strict=True)]
            grad = problem.mass_apply(d)
            hess = [list(row) for row in mass]
            for (rows, _, weight, scale, *_), z in zip(terms, residuals(q), strict=True):
                e = eps * scale
                s = math.sqrt(dot(z, z) + e * e)
                for ai, ra in enumerate(rows):
                    coef = weight * z[ai] / s
                    for k in range(12):
                        grad[k] += coef * ra[k]
                for ai, ra in enumerate(rows):
                    for bi, rb in enumerate(rows):
                        h = weight * ((1.0 / s if ai == bi else 0.0) - z[ai] * z[bi] / s**3)
                        nz_a = [k for k in range(12) if ra[k]]
                        nz_b = [m for m in range(12) if rb[m]]
                        for k in nz_a:
                            for m in nz_b:
                                hess[k][m] += h * ra[k] * rb[m]
            step = cholesky_solve(hess, [-g for g in grad])
            predicted = -dot(grad, step)
            newton_steps += 1
            if predicted <= 1e-8 * size:
                break
            alpha = 1.0
            while alpha > 1e-12 and change(q, step, alpha, eps) > -0.25 * alpha * predicted:
                alpha *= 0.5
            if alpha <= 1e-12:
                break
            q = [p + alpha * c for p, c in zip(q, step, strict=True)]
        x = forces(q, eps)
        residual = natural_residual(problem, a, b, x)
        if best is None or residual < best["natural"]:
            best = {"x": x, "q": list(q), "eps": eps, "natural": residual}
        if eps <= eps_final:
            break
        eps = max(eps * shrink, eps_final)
    assert best is not None
    return {**best, "iterations": newton_steps, "stopped": True}


def _terms(problem: Problem) -> list[dict[str, Any]]:
    """One nonsmooth term per contact (2 rows) and per motor or brake (1 row), with weight rho."""
    dt = problem.dt
    terms = []
    for i in range(problem.wheels):
        if problem.in_contact[i] and problem.friction_limit[i] > 0:
            terms.append(
                {
                    "rows": [problem.rows[3 * i], problem.rows[3 * i + 1]],
                    "offs": problem.offsets[3 * i : 3 * i + 2],
                    "w": dt * problem.friction_limit[i],
                    "scale": 1.0,
                    "i": i,
                    "kind": "contact",
                }
            )
        if problem.torque_limit[i] > 0:
            terms.append(
                {
                    "rows": [problem.rows[3 * i + 2]],
                    "offs": [problem.offsets[3 * i + 2]],
                    "w": dt * problem.torque_limit[i],
                    "scale": 1.0 / problem.radius,
                    "i": i,
                    "kind": "motor",
                }
            )
    return terms


def _z(t: dict[str, Any], q: Vec) -> Vec:
    return [dot(row, q) - c for row, c in zip(t["rows"], t["offs"], strict=True)]


def _solve_partition(
    problem: Problem, terms: list[dict[str, Any]], fixed: list[bool], q0: Vec, priors: list[Vec]
) -> dict[str, Any]:
    """Newton on the optimality conditions for one guess of which terms stick or hold.

    Returns q, each term's multiplier n, whether Newton converged, and the forces x.
    """
    mass = _mass_matrix(problem)
    q = list(q0)
    held = [k for k, f in enumerate(fixed) if f]
    sizes = [len(terms[k]["rows"]) for k in held]
    m = sum(sizes)
    lam = [v for k in held for v in priors[k]]
    converged = False
    steps = 0
    for _ in range(50):
        steps += 1
        d = [a - b for a, b in zip(q, problem.q_star, strict=True)]
        r1 = problem.mass_apply(d)
        h = [list(row) for row in mass]
        for k, t in enumerate(terms):
            if fixed[k]:
                continue
            z = _z(t, q)
            nz = math.sqrt(dot(z, z))
            if nz <= 1e-10 * t["scale"]:
                # A slip this small is a stick: its Hessian, about 1/|z|, would swamp the rest.
                continue
            for a_i, ra in enumerate(t["rows"]):
                coef = t["w"] * z[a_i] / nz
                for c in range(12):
                    r1[c] += coef * ra[c]
            for a_i, ra in enumerate(t["rows"]):
                for b_i, rb in enumerate(t["rows"]):
                    hv = t["w"] * ((1.0 / nz if a_i == b_i else 0.0) - z[a_i] * z[b_i] / nz**3)
                    for c in range(12):
                        if ra[c]:
                            for e in range(12):
                                if rb[e]:
                                    h[c][e] += hv * ra[c] * rb[e]
        rows_s, r2 = [], []
        pos = 0
        for k, size in zip(held, sizes, strict=True):
            t = terms[k]
            for a_i in range(size):
                row = [t["w"] * v for v in t["rows"][a_i]]
                rows_s.append(row)
                for c in range(12):
                    r1[c] += row[c] * lam[pos + a_i]
            r2 += [t["w"] * v for v in _z(t, q)]
            pos += size
        # Newton on [[h, S'], [S, 0]] [dq; dl] = -[r1; r2] via the Schur complement.
        solve_h = _robust_solver(h)
        hinv_r1 = solve_h(r1)
        if m:
            hinv_st = [solve_h([rows_s[j][c] for c in range(12)]) for j in range(m)]
            schur = [[dot(rows_s[i2], hinv_st[j]) for j in range(m)] for i2 in range(m)]
            rhs = [r2[i2] - dot(rows_s[i2], hinv_r1) for i2 in range(m)]
            dl = pseudo_solve(schur, rhs)
            dq = [-(hinv_r1[c] + sum(hinv_st[j][c] * dl[j] for j in range(m))) for c in range(12)]
            lam = [a + b for a, b in zip(lam, dl, strict=True)]
        else:
            dq = [-v for v in hinv_r1]
        q = [a + b for a, b in zip(q, dq, strict=True)]
        if math.sqrt(dot(dq, dq)) < 1e-13 * (1.0 + math.sqrt(dot(q, q))):
            converged = True
            break
    multipliers: dict[int, Vec] = {}
    pos = 0
    for k, size in zip(held, sizes, strict=True):
        multipliers[k] = lam[pos : pos + size]
        pos += size
    x = [0.0] * (3 * problem.wheels)
    for k, t in enumerate(terms):
        if fixed[k]:
            n = multipliers[k]
        else:
            z = _z(t, q)
            nz = math.sqrt(dot(z, z))
            n = [v / nz for v in z] if nz else [0.0] * len(z)
        i = t["i"]
        if t["kind"] == "contact":
            x[3 * i], x[3 * i + 1] = -t["w"] * n[0] / problem.dt, -t["w"] * n[1] / problem.dt
        else:
            x[3 * i + 2] = -t["w"] * n[0] / problem.dt
    return {"q": q, "multipliers": multipliers, "converged": converged, "x": x, "steps": steps}


def primal_active_set(
    problem: Problem, predictor_eps: float = 1e-5, max_rounds: int = 20, target: float = 1e-8
) -> dict[str, Any]:
    """Method D: a smoothed Newton predictor guesses which terms stick or hold; then exact KKT.

    Unknowns are q (12) and a multiplier n for each sticking contact (2) and holding motor (1).
    With rho = dt mu Fz or dt L, the optimality conditions of the primal are

        M (q - q*) + sum rho G' n = 0,   n = z / |z| where sliding or saturated,
        G q = c where sticking or holding,  |n| <= 1 there.

    Newton solves them for a fixed guess. Sticking rows can be dependent, twelve rows on six body
    freedoms, so the multiplier step is a pseudo-inverse: the smallest change from the smoothed
    multipliers it starts from, which leaves q unchanged. A guess is corrected where |n| > 1, or
    where a sliding slip has fallen to zero. A term within 30 eps of the switch looks the same
    either way, so if the result still misses the target natural residual, each such ambiguous
    term is flipped in turn, and the best result is kept. If that still misses, the result goes to
    alternating PGS as a start, at most 5,000 passes, and the result says so. A contact sliding at
    a slip near zero is the usual cause: there Newton's 1/|z| term is too stiff to converge. The
    answer is judged only by its natural residual, never by the guess.
    """
    predictor = primal_newton(problem, eps_final=predictor_eps, eps_start=10.0)
    eps = predictor["eps"]
    terms = _terms(problem)
    a, b = problem.dual()
    zs = [_z(t, predictor["q"]) for t in terms]
    ratio = [math.sqrt(dot(z, z)) / (eps * t["scale"]) for z, t in zip(zs, terms, strict=True)]
    priors = [
        [v / math.sqrt(dot(z, z) + (eps * t["scale"]) ** 2) for v in z]
        for z, t in zip(zs, terms, strict=True)
    ]

    def settle(fixed: list[bool]) -> tuple[dict[str, Any], int]:
        result: dict[str, Any] = {}
        for rounds in range(1, max_rounds + 1):
            result = _solve_partition(problem, terms, fixed, predictor["q"], priors)
            changed = False
            for k, t in enumerate(terms):
                if fixed[k]:
                    n = result["multipliers"][k]
                    if math.sqrt(dot(n, n)) > 1 + 1e-9:
                        fixed[k] = False
                        changed = True
                else:
                    z = _z(t, result["q"])
                    if math.sqrt(dot(z, z)) <= 1e-10 * t["scale"]:
                        fixed[k] = True
                        changed = True
            if not changed:
                return result, rounds
        return result, max_rounds

    newton = predictor["iterations"]
    best, rounds = settle([r <= 30 for r in ratio])
    best["natural"] = natural_residual(problem, a, b, best["x"])
    newton += best["steps"]
    attempts = 1
    if best["natural"] > target:
        ambiguous = [k for k, r in enumerate(ratio) if 1 <= r <= 1e4]
        for k in ambiguous:
            fixed = [r <= 30 for r in ratio]
            fixed[k] = not fixed[k]
            trial, _ = settle(fixed)
            trial["natural"] = natural_residual(problem, a, b, trial["x"])
            newton += trial["steps"]
            attempts += 1
            if trial["natural"] < best["natural"]:
                best = trial
            if best["natural"] <= target:
                break
    fallback = None
    if best["natural"] > target:
        fallback = block_gauss_seidel(
            problem, order="alternate", start=best["x"], passes=5000, stop_natural=target
        )
        if fallback["natural"] < best["natural"]:
            best = {
                "x": fallback["x"],
                "q": problem.velocity_after(fallback["x"]),
                "natural": fallback["natural"],
            }
    return {
        "x": best["x"],
        "q": best["q"],
        "iterations": newton,
        "predictor_iterations": predictor["iterations"],
        "rounds": rounds,
        "attempts": attempts,
        "fallback_passes": fallback["iterations"] if fallback else 0,
        "natural": best["natural"],
        "stopped": best["natural"] <= target,
    }


def _robust_solver(h: Mat) -> Callable[[Vec], Vec]:
    """Cholesky of h; if rounding breaks it, a diagonal shift from 1e-14 of the trace, tenfold."""
    shift = 0.0
    scale = sum(h[i][i] for i in range(len(h))) / len(h)
    while True:
        shifted = [
            [v + (shift if i == j else 0.0) for j, v in enumerate(row)] for i, row in enumerate(h)
        ]
        try:
            cholesky_solve(shifted, [0.0] * len(h))
        except ValueError:
            shift = 1e-14 * scale if shift == 0.0 else shift * 10
            continue
        return lambda b: cholesky_solve(shifted, b)


def symmetric_eigen(a: Mat, sweeps: int = 60) -> tuple[Vec, Mat]:
    """Cyclic Jacobi: eigenvalues and eigenvectors, as columns, of a small symmetric matrix."""
    n = len(a)
    m = [list(row) for row in a]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(sweeps):
        off = sum(m[i][j] ** 2 for i in range(n) for j in range(n) if i != j)
        if off <= 1e-30 * sum(m[i][i] ** 2 for i in range(n)):
            break
        for p in range(n):
            for q in range(p + 1, n):
                if abs(m[p][q]) < 1e-300:
                    continue
                theta = (m[q][q] - m[p][p]) / (2 * m[p][q])
                t = math.copysign(1.0, theta) / (abs(theta) + math.sqrt(theta * theta + 1))
                c = 1 / math.sqrt(t * t + 1)
                s = t * c
                for k in range(n):
                    mkp, mkq = m[k][p], m[k][q]
                    m[k][p], m[k][q] = c * mkp - s * mkq, s * mkp + c * mkq
                for k in range(n):
                    mpk, mqk = m[p][k], m[q][k]
                    m[p][k], m[q][k] = c * mpk - s * mqk, s * mpk + c * mqk
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p], v[k][q] = c * vkp - s * vkq, s * vkp + c * vkq
    return [m[i][i] for i in range(n)], v


def pseudo_solve(a: Mat, b: Vec, cutoff: float = 1e-10) -> Vec:
    """Minimum-norm least-squares solution of a x = b, for symmetric positive semidefinite a."""
    values, vectors = symmetric_eigen(a)
    top = max(abs(x) for x in values)
    n = len(a)
    x = [0.0] * n
    for k, lam in enumerate(values):
        if lam > cutoff * top:
            coef = sum(vectors[i][k] * b[i] for i in range(n)) / lam
            for i in range(n):
                x[i] += coef * vectors[i][k]
    return x


def _mass_matrix(problem: Problem) -> Mat:
    m = [[0.0] * 12 for _ in range(12)]
    for k in range(3):
        m[k][k] = problem.mass
    for k in range(3):
        for j in range(3):
            m[3 + k][3 + j] = problem.inertia[k][j]
    for k in range(6):
        m[6 + k][6 + k] = problem.wheel_inertia
    return m
