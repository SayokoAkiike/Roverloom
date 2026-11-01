"""Mission skills, and agents built on them.

A skill is a named, typed operation with declared preconditions, failure reasons, a timeout, and
resource use. Planners, including LLMs, choose skills by emitting plain data. Nothing they produce
is ever executed as code. See docs/agent-sdk.md.
"""

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from jsonschema import Draft202012Validator

from roverloom.agents.planner import Navigator
from roverloom.api import STOP, Action, MissionBrief, Observation, ScienceTarget, TaskRequest
from roverloom.contract import ContractError, JsonDict, parse_json, validate

_STOPPED_MPS = 0.05
_TASK_RESEND_S = 6.0
MAX_DECISION_CHARS = 500


class SkillStatus(Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SkillSpec:
    """The published contract of a skill."""

    name: str
    description: str
    inputs: JsonDict
    outputs: tuple[str, ...]
    preconditions: tuple[str, ...]
    failure_reasons: tuple[str, ...]
    timeout_s: float
    resources: str


@dataclass(frozen=True, slots=True)
class SkillCall:
    skill: str
    args: JsonDict = field(default_factory=dict)
    reason: str = ""


@dataclass(frozen=True, slots=True)
class SkillOutcome:
    """What a finished skill reports to its planner."""

    skill: str
    status: SkillStatus
    reason: str | None
    outputs: JsonDict
    elapsed_s: float
    battery_used_fraction: float


def _object(properties: JsonDict, required: Sequence[str] = ()) -> JsonDict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


_TARGET_ARG = {"target_id": {"type": "string", "maxLength": 64}}
SKILL_SPECS: dict[str, SkillSpec] = {
    spec.name: spec
    for spec in (
        SkillSpec(
            "observe",
            "Hold still for a moment and report the latest sensor summary.",
            _object({"duration_s": {"type": "number", "minimum": 0, "maximum": 120}}),
            ("x_m", "y_m", "battery_fraction", "nearest_range_m", "data_window_open"),
            (),
            ("timeout",),
            180.0,
            "Idle power for the duration.",
        ),
        SkillSpec(
            "navigate_to",
            "Drive to a position, replanning around obstacles found on the way.",
            _object(
                {
                    "x_m": {"type": "number"},
                    "y_m": {"type": "number"},
                    "radius_m": {"type": "number", "exclusiveMinimum": 0},
                },
                ("x_m", "y_m"),
            ),
            ("x_m", "y_m", "distance_error_m"),
            ("Position must be inside the map extent.",),
            ("outside_map", "timeout"),
            900.0,
            "Drive power; depends on the rover, slope, and soil.",
        ),
        SkillSpec(
            "inspect_target",
            "Stop at a science target and measure its true value.",
            _object(_TARGET_ARG, ("target_id",)),
            ("target_id", "value"),
            ("Rover within the target radius.", "Target not already inspected."),
            ("unknown_target", "out_of_range", "already_done", "busy", "rover_moving", "timeout"),
            180.0,
            "Instrument power for the target's inspect_s; stores 30% of its value as data.",
        ),
        SkillSpec(
            "collect_sample",
            "Collect a sample from an inspected target.",
            _object(_TARGET_ARG, ("target_id",)),
            ("target_id",),
            (
                "Rover has a sample arm.",
                "Rover within the target radius.",
                "Target inspected, and not already collected.",
            ),
            (
                "no_sample_tool",
                "unknown_target",
                "out_of_range",
                "needs_inspection",
                "already_done",
                "busy",
                "rover_moving",
                "timeout",
            ),
            300.0,
            "3x instrument power for the target's collect_s; stores 70% of its value as data.",
        ),
        SkillSpec(
            "transmit_data",
            "Send stored data to the ground, waiting for a window if needed.",
            _object({"wait": {"type": "boolean"}}),
            ("transmitted_value",),
            ("Stored data exists.", "Data window open, unless waiting is allowed."),
            ("no_data", "window_closed", "link_lost", "busy", "rover_moving", "timeout"),
            600.0,
            "1.5x instrument power while sending. Points count only once sent.",
        ),
        SkillSpec(
            "return_to_base",
            "Drive to the base site named in the mission brief.",
            _object({}),
            ("x_m", "y_m"),
            ("Mission has a base site.",),
            ("no_base", "timeout"),
            900.0,
            "Drive power.",
        ),
        SkillSpec(
            "safe_stop",
            "Stop the rover, and optionally end the mission.",
            _object({"end_mission": {"type": "boolean"}}),
            ("stopped",),
            (),
            ("timeout",),
            30.0,
            "Idle power.",
        ),
    )
}


def describe_skills() -> list[JsonDict]:
    """The skill contract as data, for documentation and planner prompts."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "inputs": spec.inputs,
            "outputs": list(spec.outputs),
            "preconditions": list(spec.preconditions),
            "failure_reasons": list(spec.failure_reasons),
            "timeout_s": spec.timeout_s,
            "resources": spec.resources,
        }
        for spec in SKILL_SPECS.values()
    ]


def parse_skill_call(data: object) -> SkillCall:
    """Check an untrusted call against the fixed skill list. Raises ContractError if invalid."""
    validate("skill_call", data)
    assert isinstance(data, dict)
    spec = SKILL_SPECS.get(data["skill"])
    if spec is None:
        raise ContractError(f"unknown skill: {data['skill']}")
    errors = list(Draft202012Validator(spec.inputs).iter_errors(data["args"]))
    if errors:
        raise ContractError(f"invalid arguments for {spec.name}: {errors[0].message}")
    return SkillCall(spec.name, data["args"], data.get("reason", ""))


def _nearest_range(observation: Observation) -> float | None:
    ranges = [r.range_m for r in observation.range_scan if r.range_m is not None]
    return min(ranges) if ranges else None


class SkillExecutor:
    """Runs one skill call at a time, enforcing its timeout. Returns an Action each step."""

    def __init__(self, brief: MissionBrief) -> None:
        self._brief = brief
        self._navigator = Navigator(brief)
        self._call: SkillCall | None = None
        self._started = 0.0
        self._start_battery = 1.0
        self._task_sent_at: float | None = None
        self._results_seen: tuple[str, str | None, float] | None = None
        self.outcome: SkillOutcome | None = None

    @property
    def busy(self) -> bool:
        return self._call is not None

    def start(self, call: SkillCall, observation: Observation) -> None:
        self._call = call
        self._started = observation.time_s
        self._start_battery = observation.battery_fraction
        self._task_sent_at = None
        self.outcome = None
        pose = observation.estimated_pose
        self._navigator.reset_progress(observation.time_s, pose.x_m, pose.y_m)
        science = observation.science
        last = science.last_result if science else None
        self._results_seen = (last.type, last.target_id, last.time_s) if last else None

    def _finish(
        self, observation: Observation, status: SkillStatus, reason: str | None, outputs: JsonDict
    ) -> Action:
        assert self._call is not None
        self.outcome = SkillOutcome(
            self._call.skill,
            status,
            reason,
            outputs,
            round(observation.time_s - self._started, 3),
            round(self._start_battery - observation.battery_fraction, 6),
        )
        self._call = None
        return STOP

    def step(self, observation: Observation) -> Action:
        call = self._call
        assert call is not None
        spec = SKILL_SPECS[call.skill]
        if observation.time_s - self._started > spec.timeout_s:
            return self._finish(observation, SkillStatus.FAILED, "timeout", {})
        action: Action = getattr(self, f"_run_{call.skill}")(observation, call.args)
        return action

    def _run_observe(self, observation: Observation, args: JsonDict) -> Action:
        if observation.time_s - self._started < args.get("duration_s", 2.0):
            return STOP
        pose = observation.estimated_pose
        science = observation.science
        return self._finish(
            observation,
            SkillStatus.SUCCEEDED,
            None,
            {
                "x_m": pose.x_m,
                "y_m": pose.y_m,
                "battery_fraction": observation.battery_fraction,
                "nearest_range_m": _nearest_range(observation),
                "data_window_open": science.data_window_open if science else False,
            },
        )

    def _drive(self, observation: Observation, x: float, y: float, radius: float) -> Action:
        pose = observation.estimated_pose
        error = math.hypot(x - pose.x_m, y - pose.y_m)
        if error <= radius:
            return self._finish(
                observation,
                SkillStatus.SUCCEEDED,
                None,
                {"x_m": pose.x_m, "y_m": pose.y_m, "distance_error_m": error},
            )
        return self._navigator.step(observation, x, y)

    def _run_navigate_to(self, observation: Observation, args: JsonDict) -> Action:
        x, y = args["x_m"], args["y_m"]
        (min_x, min_y), (max_x, max_y) = self._brief.extent_min_xy, self._brief.extent_max_xy
        if not (min_x <= x <= max_x and min_y <= y <= max_y):
            return self._finish(observation, SkillStatus.FAILED, "outside_map", {})
        return self._drive(observation, x, y, args.get("radius_m", 2.0))

    def _run_return_to_base(self, observation: Observation, args: JsonDict) -> Action:
        base = self._brief.base
        if base is None:
            return self._finish(observation, SkillStatus.FAILED, "no_base", {})
        return self._drive(observation, base.x_m, base.y_m, base.radius_m * 0.7)

    def _task(self, observation: Observation, task: TaskRequest) -> Action | None:
        """Send a task once the rover has stopped, resending in case the message was lost.

        Returns the Action to send while waiting, or None once a new result has arrived.
        """
        science = observation.science
        if science is None:
            return STOP
        last = science.last_result
        key = (last.type, last.target_id, last.time_s) if last else None
        if key != self._results_seen and last is not None and last.type == task.type:
            return None
        if science.active_task == task.type:
            return STOP
        if abs(observation.estimated_speed_mps) > _STOPPED_MPS:
            return STOP
        # Resend only after a pause, in case the message was lost. A late duplicate would be
        # rejected by the rover, and could hide the real result from this skill.
        now = observation.time_s
        if self._task_sent_at is not None and now - self._task_sent_at < _TASK_RESEND_S:
            return STOP
        self._task_sent_at = now
        return Action(0.0, 0.0, task)

    def _finish_task(self, observation: Observation, outputs: JsonDict) -> Action:
        science = observation.science
        assert science is not None and science.last_result is not None
        last = science.last_result
        if last.status == "completed":
            return self._finish(observation, SkillStatus.SUCCEEDED, None, outputs)
        return self._finish(observation, SkillStatus.FAILED, last.reason, outputs)

    def _run_inspect_target(self, observation: Observation, args: JsonDict) -> Action:
        target_id = args["target_id"]
        action = self._task(observation, TaskRequest("inspect", target_id))
        if action is not None:
            return action
        assert observation.science is not None
        value = dict(observation.science.inspected).get(target_id)
        return self._finish_task(observation, {"target_id": target_id, "value": value})

    def _run_collect_sample(self, observation: Observation, args: JsonDict) -> Action:
        target_id = args["target_id"]
        action = self._task(observation, TaskRequest("collect", target_id))
        if action is not None:
            return action
        return self._finish_task(observation, {"target_id": target_id})

    def _run_transmit_data(self, observation: Observation, args: JsonDict) -> Action:
        science = observation.science
        if (
            science is not None
            and args.get("wait", True)
            and not science.data_window_open
            and science.active_task is None
        ):
            return STOP
        action = self._task(observation, TaskRequest("transmit"))
        if action is not None:
            return action
        assert science is not None
        last = science.last_result
        if args.get("wait", True) and last is not None and last.reason == "window_closed":
            # The window closed first. Keep waiting for the next one, until the skill times out.
            self._results_seen = (last.type, last.target_id, last.time_s)
            self._task_sent_at = None
            return STOP
        return self._finish_task(observation, {"transmitted_value": science.transmitted_value})

    def _run_safe_stop(self, observation: Observation, args: JsonDict) -> Action:
        if abs(observation.estimated_speed_mps) > _STOPPED_MPS:
            return STOP
        if args.get("end_mission"):
            # The mission ends on arrival, so this skill does not wait for a reply.
            return Action(0.0, 0.0, TaskRequest("end_mission"))
        return self._finish_and_stop(observation)

    def _finish_and_stop(self, observation: Observation) -> Action:
        return self._finish(observation, SkillStatus.SUCCEEDED, None, {"stopped": True})


@dataclass(frozen=True, slots=True)
class PlanContext:
    """All a planner may use. Nothing here comes from the simulator's internal truth."""

    brief: MissionBrief
    observation: Observation
    history: tuple[SkillOutcome, ...]


class SkillPlanner(Protocol):
    def next_call(self, context: PlanContext) -> SkillCall | None:
        """Return the next skill, or None when there is nothing more to do."""


class SkillAgent:
    """An Agent that drives the rover by running a planner's skill calls."""

    VERSION = "1.0.0"

    def __init__(self, planner: SkillPlanner | None = None) -> None:
        self._planner = planner
        self._decisions: list[str] = []

    def make_planner(self, brief: MissionBrief, seed: int) -> SkillPlanner:
        assert self._planner is not None, "SkillAgent needs a planner"
        return self._planner

    def reset(self, brief: MissionBrief, seed: int) -> None:
        self._brief = brief
        self._active_planner = self.make_planner(brief, seed)
        self._executor = SkillExecutor(brief)
        self._history: list[SkillOutcome] = []
        self._decisions = []
        self._done = False

    def drain_decisions(self) -> list[str]:
        decisions, self._decisions = self._decisions, []
        return decisions

    def _note(self, text: str) -> None:
        self._decisions.append(text[:MAX_DECISION_CHARS])

    def act(self, observation: Observation) -> Action:
        executor = self._executor
        if executor.busy:
            action = executor.step(observation)
            if executor.busy:
                return action
            outcome = executor.outcome
            assert outcome is not None
            self._history.append(outcome)
            detail = outcome.reason or json.dumps(outcome.outputs, sort_keys=True, default=str)
            self._note(f"{outcome.skill}: {outcome.status.value} ({detail})")
        if self._done:
            return STOP
        call = self._active_planner.next_call(
            PlanContext(self._brief, observation, tuple(self._history))
        )
        if call is None:
            self._done = True
            self._note("planner finished")
            return STOP
        self._note(
            f"start {call.skill} {json.dumps(call.args, sort_keys=True)} {call.reason}".strip()
        )
        executor.start(call, observation)
        return executor.step(observation)


def _distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


class MissionPlanner:
    """Greedy science planner: value per travel time, with reserves for returning home.

    It knows only the brief and its observations. It uses prior values until inspection reveals
    the true value, and it skips sampling sites that turn out not to be worth it.
    """

    _SAMPLE_VALUE_RATIO = 0.6
    _RESERVE_S = 60.0
    _WINDOW_MARGIN_S = 5.0

    def __init__(self, brief: MissionBrief) -> None:
        self._brief = brief
        self._stage = "choose"
        self._current: ScienceTarget | None = None
        self._skipped: set[str] = set()
        self._ended = False

    def _speed(self) -> float:
        # Planning speed. Real progress is slower with slip, so a margin is part of the reserve.
        return self._brief.max_speed_mps * 0.7

    def _time_to_base(self, x: float, y: float) -> float:
        base = self._brief.base
        if base is None:
            return 0.0
        return _distance(x, y, base.x_m, base.y_m) / self._speed()

    def _choose(self, context: PlanContext) -> ScienceTarget | None:
        science = context.observation.science
        pose = context.observation.estimated_pose
        done = dict(science.inspected) if science else {}
        now = context.observation.time_s
        best: tuple[float, str, ScienceTarget] | None = None
        for target in self._brief.science_targets:
            if target.id in done or target.id in self._skipped:
                continue
            travel = _distance(pose.x_m, pose.y_m, target.x_m, target.y_m) / self._speed()
            work = target.inspect_s + (target.collect_s if self._brief.can_collect else 0.0)
            finish = now + travel + work + self._time_to_base(target.x_m, target.y_m)
            if finish + self._RESERVE_S > self._brief.time_limit_s:
                continue
            rate = target.prior_value / max(travel + work, 1.0)
            # The ID breaks ties, so that the choice never depends on list order.
            if best is None or (rate, target.id) > (best[0], best[1]):
                best = (rate, target.id, target)
        return best[2] if best else None

    def _window_has_room(self, context: PlanContext) -> bool:
        """Whether the open window will last long enough to start sending."""
        science = context.observation.science
        if science is None or not science.data_window_open:
            return False
        windows = self._brief.data_windows
        if windows is None:
            return True
        phase = (context.observation.time_s - windows.offset_s) % windows.period_s
        needed = (self._brief.transmit_s_per_item or 0.0) + self._WINDOW_MARGIN_S
        return windows.open_s - phase >= needed

    def _wrap_up(self, context: PlanContext) -> SkillCall:
        science = context.observation.science
        last = context.history[-1] if context.history else None
        if self._stage == "wrap_transmit":
            self._stage = "wrap_home"
            if science is not None and science.stored_items > 0 and self._window_has_room(context):
                return SkillCall("transmit_data", {"wait": False}, "send what is stored")
        if self._stage == "wrap_home":
            self._stage = "wrap_final"
            if self._brief.base is not None and self._brief.base.required:
                return SkillCall("return_to_base", {}, "go home")
        if (
            self._stage == "wrap_final"
            and science is not None
            and science.stored_items > 0
            and not (last and last.skill == "transmit_data")
        ):
            return SkillCall("transmit_data", {"wait": True}, "send what is left")
        self._stage = "ended"
        return SkillCall("safe_stop", {"end_mission": True}, "campaign finished")

    def next_call(self, context: PlanContext) -> SkillCall | None:
        if self._stage == "ended":
            return None
        last = context.history[-1] if context.history else None
        science = context.observation.science
        if self._stage.startswith("wrap"):
            return self._wrap_up(context)
        # Ordered position objectives come first, when a mission has them.
        reached = context.observation.targets_reached
        if reached < len(self._brief.targets):
            waypoint = self._brief.targets[reached]
            return SkillCall(
                "navigate_to",
                {"x_m": waypoint.x_m, "y_m": waypoint.y_m, "radius_m": waypoint.radius_m * 0.5},
                f"objective {reached + 1}",
            )
        if self._stage == "travel" and self._current is not None:
            if last is not None and last.status is SkillStatus.FAILED:
                self._skipped.add(self._current.id)
                self._stage = "choose"
            else:
                self._stage = "inspect"
                return SkillCall(
                    "inspect_target", {"target_id": self._current.id}, "measure its value"
                )
        elif self._stage == "inspect" and self._current is not None:
            value = last.outputs.get("value") if last else None
            worth = (
                value is not None and value >= self._current.prior_value * self._SAMPLE_VALUE_RATIO
            )
            succeeded = last is not None and last.status is SkillStatus.SUCCEEDED
            if succeeded and self._brief.can_collect and worth:
                self._stage = "collect"
                return SkillCall(
                    "collect_sample", {"target_id": self._current.id}, f"value {value} is good"
                )
            self._skipped.add(self._current.id)
            self._stage = "choose"
        elif self._stage == "collect":
            self._stage = "choose"

        # Send data whenever there is time left in a window, since only sent data counts.
        if (
            science is not None
            and science.stored_items > 0
            and self._window_has_room(context)
            and not (last and last.skill == "transmit_data" and last.status is SkillStatus.FAILED)
        ):
            return SkillCall("transmit_data", {"wait": False}, "window is open")
        target = self._choose(context)
        if target is None:
            self._stage = "wrap_transmit"
            return self._wrap_up(context)
        self._current = target
        self._stage = "travel"
        return SkillCall(
            "navigate_to",
            {"x_m": target.x_m, "y_m": target.y_m, "radius_m": target.radius_m * 0.7},
            f"site {target.id}: best expected value for the time",
        )


class MissionPlannerAgent(SkillAgent):
    """Mission-level planner for science campaigns."""

    def make_planner(self, brief: MissionBrief, seed: int) -> SkillPlanner:
        return MissionPlanner(brief)


class LanguageModel(Protocol):
    """A text model. Implement this to connect a real one. Its output is never executed."""

    def complete(self, prompt: str) -> str: ...


def build_prompt(context: PlanContext) -> str:
    """Everything sent to a model. It contains only what the planner is allowed to know."""
    last = context.history[-1] if context.history else None
    return json.dumps(
        {
            "instruction": (
                'Reply with one JSON object: {"skill": name, "args": {...}, "reason": text}.'
            ),
            "skills": describe_skills(),
            "brief": context.brief.to_dict(),
            "observation": context.observation.to_dict(),
            "last_result": None
            if last is None
            else {"skill": last.skill, "status": last.status.value, "reason": last.reason},
        },
        sort_keys=True,
    )


class CapPlanner:
    """Turns model text into validated skill calls, and fails safe on anything else.

    The reply must be a single JSON object naming an allowed skill. Code, unknown skills, and bad
    arguments are rejected without being evaluated. Repeated bad replies stop the rover.
    """

    MAX_INVALID_REPLIES = 3
    MAX_REPLY_CHARS = 20_000

    def __init__(self, model: LanguageModel) -> None:
        self._model = model
        self._invalid = 0
        self.rejected: list[str] = []

    def next_call(self, context: PlanContext) -> SkillCall | None:
        while self._invalid < self.MAX_INVALID_REPLIES:
            reply = self._model.complete(build_prompt(context))
            try:
                if len(reply) > self.MAX_REPLY_CHARS:
                    raise ContractError("reply is too long")
                return parse_skill_call(parse_json(reply))
            except ContractError as error:
                self._invalid += 1
                self.rejected.append(str(error)[:200])
        return SkillCall("safe_stop", {}, "model replies were invalid; stopping safely")


class MockLanguageModel:
    """A deterministic stand-in for a language model. No network, keys, or randomness.

    It reads the prompt it is given, as a real model would, and answers using MissionPlanner rules.
    It shows the interface working. It says nothing about how a real model would perform.
    """

    def __init__(self) -> None:
        self._planner: MissionPlanner | None = None

    def complete(self, prompt: str) -> str:
        data = json.loads(prompt)
        brief = MissionBrief.from_dict(data["brief"])
        observation = Observation.from_dict(data["observation"])
        if self._planner is None:
            self._planner = MissionPlanner(brief)
        last = data["last_result"]
        history: tuple[SkillOutcome, ...] = ()
        if last is not None:
            outputs: JsonDict = {}
            science = observation.science
            current = self._planner._current
            if last["skill"] == "inspect_target" and science and current:
                outputs = {"value": dict(science.inspected).get(current.id)}
            history = (
                SkillOutcome(
                    last["skill"], SkillStatus(last["status"]), last["reason"], outputs, 0, 0
                ),
            )
        call = self._planner.next_call(PlanContext(brief, observation, history))
        if call is None:
            call = SkillCall("safe_stop", {"end_mission": True}, "nothing left to do")
        return json.dumps({"skill": call.skill, "args": call.args, "reason": call.reason})


class MockCapAgent(SkillAgent):
    """A CaP-style agent driven by the mock model, through the same path a real model would use."""

    def make_planner(self, brief: MissionBrief, seed: int) -> SkillPlanner:
        return CapPlanner(MockLanguageModel())


Approver = Callable[[SkillCall], bool]


class HumanInTheLoopPlanner:
    """Asks a person before running selected skills. Declined calls are skipped."""

    NEEDS_APPROVAL = frozenset({"collect_sample", "transmit_data"})

    def __init__(self, inner: SkillPlanner, approver: Approver) -> None:
        self._inner = inner
        self._approver = approver

    def next_call(self, context: PlanContext) -> SkillCall | None:
        call = self._inner.next_call(context)
        if call is None or call.skill not in self.NEEDS_APPROVAL or self._approver(call):
            return call
        return SkillCall("observe", {"duration_s": 2.0}, f"operator declined {call.skill}")


class HumanApprovalAgent(SkillAgent):
    """Mission planner with an operator approving sampling and transmission.

    An approver may answer later, in which case the rover waits safely until it does.
    """

    def __init__(self, approver: Approver | None = None) -> None:
        super().__init__()
        self.pending: SkillCall | None = None
        self._approver = approver
        self._answer: bool | None = None

    def answer(self, approved: bool) -> None:
        self._answer = approved

    def make_planner(self, brief: MissionBrief, seed: int) -> SkillPlanner:
        self._inner = MissionPlanner(brief)
        self.pending = None
        return self

    def next_call(self, context: PlanContext) -> SkillCall | None:
        if self.pending is None:
            call = self._inner.next_call(context)
            if call is None or call.skill not in HumanInTheLoopPlanner.NEEDS_APPROVAL:
                return call
            self.pending = call
        if self._approver is not None:
            self._answer = self._approver(self.pending)
        if self._answer is None:
            return SkillCall(
                "observe", {"duration_s": 1.0}, f"awaiting approval: {self.pending.skill}"
            )
        call, self.pending, approved = self.pending, None, self._answer
        self._answer = None
        if approved:
            return call
        return SkillCall("observe", {"duration_s": 1.0}, f"operator declined {call.skill}")
