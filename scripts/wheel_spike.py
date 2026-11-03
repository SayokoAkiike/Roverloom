"""Run and judge the Unreal wheel model experiment (Step 5a, phases A and B).

Separate from the R0 physics spike, whose records and verdicts stay unchanged. It imports nothing
from `roverloom`. Records go to `unreal/Saved/WheelSpike/`. See
docs/results/unreal-wheel-model/README.md.

    python scripts/wheel_spike.py run --batch wheel-YYYYMMDD
    python scripts/wheel_spike.py analyze --batch wheel-YYYYMMDD

The thresholds below were fixed before the first gated run. Do not change them after seeing results.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from typing import Any

import physics_spike as spike

RECORDS = spike.ROOT / "unreal" / "Saved" / "WheelSpike"
MAP_URL = "/Engine/Maps/Entry?game=/Script/Roverloom.WheelSpikeGameMode"

# Thresholds, fixed before the first gated run.
GRAVITY = 371.0
MASS_A = 853.5 / 6
LOAD_TOLERANCE = 0.01
COMPRESSION_RANGE_CM = 0.1
SPEED_CMPS = 50.0
SPEED_TOLERANCE = 0.02
SLIP_CMPS = 1.0
TRACTION_TOLERANCE = 0.02
ACCEL_TOLERANCE = 0.05
LOCKED_SPIN_RADPS = 0.01
LATERAL_STOPPED_CMPS = 0.1
HOLD_CMPS = 0.1
SLOPE_SLIDE_CMPS2 = GRAVITY * (math.sin(math.radians(10)) - 0.1 * math.cos(math.radians(10)))
TIMESTEP_A = 0.05
YAW_DRIFT_DEGPS = 0.5
TURN_DEGPS = 28.178
TURN_TOLERANCE = 0.05
STOP_WITHIN_S = 2.0
STOPPED_CMPS = 0.5
TIMESTEP_B = 0.02
MAX_SPEED_CMPS = 1000.0
CIRCLE_TOLERANCE = 1e-6

SCENARIOS = ["a1", "a1s", "a2", "a2s", "a3", "a4", "a5", "a6", "a7", "b1", "b2", "b3", "b4"]


def plan() -> list[dict[str, Any]]:
    runs = [{"name": s, "scenario": s, "flags": spike.FIXED_60} for s in SCENARIOS]
    runs += [
        {"name": f"{s}_fps120", "scenario": s, "flags": spike.FIXED_120}
        for s in ("a2", "a4", "b1", "b2")
    ]
    for run in runs:
        run["map"] = MAP_URL
        run["scenario_arg"] = "WheelScenario"
    return runs


def wheels(rows: list[dict[str, float]]) -> int:
    return sum(1 for key in rows[0] if key.endswith("_hit"))


def common(rows: list[dict[str, float]], meta: dict[str, Any]) -> dict[str, Any]:
    """Every run: completed, bounded speed, and traction inside the friction circle."""
    worst = 0.0
    for row in rows:
        for i in range(wheels(rows)):
            excess = math.hypot(row[f"w{i}_flong"], row[f"w{i}_flat"]) - row[f"w{i}_limit"]
            worst = max(worst, excess / max(row[f"w{i}_limit"], 1.0))
    speed = max(math.sqrt(r["vx_cmps"] ** 2 + r["vy_cmps"] ** 2 + r["vz_cmps"] ** 2) for r in rows)
    ok = meta["outcome"] == "completed" and speed < MAX_SPEED_CMPS and worst <= CIRCLE_TOLERANCE
    return {
        "outcome": meta["outcome"],
        "max_speed_cmps": speed,
        "circle_excess": worst,
        "common_pass": ok,
    }


def mean(rows: list[dict[str, float]], key: str) -> float:
    return statistics.fmean(r[key] for r in rows)


def a_static(rows: list[dict[str, float]]) -> dict[str, Any]:
    late = spike.window(rows, 4.0, 6.0)
    load = mean(late, "w0_fz")
    comp = [r["w0_comp_cm"] for r in late]
    error = load / (MASS_A * GRAVITY) - 1
    rng = max(comp) - min(comp)
    return {
        "load_error": error,
        "compression_range_cm": rng,
        "pass": abs(error) <= LOAD_TOLERANCE and rng < COMPRESSION_RANGE_CM,
    }


def time_to_95(rows: list[dict[str, float]], start: float) -> float | None:
    hit = next(
        (r for r in rows if r["t_s"] >= start and r["forward_cmps"] >= 0.95 * SPEED_CMPS), None
    )
    return hit["t_s"] - start if hit else None


def a_drive(rows: list[dict[str, float]]) -> dict[str, Any]:
    steady = spike.window(rows, 8.0, 12.0)
    speed = mean(steady, "forward_cmps")
    slip = statistics.fmean(abs(r["w0_slip_cmps"]) for r in steady)
    ok = abs(speed - SPEED_CMPS) <= SPEED_TOLERANCE * SPEED_CMPS and slip < SLIP_CMPS
    return {
        "steady_cmps": speed,
        "mean_abs_slip_cmps": slip,
        "time_to_95_s": time_to_95(rows, 2.0),
        "pass": ok,
    }


def a_spin(rows: list[dict[str, float]]) -> dict[str, Any]:
    slipping = [
        r for r in rows if r["t_s"] >= 2.0 and r["w0_spin_radps"] * 25.0 - r["forward_cmps"] > 1.0
    ]
    if len(slipping) < 3:
        return {"slipping_rows": len(slipping), "pass": False}
    ratio = [abs(r["w0_flong"]) / r["w0_limit"] for r in slipping]
    accel = spike.slope_fit([r["t_s"] for r in slipping], [r["forward_cmps"] for r in slipping])
    expected = 0.05 * GRAVITY
    ok = (
        all(abs(x - 1) <= TRACTION_TOLERANCE for x in ratio)
        and abs(accel / expected - 1) <= ACCEL_TOLERANCE
    )
    return {
        "slipping_rows": len(slipping),
        "traction_ratio": [min(ratio), max(ratio)],
        "accel_cmps2": accel,
        "expected_cmps2": expected,
        "pass": ok,
    }


def stop_point(rows: list[dict[str, float]], start: float) -> dict[str, float] | None:
    return next(
        (r for r in rows if r["t_s"] > start and abs(r["forward_cmps"]) < STOPPED_CMPS), None
    )


def a_brake(rows: list[dict[str, float]]) -> dict[str, Any]:
    sliding = [r for r in rows if r["t_s"] >= 7.1 and r["forward_cmps"] > 1.0]
    if len(sliding) < 3:
        return {"sliding_rows": len(sliding), "pass": False}
    spin = max(abs(r["w0_spin_radps"]) for r in sliding)
    decel = -spike.slope_fit([r["t_s"] for r in sliding], [r["forward_cmps"] for r in sliding])
    expected = 0.1 * GRAVITY
    stop = stop_point(rows, 7.0)
    start = spike.at_time(rows, 7.0)
    ok = spin < LOCKED_SPIN_RADPS and abs(decel / expected - 1) <= ACCEL_TOLERANCE
    return {
        "max_locked_spin_radps": spin,
        "decel_cmps2": decel,
        "expected_cmps2": expected,
        "stopping_distance_cm": stop["x_cm"] - start["x_cm"] if stop else None,
        "pass": ok,
    }


def a_lateral(rows: list[dict[str, float]]) -> dict[str, Any]:
    sliding = [r for r in rows if r["t_s"] > 2.55 and abs(r["lateral_cmps"]) > 1.0]
    if len(sliding) < 3:
        return {"sliding_rows": len(sliding), "pass": False}
    decel = -spike.slope_fit([r["t_s"] for r in sliding], [r["lateral_cmps"] for r in sliding])
    expected = 0.3 * GRAVITY
    late = abs(spike.at_time(rows, 4.0)["lateral_cmps"])
    peak = max(abs(r["lateral_cmps"]) for r in rows)
    ok = abs(decel / expected - 1) <= ACCEL_TOLERANCE and late < LATERAL_STOPPED_CMPS
    return {
        "peak_lateral_cmps": peak,
        "decel_cmps2": decel,
        "expected_cmps2": expected,
        "lateral_at_4s": late,
        "pass": ok,
    }


def hold(rows: list[dict[str, float]]) -> dict[str, Any]:
    drift = abs(mean(spike.window(rows, 4.0, 6.0), "forward_cmps"))
    return {"mean_drift_cmps": drift, "pass": drift < HOLD_CMPS}


def a_slide(rows: list[dict[str, float]]) -> dict[str, Any]:
    part = spike.window(rows, 2.0, 6.0)
    accel = -spike.slope_fit([r["t_s"] for r in part], [r["forward_cmps"] for r in part])
    ok = abs(accel / SLOPE_SLIDE_CMPS2 - 1) <= ACCEL_TOLERANCE
    return {"downhill_accel_cmps2": accel, "expected_cmps2": SLOPE_SLIDE_CMPS2, "pass": ok}


def b_straight(rows: list[dict[str, float]]) -> dict[str, Any]:
    steady = spike.window(rows, 8.0, 12.0)
    speed = mean(steady, "forward_cmps")
    yaw = statistics.fmean(abs(r["wz_degps"]) for r in steady)
    end = spike.at_time(rows, 12.0)
    ok = abs(speed - SPEED_CMPS) <= SPEED_TOLERANCE * SPEED_CMPS and yaw < YAW_DRIFT_DEGPS
    return {
        "steady_cmps": speed,
        "mean_abs_yaw_rate_degps": yaw,
        "end_x_cm": end["x_cm"],
        "loads": [mean(steady, "w0_fz"), mean(steady, "w1_fz")],
        "drive_forces": [mean(steady, "w0_flong"), mean(steady, "w1_flong")],
        "pass": ok,
    }


def b_spin(rows: list[dict[str, float]]) -> dict[str, Any]:
    steady = spike.window(rows, 6.0, 10.0)
    yaw = spike.unwrapped_yaw(steady)
    rate = spike.slope_fit([r["t_s"] for r in steady], yaw)
    lateral = max(statistics.fmean(abs(r[f"w{i}_vlat_cmps"]) for r in steady) for i in range(2))
    total = spike.unwrapped_yaw(spike.window(rows, 0.0, 10.0))
    ok = rate > 0 and abs(rate / TURN_DEGPS - 1) <= TURN_TOLERANCE and lateral < SLIP_CMPS
    return {
        "yaw_rate_degps": rate,
        "max_mean_lateral_slip_cmps": lateral,
        "total_yaw_deg": total[-1] - total[0],
        "drive_forces": [mean(steady, "w0_flong"), mean(steady, "w1_flong")],
        "pass": ok,
    }


def b_stop(rows: list[dict[str, float]]) -> dict[str, Any]:
    stop = stop_point(rows, 7.0)
    within = stop["t_s"] - 7.0 if stop else None
    return {"stop_time_s": within, "pass": within is not None and within <= STOP_WITHIN_S}


ANALYZERS = {
    "a1": a_static,
    "a1s": a_static,
    "a2": a_drive,
    "a2s": a_drive,
    "a3": a_spin,
    "a4": a_brake,
    "a5": a_lateral,
    "a6": hold,
    "a7": a_slide,
    "b1": b_straight,
    "b2": b_spin,
    "b3": b_stop,
    "b4": hold,
}


def relative(a: float | None, b: float | None) -> float | None:
    return abs(b - a) / abs(a) if a and b is not None else None


def command_analyze(args: argparse.Namespace) -> int:
    out_dir = RECORDS / args.batch
    runs = {}
    for line in (out_dir / "runs.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        runs[record["name"]] = record
    tests: dict[str, Any] = {}
    for spec in plan():
        loaded = spike.load(out_dir, spec["name"])
        if loaded is None:
            tests[spec["name"]] = {"missing": True, "pass": False}
            continue
        rows, meta = loaded
        result = {**ANALYZERS[spec["scenario"]](rows), **common(rows, meta)}
        result["pass"] = bool(result["pass"] and result["common_pass"])
        tests[spec["name"]] = result

    def value(name: str, key: str) -> Any:
        return tests.get(name, {}).get(key)

    a8 = [
        relative(value("a2", "time_to_95_s"), value("a2_fps120", "time_to_95_s")),
        relative(value("a4", "stopping_distance_cm"), value("a4_fps120", "stopping_distance_cm")),
    ]
    b5 = [
        relative(value("b1", "end_x_cm"), value("b1_fps120", "end_x_cm")),
        relative(value("b2", "total_yaw_deg"), value("b2_fps120", "total_yaw_deg")),
    ]
    tests["a8"] = {
        "relative": a8,
        "pass": all(x is not None and x < TIMESTEP_A for x in a8)
        and tests["a2_fps120"]["pass"]
        and tests["a4_fps120"]["pass"],
    }
    tests["b5"] = {
        "relative": b5,
        "pass": all(x is not None and x < TIMESTEP_B for x in b5)
        and tests["b1_fps120"]["pass"]
        and tests["b2_fps120"]["pass"],
    }

    gate = [*SCENARIOS, "a8", "b5"]
    summary = {
        "batch": args.batch,
        "runs": runs,
        "tests": tests,
        "gate": {name: bool(tests[name]["pass"]) for name in gate},
    }
    summary["phase_a_pass"] = all(v for k, v in summary["gate"].items() if k.startswith("a"))
    summary["phase_b_pass"] = all(v for k, v in summary["gate"].items() if k.startswith("b"))
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("gate", "phase_a_pass", "phase_b_pass")}, indent=2))
    return 0


def command_run(args: argparse.Namespace) -> int:
    out_dir = RECORDS / args.batch
    out_dir.mkdir(parents=True, exist_ok=True)
    runs = plan()
    if args.only:
        runs = [spec for spec in runs if spec["name"] in args.only]
    for spec in runs:
        record = spike.run_one(spec, out_dir)
        print(json.dumps(record), flush=True)
        if record["new_crash_reports"] or record["sigterm_used"] or record["exit_code"] != 0:
            print("Stopping the batch: crash, forced stop, or a nonzero exit.", file=sys.stderr)
            return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run the phase A and B plan, or some of its runs")
    run.add_argument("--batch", required=True)
    run.add_argument("--only", nargs="*", help="Run names to include")
    analyze = sub.add_parser("analyze", help="Judge a batch against the fixed thresholds")
    analyze.add_argument("--batch", required=True)
    args = parser.parse_args()
    return command_run(args) if args.command == "run" else command_analyze(args)


if __name__ == "__main__":
    sys.exit(main())
