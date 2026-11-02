"""Design budgets, compatibility rules, and keeping cost apart from achievement."""

import copy
from pathlib import Path

import pytest

from roverloom.contract import ContractError, load_json_file, repo_root
from roverloom.evaluate import evaluate_run
from roverloom.league import design_board, load_benchmark, run_league
from roverloom.rover_builder import (
    DESIGN_CLASSES,
    compile_design,
    design_class,
    explain_design,
    list_designs,
    load_rover_document,
    require_design,
)
from roverloom.runlog import load_run
from roverloom.study import pareto_front


def design(name: str = "pathfinder_6w") -> dict:
    return copy.deepcopy(load_json_file(repo_root() / "rovers" / "designs" / f"{name}.json"))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.update(battery_wh=1000, chassis_kg=300), "chassis holds"),
        (lambda d: d.update(battery_wh=200), "the battery can deliver"),
        (lambda d: d["sensors"].update(range_beams=12) or d.update(compute="low"), "range beams"),
        (lambda d: d["sensors"].update(pose_grade="precise") or d.update(compute="low"), "precise"),
        (lambda d: d.update(chassis_kg=200, battery_wh=300), "sample arm"),
        (
            lambda d: d.update(
                power={"kind": "rtg", "output_w": 40}, chassis_kg=350, battery_wh=480
            ),
            "RTG needs",
        ),
    ],
    ids=[
        "volume",
        "peak-power",
        "beams-vs-compute",
        "pose-vs-compute",
        "arm-chassis",
        "rtg-chassis",
    ],
)
def test_each_compatibility_rule_refuses_a_bad_design(change, message: str) -> None:
    document = design()
    change(document)
    with pytest.raises(ContractError, match=message):
        compile_design(document)


def test_all_broken_rules_are_listed_together() -> None:
    document = design()
    document.update(compute="low", chassis_kg=200)
    document["sensors"].update(range_beams=12, pose_grade="precise")
    with pytest.raises(ContractError) as error:
        compile_design(document)
    text = str(error.value)
    assert "range beams" in text and "precise" in text and "sample arm" in text


def test_budget_boundary_values() -> None:
    assert design_class(40.0, 600.0) == "light"
    assert design_class(40.01, 600.0) == "standard"
    assert design_class(40.0, 600.1) == "standard"
    assert design_class(70.0, 1000.0) == "standard"
    assert design_class(70.1, 900.0) == "heavy"
    with pytest.raises(ContractError, match="no design class"):
        design_class(100.1, 100.0)


def test_standard_rovers_fall_in_three_classes_and_report_their_limits() -> None:
    classes = {}
    for name in list_designs():
        report = load_rover_document(name)["design_report"]
        classes[name] = report["design_class"]
        assert report["volume_l"] <= report["volume_capacity_l"]
        assert report["peak_power_w"] <= report["peak_power_limit_w"]
        assert set(report["limited_by"]) == {"speed", "control_rate", "endurance"}
    assert classes == {"scout_4w": "light", "pathfinder_6w": "standard", "hauler_8w": "heavy"}
    assert list(DESIGN_CLASSES) == ["light", "standard", "heavy"]


def test_wheel_geometry_matches_the_declared_wheels() -> None:
    for name in list_designs():
        rover = load_rover_document(name)
        wheels = rover["geometry"]["wheels"]
        assert [w["wheel_id"] for w in wheels] == rover["wheels"]
        for wheel in wheels:
            left = wheel["wheel_id"].endswith("_left")
            assert (wheel["position_m"][1] > 0) == left
            assert wheel["position_m"][2] == wheel["radius_m"]
        assert wheels[0]["position_m"][0] > wheels[-1]["position_m"][0]  # Front is +X.


def test_explain_traces_a_change_to_its_effect() -> None:
    rows = {row["change"]: row for row in explain_design(design())}
    assert rows["battery +25%"]["cost"] > 0
    assert rows["motor power +25%"]["max_climb_slope"] > 0
    assert rows["sensor range +25%"]["idle_power_w"] > 0
    assert rows["wheel width +25%"]["soil_slip_scale"] < 0


def test_explain_reports_a_refused_change_with_its_reason() -> None:
    document = design()
    document["battery_wh"] = 640  # The chassis is nearly full, so more battery no longer fits.
    rows = {row["change"]: row for row in explain_design(document)}
    assert "chassis holds" in rows["battery +25%"]["refused"]
    assert "refused" not in rows["chassis +25%"]


def test_plain_parameters_cannot_enter_a_design_league() -> None:
    with pytest.raises(ContractError, match="must be a rover design"):
        require_design("standard_6w")
    require_design("scout_4w")
    benchmark = copy.deepcopy(load_benchmark("roverloom-bench-v2"))
    with pytest.raises(ContractError, match="must be a rover design"):
        run_league(benchmark, "rover_design", Path("unused"), extra_rovers=["standard_6w"])


def row(entry: str, cost: float, achievement: float, robust: float) -> dict:
    return {
        "entry": entry,
        "design_cost": cost,
        "mean_achievement": achievement,
        "robustness": robust,
    }


def front(*rows: dict) -> set[str]:
    return pareto_front(rows, ("design_cost",), ("mean_achievement", "robustness"))


def test_pareto_front_rules() -> None:
    assert front(row("a", 10, 50, 10), row("b", 20, 40, 5)) == {"a"}
    assert front(row("a", 10, 50, 10), row("b", 20, 60, 5)) == {"a", "b"}
    # Equal on everything: neither dominates the other.
    assert front(row("a", 10, 50, 10), row("b", 10, 50, 10)) == {"a", "b"}
    assert front(row("only", 1, 0, 0)) == {"only"}


def test_design_board_ranks_inside_classes_and_keeps_cost_out_of_the_score() -> None:
    board = [
        {"entry": "hauler_8w", "mean_score": 90.0, "mean_energy_wh": 1.0, "mean_achievement": 90.0},
        {"entry": "scout_4w", "mean_score": 10.0, "mean_energy_wh": 1.0, "mean_achievement": 80.0},
    ]
    runs = [
        {"rover": "hauler_8w", "scenario": "a", "achievement": 90.0},
        {"rover": "hauler_8w", "scenario": "b", "achievement": 90.0},
        {"rover": "scout_4w", "scenario": "a", "achievement": 100.0},
        {"rover": "scout_4w", "scenario": "b", "achievement": 60.0},
    ]
    rows = {r["entry"]: r for r in design_board(board, runs)}
    # Each leads its own class, so a low score does not push the cheap design below the costly one.
    assert rows["scout_4w"]["rank"] == rows["hauler_8w"]["rank"] == 1
    assert rows["scout_4w"]["robustness"] == 60.0
    assert rows["hauler_8w"]["mean_score"] == 90.0
    assert rows["scout_4w"]["pareto"] and rows["hauler_8w"]["pareto"]


def test_energy_efficiency_does_not_reward_a_bigger_battery(tmp_path: Path) -> None:
    from roverloom.agents import create_agent
    from roverloom.runner import run_mission
    from roverloom.world import load_scenario

    scenario = load_scenario("science_sprint", rover="pathfinder_6w")
    assert scenario.mission["reference_energy_wh"] == 400
    bigger = copy.deepcopy(design())
    bigger["design_id"] = "bigger"
    bigger["battery_wh"] = 900
    bigger["chassis_kg"] = 540
    path = tmp_path / "bigger.json"
    import json

    path.write_text(json.dumps(bigger), encoding="utf-8")
    base = run_mission(scenario, create_agent("mission-planner"), "m", tmp_path / "a", 1).metrics
    other = run_mission(
        load_scenario("science_sprint", rover=str(path)),
        create_agent("mission-planner"),
        "m",
        tmp_path / "b",
        1,
    ).metrics
    # More battery means more mass and so more energy use. It must not improve efficiency.
    assert other.energy_used_wh > base.energy_used_wh
    assert other.score <= base.score


def test_achievement_is_recorded_and_ignores_efficiency(tmp_path: Path) -> None:
    from roverloom.agents import create_agent
    from roverloom.runner import run_mission
    from roverloom.world import load_scenario

    result = run_mission(
        load_scenario("science_sprint"), create_agent("mission-planner"), "m", tmp_path / "r", 1
    )
    metrics = evaluate_run(load_run(result.directory))
    assert metrics.achievement == pytest.approx(100.0 * metrics.science_fraction, abs=0.01)
    assert metrics.score != metrics.achievement


def test_survey_mission_needs_no_arm_and_refuses_sampling(tmp_path: Path) -> None:
    from roverloom.agents import create_agent
    from roverloom.runner import run_mission
    from roverloom.world import load_scenario

    scenario = load_scenario("canyon_survey", rover="hauler_8w")
    assert scenario.brief().can_collect is False
    assert load_scenario("science_sprint", rover="hauler_8w").brief().can_collect is True
    result = run_mission(scenario, create_agent("mission-planner"), "m", tmp_path / "r", 101)
    assert result.metrics.achievement > 0
    run = load_run(result.directory)
    assert not [
        e for e in run.events if e["type"] == "task_started" and e["data"]["task"] == "collect"
    ]
