"""Scores runs from their log files alone, so that any backend is scored by the same code."""

import math
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

from roverloom.contract import JsonDict
from roverloom.runlog import LoadedRun

RECOVERY_DISTANCE_M = 1.0
COLLISION_PENALTY = 2.0


@dataclass(frozen=True, slots=True)
class Metrics:
    outcome: str
    success: bool
    targets_reached: int
    targets_total: int
    mission_time_s: float
    distance_m: float
    energy_used_wh: float
    collisions: int
    faults: int
    faults_recovered: int
    mean_recovery_time_s: float | None
    score: float

    def to_dict(self) -> JsonDict:
        return asdict(self)


def _cumulative_distance(telemetry: Sequence[JsonDict]) -> list[float]:
    total, cumulative, last = 0.0, [], None
    for record in telemetry:
        x, y, _ = record["pose"]["position_m"]
        if last is not None:
            total += math.hypot(x - last[0], y - last[1])
        cumulative.append(total)
        last = (x, y)
    return cumulative


def _score(
    success: bool,
    reached: int,
    total: int,
    time_s: float,
    time_limit: float,
    energy: float,
    energy_budget: float,
    collisions: int,
) -> float:
    """Score out of 100: completion first, then efficiency, minus a penalty per collision."""
    base = 60.0 * reached / total
    if success:
        base += 20.0 * max(0.0, 1.0 - time_s / time_limit)
        base += 20.0 * max(0.0, 1.0 - energy / energy_budget)
    return round(max(0.0, base - COLLISION_PENALTY * collisions), 3)


def evaluate_run(run: LoadedRun) -> Metrics:
    telemetry, events = run.telemetry, run.events
    ended = events[-1]["data"]
    scenario = run.scenario
    distances = _cumulative_distance(telemetry)
    times = [record["time_s"] for record in telemetry]

    # A fault counts as recovered once the rover travels again after it. Permanent faults
    # are measured from when they start, and temporary ones from when they end.
    durations: list[float] = []
    faults = recovered = 0
    for event in events:
        if event["type"] != "fault_started":
            continue
        faults += 1
        duration = event["data"].get("duration_s", 0.0)
        reference = event["time_s"] + duration
        start = next((i for i, t in enumerate(times) if t >= reference), None)
        if start is None:
            continue
        for index in range(start, len(times)):
            if distances[index] - distances[start] >= RECOVERY_DISTANCE_M:
                recovered += 1
                durations.append(times[index] - reference)
                break

    time_s = events[-1]["time_s"]
    energy = telemetry[-1]["energy_used_wh"] if telemetry else 0.0
    collisions = sum(1 for event in events if event["type"] == "collision")
    success = ended["outcome"] == "success"
    budget = scenario.mission.get("energy_limit_wh") or scenario.rover.battery_capacity_wh
    return Metrics(
        outcome=ended["outcome"],
        success=success,
        targets_reached=ended["targets_reached"],
        targets_total=len(scenario.targets),
        mission_time_s=round(time_s, 3),
        distance_m=round(distances[-1] if distances else 0.0, 3),
        energy_used_wh=round(energy, 3),
        collisions=collisions,
        faults=faults,
        faults_recovered=recovered,
        mean_recovery_time_s=round(sum(durations) / len(durations), 3) if durations else None,
        score=_score(
            success,
            ended["targets_reached"],
            len(scenario.targets),
            time_s,
            float(scenario.mission["time_limit_s"]),
            energy,
            float(budget),
            collisions,
        ),
    )


def _mean(values: Iterable[float]) -> float | None:
    items = list(values)
    return round(sum(items) / len(items), 3) if items else None


def aggregate(metrics: Sequence[Metrics]) -> JsonDict:
    """Summarize repeated runs. Time and energy use only successful runs, when there are any."""
    if not metrics:
        return {"runs": 0}
    wins = [m for m in metrics if m.success]
    faults = sum(m.faults for m in metrics)
    return {
        "runs": len(metrics),
        "success_rate": round(len(wins) / len(metrics), 3),
        "mean_score": _mean(m.score for m in metrics),
        "mean_success_time_s": _mean(m.mission_time_s for m in wins),
        "mean_distance_m": _mean(m.distance_m for m in metrics),
        "mean_success_energy_wh": _mean(m.energy_used_wh for m in wins),
        "mean_collisions": _mean(float(m.collisions) for m in metrics),
        "fault_recovery_rate": (
            round(sum(m.faults_recovered for m in metrics) / faults, 3) if faults else None
        ),
    }
