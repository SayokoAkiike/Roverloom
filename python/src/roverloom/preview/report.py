"""Builds a self-contained HTML report: comparison table plus replay of every run."""

import json
import math
from collections.abc import Sequence
from pathlib import Path

from roverloom.contract import JsonDict
from roverloom.evaluate import evaluate_run
from roverloom.runlog import LoadedRun
from roverloom.world import Scenario

_GRID_LIMIT = 110
_REPLAY_EVERY = 5  # Telemetry is 10 Hz; 2 Hz keeps reports small and is smooth when interpolated.


def world_payload(scenario: Scenario) -> JsonDict:
    terrain = scenario.terrain
    stride = max(1, max(terrain.nx, terrain.ny) // _GRID_LIMIT)
    rows = [[round(value, 2) for value in row[::stride]] for row in terrain.heights[::stride]]
    return {
        "scenario_id": scenario.scenario_id,
        "terrain_id": terrain.terrain_id,
        "terrain_note": terrain.document["source"]["note"],
        "extent": [terrain.min_x, terrain.min_y, terrain.max_x, terrain.max_y],
        "grid": rows,
        "grid_spacing": terrain.spacing * stride,
        "rocks": [[round(r.x_m, 2), round(r.y_m, 2), round(r.radius_m, 2)] for r in terrain.rocks],
        "soil": [[a.x_m, a.y_m, a.radius_m, slip] for a, slip in terrain.soft_soil],
        "targets": [[t.x_m, t.y_m, t.radius_m] for t in scenario.targets],
        "science": _science_payload(scenario),
        "rover_id": scenario.rover.rover_id,
        "rover_radius": scenario.rover.body_radius_m,
        "max_speed": scenario.rover.max_speed_mps,
        "max_yaw": scenario.rover.max_yaw_rate_radps,
        "time_limit": scenario.mission["time_limit_s"],
    }


def _science_payload(scenario: Scenario) -> JsonDict | None:
    """Sites for display. Leaves out true values, so that a shared page does not spoil them."""
    science = scenario.mission.get("science")
    if science is None:
        return None
    return {
        "targets": [
            {
                "id": t["id"],
                "x": t["position_m"][0],
                "y": t["position_m"][1],
                "radius": t["radius_m"],
                "prior": t["prior_value"],
            }
            for t in science["targets"]
        ],
        "base": science.get("base"),
        "windows": science.get("data_windows"),
        "success_value": science["success_value"],
    }


def _sample(record: JsonDict) -> list[float]:
    qz, qw = record["pose"]["orientation_xyzw"][2:]
    x, y, _ = record["pose"]["position_m"]
    vx, vy, _ = record["linear_velocity_mps"]
    return [
        record["time_s"],
        x,
        y,
        round(2.0 * math.atan2(qz, qw), 4),
        round((vx * vx + vy * vy) ** 0.5, 3),
        record["battery_fraction"],
        record["energy_used_wh"],
        record.get("slip_fraction", 0.0),
        record.get("science_value", 0.0),
        record.get("stored_value", 0.0),
        record.get("power_generation_w", 0.0),
        1 if record.get("data_window_open", True) else 0,
    ]


def run_payload(key: tuple[str, str, int], run: LoadedRun) -> JsonDict:
    records = run.telemetry[::_REPLAY_EVERY]
    if run.telemetry and records[-1] is not run.telemetry[-1]:
        records.append(run.telemetry[-1])
    return {
        "scenario": key[0],
        "agent": key[1],
        "seed": key[2],
        "samples": [_sample(record) for record in records],
        "events": [
            {"t": event["time_s"], "type": event["type"], "data": event["data"]}
            for event in run.events
        ],
        "decisions": [{"t": d["time_s"], "text": d["text"]} for d in run.decisions],
        "rover": run.manifest.get("rover_id", ""),
        "metrics": evaluate_run(run).to_dict(),
        "model": run.manifest["model_version"],
    }


def viewer_html(data: JsonDict) -> str:
    template = (Path(__file__).parent / "viewer.html").read_text(encoding="utf-8")
    # Escaping "<" keeps embedded strings from ever closing the script element.
    payload = json.dumps(data, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    return template.replace("/*ROVERLOOM_DATA*/null", payload)


def write_report(
    rows: Sequence[JsonDict], runs: Sequence[tuple[tuple[str, str, int], LoadedRun]], path: Path
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report_html(rows, runs), encoding="utf-8", newline="\n")
    return path.resolve()


def report_html(
    rows: Sequence[JsonDict], runs: Sequence[tuple[tuple[str, str, int], LoadedRun]]
) -> str:
    worlds: dict[str, JsonDict] = {}
    for key, run in runs:
        worlds.setdefault(key[0], world_payload(run.scenario))
    data: JsonDict = {
        "mode": "report",
        "comparison": list(rows),
        "worlds": worlds,
        "runs": [run_payload(key, run) for key, run in runs],
    }
    return viewer_html(data)
