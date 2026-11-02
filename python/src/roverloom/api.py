"""Typed messages shared by agents, simulators, and logs.

Action, Observation, and MissionBrief are all an agent ever sees. RoverState and
MissionState are ground truth and must never be passed to an agent.
"""

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from roverloom.contract import ContractError, JsonDict, validate

SCHEMA_VERSION = 0
WHEEL_IDS = (
    "front_left",
    "front_right",
    "middle_left",
    "middle_right",
    "rear_left",
    "rear_right",
)
# Random faults choose among these, so that all rovers draw the same fault for a seed.
CANONICAL_WHEELS = WHEEL_IDS


def _round(value: float) -> float:
    # Rounding keeps logs compact and hides insignificant floating point noise.
    rounded = round(value, 6)
    return rounded + 0.0  # Normalizes -0.0.


def wrap_angle(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


@dataclass(frozen=True, slots=True)
class Pose:
    """Position in the site frame (+X east, +Y north, +Z up) and heading about +Z."""

    x_m: float
    y_m: float
    z_m: float
    yaw_rad: float

    def to_dict(self) -> JsonDict:
        half = self.yaw_rad / 2.0
        return {
            "position_m": [_round(self.x_m), _round(self.y_m), _round(self.z_m)],
            "orientation_xyzw": [0.0, 0.0, _round(math.sin(half)), _round(math.cos(half))],
        }

    @classmethod
    def from_dict(cls, data: JsonDict) -> "Pose":
        x, y, z = data["position_m"]
        qx, qy, qz, qw = data["orientation_xyzw"]
        norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
        if not 0.99 < norm < 1.01:
            raise ContractError(f"orientation is not a unit quaternion: norm {norm:.4f}")
        yaw = math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))
        return cls(float(x), float(y), float(z), yaw)


@dataclass(frozen=True, slots=True)
class TaskRequest:
    """Ask the rover to run a task. Executed on the rover, subject to its checks."""

    type: str
    target_id: str | None = None

    def to_dict(self) -> JsonDict:
        data: JsonDict = {"type": self.type}
        if self.target_id is not None:
            data["target_id"] = self.target_id
        return data


@dataclass(frozen=True, slots=True)
class Action:
    """Body-frame drive command. Positive yaw rate turns left."""

    linear_velocity_mps: float
    yaw_rate_radps: float
    task: TaskRequest | None = None

    def __post_init__(self) -> None:
        if not (math.isfinite(self.linear_velocity_mps) and math.isfinite(self.yaw_rate_radps)):
            raise ContractError("action values must be finite")

    def to_dict(self) -> JsonDict:
        data: JsonDict = {
            "schema_version": SCHEMA_VERSION,
            "linear_velocity_mps": _round(self.linear_velocity_mps),
            "yaw_rate_radps": _round(self.yaw_rate_radps),
        }
        if self.task is not None:
            data["task"] = self.task.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Any) -> "Action":
        validate("action", data)
        task = data.get("task")
        request = TaskRequest(task["type"], task.get("target_id")) if task else None
        return cls(data["linear_velocity_mps"], data["yaw_rate_radps"], request)


STOP = Action(0.0, 0.0)


@dataclass(frozen=True, slots=True)
class RangeReading:
    bearing_rad: float
    range_m: float | None


@dataclass(frozen=True, slots=True)
class TaskResult:
    type: str
    target_id: str | None
    status: str
    reason: str | None
    time_s: float


@dataclass(frozen=True, slots=True)
class ScienceStatus:
    """What the rover knows about its science work. Values appear only after inspection."""

    active_task: str | None
    task_progress: float
    inspected: tuple[tuple[str, float], ...]
    collected: tuple[str, ...]
    stored_items: int
    stored_value: float
    transmitted_value: float
    data_window_open: bool
    last_result: TaskResult | None

    def to_dict(self) -> JsonDict:
        last = self.last_result
        return {
            "active_task": self.active_task,
            "task_progress": self.task_progress,
            "inspected": dict(self.inspected),
            "collected": list(self.collected),
            "stored_items": self.stored_items,
            "stored_value": self.stored_value,
            "transmitted_value": self.transmitted_value,
            "data_window_open": self.data_window_open,
            "last_result": None
            if last is None
            else {
                "type": last.type,
                "target_id": last.target_id,
                "status": last.status,
                "reason": last.reason,
                "time_s": last.time_s,
            },
        }

    @classmethod
    def from_dict(cls, data: JsonDict) -> "ScienceStatus":
        last = data["last_result"]
        return cls(
            active_task=data["active_task"],
            task_progress=data["task_progress"],
            inspected=tuple(sorted(data["inspected"].items())),
            collected=tuple(data["collected"]),
            stored_items=data["stored_items"],
            stored_value=data["stored_value"],
            transmitted_value=data["transmitted_value"],
            data_window_open=data["data_window_open"],
            last_result=None
            if last is None
            else TaskResult(
                last["type"], last["target_id"], last["status"], last["reason"], last["time_s"]
            ),
        )


@dataclass(frozen=True, slots=True)
class Observation:
    """What the rover can sense, possibly stale and noisy when it reaches the agent."""

    time_s: float
    estimated_pose: Pose
    battery_fraction: float
    estimated_speed_mps: float
    targets_reached: int
    range_scan: tuple[RangeReading, ...] = ()
    measured_power_w: float = 0.0
    science: ScienceStatus | None = None

    def to_dict(self) -> JsonDict:
        data: JsonDict = {
            "schema_version": SCHEMA_VERSION,
            "time_s": _round(self.time_s),
            "estimated_pose": self.estimated_pose.to_dict(),
            "battery_fraction": _round(self.battery_fraction),
            "estimated_speed_mps": _round(self.estimated_speed_mps),
            "targets_reached": self.targets_reached,
            "range_scan": [
                {
                    "bearing_rad": _round(r.bearing_rad),
                    "range_m": None if r.range_m is None else _round(r.range_m),
                }
                for r in self.range_scan
            ],
            "measured_power_w": _round(self.measured_power_w),
        }
        if self.science is not None:
            data["science"] = self.science.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Any) -> "Observation":
        validate("observation", data)
        return cls(
            time_s=data["time_s"],
            estimated_pose=Pose.from_dict(data["estimated_pose"]),
            battery_fraction=data["battery_fraction"],
            estimated_speed_mps=data.get("estimated_speed_mps", 0.0),
            targets_reached=data.get("targets_reached", 0),
            range_scan=tuple(
                RangeReading(r["bearing_rad"], r["range_m"]) for r in data.get("range_scan", [])
            ),
            measured_power_w=data.get("measured_power_w", 0.0),
            science=ScienceStatus.from_dict(data["science"]) if "science" in data else None,
        )


@dataclass(frozen=True, slots=True)
class Target:
    x_m: float
    y_m: float
    radius_m: float


@dataclass(frozen=True, slots=True)
class ScienceTarget:
    """A site as an agent knows it. The true value is learned by inspecting."""

    id: str
    x_m: float
    y_m: float
    radius_m: float
    prior_value: float
    inspect_s: float
    collect_s: float


@dataclass(frozen=True, slots=True)
class BaseSite:
    x_m: float
    y_m: float
    radius_m: float
    required: bool


@dataclass(frozen=True, slots=True)
class DataWindows:
    period_s: float
    open_s: float
    offset_s: float

    def is_open(self, time_s: float) -> bool:
        phase = (time_s - self.offset_s) % self.period_s
        return time_s >= self.offset_s and phase < self.open_s


@dataclass(frozen=True, slots=True)
class DeclaredUncertainty:
    """What a mission claims about its sensor errors. The claim may be wrong."""

    inspection_noise_sd: float
    pose_noise_m: float


@dataclass(frozen=True, slots=True)
class MissionBrief:
    """Everything an agent may know before the mission starts."""

    mission_id: str
    start_pose: Pose
    targets: tuple[Target, ...]
    time_limit_s: float
    energy_limit_wh: float | None
    control_period_s: float
    max_speed_mps: float
    max_yaw_rate_radps: float
    body_radius_m: float
    sensor_max_range_m: float
    extent_min_xy: tuple[float, float]
    extent_max_xy: tuple[float, float]
    science_targets: tuple[ScienceTarget, ...] = ()
    base: BaseSite | None = None
    data_windows: DataWindows | None = None
    transmit_s_per_item: float | None = None
    success_value: float | None = None
    can_collect: bool = True
    battery_capacity_wh: float = 0.0
    declared_uncertainty: DeclaredUncertainty | None = None

    def to_dict(self) -> JsonDict:
        data: JsonDict = {
            "schema_version": SCHEMA_VERSION,
            "mission_id": self.mission_id,
            "start_pose": self.start_pose.to_dict(),
            "targets": [
                {"position_m": [t.x_m, t.y_m, 0.0], "radius_m": t.radius_m} for t in self.targets
            ],
            "time_limit_s": self.time_limit_s,
            "energy_limit_wh": self.energy_limit_wh,
            "control_period_s": self.control_period_s,
            "max_speed_mps": self.max_speed_mps,
            "max_yaw_rate_radps": self.max_yaw_rate_radps,
            "body_radius_m": self.body_radius_m,
            "sensor_max_range_m": self.sensor_max_range_m,
            "extent_min_xy": list(self.extent_min_xy),
            "extent_max_xy": list(self.extent_max_xy),
            "battery_capacity_wh": self.battery_capacity_wh,
        }
        if not self.can_collect:
            data["can_collect"] = False
        if self.declared_uncertainty is not None:
            data["declared_uncertainty"] = {
                "inspection_noise_sd": self.declared_uncertainty.inspection_noise_sd,
                "pose_noise_m": self.declared_uncertainty.pose_noise_m,
            }
        if self.science_targets:
            windows, base = self.data_windows, self.base
            data["science_targets"] = [
                {
                    "id": t.id,
                    "position_m": [t.x_m, t.y_m, 0.0],
                    "radius_m": t.radius_m,
                    "prior_value": t.prior_value,
                    "inspect_s": t.inspect_s,
                    "collect_s": t.collect_s,
                }
                for t in self.science_targets
            ]
            data["base"] = (
                None
                if base is None
                else {
                    "position_m": [base.x_m, base.y_m, 0.0],
                    "radius_m": base.radius_m,
                    "required": base.required,
                }
            )
            data["data_windows"] = (
                None
                if windows is None
                else {
                    "period_s": windows.period_s,
                    "open_s": windows.open_s,
                    "offset_s": windows.offset_s,
                }
            )
            data["transmit_s_per_item"] = self.transmit_s_per_item
            data["success_value"] = self.success_value
        return data

    @classmethod
    def from_dict(cls, data: Any) -> "MissionBrief":
        validate("mission_brief", data)
        return cls(
            mission_id=data["mission_id"],
            start_pose=Pose.from_dict(data["start_pose"]),
            targets=tuple(
                Target(t["position_m"][0], t["position_m"][1], t["radius_m"])
                for t in data["targets"]
            ),
            time_limit_s=data["time_limit_s"],
            energy_limit_wh=data["energy_limit_wh"],
            control_period_s=data["control_period_s"],
            max_speed_mps=data["max_speed_mps"],
            max_yaw_rate_radps=data["max_yaw_rate_radps"],
            body_radius_m=data["body_radius_m"],
            sensor_max_range_m=data["sensor_max_range_m"],
            extent_min_xy=(data["extent_min_xy"][0], data["extent_min_xy"][1]),
            extent_max_xy=(data["extent_max_xy"][0], data["extent_max_xy"][1]),
            science_targets=tuple(
                ScienceTarget(
                    t["id"],
                    t["position_m"][0],
                    t["position_m"][1],
                    t["radius_m"],
                    t["prior_value"],
                    t["inspect_s"],
                    t["collect_s"],
                )
                for t in data.get("science_targets", [])
            ),
            base=BaseSite(
                base["position_m"][0], base["position_m"][1], base["radius_m"], base["required"]
            )
            if (base := data.get("base"))
            else None,
            data_windows=DataWindows(windows["period_s"], windows["open_s"], windows["offset_s"])
            if (windows := data.get("data_windows"))
            else None,
            transmit_s_per_item=data.get("transmit_s_per_item"),
            success_value=data.get("success_value"),
            can_collect=data.get("can_collect", True),
            battery_capacity_wh=data.get("battery_capacity_wh", 0.0),
            declared_uncertainty=DeclaredUncertainty(
                declared["inspection_noise_sd"], declared["pose_noise_m"]
            )
            if (declared := data.get("declared_uncertainty"))
            else None,
        )


@dataclass(slots=True)
class RoverState:
    """Ground truth. Agents must never receive this."""

    pose: Pose
    wheel_speed_mps: float = 0.0
    ground_speed_mps: float = 0.0
    yaw_rate_radps: float = 0.0
    slip_fraction: float = 0.0
    battery_wh: float = 0.0
    energy_used_wh: float = 0.0
    distance_m: float = 0.0
    power_generation_w: float = 0.0
    failed_wheels: frozenset[str] = frozenset()


class MissionOutcome(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    TIME_LIMIT = "time_limit"
    BATTERY_DEPLETED = "battery_depleted"
    ENERGY_LIMIT = "energy_limit"
    ENDED_EARLY = "ended_early"
    AGENT_ERROR = "agent_error"
    ABORTED = "aborted"


@dataclass(slots=True)
class MissionState:
    """Ground truth mission progress. Agents only see targets_reached."""

    targets_total: int
    targets_reached: int = 0
    outcome: MissionOutcome = MissionOutcome.RUNNING
    active_faults: list[str] = field(default_factory=list)

    @property
    def finished(self) -> bool:
        return self.outcome is not MissionOutcome.RUNNING
