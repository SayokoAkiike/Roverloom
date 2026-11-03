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
WHEEL_INERTIA = 0.4 * 15.0 * 25.0**2  # kg cm^2, as in WheelModel.h; report only

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
    result: dict[str, Any] = {
        "outcome": meta["outcome"],
        "max_speed_cmps": speed,
        "circle_excess": worst,
        "common_pass": ok,
    }
    # Report only, from attempt 2: did the joint solve converge on every step. Not part of the pass.
    if "solve_passes" in rows[0]:
        result["max_solve_passes"] = max(r["solve_passes"] for r in rows)
        result["unconverged_steps"] = sum(1 for r in rows if r["solve_converged"] != 1)
    # Report only, from attempt 3: friction power F.u over mu Fz, a slip speed that must not be
    # positive, and the angle between each sliding force and the direction opposing its slip.
    if "w0_friction_power" in rows[0]:
        result["max_friction_power_over_limit_cmps"] = max(
            r[f"w{i}_friction_power"] / r[f"w{i}_limit"]
            for r in rows
            for i in range(wheels(rows))
            if r[f"w{i}_limit"] > 0
        )
        result["max_slide_angle_deg"] = max(
            [slide_angle(r, i) for r in rows for i in range(wheels(rows)) if r[f"w{i}_saturated"]],
            default=None,
        )
    return result


def slide_angle(row: dict[str, float], i: int) -> float:
    """Angle between a sliding force and minus its end-of-step slip, from rounded CSV values."""
    force = (row[f"w{i}_flong"], row[f"w{i}_flat"])
    opposing = (row[f"w{i}_end_slip_cmps"], -row[f"w{i}_end_vlat_cmps"])
    cross = force[0] * opposing[1] - force[1] * opposing[0]
    dot = force[0] * opposing[0] + force[1] * opposing[1]
    if math.hypot(*opposing) < 1e-3:
        return 0.0
    return math.degrees(math.atan2(abs(cross), dot))


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
    late = spike.window(rows, 4.0, 6.0)
    drift = abs(mean(late, "forward_cmps"))
    result: dict[str, Any] = {"mean_drift_cmps": drift, "pass": drift < HOLD_CMPS}
    # Report only, from attempt 2: the solve records over the same window. Not part of the pass.
    if "w0_gravity_dv_long" in late[0]:
        count = wheels(rows)
        moved = math.dist(
            (late[0]["x_cm"], late[0]["y_cm"], late[0]["z_cm"]),
            (late[-1]["x_cm"], late[-1]["y_cm"], late[-1]["z_cm"]),
        )
        result["report"] = {
            "contact_vlong_cmps": [mean(late, f"w{i}_vlong_cmps") for i in range(count)],
            "gravity_dv_long_cmps": [mean(late, f"w{i}_gravity_dv_long") for i in range(count)],
            "known_dv_long_cmps": [mean(late, f"w{i}_known_dv_long") for i in range(count)],
            "drive_force": [mean(late, f"w{i}_flong") for i in range(count)],
            "end_slip_cmps": [
                max(abs(r[f"w{i}_end_slip_cmps"]) for r in late) for i in range(count)
            ],
            "body_moved_cm": moved,
            "max_solve_passes": max(r["solve_passes"] for r in late),
            "all_converged": all(r["solve_converged"] == 1 for r in late),
        }
    return result


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


# Phase C. Thresholds from phase-c-design.md, fixed before the first gated run; R0's if any.
SIX_MASS = 853.5
C_HEIGHT_RANGE_CM = 0.5
C_LOAD_SUM_TOLERANCE = 0.01
C_LOAD_EACH_TOLERANCE = 0.05
C_SPEED_TOLERANCE = 0.05
C_OVERSHOOT = 0.10
C_YAW_DRIFT_DEGPS = 0.5
C_TURN_TOLERANCE = 0.10
C_TIMESTEP = 0.05
C_HOLD_CMPS = 0.1
C_CLIMB_CMPS = 25.0
C_CLIMB_TILT_DEG = 45.0
C_STABILITY_SPEED_CMPS = 200.0
C_STABILITY_TILT_DEG = 60.0
MOTOR_LIMIT_FORCE = 6.0e5 / 25.0  # The motor's torque limit as ground force; report only

C_GATED = ["c1", "c1r", "c2", "c3", "c5", "c5b", "c6_5", "c6_10", "c7"]
C_REPORTED = ["c6_15", "c6_20", "cstep_10", "cstep_25", "cstep_50"]


def plan_c() -> list[dict[str, Any]]:
    runs = [{"name": s, "scenario": s, "flags": spike.FIXED_60} for s in C_GATED]
    runs += [{"name": f"{s}_fps120", "scenario": s, "flags": spike.FIXED_120} for s in ("c2", "c3")]
    runs[C_GATED.index("c7")]["timeout_s"] = 3600
    runs += [{"name": s, "scenario": s, "flags": spike.FIXED_60} for s in C_REPORTED]
    runs += [
        {"name": f"repeat_det{i}", "scenario": "c2", "flags": spike.DETERMINISTIC_60}
        for i in range(1, 6)
    ]
    runs.append({"name": "perf", "scenario": "cperf", "flags": ["-ExecCmds=r.VSync 0"]})
    for run in runs:
        run["map"] = MAP_URL
        run["scenario_arg"] = "WheelScenario"
    return runs


def tilt(row: dict[str, float]) -> float:
    """R0's tilt: the larger of pitch and roll."""
    return max(abs(row["pitch_deg"]), abs(row["roll_deg"]))


def common_c(rows: list[dict[str, float]], meta: dict[str, Any]) -> dict[str, Any]:
    """Every phase C run: completed, bounded, inside the circle and torque limits, converged."""
    result = common(rows, meta)
    torque = sum(
        1
        for r in rows
        for i in range(6)
        if abs(r[f"w{i}_motor"]) > meta["motor_max_torque"] + 0.01
        or abs(r[f"w{i}_brake"]) > meta["brake_max_torque"] + 0.01
    )
    unconverged = sum(1 for r in rows if r["solve_passes"] > 0 and r["solve_converged"] != 1)
    result["torque_violations"] = torque
    result["unconverged_steps"] = unconverged
    result["common_pass"] = bool(result["common_pass"] and torque == 0 and unconverged == 0)
    return result


def c_static(rows: list[dict[str, float]]) -> dict[str, Any]:
    late = spike.window(rows, 10.0, 15.0)
    heights = [r["z_cm"] for r in late]
    weight = SIX_MASS * GRAVITY
    loads = [mean(late, f"w{i}_fz") for i in range(6)]
    error = sum(loads) / weight - 1
    each = [x / (weight / 6) - 1 for x in loads]
    ok = (
        max(heights) - min(heights) < C_HEIGHT_RANGE_CM
        and abs(error) <= C_LOAD_SUM_TOLERANCE
        and all(abs(x) <= C_LOAD_EACH_TOLERANCE for x in each)
    )
    return {
        "height_range_cm": max(heights) - min(heights),
        "load_sum_error": error,
        "load_each_error": each,
        "pass": ok,
    }


def c_straight(rows: list[dict[str, float]]) -> dict[str, Any]:
    driving = spike.window(rows, 3.0, 23.0)
    target = 50.0
    reached = next(
        (r["t_s"] - 3.0 for r in driving if r["forward_cmps"] >= target * (1 - C_SPEED_TOLERANCE)),
        None,
    )
    peak_row = max(driving, key=lambda r: r["forward_cmps"])
    steady = spike.window(rows, 13.0, 23.0)
    speed = mean(steady, "forward_cmps")
    yaw = statistics.fmean(abs(r["wz_degps"]) for r in steady)
    ok = (
        reached is not None
        and peak_row["forward_cmps"] <= target * (1 + C_OVERSHOOT)
        and abs(speed - target) <= C_SPEED_TOLERANCE * target
        and yaw < C_YAW_DRIFT_DEGPS
    )

    def ground(row: dict[str, float]) -> float:
        return statistics.fmean(row[f"w{i}_vlong_cmps"] for i in range(6))

    return {
        "time_to_95_percent_s": reached,
        "peak_cmps": peak_row["forward_cmps"],
        "steady_mean_cmps": speed,
        "mean_abs_yaw_rate_degps": yaw,
        "end_x_cm": spike.at_time(rows, 23.0)["x_cm"],
        # Report only: at the peak, the wheels' mean ground speed, and the rest of the body's
        # speed, which comes from pitching about the contacts.
        "report": {
            "peak_t_s": peak_row["t_s"],
            "peak_ground_speed_cmps": ground(peak_row),
            "peak_rotation_part_cmps": peak_row["forward_cmps"] - ground(peak_row),
            "peak_pitch_deg": peak_row["pitch_deg"],
            "max_ground_speed_cmps": max(ground(r) for r in driving),
            "max_abs_pitch_rate_degps": max(abs(r["wy_degps"]) for r in driving),
        },
        "pass": ok,
    }


def c_turn(rows: list[dict[str, float]]) -> dict[str, Any]:
    steady = spike.window(rows, 13.0, 23.0)
    rate = spike.slope_fit([r["t_s"] for r in steady], spike.unwrapped_yaw(steady))
    ok = rate > 0 and abs(rate - TURN_DEGPS) <= C_TURN_TOLERANCE * TURN_DEGPS
    turned = spike.unwrapped_yaw(spike.window(rows, 0.0, 23.0))
    last = steady[-1]
    return {
        "yaw_rate_degps": rate,
        "commanded_degps": TURN_DEGPS,
        "total_yaw_deg": turned[-1] - turned[0],
        "wz_range_degps": [min(r["wz_degps"] for r in steady), max(r["wz_degps"] for r in steady)],
        # Report only: how close each wheel's ground force is to the motor's limit, and which slide.
        "report": {
            "long_force_over_motor_limit": [
                abs(last[f"w{i}_flong"]) / MOTOR_LIMIT_FORCE for i in range(6)
            ],
            "motor_torque": [last[f"w{i}_motor"] for i in range(6)],
            "sliding": [int(last[f"w{i}_saturated"]) for i in range(6)],
            "lateral_force": [last[f"w{i}_flat"] for i in range(6)],
            "net_yaw_torque": last["wheel_tz"],
        },
        "pass": ok,
    }


def c_hold(rows: list[dict[str, float]]) -> dict[str, Any]:
    drift = abs(mean(spike.window(rows, 5.0, 10.0), "forward_cmps"))
    return {"mean_drift_cmps": drift, "pass": drift < C_HOLD_CMPS}


def c_climb(rows: list[dict[str, float]]) -> dict[str, Any]:
    climb = mean(spike.window(rows, 20.0, 30.0), "forward_cmps")
    worst = max(tilt(r) for r in rows)
    return {
        "climb_cmps": climb,
        "max_tilt_deg": worst,
        "pass": climb >= C_CLIMB_CMPS and worst < C_CLIMB_TILT_DEG,
    }


def c_stability(rows: list[dict[str, float]], meta: dict[str, Any]) -> dict[str, Any]:
    speed = max(math.sqrt(r["vx_cmps"] ** 2 + r["vy_cmps"] ** 2 + r["vz_cmps"] ** 2) for r in rows)
    worst = max(tilt(r) for r in rows)
    ok = (
        meta["outcome"] == "completed"
        and meta["sim_time_s"] >= 600.0
        and speed <= C_STABILITY_SPEED_CMPS
        and worst <= C_STABILITY_TILT_DEG
        and meta["body_hits"] == 0
    )
    return {
        "sim_time_s": meta["sim_time_s"],
        "max_speed_cmps": speed,
        "max_tilt_deg": worst,
        "body_hits": meta["body_hits"],
        "pass": ok,
    }


def command_analyze_c(args: argparse.Namespace) -> int:
    out_dir = RECORDS / args.batch
    runs = [
        json.loads(x) for x in (out_dir / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    loaded = {spec["name"]: spike.load(out_dir, spec["name"]) for spec in plan_c()}
    judged: dict[str, Any] = {}
    for name, data in loaded.items():
        if data is None:
            judged[name] = {"missing": True, "pass": False}
            continue
        rows, meta = data
        scenario = name.split("_fps")[0]
        if scenario in ("c1", "c1r"):
            result = c_static(rows)
        elif scenario == "c2" or name.startswith("repeat_det"):
            result = c_straight(rows)
        elif scenario == "c3":
            result = c_turn(rows)
        elif scenario in ("c5", "c5b"):
            result = c_hold(rows)
        elif scenario.startswith("c6_"):
            result = c_climb(rows)
        elif scenario == "c7":
            result = c_stability(rows, meta)
        else:
            result = {"max_tilt_deg": max(tilt(r) for r in rows), "end_x_cm": rows[-1]["x_cm"]}
        result.update(common_c(rows, meta))
        result["numerics"] = numerics(rows, meta)
        result["pass"] = bool(result.get("pass", True) and result["common_pass"])
        judged[name] = result

    def get(name: str, key: str) -> Any:
        return judged.get(name, {}).get(key)

    straight = relative(get("c2", "end_x_cm"), get("c2_fps120", "end_x_cm"))
    turn = relative(get("c3", "total_yaw_deg"), get("c3_fps120", "total_yaw_deg"))
    tests = {name: judged[name]["pass"] for name in ("c1", "c1r", "c2", "c3", "c5", "c5b", "c7")}
    tests["c4"] = bool(
        straight is not None
        and turn is not None
        and straight < C_TIMESTEP
        and turn < C_TIMESTEP
        and judged["c2_fps120"]["pass"]
        and judged["c3_fps120"]["pass"]
    )
    tests["c6"] = bool(judged["c6_5"]["pass"] and judged["c6_10"]["pass"])
    repeats = [
        judged[f"repeat_det{i}"] for i in range(1, 6) if "end_x_cm" in judged[f"repeat_det{i}"]
    ]
    perf = loaded.get("perf")
    summary = {
        "batch": args.batch,
        "runs": runs,
        "judged": judged,
        "timestep_relative": {"c2_end_x": straight, "c3_total_yaw": turn},
        "repeatability_end_x_cm": spike.spread([r["end_x_cm"] for r in repeats])
        if repeats
        else None,
        "performance": spike.frame_stats(perf[0]) if perf else None,
        "tests": tests,
        "phase_c_pass": all(tests.values()),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("tests", "phase_c_pass")}, indent=2))
    return 0


def numerics(rows: list[dict[str, float]], meta: dict[str, Any]) -> dict[str, Any]:
    """Report only: contact residuals, limits, prediction against Chaos, Newton, and energy."""
    count = wheels(rows)
    mass, gravity, radius = meta["mass_kg"], abs(meta["gravity_z"]), 25.0
    inertia = meta["principal_inertia"]
    # Rig A locks all rotation, rig B roll and pitch; the six-wheel body is free.
    axes = dict(zip("xyz", inertia, strict=True))
    free = {} if count == 1 else ({"z": axes["z"]} if count == 2 else axes)
    stick, circle, angles, power = [], [], [], []
    circle_violations = torque_violations = power_violations = 0
    for row in rows:
        for i in range(count):
            limit = row[f"w{i}_limit"]
            if not row[f"w{i}_hit"] or limit <= 0:
                continue
            force = math.hypot(row[f"w{i}_flong"], row[f"w{i}_flat"])
            slip = math.hypot(row[f"w{i}_end_slip_cmps"], row[f"w{i}_end_vlat_cmps"])
            circle_violations += (force - limit) / limit > CIRCLE_TOLERANCE
            torque_violations += (
                abs(row[f"w{i}_motor"]) > meta["motor_max_torque"] + 0.01
                or abs(row[f"w{i}_brake"]) > meta["brake_max_torque"] + 0.01
            )
            power.append(row[f"w{i}_friction_power"] / limit)
            power_violations += power[-1] > 1e-6
            if row[f"w{i}_saturated"]:
                circle.append(abs(force - limit) / limit)
                if slip >= 1e-3:
                    angles.append(slide_angle(row, i))
            else:
                stick.append(slip)
    predicted, newton, yaw, excess = [], [], [], []
    sleeps = 0
    for before, now, after in zip(rows, rows[1:], rows[2:], strict=False):
        dt = after["dt_s"]
        # Chaos sleep zeroes the body velocity, which no force here explains. Count it, keep it
        # out of the other checks.
        if asleep(now, after, mass, gravity, free):
            sleeps += 1
            continue
        for i in range(count):
            if now[f"w{i}_hit"] and after[f"w{i}_hit"]:
                along = now[f"w{i}_spin_radps"] * radius - now[f"w{i}_end_slip_cmps"]
                predicted.append(
                    max(
                        abs(along - after[f"w{i}_vlong_cmps"]),
                        abs(now[f"w{i}_end_vlat_cmps"] - after[f"w{i}_vlat_cmps"]),
                    )
                )
        if now["push"] == 0:
            measured = [(after[k] - now[k]) / dt for k in ("vx_cmps", "vy_cmps", "vz_cmps")]
            expected = [now["wheel_fx"] / mass, now["wheel_fy"] / mass]
            expected.append(now["wheel_fz"] / mass - gravity)
            newton.append(math.dist(measured, expected))
            spin_up = math.radians(after["wz_degps"] - now["wz_degps"]) / dt
            yaw.append(abs(spin_up - now["wheel_tz"] / inertia[2]))
        if now["push"] == 0:
            work = sum(now[f"w{i}_wheel_power"] for i in range(count)) * dt
            excess.append(energy(after, now, meta, count) - energy(now, before, meta, count) - work)
    return {
        "sleep_resets": sleeps,
        "unconverged_steps": sum(
            1 for r in rows if r["solve_converged"] != 1 and r["solve_passes"] > 0
        ),
        "max_solve_passes": max(r["solve_passes"] for r in rows),
        "max_last_change_cmps": max(r["solve_change_cmps"] for r in rows),
        "max_stick_residual_cmps": max(stick, default=None),
        "max_slide_circle_residual": max(circle, default=None),
        "max_slide_angle_deg": max(angles, default=None),
        "slide_angle_over_1deg": sum(1 for a in angles if a > 1.0),
        "circle_violations": circle_violations,
        "torque_violations": torque_violations,
        "max_friction_power_over_limit_cmps": max(power, default=None),
        "friction_power_over_1e-6": power_violations,
        "max_prediction_error_cmps": max(predicted, default=None),
        "max_newton_residual_cmps2": max(newton, default=None),
        "max_yaw_residual_radps2": max(yaw, default=None),
        "max_energy_excess_over_mg_cm": max(excess, default=0.0) / (mass * gravity),
        "nonfinite": any(not math.isfinite(v) for r in rows for v in r.values()),
        "max_load_over_static": max(r[f"w{i}_fz"] for r in rows for i in range(count))
        / (mass * gravity / count),
    }


def asleep(
    now: dict[str, float],
    after: dict[str, float],
    mass: float,
    gravity: float,
    free: dict[str, float],
) -> bool:
    """The next step's velocities are all exactly zero, where the step's forces predict motion."""
    keys = ("vx_cmps", "vy_cmps", "vz_cmps", "wx_degps", "wy_degps", "wz_degps")
    if any(after[k] != 0 for k in keys):
        return False
    dt = after["dt_s"]
    linear = (
        now["vx_cmps"] + dt * now["wheel_fx"] / mass,
        now["vy_cmps"] + dt * now["wheel_fy"] / mass,
        now["vz_cmps"] + dt * (now["wheel_fz"] / mass - gravity),
    )
    # Angular in deg/s about the free axes, with inertia on world axes: approximate when tilted.
    angular = [
        now[f"w{axis}_degps"] + math.degrees(dt * now[f"wheel_t{axis}"] / i)
        for axis, i in free.items()
    ]
    return math.hypot(*linear) > 0.01 or math.hypot(*angular) > 0.01


def energy(
    row: dict[str, float], spun: dict[str, float], meta: dict[str, Any], count: int
) -> float:
    """Body, wheel spin, gravity, and spring energy at the start of a row's step.

    A row holds the body's state at the start of its step, but wheel spin at the end, so spin comes
    from the row before. Rotation uses world axes, so it is approximate when the body is tilted.
    """
    mass, gravity, inertia = meta["mass_kg"], abs(meta["gravity_z"]), meta["principal_inertia"]
    speed2 = sum(row[k] ** 2 for k in ("vx_cmps", "vy_cmps", "vz_cmps"))
    spin = [math.radians(row[k]) for k in ("wx_degps", "wy_degps", "wz_degps")]
    total = 0.5 * mass * speed2 + 0.5 * sum(i * w * w for i, w in zip(inertia, spin, strict=True))
    total += mass * gravity * row["z_cm"]
    for i in range(count):
        total += 0.5 * WHEEL_INERTIA * spun[f"w{i}_spin_radps"] ** 2
        if row[f"w{i}_hit"]:
            total += 0.5 * meta["spring_rate"] * max(row[f"w{i}_comp_cm"], 0.0) ** 2
    return total


def command_numerics(args: argparse.Namespace) -> int:
    out_dir = RECORDS / args.batch
    report = {}
    for run_dir in sorted(p for p in out_dir.iterdir() if p.is_dir()):
        loaded = spike.load(out_dir, run_dir.name)
        if loaded is not None:
            rows, meta = loaded
            report[run_dir.name] = numerics(rows, meta)
    (out_dir / "numerics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def diagnostic_plan(scenarios: list[str], extra: list[str] | None = None) -> list[dict[str, Any]]:
    """Runs that are not gated, at 60 Hz unless the name ends in _fps120."""
    runs = []
    for name in scenarios:
        scenario, _, rate = name.partition("_fps")
        flags = spike.FIXED_120 if rate == "120" else spike.FIXED_60
        runs.append({"name": name, "scenario": scenario, "flags": flags, "extra": extra or []})
    for run in runs:
        run["map"] = MAP_URL
        run["scenario_arg"] = "WheelScenario"
    return runs


def command_run(args: argparse.Namespace) -> int:
    out_dir = RECORDS / args.batch
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.diagnostic:
        runs = diagnostic_plan(args.diagnostic, args.extra.split())
    else:
        runs = plan_c() if args.phase == "c" else plan()
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
    run.add_argument("--diagnostic", nargs="*", help="Scenarios to run instead, not gated")
    run.add_argument("--phase", choices=["ab", "c"], default="ab", help="Which gated plan")
    run.add_argument(
        "--extra",
        default="",
        help='Engine flags for diagnostic runs, as one string: "-WheelPasses=2000"',
    )
    analyze = sub.add_parser("analyze", help="Judge a batch against the fixed thresholds")
    analyze.add_argument("--batch", required=True)
    analyze_c = sub.add_parser(
        "analyze-c", help="Judge a phase C batch against its fixed thresholds"
    )
    analyze_c.add_argument("--batch", required=True)
    numeric = sub.add_parser("numerics", help="Report solver and physics checks; not gated")
    numeric.add_argument("--batch", required=True)
    args = parser.parse_args()
    commands = {
        "run": command_run,
        "analyze": command_analyze,
        "analyze-c": command_analyze_c,
        "numerics": command_numerics,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
