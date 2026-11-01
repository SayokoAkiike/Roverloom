"""Skills for plans expressed as data.

This is the planned attachment point for code-as-policy style agents. A planner, possibly an
LLM in the future, produces a JSON plan naming skills from a fixed list. The plan is validated
and interpreted, and nothing in it is ever executed as code. See docs/adding-agents.md.
"""

import math
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from roverloom.agents.basic import next_target, steer_to
from roverloom.api import STOP, Action, MissionBrief, Observation, wrap_angle
from roverloom.contract import JsonDict, load_json_file, validate


class SkillStatus(Enum):
    RUNNING = "running"
    DONE = "done"


class Skill(Protocol):
    def step(self, observation: Observation) -> tuple[Action, SkillStatus]: ...


class GoToSkill:
    def __init__(self, brief: MissionBrief, x_m: float, y_m: float, radius_m: float = 2.0) -> None:
        self._brief, self._x, self._y, self._radius = brief, x_m, y_m, radius_m

    def step(self, observation: Observation) -> tuple[Action, SkillStatus]:
        pose = observation.estimated_pose
        if math.hypot(self._x - pose.x_m, self._y - pose.y_m) <= self._radius:
            return STOP, SkillStatus.DONE
        return steer_to(self._brief, observation, self._x, self._y), SkillStatus.RUNNING


class GoToNextTargetSkill:
    def __init__(self, brief: MissionBrief) -> None:
        self._brief = brief
        self._index: int | None = None

    def step(self, observation: Observation) -> tuple[Action, SkillStatus]:
        if self._index is None:
            self._index = observation.targets_reached
        target = next_target(self._brief, observation)
        if target is None or observation.targets_reached > self._index:
            return STOP, SkillStatus.DONE
        return steer_to(self._brief, observation, target.x_m, target.y_m), SkillStatus.RUNNING


class WaitSkill:
    def __init__(self, brief: MissionBrief, duration_s: float) -> None:
        self._duration = duration_s
        self._start: float | None = None

    def step(self, observation: Observation) -> tuple[Action, SkillStatus]:
        if self._start is None:
            self._start = observation.time_s
        done = observation.time_s - self._start >= self._duration
        return STOP, SkillStatus.DONE if done else SkillStatus.RUNNING


class TurnToSkill:
    def __init__(self, brief: MissionBrief, yaw_rad: float) -> None:
        self._brief, self._yaw = brief, yaw_rad

    def step(self, observation: Observation) -> tuple[Action, SkillStatus]:
        error = wrap_angle(self._yaw - observation.estimated_pose.yaw_rad)
        if abs(error) < 0.05:
            return STOP, SkillStatus.DONE
        limit = self._brief.max_yaw_rate_radps
        return Action(0.0, max(-limit, min(limit, 1.5 * error))), SkillStatus.RUNNING


# The complete list of what a plan can do. Adding to it is a reviewed code change.
SKILLS: MappingProxyType[str, Callable[..., Skill]] = MappingProxyType(
    {
        "go_to": GoToSkill,
        "go_to_next_target": GoToNextTargetSkill,
        "wait": WaitSkill,
        "turn_to": TurnToSkill,
    }
)


def load_plan(path: Path) -> JsonDict:
    plan = load_json_file(path)
    validate("skill_plan", plan, str(path))
    return plan


class SkillPlanAgent:
    """Runs a validated plan one skill at a time, then stops.

    Without a plan, it visits every target in order.
    """

    def __init__(self, plan: JsonDict | None = None) -> None:
        if plan is not None:
            validate("skill_plan", plan)
        self._plan = plan
        self._brief: MissionBrief | None = None

    def reset(self, brief: MissionBrief, seed: int) -> None:
        self._brief = brief
        steps = (
            self._plan["steps"]
            if self._plan is not None
            else [{"skill": "go_to_next_target"} for _ in brief.targets]
        )
        self._steps = list(steps)
        self._index = 0
        self._skill: Skill | None = None

    def act(self, observation: Observation) -> Action:
        assert self._brief is not None
        while self._index < len(self._steps):
            if self._skill is None:
                step = self._steps[self._index]
                arguments = {key: value for key, value in step.items() if key != "skill"}
                self._skill = SKILLS[step["skill"]](self._brief, **arguments)
            action, status = self._skill.step(observation)
            if status is SkillStatus.RUNNING:
                return action
            self._index += 1
            self._skill = None
        return STOP
