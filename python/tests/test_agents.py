"""Sample agents, custom agents, skill plans, and what agents are allowed to know."""

import dataclasses
import json
from pathlib import Path

import pytest
from conftest import MakeScenario

from roverloom.agents import BUILTIN_AGENTS, create_agent
from roverloom.agents.skills import SKILLS, SkillPlanAgent, load_plan
from roverloom.api import Action, MissionBrief, MissionOutcome, Observation
from roverloom.contract import ContractError, repo_root
from roverloom.runner import run_mission
from roverloom.session import MissionSession
from roverloom.world import load_scenario


def run(scenario, agent) -> MissionSession:
    session = MissionSession(scenario, {"agent": agent}, "agent")
    while not session.mission.finished:
        session.step()
    return session


@pytest.mark.parametrize("name", sorted(BUILTIN_AGENTS))
@pytest.mark.parametrize("scenario", ["example_reach_position", "boulder_gap"])
def test_every_agent_finishes_without_error(name: str, scenario: str) -> None:
    session = run(load_scenario(scenario), create_agent(name))
    assert session.mission.finished
    assert session.mission.outcome is not MissionOutcome.AGENT_ERROR


def test_stop_agent_never_moves() -> None:
    session = run(load_scenario("example_reach_position"), create_agent("stop"))
    assert session.sim.state.distance_m == 0


def test_waypoint_agent_succeeds_on_open_ground() -> None:
    session = run(load_scenario("example_reach_position"), create_agent("waypoint"))
    assert session.mission.outcome is MissionOutcome.SUCCESS


def test_waypoint_agent_is_blocked_by_the_wall() -> None:
    session = run(load_scenario("boulder_gap"), create_agent("waypoint"))
    assert session.mission.outcome is MissionOutcome.TIME_LIMIT


def test_replanner_finds_the_gap_for_every_seed() -> None:
    for seed in (1, 2, 3, 4, 5):
        session = MissionSession(
            load_scenario("boulder_gap"), {"agent": create_agent("replanner")}, "agent", seed=seed
        )
        while not session.mission.finished:
            session.step()
        assert session.mission.outcome is MissionOutcome.SUCCESS, seed


def test_reactive_avoids_a_single_rock(make_scenario: MakeScenario) -> None:
    rocks = {"explicit": [{"center_xy": [10, 0], "radius_m": 2}]}
    session = run(make_scenario(terrain={"rocks": rocks}), create_agent("reactive"))
    assert session.mission.outcome is MissionOutcome.SUCCESS


# Custom agents, the way a participant would add one.
CUSTOM_AGENT = """
from roverloom.api import Action

class MyAgent:
    def reset(self, brief, seed):
        self.speed = brief.max_speed_mps
    def act(self, observation):
        return Action(self.speed, 0.0)
"""


def test_custom_agent_file_loads_and_runs(tmp_path: Path, make_scenario: MakeScenario) -> None:
    path = tmp_path / "my_agent.py"
    path.write_text(CUSTOM_AGENT, encoding="utf-8")
    session = run(make_scenario(), create_agent(f"{path}:MyAgent"))
    assert session.mission.outcome is MissionOutcome.SUCCESS


def test_documented_example_agent_works() -> None:
    path = repo_root() / "python" / "examples" / "my_agent.py"
    session = run(load_scenario("example_reach_position"), create_agent(f"{path}:CautiousAgent"))
    assert session.mission.outcome is MissionOutcome.SUCCESS


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ("nonexistent", "unknown agent"),
        ("missing.py:Agent", "not found"),
        ("roverloom.api:NoSuchClass", "no class"),
        ("roverloom.api:SCHEMA_VERSION", "not a class"),
        ("roverloom.api:Action.__name__", "no class"),
    ],
)
def test_bad_agent_specs_are_rejected(spec: str, message: str) -> None:
    with pytest.raises(ContractError, match=message):
        create_agent(spec)


def test_class_without_required_methods_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.py"
    path.write_text("class Bad:\n    def reset(self, brief, seed): pass\n", encoding="utf-8")
    with pytest.raises(ContractError, match="act"):
        create_agent(f"{path}:Bad")


# Information boundaries.
FORBIDDEN_WORDS = (
    "rock",
    "soil",
    "slip",
    "fault",
    "wheel",
    "noise",
    "terrain",
    "seed",
    "true",
    "truth",
)


@pytest.mark.parametrize("message", [MissionBrief, Observation])
def test_agent_messages_have_no_ground_truth_fields(message: type) -> None:
    for field in dataclasses.fields(message):
        assert not any(word in field.name for word in FORBIDDEN_WORDS), field.name


def test_brief_document_does_not_contain_hidden_scenario_data() -> None:
    scenario = load_scenario("demo_traverse")
    text = json.dumps(scenario.brief().to_dict())
    for word in FORBIDDEN_WORDS:
        assert word not in text, word


class Recorder:
    def __init__(self) -> None:
        self.observations: list[Observation] = []

    def reset(self, brief: MissionBrief, seed: int) -> None:
        pass

    def act(self, observation: Observation) -> Action:
        self.observations.append(observation)
        return Action(0.5, 0.0)


def observations_with_faults(make_scenario: MakeScenario, faults: list[dict]) -> list[Observation]:
    recorder = Recorder()
    noisy = {
        "pose_noise_m": 0.1,
        "yaw_noise_rad": 0.01,
        "speed_noise_mps": 0.01,
        "range_noise_m": 0.01,
    }
    run(
        make_scenario(scenario={"faults": faults, "sensors": noisy}, mission={"time_limit_s": 40}),
        recorder,
    )
    return recorder.observations


def test_future_faults_do_not_leak_before_they_start(make_scenario: MakeScenario) -> None:
    fault_time = 20.0
    without = observations_with_faults(make_scenario, [])
    faulty = observations_with_faults(
        make_scenario,
        [{"type": "wheel_drive_failure", "wheel": "rear_left", "start_time_s": fault_time}],
    )
    before = [o for o in without if o.time_s < fault_time]
    assert before == [o for o in faulty if o.time_s < fault_time]
    assert without != faulty  # The fault does matter afterward.


def test_observed_pose_differs_from_truth_under_noise(make_scenario: MakeScenario) -> None:
    noisy = {
        "pose_noise_m": 0.5,
        "yaw_noise_rad": 0.05,
        "speed_noise_mps": 0.05,
        "range_noise_m": 0.1,
    }
    recorder = Recorder()
    telemetry: list[dict] = []
    session = MissionSession(
        make_scenario(scenario={"sensors": noisy}), {"agent": recorder}, "agent",
        on_telemetry=telemetry.append,
    )  # fmt: skip
    while not session.mission.finished:
        session.step()
    truth = {round(t["time_s"], 1): t["pose"]["position_m"][0] for t in telemetry}
    differences = [
        abs(o.estimated_pose.x_m - truth[round(o.time_s, 1)])
        for o in recorder.observations
        if round(o.time_s, 1) in truth
    ]
    assert max(differences) > 0.2


def test_session_does_not_hand_agents_a_way_to_truth(make_scenario: MakeScenario) -> None:
    class Inspector(Recorder):
        def reset(self, brief: MissionBrief, seed: int) -> None:
            self.brief = brief

    inspector = Inspector()
    run(make_scenario(), inspector)
    # Messages are frozen values with no references back to the simulation.
    with pytest.raises(dataclasses.FrozenInstanceError):
        inspector.brief.time_limit_s = 1e9  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        inspector.observations[0].battery_fraction = 1.0  # type: ignore[misc]
    assert not hasattr(inspector.brief, "__dict__")


# Skill plans are data. Nothing in them is executed.
def plan_file(tmp_path: Path, document: object) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_plan_runs_named_skills_in_order(make_scenario: MakeScenario) -> None:
    plan = {
        "schema_version": 0,
        "steps": [
            {"skill": "wait", "duration_s": 3},
            {"skill": "turn_to", "yaw_rad": 0.5},
            {"skill": "go_to", "x_m": 5, "y_m": 5},
            {"skill": "go_to_next_target"},
        ],
    }
    session = run(make_scenario(), SkillPlanAgent(plan))
    assert session.mission.outcome is MissionOutcome.SUCCESS
    assert session.time_s > 3


def test_default_plan_visits_all_targets() -> None:
    session = run(load_scenario("example_reach_position"), SkillPlanAgent())
    assert session.mission.outcome is MissionOutcome.SUCCESS


@pytest.mark.parametrize(
    "steps",
    [
        [{"skill": "exec", "code": "import os"}],
        [{"skill": "__import__"}],
        [{"skill": "go_to", "x_m": 1, "y_m": 1, "callback": "os.system"}],
        [{"skill": "go_to", "x_m": "__import__('os')", "y_m": 1}],
        [{"skill": "wait", "duration_s": -1}],
        [],
    ],
)
def test_plan_with_anything_unknown_is_rejected(tmp_path: Path, steps: list) -> None:
    document = {"schema_version": 0, "steps": steps}
    with pytest.raises(ContractError):
        load_plan(plan_file(tmp_path, document))
    with pytest.raises(ContractError):
        SkillPlanAgent(document)


def test_skill_list_cannot_be_changed_at_runtime() -> None:
    with pytest.raises(TypeError):
        SKILLS["exec"] = exec  # type: ignore[index]


def test_run_with_custom_agent_records_its_name(
    tmp_path: Path, make_scenario: MakeScenario
) -> None:
    result = run_mission(make_scenario(), create_agent("waypoint"), "my-name", tmp_path / "r")
    assert result.manifest["agent"] == "my-name"
