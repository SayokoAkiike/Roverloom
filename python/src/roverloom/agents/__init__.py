"""Sample agents, and the way to load your own. See docs/adding-agents.md."""

import importlib
import importlib.util
import inspect
from pathlib import Path
from typing import Protocol

from roverloom.agents.basic import ReactiveAgent, StopAgent, WaypointFollowerAgent
from roverloom.agents.planner import GridReplannerAgent
from roverloom.agents.sdk import HumanApprovalAgent, MissionPlannerAgent, MockCapAgent
from roverloom.agents.skills import SkillPlanAgent
from roverloom.api import Action, MissionBrief, Observation
from roverloom.contract import ContractError


class Agent(Protocol):
    """Implement these two methods to write an agent.

    An agent receives only a MissionBrief and Observations. It has no access to terrain,
    rocks, soil, noise settings, or future faults, and must decide from what it senses.
    """

    def reset(self, brief: MissionBrief, seed: int) -> None:
        """Prepare for a new mission. Use only this seed for any randomness."""

    def act(self, observation: Observation) -> Action:
        """Return the next command. Called once for each observation that arrives."""


BUILTIN_AGENTS: dict[str, type[Agent]] = {
    "stop": StopAgent,
    "waypoint": WaypointFollowerAgent,
    "reactive": ReactiveAgent,
    "replanner": GridReplannerAgent,
    "skill-plan": SkillPlanAgent,
    "mission-planner": MissionPlannerAgent,
    "cap-mock": MockCapAgent,
    "human-approval": HumanApprovalAgent,
}


def _load_class(spec: str) -> object:
    target, _, class_name = spec.rpartition(":")
    if not target or not class_name:
        names = ", ".join(sorted(BUILTIN_AGENTS))
        raise ContractError(f"unknown agent {spec!r}; use one of {names}, or path.py:ClassName")
    if target.endswith(".py"):
        path = Path(target)
        if not path.is_file():
            raise ContractError(f"agent file not found: {target}")
        module_spec = importlib.util.spec_from_file_location(f"roverloom_user_{path.stem}", path)
        if module_spec is None or module_spec.loader is None:
            raise ContractError(f"cannot load agent file: {target}")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
    else:
        module = importlib.import_module(target)
    try:
        return getattr(module, class_name)
    except AttributeError as error:
        raise ContractError(f"{target} has no class {class_name}") from error


def create_agent(spec: str) -> Agent:
    """Create a built-in agent, or load one from "file.py:Class" or "module:Class".

    Loading from a file runs that file's code with your permissions. Only load code you trust.
    """
    factory = BUILTIN_AGENTS.get(spec) or _load_class(spec)
    if not callable(factory):
        raise ContractError(f"{spec} is not a class")
    agent = factory()
    for method in ("reset", "act"):
        if not inspect.isroutine(getattr(agent, method, None)):
            raise ContractError(f"{spec} does not implement {method}()")
    result: Agent = agent
    return result


__all__ = ["Agent", "BUILTIN_AGENTS", "create_agent"]
