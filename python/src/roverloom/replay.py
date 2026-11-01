"""Plays back a run from its logs. Kinematic only: no physics is re-simulated."""

import bisect
from dataclasses import dataclass

from roverloom.api import Pose, wrap_angle
from roverloom.contract import ContractError, JsonDict
from roverloom.runlog import LoadedRun


@dataclass(frozen=True, slots=True)
class ReplayFrame:
    time_s: float
    pose: Pose
    battery_fraction: float
    energy_used_wh: float
    targets_reached: int
    failed_wheels: tuple[str, ...]


class Replay:
    def __init__(self, run: LoadedRun) -> None:
        if not run.telemetry:
            raise ContractError(f"{run.directory}: no telemetry to replay")
        self._records = run.telemetry
        self._times = [record["time_s"] for record in run.telemetry]
        self._events = run.events

    @property
    def duration_s(self) -> float:
        return float(self._times[-1])

    def frame_at(self, time_s: float) -> ReplayFrame:
        """Interpolate pose between records. Times outside the run are clamped to its ends."""
        index = bisect.bisect_left(self._times, time_s)
        if index <= 0:
            return _frame(self._records[0], self._records[0], 0.0, self._times[0])
        if index >= len(self._records):
            return _frame(self._records[-1], self._records[-1], 0.0, self._times[-1])
        before, after = self._records[index - 1], self._records[index]
        span = after["time_s"] - before["time_s"]
        fraction = (time_s - before["time_s"]) / span if span > 0 else 0.0
        return _frame(before, after, fraction, time_s)

    def events_until(self, time_s: float) -> list[JsonDict]:
        return [event for event in self._events if event["time_s"] <= time_s]


def _frame(before: JsonDict, after: JsonDict, fraction: float, time_s: float) -> ReplayFrame:
    start = Pose.from_dict(before["pose"])
    end = Pose.from_dict(after["pose"])
    return ReplayFrame(
        time_s=time_s,
        pose=Pose(
            start.x_m + (end.x_m - start.x_m) * fraction,
            start.y_m + (end.y_m - start.y_m) * fraction,
            start.z_m + (end.z_m - start.z_m) * fraction,
            wrap_angle(start.yaw_rad + wrap_angle(end.yaw_rad - start.yaw_rad) * fraction),
        ),
        battery_fraction=before["battery_fraction"],
        energy_used_wh=before["energy_used_wh"],
        targets_reached=before.get("targets_reached", 0),
        failed_wheels=tuple(before.get("failed_wheels", ())),
    )
