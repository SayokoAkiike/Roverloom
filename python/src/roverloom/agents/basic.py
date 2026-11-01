"""Baseline agents: stop, go straight to each target, and react to nearby obstacles."""

import math

from roverloom.api import STOP, Action, MissionBrief, Observation, Target, wrap_angle


def next_target(brief: MissionBrief, observation: Observation) -> Target | None:
    index = observation.targets_reached
    return brief.targets[index] if index < len(brief.targets) else None


def steer_to(
    brief: MissionBrief, observation: Observation, x_m: float, y_m: float, speed_scale: float = 1.0
) -> Action:
    """Turn toward a point, driving forward only when roughly facing it."""
    pose = observation.estimated_pose
    error = wrap_angle(math.atan2(y_m - pose.y_m, x_m - pose.x_m) - pose.yaw_rad)
    yaw_rate = max(-brief.max_yaw_rate_radps, min(brief.max_yaw_rate_radps, 1.5 * error))
    speed = brief.max_speed_mps * speed_scale * max(0.0, math.cos(error)) ** 2
    if abs(error) > 0.8:
        speed = 0.0
    return Action(speed, yaw_rate)


class StopAgent:
    """Never moves. Useful as a lower bound and for testing watchdogs and limits."""

    VERSION = "1.0.0"

    def reset(self, brief: MissionBrief, seed: int) -> None:
        pass

    def act(self, observation: Observation) -> Action:
        return STOP


class WaypointFollowerAgent:
    """Drives straight at each target, ignoring obstacles."""

    VERSION = "1.0.0"

    def __init__(self) -> None:
        self._brief: MissionBrief | None = None

    def reset(self, brief: MissionBrief, seed: int) -> None:
        self._brief = brief

    def act(self, observation: Observation) -> Action:
        assert self._brief is not None
        target = next_target(self._brief, observation)
        if target is None:
            return STOP
        return steer_to(self._brief, observation, target.x_m, target.y_m)


class ReactiveAgent:
    """Heads for the target, and steers around whatever the range sensor sees.

    It remembers which way it committed to turning, and backs out when it stops making
    progress. It has no map, so it can still get trapped by large obstacles.
    """

    VERSION = "1.0.0"

    _STUCK_WINDOW_S = 10.0
    _BACKUP_S = 5.0
    _COMMIT_S = 6.0

    def __init__(self) -> None:
        self._brief: MissionBrief | None = None

    def reset(self, brief: MissionBrief, seed: int) -> None:
        self._brief = brief
        self._side = 1.0
        self._commit_until = -1.0
        self._backup_until = -1.0
        self._check_time = 0.0
        self._check_xy = (brief.start_pose.x_m, brief.start_pose.y_m)

    def _update_stuck(self, observation: Observation) -> None:
        pose = observation.estimated_pose
        if observation.time_s < self._backup_until:
            # Measure progress afresh after backing up, or reversing would look like being stuck.
            self._check_time = observation.time_s
            self._check_xy = (pose.x_m, pose.y_m)
            return
        if observation.time_s - self._check_time < self._STUCK_WINDOW_S:
            return
        moved = math.hypot(pose.x_m - self._check_xy[0], pose.y_m - self._check_xy[1])
        if moved < 1.0:
            self._backup_until = observation.time_s + self._BACKUP_S
            self._side = -self._side
            self._commit_until = observation.time_s + self._BACKUP_S + self._COMMIT_S
        self._check_time = observation.time_s
        self._check_xy = (pose.x_m, pose.y_m)

    def act(self, observation: Observation) -> Action:
        brief = self._brief
        assert brief is not None
        target = next_target(brief, observation)
        if target is None:
            return STOP
        self._update_stuck(observation)
        now = observation.time_s
        if now < self._backup_until:
            return Action(-0.5 * brief.max_speed_mps, self._side * 0.5 * brief.max_yaw_rate_radps)

        safe = brief.body_radius_m + 3.0
        ahead = [r.range_m for r in observation.range_scan if abs(r.bearing_rad) < 0.5]
        nearest = min((r for r in ahead if r is not None), default=None)
        if nearest is not None and nearest < safe:
            left = _clearance(observation, 1.0, brief.sensor_max_range_m)
            right = _clearance(observation, -1.0, brief.sensor_max_range_m)
            if now >= self._commit_until:
                self._side = 1.0 if left >= right else -1.0
                self._commit_until = now + self._COMMIT_S
            speed = 0.0 if nearest < brief.body_radius_m + 1.0 else 0.3 * brief.max_speed_mps
            return Action(speed, self._side * brief.max_yaw_rate_radps)
        side_margin = brief.body_radius_m + 1.8
        close = [
            r
            for r in observation.range_scan
            if abs(r.bearing_rad) >= 0.5 and r.range_m is not None and r.range_m < side_margin
        ]
        if close:
            # Something is alongside: edge away from it while continuing forward.
            nearest_side = min(close, key=lambda r: r.range_m or 0.0)
            away = -1.0 if nearest_side.bearing_rad > 0 else 1.0
            return Action(0.5 * brief.max_speed_mps, away * 0.8 * brief.max_yaw_rate_radps)
        if now < self._commit_until:
            # Keep clear of the obstacle for a moment before turning back to the target.
            return Action(0.8 * brief.max_speed_mps, 0.0)
        return steer_to(brief, observation, target.x_m, target.y_m)


def _clearance(observation: Observation, side: float, max_range: float) -> float:
    readings = [
        max_range if r.range_m is None else r.range_m
        for r in observation.range_scan
        if r.bearing_rad * side > 0
    ]
    return sum(readings) / len(readings) if readings else 0.0
