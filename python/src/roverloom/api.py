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
class Action:
    """Body-frame drive command. Positive yaw rate turns left."""

    linear_velocity_mps: float
    yaw_rate_radps: float

    def __post_init__(self) -> None:
        if not (math.isfinite(self.linear_velocity_mps) and math.isfinite(self.yaw_rate_radps)):
            raise ContractError("action values must be finite")

    def to_dict(self) -> JsonDict:
        return {
            "schema_version": SCHEMA_VERSION,
            "linear_velocity_mps": _round(self.linear_velocity_mps),
            "yaw_rate_radps": _round(self.yaw_rate_radps),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Action":
        validate("action", data)
        return cls(data["linear_velocity_mps"], data["yaw_rate_radps"])


STOP = Action(0.0, 0.0)


@dataclass(frozen=True, slots=True)
class RangeReading:
    bearing_rad: float
    range_m: float | None


@dataclass(frozen=True, slots=True)
class Observation:
    """What the rover can sense, possibly stale and noisy when it reaches the agent."""

    time_s: float
    estimated_pose: Pose
    battery_fraction: float
    estimated_speed_mps: float
    targets_reached: int
    range_scan: tuple[RangeReading, ...] = ()

    def to_dict(self) -> JsonDict:
        return {
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
        }

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
        )


@dataclass(frozen=True, slots=True)
class Target:
    x_m: float
    y_m: float
    radius_m: float


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

    def to_dict(self) -> JsonDict:
        return {
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
        }

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
    failed_wheels: frozenset[str] = frozenset()


class MissionOutcome(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    TIME_LIMIT = "time_limit"
    BATTERY_DEPLETED = "battery_depleted"
    ENERGY_LIMIT = "energy_limit"
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
