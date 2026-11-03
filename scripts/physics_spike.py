"""Run and analyze the Unreal physics spike (Step 5a) on the Mac.

This is an experiment outside the Mission Core. It imports nothing from `roverloom`, reads only the
spike's own records, and never writes contract logs. Records stay in `unreal/Saved/PhysicsSpike/`.

    python scripts/physics_spike.py run r0 --batch r0-YYYYMMDD
    python scripts/physics_spike.py analyze --batch r0-YYYYMMDD

The thresholds below were fixed before the first gated run. Do not change them after seeing results.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "unreal" / "Roverloom.uproject"
RECORDS = ROOT / "unreal" / "Saved" / "PhysicsSpike"
ENGINE = Path(os.environ.get("ROVERLOOM_UE_ROOT", Path.home() / "UnrealEngineInstall" / "UE_5.8"))
EDITOR = ENGINE / "Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
CRASH_DIRS = [
    Path.home() / "Library/Application Support/Epic/UnrealEngine/5.8/Saved/Crashes",
    ROOT / "unreal" / "Saved" / "Crashes",
]
MAP_URL = "/Engine/Maps/Entry?game=/Script/Roverloom.SpikeGameMode"
MIN_FREE_PERCENT = 10

# Thresholds, fixed before the first gated run.
GRAVITY_CMPS2 = -371.0
GRAVITY_TOLERANCE = 0.01
STATIC_Z_RANGE_CM = 0.5
WHEEL_PENETRATION_CM = 1.0
CHASSIS_WEIGHT = (853.5 - 6 * 15.0) * 371.0
SPEED_CMPS = 50.0
SPEED_TOLERANCE = 0.05
OVERSHOOT = 0.10
YAW_RATE_DEGPS = 28.178
YAW_TOLERANCE = 0.10
PROBE_TOLERANCE = 0.10
TIMESTEP_TOLERANCE = 0.05
STABILITY_MAX_SPEED_CMPS = 200.0
STABILITY_MIN_WHEEL_Z_CM = 20.0
STABILITY_MAX_TILT_DEG = 60.0
SLOPE_HOLD_CMPS = 0.5
SLOPE_CLIMB_CMPS = 25.0
OBSTACLE_FRONT_CM = 300.0
OBSTACLE_MAX_TILT_DEG = 45.0
WHEEL_RADIUS_CM = 25.0

FIXED_60 = ["-UseFixedTimeStep", "-FPS=60"]
FIXED_120 = ["-UseFixedTimeStep", "-FPS=120"]
DETERMINISTIC_60 = ["-Deterministic", "-FPS=60"]


def r0_plan() -> list[dict[str, Any]]:
    """Every R0 run, in order. Names are the record file names."""
    runs: list[dict[str, Any]] = [
        {"name": "probe", "scenario": "probe", "flags": FIXED_60},
        {"name": "freefall", "scenario": "freefall", "flags": FIXED_60},
        {"name": "static", "scenario": "static", "flags": FIXED_60},
        {"name": "straight_fps60", "scenario": "straight", "flags": FIXED_60},
        {"name": "straight_fps120", "scenario": "straight", "flags": FIXED_120},
        {"name": "turn_fps60", "scenario": "turn", "flags": FIXED_60},
        {"name": "turn_fps120", "scenario": "turn", "flags": FIXED_120},
    ]
    runs += [
        {
            "name": f"slope{deg}",
            "scenario": "slope",
            "flags": FIXED_60,
            "extra": [f"-SpikeSlopeDeg={deg}"],
        }
        for deg in (5, 10, 15, 20)
    ]
    runs += [
        {
            "name": f"obstacle{cm}",
            "scenario": "obstacle",
            "flags": FIXED_60,
            "extra": [f"-SpikeObstacleCm={cm}"],
        }
        for cm in (10, 25, 50)
    ]
    runs += [
        {"name": f"repeat_det{i}", "scenario": "straight", "flags": DETERMINISTIC_60}
        for i in range(1, 6)
    ]
    runs += [{"name": f"repeat_rt{i}", "scenario": "straight", "flags": []} for i in range(1, 6)]
    runs.append(
        {"name": "stability", "scenario": "stability", "flags": FIXED_60, "timeout_s": 3600}
    )
    runs.append({"name": "perf", "scenario": "perf", "flags": ["-ExecCmds=r.VSync 0"]})
    return runs


def crash_count() -> int:
    return sum(len(list(d.iterdir())) for d in CRASH_DIRS if d.is_dir())


def free_percent() -> int:
    out = subprocess.run(
        ["memory_pressure", "-Q"], capture_output=True, text=True, check=True
    ).stdout
    match = re.search(r"free percentage: (\d+)%", out)
    return int(match.group(1)) if match else -1


def swap_used_mb() -> float:
    out = subprocess.run(
        ["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, check=True
    ).stdout
    match = re.search(r"used = ([\d.]+)M", out)
    return float(match.group(1)) if match else -1.0


def rss_mb(pid: int) -> float:
    out = subprocess.run(
        ["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True
    ).stdout.strip()
    return int(out) / 1024 if out else 0.0


def listeners_1985() -> list[str]:
    out = subprocess.run(
        ["lsof", "-nP", "-iTCP:1985", "-sTCP:LISTEN"], capture_output=True, text=True
    ).stdout
    return sorted({f"{line.split()[0]} {line.split()[8]}" for line in out.splitlines()[1:] if line})


def run_one(spec: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    run_dir = out_dir / spec["name"]
    run_dir.mkdir(parents=True, exist_ok=True)
    args = [
        str(EDITOR),
        str(PROJECT),
        MAP_URL,
        "-game",
        "-windowed",
        "-ResX=1280",
        "-ResY=720",
        "-nosplash",
        "-nosound",
        "-unattended",
        "-log",
        f"-abslog={run_dir / 'editor.log'}",
        f"-SpikeScenario={spec['scenario']}",
        f"-SpikeOut={run_dir}",
        *spec["flags"],
        *spec.get("extra", []),
    ]
    crashes_before = crash_count()
    swap_before = swap_used_mb()
    started = time.monotonic()
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    peak_rss, min_free, ports, stop_reason = 0.0, 100, None, None
    timeout = spec.get("timeout_s", 600)
    while process.poll() is None:
        time.sleep(0.5)
        elapsed = time.monotonic() - started
        peak_rss = max(peak_rss, rss_mb(process.pid))
        free = free_percent()
        min_free = min(min_free, free)
        if ports is None and elapsed > 8:
            ports = listeners_1985()
        if 0 <= free < MIN_FREE_PERCENT:
            stop_reason = f"free memory {free}% below {MIN_FREE_PERCENT}%"
        elif elapsed > timeout:
            stop_reason = f"timeout after {timeout} s"
        if stop_reason:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.kill()
            break
    record = {
        "name": spec["name"],
        "flags": spec["flags"] + spec.get("extra", []),
        "exit_code": process.wait(),
        "wall_s": round(time.monotonic() - started, 2),
        "peak_rss_mb": round(peak_rss),
        "min_free_percent": min_free,
        "swap_used_mb_before": swap_before,
        "swap_used_mb_after": swap_used_mb(),
        "port_1985_listeners": ports or [],
        "new_crash_reports": crash_count() - crashes_before,
        "sigterm_used": stop_reason is not None,
        "stop_reason": stop_reason,
    }
    with (out_dir / "runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return record


def command_run(args: argparse.Namespace) -> int:
    out_dir = RECORDS / args.batch
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = r0_plan()
    if args.only:
        plan = [spec for spec in plan if spec["name"] in args.only]
    for spec in plan:
        record = run_one(spec, out_dir)
        print(json.dumps(record), flush=True)
        if record["new_crash_reports"] or record["sigterm_used"] or record["exit_code"] != 0:
            print("Stopping the batch: crash, forced stop, or a nonzero exit.", file=sys.stderr)
            return 1
    return 0


def load(out_dir: Path, name: str) -> tuple[list[dict[str, float]], dict[str, Any]] | None:
    csv_path = next((out_dir / name).glob("*.csv"), None)
    meta_path = next((out_dir / name).glob("*.json"), None)
    if csv_path is None or meta_path is None:
        return None
    with csv_path.open(encoding="utf-8") as handle:
        rows = [{key: float(value) for key, value in row.items()} for row in csv.DictReader(handle)]
    return rows, json.loads(meta_path.read_text(encoding="utf-8"))


def window(rows: list[dict[str, float]], start: float, end: float) -> list[dict[str, float]]:
    return [row for row in rows if start <= row["t_s"] <= end]


def at_time(rows: list[dict[str, float]], t: float) -> dict[str, float]:
    return min(rows, key=lambda row: abs(row["t_s"] - t))


def slope_fit(xs: list[float], ys: list[float]) -> float:
    mean_x, mean_y = statistics.fmean(xs), statistics.fmean(ys)
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / sum(
        (x - mean_x) ** 2 for x in xs
    )


def unwrapped_yaw(rows: list[dict[str, float]]) -> list[float]:
    out, offset = [rows[0]["yaw_deg"]], 0.0
    for previous, row in zip(rows, rows[1:], strict=False):
        step = row["yaw_deg"] - previous["yaw_deg"]
        offset -= 360.0 * round(step / 360.0)
        out.append(row["yaw_deg"] + offset)
    return out


def spin_mean(rows: list[dict[str, float]]) -> float:
    return statistics.fmean(row[f"w{i}_spin_radps"] for row in rows for i in range(6))


def analyze_probe(rows: list[dict[str, float]]) -> dict[str, Any]:
    forward = spin_mean(window(rows, 2.0, 4.0))
    backward = spin_mean(window(rows, 5.0, 7.0))
    target = SPEED_CMPS / WHEEL_RADIUS_CM
    ok = (
        abs(forward - target) <= PROBE_TOLERANCE * target
        and abs(backward + target) <= PROBE_TOLERANCE * target
    )
    return {
        "forward_spin_radps": forward,
        "backward_spin_radps": backward,
        "target_radps": target,
        "pass": ok,
    }


def analyze_freefall(rows: list[dict[str, float]]) -> dict[str, Any]:
    part = window(rows, 0.1, 0.6)
    accel = slope_fit([r["t_s"] for r in part], [r["vz_cmps"] for r in part])
    airborne = min(r[f"w{i}_z_cm"] for r in part for i in range(6)) > 2 * WHEEL_RADIUS_CM
    ok = airborne and abs(accel - GRAVITY_CMPS2) <= GRAVITY_TOLERANCE * abs(GRAVITY_CMPS2)
    return {"accel_cmps2": accel, "airborne": airborne, "pass": ok}


def analyze_static(rows: list[dict[str, float]]) -> dict[str, Any]:
    late = window(rows, 10.0, 15.0)
    z_range = max(r["z_cm"] for r in late) - min(r["z_cm"] for r in late)
    min_wheel_z = min(r[f"w{i}_z_cm"] for r in window(rows, 1.0, 15.0) for i in range(6))
    loads = [abs(r["axle_fz"]) for r in late]
    ok = z_range < STATIC_Z_RANGE_CM and min_wheel_z >= WHEEL_RADIUS_CM - WHEEL_PENETRATION_CM
    # Not judged. Before the gated runs, Chaos's joint force output varied from 44 to 3161 at rest,
    # against a weight near 283,000, so it is recorded as an unusable measurement.
    return {
        "z_range_cm": z_range,
        "min_wheel_z_cm": min_wheel_z,
        "axle_load_judged": False,
        "axle_load_mean": statistics.fmean(loads),
        "axle_load_min": min(loads),
        "axle_load_max": max(loads),
        "chassis_weight": CHASSIS_WEIGHT,
        "pass": ok,
    }


def analyze_straight(rows: list[dict[str, float]]) -> dict[str, Any]:
    driving = window(rows, 3.0, 23.0)
    reached = next(
        (
            r["t_s"] - 3.0
            for r in driving
            if r["forward_cmps"] >= SPEED_CMPS * (1 - SPEED_TOLERANCE)
        ),
        None,
    )
    peak = max(r["forward_cmps"] for r in driving)
    steady = window(rows, 13.0, 23.0)
    mean = statistics.fmean(r["forward_cmps"] for r in steady)
    rim = spin_mean(steady) * WHEEL_RADIUS_CM
    ok = (
        reached is not None
        and peak <= SPEED_CMPS * (1 + OVERSHOOT)
        and abs(mean - SPEED_CMPS) <= SPEED_TOLERANCE * SPEED_CMPS
    )
    end = at_time(rows, 23.0)
    return {
        "time_to_95_percent_s": reached,
        "peak_cmps": peak,
        "steady_mean_cmps": mean,
        "slip": 1 - mean / rim if rim else None,
        "end_x_cm": end["x_cm"],
        "end_y_cm": end["y_cm"],
        "end_yaw_deg": end["yaw_deg"],
        "pass": ok,
    }


def analyze_turn(rows: list[dict[str, float]]) -> dict[str, Any]:
    steady = window(rows, 13.0, 23.0)
    yaw = unwrapped_yaw(steady)
    rate = slope_fit([r["t_s"] for r in steady], yaw)
    ok = rate > 0 and abs(rate - YAW_RATE_DEGPS) <= YAW_TOLERANCE * YAW_RATE_DEGPS
    turned = unwrapped_yaw(window(rows, 0.0, 23.0))
    return {
        "yaw_rate_degps": rate,
        "body_wz_degps": statistics.fmean(r["wz_degps"] for r in steady),
        "total_yaw_deg": turned[-1] - turned[0],
        "drift_cm": math.hypot(
            steady[-1]["x_cm"] - rows[0]["x_cm"], steady[-1]["y_cm"] - rows[0]["y_cm"]
        ),
        "pass": ok,
    }


def analyze_slope(rows: list[dict[str, float]]) -> dict[str, Any]:
    hold = statistics.fmean(r["forward_cmps"] for r in window(rows, 5.0, 10.0))
    climb_rows = window(rows, 20.0, 30.0)
    climb = statistics.fmean(r["forward_cmps"] for r in climb_rows)
    rim = spin_mean(climb_rows) * WHEEL_RADIUS_CM
    return {
        "hold_drift_cmps": hold,
        "holds": abs(hold) < SLOPE_HOLD_CMPS,
        "climb_cmps": climb,
        "climbs": climb >= SLOPE_CLIMB_CMPS,
        "climb_slip": 1 - climb / rim if rim else None,
    }


def analyze_obstacle(rows: list[dict[str, float]], height: float) -> dict[str, Any]:
    end = rows[-1]
    on_top = all(
        end[f"w{i}_x_cm"] > OBSTACLE_FRONT_CM + WHEEL_RADIUS_CM
        and end[f"w{i}_z_cm"] > height + WHEEL_RADIUS_CM - 5
        for i in range(6)
    )
    tilt = max(max(abs(r["pitch_deg"]), abs(r["roll_deg"])) for r in rows)
    return {
        "climbed": on_top and tilt < OBSTACLE_MAX_TILT_DEG,
        "max_tilt_deg": tilt,
        "front_wheel_max_z_cm": max(max(r["w0_z_cm"], r["w1_z_cm"]) for r in rows),
        "end_x_cm": end["x_cm"],
    }


def analyze_stability(rows: list[dict[str, float]], meta: dict[str, Any]) -> dict[str, Any]:
    speed = max(math.sqrt(r["vx_cmps"] ** 2 + r["vy_cmps"] ** 2 + r["vz_cmps"] ** 2) for r in rows)
    wheel_z = min(r[f"w{i}_z_cm"] for r in rows if r["t_s"] >= 1.0 for i in range(6))
    tilt = max(max(abs(r["pitch_deg"]), abs(r["roll_deg"])) for r in rows)
    ok = (
        meta["outcome"] == "completed"
        and speed <= STABILITY_MAX_SPEED_CMPS
        and wheel_z >= STABILITY_MIN_WHEEL_Z_CM
        and tilt <= STABILITY_MAX_TILT_DEG
    )
    return {
        "sim_time_s": meta["sim_time_s"],
        "max_speed_cmps": speed,
        "min_wheel_z_cm": wheel_z,
        "max_tilt_deg": tilt,
        "pass": ok,
    }


def frame_stats(rows: list[dict[str, float]]) -> dict[str, Any]:
    times = sorted(r["wall_frame_ms"] for r in rows if r["t_s"] >= 3.0)

    def pick(quantile: float) -> float:
        return times[min(len(times) - 1, int(quantile * len(times)))]

    return {
        "frames": len(times),
        "mean_fps": 1000 / statistics.fmean(times),
        "p50_ms": pick(0.50),
        "p95_ms": pick(0.95),
        "p99_ms": pick(0.99),
        "max_ms": times[-1],
    }


def spread(values: list[float]) -> dict[str, float]:
    return {
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
        "stdev": statistics.pstdev(values),
    }


def command_analyze(args: argparse.Namespace) -> int:
    out_dir = RECORDS / args.batch
    runs = {}
    runs_file = out_dir / "runs.jsonl"
    if runs_file.exists():
        for line in runs_file.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            runs[record["name"]] = record
    data = {name: load(out_dir, name) for name in runs}
    result: dict[str, Any] = {"batch": args.batch, "runs": runs, "tests": {}}
    tests = result["tests"]

    def get(name: str) -> tuple[list[dict[str, float]], dict[str, Any]] | None:
        return data.get(name)

    simple = {"probe": analyze_probe, "freefall": analyze_freefall, "static": analyze_static}
    for name, analyzer in simple.items():
        loaded = get(name)
        tests[name] = analyzer(loaded[0]) if loaded else {"missing": True, "pass": False}
    for prefix, analyzer in (("straight", analyze_straight), ("turn", analyze_turn)):
        for fps in (60, 120):
            loaded = get(f"{prefix}_fps{fps}")
            tests[f"{prefix}_fps{fps}"] = (
                analyzer(loaded[0]) if loaded else {"missing": True, "pass": False}
            )

    s60, s120 = tests["straight_fps60"], tests["straight_fps120"]
    t60, t120 = tests["turn_fps60"], tests["turn_fps120"]
    if (
        "end_x_cm" in s60
        and "end_x_cm" in s120
        and "total_yaw_deg" in t60
        and "total_yaw_deg" in t120
    ):
        straight_rel = abs(s120["end_x_cm"] - s60["end_x_cm"]) / abs(s60["end_x_cm"])
        turn_rel = abs(t120["total_yaw_deg"] - t60["total_yaw_deg"]) / abs(t60["total_yaw_deg"])
        tests["timestep"] = {
            "straight_relative_difference": straight_rel,
            "turn_relative_difference": turn_rel,
            "pass": straight_rel < TIMESTEP_TOLERANCE and turn_rel < TIMESTEP_TOLERANCE,
        }
    else:
        tests["timestep"] = {"missing": True, "pass": False}

    for degrees in (5, 10, 15, 20):
        loaded = get(f"slope{degrees}")
        tests[f"slope{degrees}"] = analyze_slope(loaded[0]) if loaded else {"missing": True}
    for height in (10, 25, 50):
        loaded = get(f"obstacle{height}")
        tests[f"obstacle{height}"] = (
            analyze_obstacle(loaded[0], height) if loaded else {"missing": True}
        )

    for group in ("det", "rt"):
        ends = [analyze_straight(d[0]) for i in range(1, 6) if (d := get(f"repeat_{group}{i}"))]
        tests[f"repeat_{group}"] = (
            {
                "runs": len(ends),
                "end_x_cm": spread([e["end_x_cm"] for e in ends]),
                "end_y_cm": spread([e["end_y_cm"] for e in ends]),
                "end_yaw_deg": spread([e["end_yaw_deg"] for e in ends]),
            }
            if ends
            else {"missing": True}
        )

    loaded = get("stability")
    tests["stability"] = analyze_stability(*loaded) if loaded else {"missing": True, "pass": False}
    loaded = get("perf")
    tests["perf"] = (
        {
            **frame_stats(loaded[0]),
            **{k: runs["perf"][k] for k in ("peak_rss_mb", "min_free_percent")},
        }
        if loaded
        else {"missing": True}
    )

    gate = ["probe", "freefall", "static", "straight_fps60", "turn_fps60", "timestep", "stability"]
    result["r0_gate"] = {name: bool(tests[name].get("pass")) for name in gate}
    result["r0_pass"] = all(result["r0_gate"].values())
    (out_dir / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"r0_gate": result["r0_gate"], "r0_pass": result["r0_pass"]}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run the R0 plan, or some of its runs")
    run.add_argument("plan", choices=["r0"])
    run.add_argument("--batch", required=True)
    run.add_argument("--only", nargs="*", help="Run names to include")
    analyze = sub.add_parser("analyze", help="Judge a batch against the fixed thresholds")
    analyze.add_argument("--batch", required=True)
    args = parser.parse_args()
    return command_run(args) if args.command == "run" else command_analyze(args)


if __name__ == "__main__":
    sys.exit(main())
