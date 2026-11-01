"""A template for your own agent. Run it from python/ with:

uv run roverloom run --scenario demo_traverse --agent examples/my_agent.py:CautiousAgent
"""

import math

from roverloom.api import STOP, Action, MissionBrief, Observation, wrap_angle


class CautiousAgent:
    """Heads for the next target, and slows down when the range sensor sees something close."""

    def reset(self, brief: MissionBrief, seed: int) -> None:
        # The brief holds targets and rover limits. There is no map and no fault schedule.
        self.brief = brief

    def act(self, observation: Observation) -> Action:
        if observation.targets_reached >= len(self.brief.targets):
            return STOP
        target = self.brief.targets[observation.targets_reached]
        pose = observation.estimated_pose  # An estimate: it can be noisy and out of date.

        heading = math.atan2(target.y_m - pose.y_m, target.x_m - pose.x_m)
        error = wrap_angle(heading - pose.yaw_rad)
        turn = max(-self.brief.max_yaw_rate_radps, min(self.brief.max_yaw_rate_radps, error))

        ranges = [r.range_m for r in observation.range_scan if r.range_m is not None]
        nearest = min(ranges, default=self.brief.sensor_max_range_m)
        speed = self.brief.max_speed_mps * min(1.0, nearest / self.brief.sensor_max_range_m)
        if abs(error) > 0.8:
            speed = 0.0
        return Action(speed, turn)
