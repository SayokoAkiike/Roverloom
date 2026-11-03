"""Export saved solver states, and Python method D's answers, as plain numbers for the C++ port.

    python -m contact_solver.export_states --states <dir> --out <dir>   (run from scripts/)

Writes states.txt, one state per line, and python_d.txt, one answer per line, in the same order.
The C++ benchmark reads both. Layout of a state line:

    window index dt radius wheel_inertia spring damper friction motor brake inv_mass
    inv_inertia(9) com(3) v(3) w(3) acc(3) ext(3)
    then per wheel, 6 times: hit comp comp_rate point(3) normal(3) forward(3) lateral(3)
    mode target spin engine_f_long engine_f_lat engine_motor engine_brake

An answer line: window index natural fallback_passes seconds x(18) q(12).
"""

from __future__ import annotations

import argparse
import json
import time
from multiprocessing import Pool
from pathlib import Path
from typing import Any

from .methods import primal_active_set
from .problem import build


def state_line(window: str, index: int, data: dict[str, Any]) -> str:
    p, b = data["params"], data["body"]
    values: list[float] = [
        data["dt"],
        p["radius"],
        p["inertia"],
        p["spring"],
        p["damper"],
        p["friction"],
        p["motor"],
        p["brake"],
        b["inv_mass"],
    ]
    values += [v for row in b["inv_inertia"] for v in row]
    for key in ("com", "v", "w", "acc", "ext"):
        values += b[key]
    for w in data["wheels"]:
        r = w["result"]
        values += [
            1.0 if w["hit"] else 0.0,
            w["comp"],
            w["comp_rate"],
            *w["point"],
            *w["normal"],
            *w["forward"],
            *w["lateral"],
            float(w["mode"]),
            w["target"],
            w["spin"],
            r["f_long"],
            r["f_lat"],
            r["motor"],
            r["brake"],
        ]
    return f"{window} {index} " + " ".join(repr(float(v)) for v in values)


def answer(job: tuple[str, int, str]) -> str:
    window, index, line = job
    problem = build(json.loads(line))
    begin = time.perf_counter()
    result = primal_active_set(problem)
    seconds = time.perf_counter() - begin
    numbers = [
        result["natural"],
        float(result["fallback_passes"]),
        seconds,
        *result["x"],
        *result["q"],
    ]
    return f"{window} {index} " + " ".join(repr(float(v)) for v in numbers)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--states", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    jobs = []
    lines = []
    for path in sorted(args.states.rglob("*_solver_steps.jsonl")):
        window = path.parent.parent.name
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            jobs.append((window, index, line))
            lines.append(state_line(window, index, json.loads(line)))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "states.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with Pool(args.workers) as pool:
        answers = pool.map(answer, jobs)
    (args.out / "python_d.txt").write_text("\n".join(answers) + "\n", encoding="utf-8")
    print(f"{len(lines)} states written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
