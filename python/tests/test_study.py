"""Scientific tracks, intervals, failure causes, decisions, and information separation."""

import copy
import json
from pathlib import Path

import pytest
from conftest import MakeScenario

from roverloom.agents import create_agent
from roverloom.api import STOP, Action, TaskRequest
from roverloom.contract import ContractError, dump_json, validate
from roverloom.league import load_benchmark
from roverloom.runlog import load_run
from roverloom.runner import run_mission
from roverloom.session import MissionSession
from roverloom.study import (
    FAILURE_CAUSES,
    bootstrap_ci,
    classify_run,
    distribution_report,
    paired_difference,
    run_jobs,
    run_study,
    summarize,
    wilson_interval,
)
from roverloom.world import build_scenario, load_scenario

BENCH = "roverloom-bench-v2"


def test_bootstrap_is_deterministic_and_contains_the_mean() -> None:
    values = [1.0, 2.0, 2.5, 8.0, 3.0, 2.0]
    first = bootstrap_ci(values)
    assert first == bootstrap_ci(values)
    assert first[1] <= first[0] <= first[2]


def test_bootstrap_edge_cases() -> None:
    assert bootstrap_ci([5.0]) == (5.0, 5.0, 5.0)
    assert bootstrap_ci([3.0, 3.0, 3.0]) == (3.0, 3.0, 3.0)
    with pytest.raises(ContractError):
        bootstrap_ci([])


@pytest.mark.parametrize(("wins", "count"), [(0, 20), (20, 20), (10, 20), (1, 1), (0, 1)], ids=str)
def test_wilson_interval_stays_in_range_and_is_not_degenerate(wins: int, count: int) -> None:
    low, high = wilson_interval(wins, count)
    assert 0.0 <= low <= wins / count <= high <= 1.0
    assert high - low > 0


def rows_for(agent: str, values: list[float]) -> list[dict]:
    return [
        {"scenario": "s", "seed": seed, "agent": agent, "achievement": value}
        for seed, value in enumerate(values)
    ]


def test_paired_difference_uses_matched_seeds() -> None:
    rows = rows_for("a", [10, 20, 30, 40]) + rows_for("b", [5, 15, 25, 35])
    result = paired_difference(rows, "a", "b")
    assert result["mean_difference"] == 5
    assert result["ci95"] == [5, 5]
    assert result["wins"] == 4 and result["interval_excludes_zero"]


def test_paired_difference_refuses_unmatched_agents() -> None:
    with pytest.raises(ContractError, match="no shared runs"):
        paired_difference(rows_for("a", [1, 2]), "a", "ghost")


def run_with(scenario, agent, tmp_path: Path, seed: int = 1):
    return load_run(run_mission(scenario, agent, "x", tmp_path / "run", seed, True).directory)


class Script:
    """Drives at a fixed speed, optionally requesting one task at the start."""

    def __init__(self, speed: float = 0.0, task: TaskRequest | None = None) -> None:
        self.speed, self.task = speed, task

    def reset(self, brief, seed) -> None:
        pass

    def act(self, observation):
        task, self.task = self.task, None
        return Action(self.speed, 0.0, task)


class Crash(Script):
    def act(self, observation):
        raise RuntimeError("boom")


def science_mission(**changes: object) -> dict:
    science = {
        "targets": [
            {
                "id": "a",
                "position_m": [3, 0, 0],
                "radius_m": 8,
                "prior_value": 2,
                "true_value": 2,
                "inspect_s": 1,
                "collect_s": 1,
            }
        ],
        "transmit_s_per_item": 1,
        "success_value": 0.1,
        **changes,
    }
    return {"objectives": [], "science": science}


@pytest.mark.parametrize(
    ("build", "agent", "expected"),
    [
        ({"mission": {"time_limit_s": 3}}, Script(0.1), "stalled"),
        ({"mission": {"time_limit_s": 30}}, Script(1.0), "out_of_time"),
        ({"mission": {"time_limit_s": 5}}, Crash(), "agent_error"),
        (
            {"mission": {"time_limit_s": 30, "energy_limit_wh": 0.05}},
            Script(0.0),
            "energy_exhausted",
        ),
        (
            {
                "mission": {"time_limit_s": 30},
                "scenario": {
                    "faults": [{"type": "immobilized", "start_time_s": 0, "duration_s": 100}]
                },
            },
            Script(1.0),
            "immobilized",
        ),
        (
            {
                "mission": {"time_limit_s": 30},
                "scenario": {
                    "faults": [
                        {"type": "wheel_drive_failure", "wheel": "front_left", "start_time_s": 1}
                    ]
                },
            },
            Script(1.0),
            "degraded_mobility",
        ),
        (
            {
                "mission": {"time_limit_s": 80},
                "terrain": {
                    "rocks": {"explicit": [{"center_xy": [4, 0], "radius_m": 1}]},
                },
            },
            Script(1.0),
            "blocked_by_obstacles",
        ),
        (
            {"mission": {**science_mission(), "time_limit_s": 30}},
            Script(0.0, TaskRequest("end_mission")),
            "insufficient_science",
        ),
        (
            {
                "mission": {
                    **science_mission(
                        base={"position_m": [50, 0, 0], "radius_m": 1, "required": True}
                    ),
                    "time_limit_s": 30,
                }
            },
            Script(0.0, TaskRequest("end_mission")),
            "did_not_return",
        ),
    ],
    ids=[
        "stalled",
        "out-of-time",
        "agent-error",
        "energy",
        "immobilized",
        "degraded",
        "hit-rock-once",
        "no-science",
        "not-home",
    ],
)
def test_failure_causes_from_logs(
    make_scenario: MakeScenario, tmp_path, build, agent, expected
) -> None:
    run = run_with(make_scenario(**build), agent, tmp_path)
    result = classify_run(run)
    assert result["cause"] == expected
    assert result["cause"] in FAILURE_CAUSES


def test_success_and_missing_capability(tmp_path: Path) -> None:
    good = run_mission(
        load_scenario("science_sprint"), create_agent("mission-planner"), "m", tmp_path / "g", 1
    )
    assert classify_run(load_run(good.directory))["cause"] == "success"
    weak = run_mission(
        load_scenario("science_campaign", rover="scout_4w"),
        create_agent("mission-planner"),
        "m",
        tmp_path / "w",
        1,
    )
    assert classify_run(load_run(weak.directory))["cause"] == "capability_missing"


def test_tracks_are_separate_and_every_scenario_is_labeled_honestly() -> None:
    benchmark = load_benchmark(BENCH)
    tracks = benchmark["tracks"]
    names = [name for track in tracks.values() for name in track]
    assert len(names) == len(set(names)), "a scenario can only be evidence for one track"
    for name in tracks["stress"]:
        document = load_scenario(name).document
        faults = [*document["faults"], *document.get("fault_generators", [])]
        assert faults, name
        # Invented stress must never be presented as Mars-derived.
        assert {f.get("category") for f in faults} == {"stress_test"}, name


def test_compound_scenarios_really_have_overlapping_faults() -> None:
    for name in ("compound_drive_power", "compound_late_cascade"):
        faults = load_scenario(name).document["faults"]
        # Permanent faults count as active forever after they start.
        spans = [(f["start_time_s"], f["start_time_s"] + f.get("duration_s", 1e9)) for f in faults]
        most = max(sum(1 for a, b in spans if a <= start < b) for start, _ in spans)
        assert most >= 3, name


def test_out_of_distribution_scenarios_leave_the_standard_range() -> None:
    report = distribution_report(load_benchmark(BENCH))
    assert set(report) == set(load_benchmark(BENCH)["tracks"]["out_of_distribution"])
    for name, outside in report.items():
        assert outside, f"{name} lies inside the standard range"


def test_declared_uncertainty_differs_from_the_truth_on_purpose() -> None:
    for name in load_benchmark(BENCH)["tracks"]["misestimated_uncertainty"]:
        scenario = load_scenario(name)
        uncertainty = scenario.document["uncertainty"]
        declared = uncertainty["declared"]
        assert (
            uncertainty.get("inspection_noise_sd", 0.0) > declared["inspection_noise_sd"] * 5
            or "pose_bias_m" in uncertainty
        ), name


# Information separation.
class Recorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def reset(self, brief, seed) -> None:
        self.messages.append(dump_json(brief.to_dict()))

    def act(self, observation):
        self.messages.append(dump_json(observation.to_dict()))
        return Action(0.3, 0.05)


def record(document: dict, terrain: dict, rover: dict, seconds: float, seed: int = 3) -> list[str]:
    agent = Recorder()
    session = MissionSession(
        build_scenario(document, terrain, rover), {"agent": agent}, "agent", seed=seed
    )
    while session.time_s < seconds and not session.mission.finished:
        session.step()
    return agent.messages


def documents(name: str = "mis_both") -> tuple[dict, dict, dict]:
    scenario = load_scenario(name)
    return (
        copy.deepcopy(scenario.document),
        copy.deepcopy(scenario.terrain.document),
        copy.deepcopy(scenario.rover.document),
    )


def test_changing_hidden_truth_does_not_change_what_an_agent_sees() -> None:
    document, terrain, rover = documents()
    baseline = record(document, terrain, rover, 100.0)

    hidden = copy.deepcopy(document)
    for target in hidden["mission"]["science"]["targets"]:
        target["true_value"] = target["true_value"] + 3.21  # Uninspected values.
    hidden["uncertainty"]["inspection_noise_sd"] = 9.0  # The real error, not the declared one.
    hidden["faults"] = [
        {"type": "dust_storm", "start_time_s": 500, "duration_s": 10, "severity": 0.9},
        {"type": "wheel_drive_failure", "wheel": "rear_left", "start_time_s": 700},
    ]
    assert record(hidden, terrain, rover, 100.0) == baseline


def test_rocks_out_of_sensor_range_are_invisible() -> None:
    document, terrain, rover = documents("science_sprint")
    baseline = record(document, terrain, rover, 40.0)
    changed = copy.deepcopy(terrain)
    rocks = changed.setdefault("rocks", {}).setdefault("explicit", [])
    rocks.append({"center_xy": [95, 35], "radius_m": 2})
    assert record(document, changed, rover, 40.0) == baseline


def test_canary_values_never_reach_an_agent() -> None:
    document, terrain, rover = documents()
    canaries = {
        "true_value": 7.7713,
        "inspection_noise_sd": 2.71828,
        "bias": 3.14159,
        "fault_time": 1234.567,
        "seed": 987654321,
    }
    for target in document["mission"]["science"]["targets"]:
        target["true_value"] = canaries["true_value"]
    document["uncertainty"]["inspection_noise_sd"] = canaries["inspection_noise_sd"]
    document["faults"] = [
        {"type": "dust_storm", "start_time_s": canaries["fault_time"], "duration_s": 5}
    ]
    document["mission"]["science"]["success_value"] = 0.1
    document["uncertainty"]["pose_bias_m"] = [canaries["bias"], 0.0]
    text = "\n".join(record(document, terrain, rover, 60.0, seed=canaries["seed"]))
    for name in ("true_value", "inspection_noise_sd", "fault_time", "seed"):
        assert str(canaries[name]) not in text, name
    for word in ("true_value", "pose_bias", "range_bias", "fault", "rocks", '"seed"'):
        assert word not in text, word


def test_real_errors_are_not_in_the_brief() -> None:
    brief = load_scenario("mis_both").brief().to_dict()
    validate("mission_brief", brief)
    assert brief["declared_uncertainty"] == {"inspection_noise_sd": 0.2, "pose_noise_m": 0.1}
    assert "2.5" not in json.dumps(brief["declared_uncertainty"])
    assert "pose_bias_m" not in json.dumps(brief)


def test_pose_bias_shifts_only_the_estimate() -> None:
    scenario = load_scenario("mis_pose_bias")
    seen = []

    class Look:
        def reset(self, brief, seed) -> None:
            pass

        def act(self, observation):
            seen.append(observation)
            return STOP

    session = MissionSession(scenario, {"agent": Look()}, "agent")
    for _ in range(20):
        session.step()
    assert seen[0].estimated_pose.x_m == pytest.approx(3.2, abs=0.6)
    assert seen[0].estimated_pose.y_m == pytest.approx(-2.4, abs=0.6)
    assert session.sim.state.pose.x_m == pytest.approx(0.0, abs=0.01)


def test_noisy_inspection_allows_measuring_again_without_extra_data(
    make_scenario: MakeScenario,
) -> None:
    class TwoInspections:
        def __init__(self) -> None:
            self.sent = 0

        def reset(self, brief, seed) -> None:
            pass

        def act(self, observation):
            self.sent += 1
            if self.sent in (1, 30):
                return Action(0.0, 0.0, TaskRequest("inspect", "a"))
            return STOP

    scenario = make_scenario(
        mission={**science_mission(), "time_limit_s": 60},
        scenario={
            "uncertainty": {
                "inspection_noise_sd": 1.0,
                "declared": {"inspection_noise_sd": 0.1, "pose_noise_m": 0.0},
            }
        },
    )
    session = MissionSession(scenario, {"agent": TwoInspections()}, "agent")
    while session.time_s < 30:
        session.step()
    assert session.science.stored_value == pytest.approx(0.6)
    assert len(session.science._stored) == 1


def test_noiseless_missions_still_refuse_a_second_inspection(make_scenario: MakeScenario) -> None:
    scenario = make_scenario(mission={**science_mission(), "time_limit_s": 60})
    events = []
    session = MissionSession(
        scenario,
        {"agent": Script(0.0, TaskRequest("inspect", "a"))},
        "agent",
        on_event=events.append,
    )
    while session.time_s < 3:
        session.step()
    session.science.request(TaskRequest("inspect", "a"), 0, 0, 0, session.time_s)
    assert events[-1]["data"]["reason"] == "already_done"


# The adaptive planner.
def run_agent(name: str, scenario: str, tmp_path: Path, seed: int = 2001):
    result = run_mission(load_scenario(scenario), create_agent(name), name, tmp_path / name, seed)
    return result, load_run(result.directory)


def kinds(run) -> set[str]:
    return {d["kind"] for d in run.decisions if "kind" in d}


def test_decisions_are_recorded_with_kinds_and_pass_the_schema(tmp_path: Path) -> None:
    result, run = run_agent("adaptive-planner", "mis_both", tmp_path)
    assert {"reobserve", "replan"} <= kinds(run)
    for decision in run.decisions:
        validate("decision", decision)
    assert classify_run(run)["decisions"]["replan"] >= 1
    assert result.metrics.success


def test_mismatch_between_declared_and_real_noise_is_noticed(tmp_path: Path) -> None:
    _, run = run_agent("adaptive-planner", "mis_inspection", tmp_path)
    assert "uncertainty_mismatch" in kinds(run)
    text = next(d["text"] for d in run.decisions if d.get("kind") == "uncertainty_mismatch")
    assert "declared" in text


def test_position_error_is_found_by_searching_and_then_used(tmp_path: Path) -> None:
    fixed, run = run_agent("mission-planner", "mis_pose_bias", tmp_path / "a")
    adaptive, run2 = run_agent("adaptive-planner", "mis_pose_bias", tmp_path / "b")
    assert adaptive.metrics.science_value > fixed.metrics.science_value
    assert any("position error estimate" in d["text"] for d in run2.decisions)
    assert not kinds(run)


def test_ablations_switch_off_only_their_behavior(tmp_path: Path) -> None:
    _, no_obs = run_agent("adaptive-no-reobserve", "mis_both", tmp_path / "a")
    _, no_replan = run_agent("adaptive-no-replan", "mis_both", tmp_path / "b")
    assert "reobserve" not in kinds(no_obs) and "replan" in kinds(no_obs)
    assert "replan" not in kinds(no_replan)


def test_adaptive_planner_turns_back_when_power_runs_out(tmp_path: Path) -> None:
    fixed, _ = run_agent("mission-planner", "dust_season", tmp_path / "a")
    result = run_mission(
        load_scenario("dust_season"), create_agent("adaptive-planner"), "a", tmp_path / "b", 2001
    )
    run = load_run(result.directory)
    assert fixed.metrics.outcome == "battery_depleted"
    assert "withdraw" in kinds(run)
    assert result.metrics.outcome != "battery_depleted"


def test_adaptive_planner_is_reproducible(tmp_path: Path) -> None:
    first, _ = run_agent("adaptive-planner", "mis_both", tmp_path / "a")
    second, _ = run_agent("adaptive-planner", "mis_both", tmp_path / "b")
    assert first.manifest["logs_sha256"] == second.manifest["logs_sha256"]


def test_adaptive_planner_changes_nothing_when_nothing_is_wrong(tmp_path: Path) -> None:
    fixed, _ = run_agent("mission-planner", "science_sprint", tmp_path / "a")
    adaptive, _ = run_agent("adaptive-planner", "science_sprint", tmp_path / "b")
    assert adaptive.metrics.score == pytest.approx(fixed.metrics.score, abs=1.0)


# The study runner.
def small(tmp_path: Path, workers: int) -> dict:
    return run_study(
        load_benchmark(BENCH),
        tmp_path / f"w{workers}",
        ["standard"],
        ["stop", "mission-planner"],
        seed_count=2,
        workers=workers,
    )


def test_study_report_is_complete(tmp_path: Path) -> None:
    report = small(tmp_path, 1)
    track = report["tracks"]["standard"]
    row = track["agents"]["mission-planner"]
    assert row["runs"] == 4
    assert row["achievement_ci95"][0] <= row["achievement"] <= row["achievement_ci95"][1]
    assert sum(row["causes"].values()) == 4
    assert track["paired_vs_baseline"][0]["baseline"] == "stop"
    assert track["paired_vs_baseline"][0]["pairs"] == 4
    assert (tmp_path / "w1" / "study.json").is_file()
    assert (tmp_path / "w1" / "study_runs.csv").is_file()
    assert "Simplified model" in report["note"]


def test_parallel_and_serial_studies_match(tmp_path: Path) -> None:
    serial = small(tmp_path, 1)
    parallel = small(tmp_path, 2)
    assert serial["tracks"] == parallel["tracks"]


def test_summary_counts_causes() -> None:
    row = {
        "achievement": 10.0,
        "score": 5.0,
        "success": False,
        "cause": "stalled",
        "reobserve": 1,
        "replan": 0,
        "withdraw": 0,
        "uncertainty_mismatch": 0,
    }
    summary = summarize([row, {**row, "success": True, "cause": "success", "achievement": 30.0}])
    assert summary["causes"] == {"stalled": 1, "success": 1}
    assert summary["success_rate"] == 0.5
    assert summary["reobserve_per_run"] == 1


def test_job_results_do_not_depend_on_order(tmp_path: Path) -> None:
    job = ("t", "science_sprint", "pathfinder_6w|stop", 5, str(tmp_path))
    assert run_jobs([job], 1)[0]["digest"] == run_jobs([job], 1)[0]["digest"]
