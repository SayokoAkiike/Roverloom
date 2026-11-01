"""Whole missions: outcomes, faults, logs, replay, and scoring."""

import json
from pathlib import Path

import pytest
from conftest import MakeScenario

from roverloom.agents import create_agent
from roverloom.api import Action, MissionBrief, MissionOutcome, Observation
from roverloom.contract import ContractError, validate
from roverloom.evaluate import Metrics, aggregate, evaluate_run
from roverloom.replay import Replay
from roverloom.runlog import load_run
from roverloom.runner import run_mission
from roverloom.session import MissionSession
from roverloom.world import load_scenario

FORWARD = Action(0.5, 0.0)


class Scripted:
    """Agent returning a fixed action, and recording what it saw."""

    def __init__(self, action: Action = FORWARD) -> None:
        self.action = action
        self.seen: list[Observation] = []
        self.brief: MissionBrief | None = None

    def reset(self, brief: MissionBrief, seed: int) -> None:
        self.brief = brief

    def act(self, observation: Observation) -> Action:
        self.seen.append(observation)
        return self.action


def events_of(scenario, source, **kwargs) -> tuple[MissionSession, list[dict]]:
    events: list[dict] = []
    session = MissionSession(scenario, {"agent": source}, "agent", on_event=events.append, **kwargs)
    while not session.mission.finished:
        session.step()
    return session, events


def types(events: list[dict]) -> list[str]:
    return [event["type"] for event in events]


def test_mission_succeeds_at_target(make_scenario: MakeScenario) -> None:
    session, events = events_of(make_scenario(), create_agent("waypoint"))
    assert session.mission.outcome is MissionOutcome.SUCCESS
    assert types(events)[0] == "mission_started"
    assert types(events)[-2:] == ["target_reached", "mission_ended"]


def test_objectives_complete_in_order(make_scenario: MakeScenario) -> None:
    objectives = [
        {"type": "reach_position", "position_m": [10, 0, 0], "radius_m": 2},
        {"type": "reach_position", "position_m": [10, 10, 0], "radius_m": 2},
    ]
    session, events = events_of(
        make_scenario(mission={"objectives": objectives}), create_agent("waypoint")
    )
    assert session.mission.outcome is MissionOutcome.SUCCESS
    reached = [e["data"]["index"] for e in events if e["type"] == "target_reached"]
    assert reached == [0, 1]


def test_time_limit_ends_mission_exactly(make_scenario: MakeScenario) -> None:
    session, _ = events_of(make_scenario(mission={"time_limit_s": 5}), create_agent("stop"))
    assert session.mission.outcome is MissionOutcome.TIME_LIMIT
    assert session.time_s == pytest.approx(5.0)


def test_battery_depletion_ends_mission(make_scenario: MakeScenario) -> None:
    session, _ = events_of(make_scenario(rover={"battery_capacity_wh": 1}), create_agent("stop"))
    assert session.mission.outcome is MissionOutcome.BATTERY_DEPLETED


def test_energy_limit_ends_mission(make_scenario: MakeScenario) -> None:
    session, _ = events_of(make_scenario(mission={"energy_limit_wh": 0.5}), create_agent("stop"))
    assert session.mission.outcome is MissionOutcome.ENERGY_LIMIT


class Raises(Scripted):
    def act(self, observation: Observation) -> Action:
        raise RuntimeError("agent bug")


class ReturnsNonsense(Scripted):
    def act(self, observation: Observation) -> Action:
        return "forward"  # type: ignore[return-value]


class ReturnsNaN(Scripted):
    def act(self, observation: Observation) -> Action:
        return Action(float("nan"), 0.0)


@pytest.mark.parametrize("agent", [Raises, ReturnsNonsense, ReturnsNaN])
def test_failing_agent_ends_mission_safely(make_scenario: MakeScenario, agent: type) -> None:
    session, events = events_of(make_scenario(), agent())
    assert session.mission.outcome is MissionOutcome.AGENT_ERROR
    assert "agent_error" in types(events)


def test_latency_delays_observation_and_command(make_scenario: MakeScenario) -> None:
    scenario = make_scenario(scenario={"comms": {"latency_s": 1.0, "loss_probability": 0.0}})
    agent = Scripted()
    session = MissionSession(scenario, {"agent": agent}, "agent")
    for _ in range(9):
        session.step()
    assert agent.seen == []  # Nothing arrives before one second.
    session.step()
    session.step()
    assert agent.seen[0].time_s == 0.0
    assert session.sim.state.wheel_speed_mps == 0.0  # The reply is still in flight.
    for _ in range(12):
        session.step()
    assert session.sim.state.wheel_speed_mps > 0.0


def test_blackout_triggers_watchdog_and_recovers(make_scenario: MakeScenario) -> None:
    faults = [{"type": "comm_blackout", "start_time_s": 2, "duration_s": 5}]
    scenario = make_scenario(scenario={"faults": faults}, mission={"time_limit_s": 20})
    objective = [{"type": "reach_position", "position_m": [50, 0, 0], "radius_m": 1}]
    scenario = make_scenario(
        scenario={"faults": faults}, mission={"time_limit_s": 20, "objectives": objective}
    )
    _, events = events_of(scenario, Scripted())
    order = types(events)
    assert order.index("fault_started") < order.index("watchdog_stop")
    assert order.index("fault_ended") < order.index("watchdog_cleared")


def test_sensor_dropout_blanks_scan_only_during_fault(make_scenario: MakeScenario) -> None:
    rocks = {"explicit": [{"center_xy": [6, 0], "radius_m": 1}]}
    faults = [{"type": "sensor_dropout", "start_time_s": 1, "duration_s": 2}]
    agent = Scripted(Action(0, 0))
    scenario = make_scenario(
        scenario={"faults": faults}, terrain={"rocks": rocks}, mission={"time_limit_s": 5}
    )
    events_of(scenario, agent)
    for observation in agent.seen:
        sees_rock = any(r.range_m is not None for r in observation.range_scan)
        assert sees_rock == (not 1.0 <= observation.time_s < 3.0), observation.time_s


def test_wheel_failure_is_logged_and_applies(make_scenario: MakeScenario) -> None:
    faults = [{"type": "wheel_drive_failure", "wheel": "rear_left", "start_time_s": 1}]
    session, events = events_of(
        make_scenario(scenario={"faults": faults}), create_agent("waypoint")
    )
    assert session.sim.state.failed_wheels == {"rear_left"}
    assert [e["data"].get("wheel") for e in events if e["type"] == "fault_started"] == ["rear_left"]


def test_switching_driver_logs_and_rejects_old_source(make_scenario: MakeScenario) -> None:
    commands: list[dict] = []
    events: list[dict] = []
    manual, agent = Scripted(Action(0.1, 0)), Scripted(Action(0.3, 0))
    session = MissionSession(
        make_scenario(), {"manual": manual, "agent": agent}, "manual",
        on_command=commands.append, on_event=events.append,
    )  # fmt: skip
    for _ in range(10):
        session.step()
    session.set_active_source("agent")
    for _ in range(30):
        session.step()
    assert "source_changed" in types(events)
    assert {c["source"] for c in commands} == {"manual", "agent"}
    assert session.router.current(session.time_s).linear_velocity_mps == 0.3
    # Both drivers use the same message and path.
    assert manual.seen and agent.seen


def test_stepping_after_finish_does_nothing(make_scenario: MakeScenario) -> None:
    session, _ = events_of(make_scenario(mission={"time_limit_s": 1}), create_agent("stop"))
    before = session.step_index
    session.step()
    assert session.step_index == before


def _run(
    tmp_path: Path, name: str = "run", agent: str = "replanner", scenario: str = "demo_traverse"
):
    return run_mission(load_scenario(scenario), create_agent(agent), agent, tmp_path / name, seed=3)


def test_run_directory_is_complete_and_conforms(tmp_path: Path) -> None:
    result = _run(tmp_path)
    names = {p.name for p in result.directory.iterdir()}
    assert names == {
        "run.json", "scenario.json", "terrain.json", "rover.json", "metrics.json",
        "telemetry.jsonl", "commands.jsonl", "events.jsonl",
    }  # fmt: skip
    run = load_run(result.directory)  # Validates every line against its schema.
    manifest = run.manifest
    assert manifest["seed"] == 3
    assert manifest["model_version"]
    assert manifest["environment"]["python"]
    assert manifest["environment"]["uv_lock_sha256"]
    assert "git_commit" in manifest["environment"]
    assert manifest["wall_time_s"] >= 0
    assert manifest["scenario_id"] == "demo_traverse"
    validate("run_manifest", manifest)


def test_score_is_recomputed_from_logs_alone(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert evaluate_run(load_run(result.directory)) == result.metrics
    stored = json.loads((result.directory / "metrics.json").read_text(encoding="utf-8"))
    assert stored == result.metrics.to_dict()


def test_metrics_values_on_a_known_run(make_scenario: MakeScenario, tmp_path: Path) -> None:
    faults = [{"type": "wheel_drive_failure", "wheel": "rear_left", "start_time_s": 5}]
    scenario = make_scenario(scenario={"faults": faults})
    metrics = run_mission(scenario, create_agent("waypoint"), "w", tmp_path / "r").metrics
    assert metrics.success
    assert metrics.targets_reached == metrics.targets_total == 1
    assert 16 < metrics.distance_m < 22
    assert metrics.faults == 1
    assert metrics.faults_recovered == 1
    assert metrics.mean_recovery_time_s is not None
    assert 0 < metrics.score <= 100


def test_failed_mission_scores_low_and_does_not_recover(
    make_scenario: MakeScenario, tmp_path: Path
) -> None:
    faults = [{"type": "wheel_drive_failure", "wheel": "rear_left", "start_time_s": 5}]
    scenario = make_scenario(scenario={"faults": faults}, mission={"time_limit_s": 20})
    metrics = run_mission(scenario, create_agent("stop"), "s", tmp_path / "r").metrics
    assert not metrics.success
    assert metrics.score == 0
    assert metrics.faults == 1
    assert metrics.faults_recovered == 0
    assert metrics.mean_recovery_time_s is None


def test_collisions_lower_score(make_scenario: MakeScenario, tmp_path: Path) -> None:
    clear = make_scenario()
    rocks = {"explicit": [{"center_xy": [8, 0], "radius_m": 1}]}
    blocked = make_scenario(terrain={"rocks": rocks}, mission={"time_limit_s": 30})
    assert run_mission(clear, create_agent("waypoint"), "w", tmp_path / "a").metrics.collisions == 0
    assert (
        run_mission(blocked, create_agent("waypoint"), "w", tmp_path / "b").metrics.collisions >= 1
    )


def test_aggregate() -> None:
    win = Metrics("success", True, 1, 1, 10, 5, 2, 0, 1, 1, 2.0, 90)
    lose = Metrics("time_limit", False, 0, 1, 20, 1, 9, 1, 1, 0, None, 0)
    summary = aggregate([win, lose])
    assert summary["success_rate"] == 0.5
    assert summary["mean_score"] == 45
    assert summary["mean_success_time_s"] == 10  # Failed runs do not count toward time.
    assert summary["fault_recovery_rate"] == 0.5
    assert aggregate([]) == {"runs": 0}


# Corrupt and tampered logs must never load.
def _tamper_telemetry_value(directory: Path) -> None:
    path = directory / "telemetry.jsonl"
    path.write_bytes(path.read_bytes().replace(b'"energy_used_wh":', b'"energy_used_wh":1', 1))


def _truncate(directory: Path) -> None:
    path = directory / "events.jsonl"
    path.write_bytes(path.read_bytes()[:-5])


def _delete(directory: Path) -> None:
    (directory / "commands.jsonl").unlink()


def _delete_manifest(directory: Path) -> None:
    (directory / "run.json").unlink()


def _corrupt_manifest(directory: Path) -> None:
    (directory / "run.json").write_text("{not json", encoding="utf-8")


def _change_scenario(directory: Path) -> None:
    path = directory / "scenario.json"
    path.write_bytes(path.read_bytes().replace(b'"seed":7', b'"seed":8'))


@pytest.mark.parametrize(
    "damage",
    [
        _tamper_telemetry_value,
        _truncate,
        _delete,
        _delete_manifest,
        _corrupt_manifest,
        _change_scenario,
    ],
)
def test_damaged_run_is_rejected(tmp_path: Path, damage) -> None:
    directory = _run(tmp_path, agent="stop").directory
    damage(directory)
    with pytest.raises(ContractError):
        load_run(directory)


def _reseal(directory: Path) -> None:
    from roverloom.contract import dump_json, sha256_bytes

    manifest = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    for key, name in (("telemetry", "telemetry.jsonl"), ("events", "events.jsonl")):
        manifest["logs_sha256"][key] = sha256_bytes((directory / name).read_bytes())
    (directory / "run.json").write_text(dump_json(manifest) + "\n", encoding="utf-8", newline="\n")


@pytest.mark.parametrize(
    ("file", "transform", "message"),
    [
        ("telemetry.jsonl", lambda lines: ["{bad json"] + lines, "telemetry.jsonl:1"),
        ("telemetry.jsonl", lambda lines: ['{"schema_version":0}'] + lines, "telemetry.jsonl:1"),
        ("telemetry.jsonl", lambda lines: list(reversed(lines)), "backwards"),
        ("events.jsonl", lambda lines: lines[:-1], "mission_ended|sequence"),
        ("events.jsonl", lambda lines: lines[1:], "sequence"),
    ],
)
def test_resealed_bad_content_is_still_rejected(
    tmp_path: Path, file: str, transform, message: str
) -> None:
    # Someone who also updates the hashes must still fail the content checks.
    directory = _run(tmp_path, agent="stop", scenario="example_reach_position").directory
    path = directory / file
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(transform(lines)) + "\n", encoding="utf-8", newline="\n")
    _reseal(directory)
    with pytest.raises(ContractError, match=message):
        load_run(directory)


def test_run_directory_is_not_overwritten_by_accident(tmp_path: Path) -> None:
    _run(tmp_path, agent="stop")
    with pytest.raises(ContractError, match="not empty"):
        _run(tmp_path, agent="stop")


def test_overwrite_refuses_directories_with_unknown_files(tmp_path: Path) -> None:
    directory = tmp_path / "mine"
    directory.mkdir()
    (directory / "thesis.docx").write_text("important", encoding="utf-8")
    with pytest.raises(ContractError, match="unknown files"):
        run_mission(
            load_scenario("demo_traverse"), create_agent("stop"), "s", directory, overwrite=True
        )
    assert (directory / "thesis.docx").exists()


def test_replay_interpolates_and_clamps(tmp_path: Path) -> None:
    run = load_run(_run(tmp_path).directory)
    replay = Replay(run)
    records = run.telemetry
    a, b = records[100], records[101]
    middle = (a["time_s"] + b["time_s"]) / 2
    frame = replay.frame_at(middle)
    expected = (a["pose"]["position_m"][0] + b["pose"]["position_m"][0]) / 2
    assert frame.pose.x_m == pytest.approx(expected)
    assert replay.frame_at(-5).pose.x_m == pytest.approx(records[0]["pose"]["position_m"][0])
    end = replay.frame_at(1e9)
    assert end.pose.x_m == pytest.approx(records[-1]["pose"]["position_m"][0])
    assert end.battery_fraction == records[-1]["battery_fraction"]


def test_replay_reports_events_and_fault_history(tmp_path: Path) -> None:
    run = load_run(_run(tmp_path).directory)
    replay = Replay(run)
    assert [e["type"] for e in replay.events_until(0.0)] == ["mission_started"]
    assert any(e["type"] == "fault_started" for e in replay.events_until(replay.duration_s))
    assert replay.frame_at(149).failed_wheels == ()
    assert replay.frame_at(160).failed_wheels == ("middle_left",)
