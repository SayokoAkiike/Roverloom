"""Lightweight rover, fault, sensor, and communications models.

These are simple game and early-research approximations. They are not validated against any
rover or against terramechanics. See docs/lightweight-models.md.
"""

import math
import random
from collections import deque
from dataclasses import dataclass

from roverloom.api import (
    CANONICAL_WHEELS,
    WHEEL_IDS,
    Action,
    Observation,
    Pose,
    RangeReading,
    RoverState,
    ScienceStatus,
    wrap_angle,
)
from roverloom.contract import JsonDict
from roverloom.world import Scenario

_LEFT = {"front_left", "middle_left", "middle2_left", "rear_left"}
# A fault on a wheel the rover does not have falls on the nearest wheel on the same side.
_WHEEL_FALLBACK = {
    "middle_left": "rear_left",
    "middle_right": "rear_right",
    "middle2_left": "rear_left",
    "middle2_right": "rear_right",
}


def map_wheel(wheel: str, wheels: tuple[str, ...]) -> str:
    return wheel if wheel in wheels else _WHEEL_FALLBACK[wheel]


@dataclass(frozen=True, slots=True)
class Effects:
    """How active environment events and tasks change the rover this step."""

    extra_slip: float = 0.0
    immobilized: bool = False
    solar_scale: float = 1.0
    extra_load_w: float = 0.0
    task_power_w: float = 0.0


NO_EFFECTS = Effects()


@dataclass(frozen=True, slots=True)
class Fault:
    type: str
    start_time_s: float
    duration_s: float | None = None
    wheel: str | None = None
    severity: float = 1.0
    category: str | None = None

    @property
    def end_time_s(self) -> float | None:
        return None if self.duration_s is None else self.start_time_s + self.duration_s

    def to_dict(self) -> JsonDict:
        data: JsonDict = {"fault": self.type}
        if self.duration_s is not None:
            data["duration_s"] = self.duration_s
        if self.wheel is not None:
            data["wheel"] = self.wheel
        if self.severity != 1.0:
            data["severity"] = self.severity
        if self.category is not None:
            data["category"] = self.category
        return data


def build_fault_schedule(scenario: Scenario, seed: int) -> list[Fault]:
    """Combine fixed faults with seeded random faults.

    The schedule is drawn before the mission, so it depends only on the scenario and seed.
    Every agent therefore faces the same faults for a given seed.
    """
    document = scenario.document
    faults = [
        Fault(
            f["type"],
            float(f["start_time_s"]),
            f.get("duration_s"),
            f.get("wheel"),
            f.get("severity", 1.0),
            f.get("category"),
        )
        for f in document["faults"]
    ]
    limit = float(scenario.mission["time_limit_s"])
    for index, generator in enumerate(document.get("fault_generators", [])):
        rng = random.Random(f"faults:{seed}:{index}")
        time_s, count = 0.0, 0
        max_count = generator.get("max_count", 1_000_000)
        while count < max_count:
            time_s += rng.expovariate(generator["rate_per_hour"] / 3600.0)
            if time_s >= limit:
                break
            wheel = (
                rng.choice(CANONICAL_WHEELS) if generator["type"] == "wheel_drive_failure" else None
            )
            duration = (
                None
                if generator["type"] == "wheel_drive_failure"
                else float(generator.get("duration_s", 10.0))
            )
            faults.append(
                Fault(
                    generator["type"],
                    time_s,
                    duration,
                    wheel,
                    generator.get("severity", 1.0),
                    generator.get("category"),
                )
            )
            count += 1
    return sorted(faults, key=lambda f: (f.start_time_s, f.type, f.wheel or ""))


class CommLink[T]:
    """One-way link with fixed latency, random loss, and blackout handling."""

    def __init__(self, latency_s: float, loss_probability: float, rng: random.Random) -> None:
        self._latency = latency_s
        self._loss = loss_probability
        self._rng = rng
        self._queue: deque[tuple[float, T]] = deque()

    def send(self, now: float, message: T, blackout: bool) -> bool:
        # The draw always happens, so a blackout does not shift later losses.
        lost = self._rng.random() < self._loss
        if blackout or lost:
            return False
        self._queue.append((now + self._latency, message))
        return True

    def receive(self, now: float, blackout: bool) -> list[T]:
        delivered: list[T] = []
        while self._queue and self._queue[0][0] <= now + 1e-9:
            _, message = self._queue.popleft()
            if not blackout:  # Messages arriving during a blackout are lost.
                delivered.append(message)
        return delivered


class RoverSim:
    """Advances the true rover state one fixed step at a time."""

    def __init__(self, scenario: Scenario, seed: int) -> None:
        self._terrain = scenario.terrain
        self._spec = scenario.rover
        self._gravity = float(scenario.document["environment"]["gravity_mps2"])
        self._rng = random.Random(f"slip:{seed}")
        self.state = RoverState(
            pose=scenario.start_pose,
            battery_wh=float(self._spec.battery_capacity_wh),
        )
        document = self._spec.document
        self._wheels: tuple[str, ...] = tuple(document.get("wheels", WHEEL_IDS))
        self._soil_scale = float(document.get("soil_slip_scale", 1.0))
        self._solar_w = float(document.get("solar_panel_w", 0.0))
        self._rtg_w = float(document.get("rtg_w", 0.0))
        self._solar_factor = float(scenario.document["environment"].get("solar_factor", 1.0))

    def fail_wheel(self, wheel: str) -> None:
        self.state.failed_wheels = self.state.failed_wheels | {map_wheel(wheel, self._wheels)}

    def step(self, action: Action, dt: float, effects: Effects = NO_EFFECTS) -> bool:
        """Advance one step, and return True if the rover hit a rock or the boundary."""
        state, spec = self.state, self._spec
        pose = state.pose
        failed = state.failed_wheels
        capacity = 1.0 - len(failed) / len(self._wheels)
        slope = self._terrain.slope_along(pose.x_m, pose.y_m, pose.yaw_rad)

        # Motor limits: lost wheels and uphill slopes reduce the reachable speed.
        climb_margin = 1.0 - max(slope, 0.0) / spec.max_climb_slope
        speed_limit = spec.max_speed_mps * capacity * max(climb_margin, 0.0)
        target = max(-speed_limit, min(speed_limit, action.linear_velocity_mps))
        delta = spec.max_accel_mps2 * dt
        wheel_speed = state.wheel_speed_mps + max(
            -delta, min(delta, target - state.wheel_speed_mps)
        )

        # An unbalanced drive pulls the rover toward the side with failed wheels.
        left = sum(1 for wheel in failed if wheel in _LEFT)
        right = len(failed) - left
        bias = spec.failed_wheel_yaw_bias_radps * (left - right) * abs(wheel_speed)
        yaw_target = action.yaw_rate_radps * capacity + bias
        yaw_delta = spec.max_yaw_accel_radps2 * dt
        yaw_rate = state.yaw_rate_radps + max(
            -yaw_delta, min(yaw_delta, yaw_target - state.yaw_rate_radps)
        )

        # Empirical slip: soil, slope magnitude, and a small random term.
        soil = max(
            spec.base_slip_fraction,
            self._terrain.soil_slip_at(pose.x_m, pose.y_m) * self._soil_scale,
        )
        slip = soil + spec.slope_slip_factor * abs(slope) + self._rng.gauss(0.0, spec.slip_noise)
        slip = max(0.0, min(0.95, slip + effects.extra_slip))
        if effects.immobilized:
            slip = 1.0  # The wheels turn but the rover does not move.
        ground_speed = wheel_speed * (1.0 - slip)

        yaw_mid = pose.yaw_rad + yaw_rate * dt / 2.0
        x = pose.x_m + ground_speed * math.cos(yaw_mid) * dt
        y = pose.y_m + ground_speed * math.sin(yaw_mid) * dt
        yaw = wrap_angle(pose.yaw_rad + yaw_rate * dt)

        radius = spec.body_radius_m
        hit = not self._terrain.in_bounds(x, y, radius) or self._terrain.collides(x, y, radius)
        if hit:
            x, y = pose.x_m, pose.y_m
            wheel_speed = ground_speed = 0.0

        # Power: idle load plus resistance and climbing at the wheels, plus turning.
        grade_force = self._spec.mass_kg * self._gravity * (spec.rolling_resistance + slope)
        drive_power = max(grade_force, 0.0) * abs(wheel_speed) / spec.drive_efficiency
        power = spec.idle_power_w + drive_power + spec.turn_power_w_per_radps * abs(yaw_rate)
        power += effects.extra_load_w + effects.task_power_w
        energy = power * dt / 3600.0
        generation = self._rtg_w + self._solar_w * self._solar_factor * effects.solar_scale

        state.distance_m += math.hypot(x - pose.x_m, y - pose.y_m)
        state.pose = Pose(x, y, self._terrain.height_at(x, y), yaw)
        state.wheel_speed_mps = wheel_speed
        state.ground_speed_mps = ground_speed
        state.yaw_rate_radps = yaw_rate
        state.slip_fraction = slip
        state.power_generation_w = generation
        state.battery_wh = max(
            0.0,
            min(
                float(spec.battery_capacity_wh),
                state.battery_wh - energy + generation * dt / 3600.0,
            ),
        )
        state.energy_used_wh += energy
        return hit


class Sensors:
    """Turns ground truth into a noisy Observation. The only path from truth to agents."""

    def __init__(self, scenario: Scenario, seed: int) -> None:
        self._terrain = scenario.terrain
        self._capacity = float(scenario.rover.battery_capacity_wh)
        sensor = scenario.rover.range_sensor
        self._bearings: list[float] = sensor["bearings_rad"]
        self._max_range: float = sensor["max_range_m"]
        self._noise: JsonDict = scenario.document.get(
            "sensors",
            {
                "pose_noise_m": 0.0,
                "yaw_noise_rad": 0.0,
                "speed_noise_mps": 0.0,
                "range_noise_m": 0.0,
            },
        )
        self._rng = random.Random(f"sensors:{seed}")
        self._pose_scale = float(scenario.rover.document.get("pose_noise_scale", 1.0))
        uncertainty = scenario.document.get("uncertainty", {})
        self._pose_bias: tuple[float, float] = tuple(uncertainty.get("pose_bias_m", (0.0, 0.0)))
        self._range_bias = float(uncertainty.get("range_bias_m", 0.0))

    def observe(
        self,
        time_s: float,
        state: RoverState,
        targets_reached: int,
        range_available: bool,
        range_scale: float = 1.0,
        noise_scale: float = 1.0,
        science: ScienceStatus | None = None,
    ) -> Observation:
        rng, pose = self._rng, state.pose
        pose_scale = noise_scale * self._pose_scale
        noise = {
            "pose_noise_m": self._noise["pose_noise_m"] * pose_scale,
            "yaw_noise_rad": self._noise["yaw_noise_rad"] * pose_scale,
            "speed_noise_mps": self._noise["speed_noise_mps"] * noise_scale,
            "range_noise_m": self._noise["range_noise_m"] * noise_scale,
        }
        # Every random draw happens regardless of faults, so draws stay aligned between runs.
        estimated = Pose(
            pose.x_m + self._pose_bias[0] + rng.gauss(0.0, noise["pose_noise_m"]),
            pose.y_m + self._pose_bias[1] + rng.gauss(0.0, noise["pose_noise_m"]),
            pose.z_m + rng.gauss(0.0, noise["pose_noise_m"]),
            wrap_angle(pose.yaw_rad + rng.gauss(0.0, noise["yaw_noise_rad"])),
        )
        speed = state.wheel_speed_mps + rng.gauss(0.0, noise["speed_noise_mps"])
        scan = []
        for bearing in self._bearings:
            distance = self._terrain.cast_ray(
                pose.x_m, pose.y_m, pose.yaw_rad + bearing, self._max_range * range_scale
            )
            jitter = rng.gauss(0.0, noise["range_noise_m"])
            reading = None
            if range_available and distance is not None:
                reading = max(0.0, distance + jitter + self._range_bias)
            scan.append(RangeReading(bearing, reading))
        return Observation(
            time_s=time_s,
            estimated_pose=estimated,
            battery_fraction=max(0.0, min(1.0, state.battery_wh / self._capacity)),
            estimated_speed_mps=speed,
            targets_reached=targets_reached,
            range_scan=tuple(scan),
            measured_power_w=state.power_generation_w,
            science=science,
        )
