"""Compare contact solvers on dumped steps, the same input for every method.

    python -m contact_solver.compare --states <dir> --out <file.json>   (run from scripts/)

<dir> holds solver_steps.jsonl files written by runs with -WheelDumpEvery. Each file is one window
of consecutive steps, solved in order so that warm starts carry over. Python, single-threaded per
window; times are this prototype's and are not C++ times.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import tracemalloc
from collections.abc import Callable
from multiprocessing import Pool
from pathlib import Path
from typing import Any

from .methods import block_gauss_seidel, fista, primal_active_set
from .problem import Problem, Vec, build, evaluate

Method = Callable[[Problem, "Vec | None"], dict[str, Any]]

METHODS: dict[str, tuple[str, Method, bool]] = {
    # name: (description, solve(problem, warm start), uses a warm start)
    "A": (
        "PGS forward, 200 passes, stop on change < 1e-7 cm/s",
        lambda p, s: block_gauss_seidel(p),
        False,
    ),
    "B": (
        "PGS alternating, warm start, 200 passes, stop on change < 1e-7 cm/s",
        lambda p, s: block_gauss_seidel(p, order="alternate", start=s),
        True,
    ),
    "B_res": (
        "PGS alternating, warm start, stop on natural residual <= 1e-8, at most 2,000 passes",
        lambda p, s: block_gauss_seidel(
            p, order="alternate", start=s, passes=2000, stop_natural=1e-8
        ),
        True,
    ),
    "C": (
        "FISTA on the dual, stop on natural residual <= 1e-8, at most 20,000 iterations",
        lambda p, s: fista(p, iterations=20000, tolerance=1e-8),
        False,
    ),
    "D": ("Generalized-velocity active-set Newton", lambda p, s: primal_active_set(p), False),
    "E_1e-6": (
        "B with gamma 1e-6 diag(A)",
        lambda p, s: block_gauss_seidel(p, order="alternate", start=s, gamma=1e-6),
        True,
    ),
    "E_1e-4": (
        "B with gamma 1e-4 diag(A)",
        lambda p, s: block_gauss_seidel(p, order="alternate", start=s, gamma=1e-4),
        True,
    ),
    "E_1e-2": (
        "B with gamma 1e-2 diag(A)",
        lambda p, s: block_gauss_seidel(p, order="alternate", start=s, gamma=1e-2),
        True,
    ),
}


def engine_x(data: dict[str, Any]) -> Vec:
    x = []
    for w in data["wheels"]:
        r = w["result"]
        x += [
            r["f_long"] if w["hit"] else 0.0,
            r["f_lat"] if w["hit"] else 0.0,
            r["brake"] if w["mode"] == 1 else (r["motor"] if w["mode"] == 0 else 0.0),
        ]
    return x


def warm_start(problem: Problem, last: dict[str, Any] | None) -> Vec | None:
    """The last solution's force on this step's contact plane; zero where contact is new or lost."""
    if last is None:
        return None
    start = [0.0] * (3 * problem.wheels)
    for i in range(problem.wheels):
        if problem.in_contact[i] and last["contact"][i]:
            world = last["world"][i]
            start[3 * i] = sum(a * b for a, b in zip(world, problem.forward[i], strict=True))
            start[3 * i + 1] = sum(a * b for a, b in zip(world, problem.lateral[i], strict=True))
        start[3 * i + 2] = last["x"][3 * i + 2]
    return start


def remember(problem: Problem, x: Vec) -> dict[str, Any]:
    world = [
        [
            x[3 * i] * f + x[3 * i + 1] * side
            for f, side in zip(problem.forward[i], problem.lateral[i], strict=True)
        ]
        for i in range(problem.wheels)
    ]
    return {"x": x, "world": world, "contact": list(problem.in_contact)}


def distance(a: Vec, b: Vec) -> float:
    return math.sqrt(sum((p - q) ** 2 for p, q in zip(a, b, strict=True)))


def reference_solution(problem: Problem) -> dict[str, Any]:
    """The more nearly optimal of D and a long alternating PGS: neither reaches 1e-10 everywhere."""
    d = primal_active_set(problem, target=1e-10)
    if d["natural"] <= 1e-10:
        return {**d, "source": "D"}
    long = block_gauss_seidel(
        problem, order="alternate", start=d["x"], passes=5000, stop_natural=1e-10
    )
    return {**long, "source": "PGS"} if long["natural"] < d["natural"] else {**d, "source": "D"}


def compare_window(path: str) -> list[dict[str, Any]]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    window = Path(path).parent.parent.name
    last: dict[str, Any] = {}
    records = []
    for index, line in enumerate(lines):
        data = json.loads(line)
        problem = build(data)
        reference = reference_solution(problem)
        ref = evaluate(problem, reference["x"])
        record: dict[str, Any] = {
            "window": window,
            "index": index,
            "time": data["time"],
            "dt": data["dt"],
            "reference_natural": reference["natural"],
            "reference_source": reference["source"],
            "methods": {},
        }
        engine = engine_x(data)
        solved = {"engine": {"x": engine, "iterations": data["stats"]["passes"], "natural": None}}
        timings: dict[str, float] = {}
        memory: dict[str, int] = {}
        for name, (_, solve, warm) in METHODS.items():
            start = warm_start(problem, last.get(name)) if warm else None
            begin = time.perf_counter()
            result = solve(problem, start)
            timings[name] = time.perf_counter() - begin
            if index % 20 == 0:
                tracemalloc.start()
                solve(problem, start)
                memory[name] = tracemalloc.get_traced_memory()[1]
                tracemalloc.stop()
            solved[name] = result
            last[name] = remember(problem, result["x"])
        for name, result in solved.items():
            got = evaluate(problem, result["x"])
            limits = [max(problem.friction_limit[i], 1e-300) for i in range(problem.wheels)]
            record["methods"][name] = {
                "natural": max(got["natural_force"], got["natural_torque"]),
                "stick_slip_cmps": got["stick_slip_cmps"],
                "slide_angle_deg": got["slide_angle_deg"],
                "circle_excess": got["circle_excess"],
                "torque_excess": got["torque_excess"],
                "dv_cmps": distance(got["velocity"], ref["velocity"]),
                "dw_degps": math.degrees(
                    distance(got["angular_velocity"], ref["angular_velocity"])
                ),
                "dspin_radps": distance(got["spins"], ref["spins"]),
                "dnet_force": distance(got["net_force"], ref["net_force"]),
                "dnet_torque": distance(got["net_torque"], ref["net_torque"]),
                "dwheel_force_over_limit": max(
                    math.hypot(
                        result["x"][3 * i] - reference["x"][3 * i],
                        result["x"][3 * i + 1] - reference["x"][3 * i + 1],
                    )
                    / limits[i]
                    for i in range(problem.wheels)
                    if problem.in_contact[i]
                )
                if any(problem.in_contact)
                else 0.0,
                "friction_power_over_limit_cmps": got["friction_power"]
                / max(sum(problem.friction_limit), 1e-300),
                "energy_identity_error": got["energy_identity_error"],
                "numerical_dissipation": got["numerical_dissipation"],
                "iterations": result.get("iterations"),
                "fallback_passes": result.get("fallback_passes"),
                "seconds": timings.get(name),
                "peak_bytes": memory.get(name),
            }
        records.append(record)
    return records


def quantiles(values: list[float]) -> dict[str, float] | None:
    values = sorted(v for v in values if v is not None)
    if not values:
        return None

    def at(p: float) -> float:
        return values[min(len(values) - 1, int(p * (len(values) - 1) + 0.5))]

    return {
        "median": statistics.median(values),
        "p95": at(0.95),
        "p99": at(0.99),
        "max": values[-1],
        "n": len(values),
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    names = list(records[0]["methods"])
    keys = list(records[0]["methods"][names[0]])
    groups: dict[str, list[dict[str, Any]]] = {"all": records}
    for r in records:
        groups.setdefault(r["window"], []).append(r)
    out: dict[str, Any] = {}
    for group, rows in groups.items():
        out[group] = {
            name: {key: quantiles([r["methods"][name][key] for r in rows]) for key in keys}
            for name in names
        }
        out[group]["reference_natural"] = quantiles([r["reference_natural"] for r in rows])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--states", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--windows", nargs="*", help="Window names to include; all if none")
    args = parser.parse_args()
    files = sorted(str(p) for p in args.states.rglob("*_solver_steps.jsonl"))
    if args.windows:
        files = [f for f in files if Path(f).parent.parent.name in args.windows]
    with Pool(args.workers) as pool:
        records = [r for window in pool.map(compare_window, files) for r in window]
    summary = {"methods": {k: v[0] for k, v in METHODS.items()}, "summary": summarize(records)}
    args.out.write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    args.out.with_suffix(".steps.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
    )
    print(json.dumps({k: len(v) for k, v in summarize(records).items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
