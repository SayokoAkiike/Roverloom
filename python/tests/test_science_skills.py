"""Science tasks, environment events, skills, CaP safety, and what agents can learn."""

import json

import pytest

from roverloom.agents import create_agent
from roverloom.agents.sdk import (
    SKILL_SPECS,
    CapPlanner,
    HumanApprovalAgent,
    MissionPlanner,
    MockLanguageModel,
    PlanContext,
    SkillAgent,
    SkillCall,
    SkillExecutor,
    SkillStatus,
    build_prompt,
    describe_skills,
    parse_skill_call,
)
from roverloom.api import STOP, Action, MissionOutcome, Observation, Pose, TaskRequest
from roverloom.contract import ContractError, load_json_file, repo_root, validate
from roverloom.runner import run_mission
from roverloom.science import ScienceSystem
from roverloom.session import MissionSession
from roverloom.world import build_scenario, list_practice_scenarios, load_scenario

SPEC = {
    "targets": [
        {
            "id": "a",
            "position_m": [0, 0, 0],
            "radius_m": 3,
            "prior_value": 5,
            "true_value": 10,
            "inspect_s": 2,
            "collect_s": 4,
        },
    ],
    "data_windows": {"period_s": 100, "open_s": 20, "offset_s": 10},
    "base": {"position_m": [0, 0, 0], "radius_m": 5, "required": True},
    "transmit_s_per_item": 1,
    "success_value": 5,
}


def system(has_tool: bool = True) -> tuple[ScienceSystem, list]:
    events: list = []
    return ScienceSystem(SPEC, has_tool, 100, lambda t, d: events.append((t, d))), events


def rejected_reason(science: ScienceSystem) -> str | None:
    return science.status(0).last_result.reason


@pytest.mark.parametrize(
    ("task", "x", "speed", "reason"),
    [
        (TaskRequest("inspect", "missing"), 0, 0, "unknown_target"),
        (TaskRequest("inspect", "a"), 50, 0, "out_of_range"),
        (TaskRequest("inspect", "a"), 0, 0.3, "rover_moving"),
        (TaskRequest("collect", "a"), 0, 0, "needs_inspection"),
        (TaskRequest("transmit"), 0, 0, "no_data"),
    ],
)
def test_task_preconditions(task: TaskRequest, x: float, speed: float, reason: str) -> None:
    science, _ = system()
    science.request(task, x, 0, speed, 15.0)
    assert rejected_reason(science) == reason
    assert not science.busy


def run_task(science: ScienceSystem, task: TaskRequest, start: float, seconds: float) -> float:
    science.request(task, 0, 0, 0, start)
    now = start
    while now < start + seconds:
        now += 0.1
        science.update(round(now, 1), True)
    return round(now, 1)


def test_inspect_then_collect_then_transmit() -> None:
    science, _ = system()
    now = run_task(science, TaskRequest("inspect", "a"), 11.0, 2.2)
    assert dict(science.status(now).inspected) == {"a": 10.0}
    assert science.stored_value == pytest.approx(3.0)
    now = run_task(science, TaskRequest("collect", "a"), now, 4.2)
    assert science.collected == ["a"]
    run_task(science, TaskRequest("transmit"), now, 2.5)
    assert science.transmitted_value == pytest.approx(10.0)
    assert science.stored_value == 0


def test_cannot_repeat_or_sample_without_tool() -> None:
    science, _ = system(has_tool=False)
    now = run_task(science, TaskRequest("inspect", "a"), 11.0, 2.2)
    science.request(TaskRequest("inspect", "a"), 0, 0, 0, now)
    assert rejected_reason(science) == "already_done"
    science.request(TaskRequest("collect", "a"), 0, 0, 0, now)
    assert rejected_reason(science) == "no_sample_tool"


def test_second_task_while_busy_is_rejected_but_retry_is_not_an_error() -> None:
    science, _ = system()
    science.request(TaskRequest("inspect", "a"), 0, 0, 0, 11.0)
    science.request(TaskRequest("inspect", "a"), 0, 0, 0, 11.1)
    assert science.status(11.1).last_result is None
    science.request(TaskRequest("transmit"), 0, 0, 0, 11.2)
    assert rejected_reason(science) == "busy"


@pytest.mark.parametrize(
    ("time_s", "expected"),
    [(9.9, False), (10.0, True), (29.9, True), (30.0, False), (110.0, True), (130.0, False)],
)
def test_window_boundaries(time_s: float, expected: bool) -> None:
    assert system()[0].window_open(time_s) is expected


def test_transmit_refused_when_window_closed_and_stops_when_it_closes() -> None:
    science, _ = system()
    now = run_task(science, TaskRequest("inspect", "a"), 11.0, 2.2)
    science.request(TaskRequest("transmit"), 0, 0, 0, 50.0)
    assert rejected_reason(science) == "window_closed"
    assert science.stored_value > 0
    science.request(TaskRequest("transmit"), 0, 0, 0, now)
    science.update(29.0, False)  # Command link fails during the send.
    assert science.status(29.0).last_result.reason == "link_lost"
    assert science.stored_value > 0, "unsent data is kept"


def mission_scenario(**mission_changes):
    document = load_json_file(repo_root() / "scenarios" / "practice" / "science_sprint.json")
    document["mission"].update(mission_changes)
    terrain = load_json_file(repo_root() / "scenarios" / "terrains" / "flat_test.json")
    from roverloom.rover_builder import load_rover_document

    return build_scenario(document, terrain, load_rover_document("pathfinder_6w"))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"objectives": [], "science": None}, "science"),
        (
            {
                "science": {
                    **SPEC,
                    "targets": [SPEC["targets"][0], SPEC["targets"][0]],
                    "success_value": 1,
                }
            },
            "unique",
        ),
        ({"science": {**SPEC, "success_value": 999}}, "success_value"),
        (
            {"science": {**SPEC, "data_windows": {"period_s": 5, "open_s": 9, "offset_s": 0}}},
            "window",
        ),
        (
            {
                "science": {
                    **SPEC,
                    "base": {"position_m": [9999, 0, 0], "radius_m": 1, "required": True},
                }
            },
            "outside",
        ),
    ],
    ids=["none", "dup", "value", "window", "base"],
)
def test_invalid_science_setup_is_rejected(change: dict, message: str) -> None:
    if change.get("science") is None:
        document = load_json_file(repo_root() / "scenarios" / "practice" / "boulder_gap.json")
        document["mission"]["objectives"] = []
        terrain = load_json_file(
            repo_root() / "scenarios" / "terrains" / "practice_boulder_wall.json"
        )
        with pytest.raises(ContractError):
            build_scenario(
                document, terrain, load_json_file(repo_root() / "rovers" / "standard_6w.json")
            )
        return
    with pytest.raises(ContractError, match=message):
        mission_scenario(**change)


def run_session(scenario, agent, seed=1) -> tuple[MissionSession, list[dict]]:
    events: list[dict] = []
    session = MissionSession(scenario, {"agent": agent}, "agent", seed=seed, on_event=events.append)
    while not session.mission.finished:
        session.step()
    return session, events


class EndNow:
    def reset(self, brief, seed) -> None:
        pass

    def act(self, observation):
        return Action(0, 0, TaskRequest("end_mission"))


def test_ending_without_enough_science_is_not_success() -> None:
    session, _ = run_session(mission_scenario(), EndNow())
    assert session.mission.outcome is MissionOutcome.ENDED_EARLY


def test_stop_agent_at_base_scores_zero(tmp_path) -> None:
    metrics = run_mission(
        load_scenario("science_sprint"), create_agent("stop"), "s", tmp_path / "r"
    ).metrics
    assert metrics.returned_to_base is True
    assert metrics.score == 0, "sitting at base must not earn points"


def test_rover_holds_still_during_task_even_if_commanded() -> None:
    class Greedy:
        def reset(self, brief, seed) -> None:
            self.sent = False

        def act(self, observation):
            if not self.sent:
                self.sent = True
                return Action(0, 0, TaskRequest("inspect", "near"))
            return Action(0.5, 0)

    document = load_json_file(repo_root() / "scenarios" / "practice" / "science_sprint.json")
    document["mission"]["start_pose"]["position_m"] = [30, 10, 0]
    terrain = load_json_file(repo_root() / "scenarios" / "terrains" / "flat_test.json")
    from roverloom.rover_builder import load_rover_document

    scenario = build_scenario(document, terrain, load_rover_document("pathfinder_6w"))
    session = MissionSession(scenario, {"agent": Greedy()}, "agent")
    for _ in range(100):
        session.step()
    assert session.science.busy
    assert session.sim.state.distance_m == 0


# Environment events.
def fault_session(fault: dict, agent=None):
    document = load_json_file(
        repo_root() / "scenarios" / "practice" / "example_reach_position.json"
    )
    document["faults"] = [fault]
    document["sensors"] = {
        "pose_noise_m": 0.01,
        "yaw_noise_rad": 0.001,
        "speed_noise_mps": 0.0,
        "range_noise_m": 0.0,
    }
    terrain = load_json_file(repo_root() / "scenarios" / "terrains" / "flat_test.json")
    terrain["rocks"] = {"explicit": [{"center_xy": [8, 0], "radius_m": 2}]}
    from roverloom.rover_builder import load_rover_document

    scenario = build_scenario(document, terrain, load_rover_document("standard_6w"))
    return scenario


class Recorder:
    def __init__(self, action=STOP) -> None:
        self.seen: list[Observation] = []
        self.action = action

    def reset(self, brief, seed) -> None:
        pass

    def act(self, observation):
        self.seen.append(observation)
        return self.action


def test_dust_shortens_sensor_range_during_the_event_only() -> None:
    scenario = fault_session(
        {
            "type": "dust_storm",
            "start_time_s": 5,
            "duration_s": 5,
            "severity": 1.0,
            "category": "mars_inspired",
        }
    )
    recorder = Recorder()
    session = MissionSession(scenario, {"agent": recorder}, "agent")
    for _ in range(150):
        session.step()
    sees = [(o.time_s, any(r.range_m is not None for r in o.range_scan)) for o in recorder.seen]
    assert all(seen for t, seen in sees if t < 5 or t >= 10)
    assert not any(seen for t, seen in sees if 5 <= t < 10)


def test_dust_reduces_solar_generation_and_says_so(tmp_path) -> None:
    scenario = load_scenario("science_campaign")
    events: list[dict] = []
    session = MissionSession(scenario, {"agent": Recorder()}, "agent", on_event=events.append)
    while session.time_s < 505:
        session.step()
    during = session.sim.state.power_generation_w
    while session.time_s < 630:
        session.step()
    assert during < session.sim.state.power_generation_w
    started = next(
        e for e in events if e["type"] == "fault_started" and e["data"]["fault"] == "dust_storm"
    )
    assert started["data"]["category"] == "mars_inspired"


def test_immobilized_rover_does_not_move_then_recovers() -> None:
    scenario = fault_session(
        {"type": "immobilized", "start_time_s": 0, "duration_s": 5, "category": "stress_test"}
    )
    session = MissionSession(scenario, {"agent": Recorder(Action(0.5, 0))}, "agent")
    while session.time_s < 5:
        session.step()
    assert session.sim.state.distance_m == 0
    for _ in range(50):
        session.step()
    assert session.sim.state.distance_m > 0


def test_slip_burst_and_brownout_change_the_rover() -> None:
    plain = fault_session({"type": "comm_blackout", "start_time_s": 500, "duration_s": 1})
    slip = fault_session(
        {"type": "slip_burst", "start_time_s": 0, "duration_s": 100, "severity": 1.0}
    )
    power = fault_session(
        {"type": "power_brownout", "start_time_s": 0, "duration_s": 100, "severity": 1.0}
    )
    states = {}
    for name, scenario in (("plain", plain), ("slip", slip), ("power", power)):
        session = MissionSession(scenario, {"agent": Recorder(Action(0.5, 0))}, "agent")
        for _ in range(100):
            session.step()
        states[name] = session.sim.state
    assert states["slip"].distance_m < states["plain"].distance_m
    assert states["power"].energy_used_wh > states["plain"].energy_used_wh


def test_noise_burst_raises_pose_error() -> None:
    scenario = fault_session(
        {"type": "sensor_noise_burst", "start_time_s": 10, "duration_s": 20, "severity": 1.0}
    )
    recorder = Recorder()
    session = MissionSession(scenario, {"agent": recorder}, "agent")
    for _ in range(400):
        session.step()
    calm = [abs(o.estimated_pose.x_m) for o in recorder.seen if o.time_s < 10]
    noisy = [abs(o.estimated_pose.x_m) for o in recorder.seen if 10 <= o.time_s < 30]
    assert max(noisy) > max(calm) * 2


@pytest.mark.parametrize("name", ["science_campaign", "stress_blackout"])
def test_new_event_scenarios_label_every_fault(name: str) -> None:
    document = load_scenario(name).document
    for fault in document["faults"] + document.get("fault_generators", []):
        assert fault.get("category") in ("mars_inspired", "stress_test")


def test_stress_scenario_is_entirely_labelled_artificial() -> None:
    document = load_scenario("stress_blackout").document
    assert {f["category"] for f in document["faults"]} == {"stress_test"}


def test_every_practice_scenario_validates_with_every_standard_rover() -> None:
    from roverloom.rover_builder import list_designs

    for name in list_practice_scenarios():
        for rover in list_designs():
            load_scenario(name, rover=rover)


# Information boundaries for the science campaign.
def test_true_value_is_hidden_until_inspected() -> None:
    scenario = load_scenario("science_campaign")
    assert "true_value" not in json.dumps(scenario.brief().to_dict())
    validate("mission_brief", scenario.brief().to_dict())
    recorder = Recorder()
    session = MissionSession(scenario, {"agent": recorder}, "agent")
    for _ in range(40):
        session.step()
    assert recorder.seen[0].science.inspected == ()
    text = json.dumps(recorder.seen[0].to_dict())
    for hidden in ("true_value", "dust_storm", "wheel_drive", "category", "severity"):
        assert hidden not in text


def test_prompt_contains_no_hidden_data() -> None:
    scenario = load_scenario("science_campaign")
    recorder = Recorder()
    session = MissionSession(scenario, {"agent": recorder}, "agent")
    for _ in range(10):
        session.step()
    prompt = build_prompt(PlanContext(scenario.brief(), recorder.seen[0], ()))
    for hidden in ("true_value", "dust_storm", "fault", "rocks", "soft_soil", '"seed"'):
        assert hidden not in prompt.replace("fault_", "fault_").replace("failure_reasons", ""), (
            hidden
        )


# Skills.
def test_skill_contract_is_complete() -> None:
    assert set(SKILL_SPECS) == {
        "observe", "navigate_to", "inspect_target", "collect_sample",
        "transmit_data", "return_to_base", "safe_stop",
    }  # fmt: skip
    for skill in describe_skills():
        for key in ("inputs", "outputs", "preconditions", "failure_reasons", "resources"):
            assert key in skill
        assert skill["timeout_s"] > 0
        assert "timeout" in skill["failure_reasons"]


@pytest.mark.parametrize(
    "call",
    [
        {"skill": "exec", "args": {}},
        {"skill": "__import__", "args": {"name": "os"}},
        {"skill": "navigate_to", "args": {"x_m": 1}},
        {"skill": "navigate_to", "args": {"x_m": "__import__('os')", "y_m": 1}},
        {"skill": "navigate_to", "args": {"x_m": 1, "y_m": 1, "code": "print(1)"}},
        {"skill": "safe_stop"},
        {"skill": "safe_stop", "args": {}, "extra": 1},
        "safe_stop()",
        ["safe_stop"],
        None,
    ],
)
def test_bad_skill_calls_are_rejected(call: object) -> None:
    with pytest.raises(ContractError):
        parse_skill_call(call)


def observation(time_s: float, science=None, speed: float = 0.0, x: float = 0.0) -> Observation:
    return Observation(time_s, Pose(x, 0, 0, 0), 0.9, speed, 0, (), 0.0, science)


def run_executor(call: SkillCall, brief, until: float = 2000):
    executor = SkillExecutor(brief)
    executor.start(call, observation(0))
    time_s = 0.0
    while executor.busy and time_s < until:
        time_s += 0.5
        executor.step(observation(time_s))
    return executor.outcome


def test_skills_time_out_and_report_it() -> None:
    brief = load_scenario("science_sprint").brief()
    outcome = run_executor(SkillCall("navigate_to", {"x_m": 60, "y_m": 0}), brief)
    assert outcome.status is SkillStatus.FAILED
    assert outcome.reason == "timeout"
    assert outcome.elapsed_s > SKILL_SPECS["navigate_to"].timeout_s


def test_navigate_outside_map_and_return_without_base_fail_clearly() -> None:
    brief = load_scenario("science_sprint").brief()
    outcome = run_executor(SkillCall("navigate_to", {"x_m": 99999, "y_m": 0}), brief)
    assert outcome.reason == "outside_map"
    reach_only = load_scenario("example_reach_position").brief()
    assert run_executor(SkillCall("return_to_base", {}), reach_only).reason == "no_base"


def test_observe_reports_a_summary() -> None:
    brief = load_scenario("science_sprint").brief()
    outcome = run_executor(SkillCall("observe", {"duration_s": 1}), brief)
    assert outcome.status is SkillStatus.SUCCEEDED
    assert set(outcome.outputs) == set(SKILL_SPECS["observe"].outputs)


def test_safe_stop_waits_for_the_rover_to_stop() -> None:
    brief = load_scenario("science_sprint").brief()
    executor = SkillExecutor(brief)
    executor.start(SkillCall("safe_stop", {}), observation(0, speed=0.4))
    assert executor.step(observation(0.5, speed=0.4)) == STOP
    assert executor.busy
    executor.step(observation(1.0, speed=0.0))
    assert executor.outcome.status is SkillStatus.SUCCEEDED


class ScriptedPlanner:
    def __init__(self, calls) -> None:
        self.calls = list(calls)
        self.results = []

    def next_call(self, context):
        self.results = list(context.history)
        return self.calls.pop(0) if self.calls else None


@pytest.mark.parametrize(
    ("skills", "reason"),
    [
        ([SkillCall("inspect_target", {"target_id": "near"})], "out_of_range"),
        ([SkillCall("collect_sample", {"target_id": "near"})], "out_of_range"),
        ([SkillCall("transmit_data", {"wait": False})], "no_data"),
        ([SkillCall("inspect_target", {"target_id": "ghost"})], "unknown_target"),
    ],
)
def test_rover_rejections_reach_the_planner_as_failure_reasons(skills, reason: str) -> None:
    planner = ScriptedPlanner(skills)
    session = MissionSession(
        load_scenario("science_sprint"), {"agent": SkillAgent(planner)}, "agent"
    )
    for _ in range(200):
        session.step()
    assert planner.results[-1].status is SkillStatus.FAILED
    assert planner.results[-1].reason == reason
    assert reason in SKILL_SPECS[skills[0].skill].failure_reasons


def test_all_skills_work_in_one_real_mission(tmp_path) -> None:
    calls = [
        SkillCall("observe", {"duration_s": 2}),
        SkillCall("navigate_to", {"x_m": 30, "y_m": 12, "radius_m": 2.5}),
        SkillCall("inspect_target", {"target_id": "near"}),
        SkillCall("collect_sample", {"target_id": "near"}),
        SkillCall("transmit_data", {"wait": True}),
        SkillCall("return_to_base", {}),
        SkillCall("safe_stop", {"end_mission": True}),
    ]
    planner = ScriptedPlanner(calls)
    agent = SkillAgent(planner)
    decisions: list[dict] = []
    session = MissionSession(
        load_scenario("science_sprint"), {"agent": agent}, "agent", on_decision=decisions.append
    )
    while not session.mission.finished:
        session.step()
    assert session.mission.outcome is MissionOutcome.SUCCESS
    assert [r.status for r in planner.results[:6]] == [SkillStatus.SUCCEEDED] * 6
    assert planner.results[0].battery_used_fraction >= 0
    assert any("collect_sample" in d["text"] for d in decisions)


class Fake:
    def __init__(self, replies) -> None:
        self.replies = list(replies)
        self.prompts = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.replies.pop(0)


def context():
    scenario = load_scenario("science_sprint")
    return PlanContext(scenario.brief(), observation(0), ())


def test_cap_accepts_only_valid_calls() -> None:
    planner = CapPlanner(Fake(['{"skill":"observe","args":{"duration_s":1}}']))
    assert planner.next_call(context()).skill == "observe"


def test_cap_rejects_code_and_falls_back_to_safe_stop(tmp_path) -> None:
    marker = tmp_path / "pwned"
    attacks = [
        f"import os; open(r'{marker}','w')",
        f'{{"skill":"exec","args":{{"code":"open(r\'{marker}\',\'w\')"}}}}',
        "```python\nprint('hello')\n```",
    ]
    planner = CapPlanner(Fake(attacks))
    call = planner.next_call(context())
    assert call.skill == "safe_stop"
    assert len(planner.rejected) == 3
    assert not marker.exists()


def test_cap_rejects_oversized_reply() -> None:
    planner = CapPlanner(Fake(["x" * 30000] * 3))
    assert planner.next_call(context()).skill == "safe_stop"


def test_mock_model_needs_no_network_and_is_deterministic() -> None:
    first = MockLanguageModel().complete(build_prompt(context()))
    second = MockLanguageModel().complete(build_prompt(context()))
    assert first == second
    assert parse_skill_call(json.loads(first)).skill == "navigate_to"


def test_mock_cap_agent_completes_a_mission() -> None:
    session, _ = run_session(load_scenario("science_sprint"), create_agent("cap-mock"))
    assert session.mission.outcome is MissionOutcome.SUCCESS
    assert session.science.transmitted_value > 0


@pytest.mark.parametrize("approved", [True, False])
def test_human_approval_controls_sampling(approved: bool) -> None:
    seen = []

    def approver(call: SkillCall) -> bool:
        seen.append(call.skill)
        return approved

    session, _ = run_session(load_scenario("science_sprint"), HumanApprovalAgent(approver))
    assert "collect_sample" in seen or "transmit_data" in seen
    assert (session.science.transmitted_value > 0) is approved
    assert bool(session.science.collected) is approved


def test_human_approval_waits_when_nobody_answers() -> None:
    agent = HumanApprovalAgent()
    session = MissionSession(load_scenario("science_sprint"), {"agent": agent}, "agent")
    while session.time_s < 400 and agent.pending is None:
        session.step()
    assert agent.pending is not None
    pending = agent.pending
    for _ in range(100):
        session.step()
    assert agent.pending == pending, "the rover must wait for an answer"
    assert session.sim.state.ground_speed_mps == 0
    agent.answer(True)
    for _ in range(40):
        session.step()
    assert agent.pending != pending


def test_planner_copes_with_reach_only_mission() -> None:
    session, _ = run_session(
        load_scenario("example_reach_position"), create_agent("mission-planner")
    )
    assert session.mission.outcome is MissionOutcome.SUCCESS


def test_planner_uses_only_public_inputs() -> None:
    planner = MissionPlanner(load_scenario("science_campaign").brief())
    assert not any("scenario" in name or "sim" in name for name in vars(planner))


def test_data_windows_are_respected_by_the_planner(tmp_path) -> None:
    result = run_mission(
        load_scenario("science_sprint"), create_agent("mission-planner"), "m", tmp_path / "r"
    )
    assert result.metrics.science_value > 0
    from roverloom.runlog import load_run

    run = load_run(result.directory)
    rejected = [e for e in run.events if e["type"] == "task_rejected"]
    assert not [e for e in rejected if e["data"]["reason"] == "rover_moving"]
