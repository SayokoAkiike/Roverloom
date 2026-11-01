"""Rover designs: rejection of bad designs, and real effects of design choices."""

import copy
import json
from pathlib import Path

import pytest
from conftest import MakeScenario

from roverloom.agents import create_agent
from roverloom.api import Action
from roverloom.contract import ContractError, load_json_file, repo_root
from roverloom.rover_builder import (
    MAX_COST,
    MAX_MASS_KG,
    compile_design,
    list_designs,
    load_rover_document,
)
from roverloom.runlog import logs_digest
from roverloom.runner import run_mission
from roverloom.session import MissionSession
from roverloom.sim import RoverSim, build_fault_schedule
from roverloom.world import load_scenario


def design(name: str = "pathfinder_6w") -> dict:
    return copy.deepcopy(load_json_file(repo_root() / "rovers" / "designs" / f"{name}.json"))


def changed(path: str, value: object) -> dict:
    document = design()
    keys = path.split(".")
    node = document
    for key in keys[:-1]:
        node = node[key]
    node[keys[-1]] = value
    return document


def test_at_least_three_standard_rovers_compile() -> None:
    assert len(list_designs()) >= 3
    for name in list_designs():
        report = load_rover_document(name)["design_report"]
        assert report["mass_kg"] <= MAX_MASS_KG
        assert report["cost"] <= MAX_COST
        assert report["simplified_model"] is True


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        ("wheels.radius_m", 0.01, "wheel radius"),
        ("wheels.radius_m", 5.0, "wheel radius"),
        ("wheels.width_m", 2.0, "wheel width"),
        ("wheels.motor_w", 1.0, "motor power"),
        ("wheels.count", 5, "count"),
        ("wheels.radius_m", -1, "radius_m"),
        ("battery_wh", 0, "battery_wh"),
        ("battery_wh", 10, "battery"),
        ("battery_wh", 99999, "battery"),
        ("sensors.range_beams", 0, "range_beams"),
        ("sensors.range_beams", 100, "range beams"),
        ("sensors.range_max_m", 1000, "range sensor"),
        ("power", {"kind": "solar", "panel_m2": 500}, "solar panel"),
        ("power", {"kind": "rtg", "output_w": 5000}, "RTG"),
        ("power", {"kind": "fusion"}, "power"),
        ("compute", "quantum", "compute"),
        ("design_id", "../../evil", "design_id"),
        ("provenance", {"author": "x"}, "provenance"),
    ],
    ids=lambda v: str(v)[:18],
)
def test_unreasonable_design_is_rejected(path: str, value: object, message: str) -> None:
    with pytest.raises(ContractError, match=message):
        compile_design(changed(path, value))


def test_mass_budget_is_enforced() -> None:
    document = changed("chassis_kg", 1500)
    with pytest.raises(ContractError, match="mass"):
        compile_design(document)


def test_weak_chassis_is_rejected() -> None:
    document = changed("chassis_kg", 100)
    document["battery_wh"] = 1500
    with pytest.raises(ContractError, match="cannot carry"):
        compile_design(document)


def test_cost_budget_is_enforced() -> None:
    document = changed(
        "sensors",
        {"range_max_m": 60, "range_beams": 32, "range_fov_rad": 3, "pose_grade": "precise"},
    )
    document["compute"] = "high"
    document["battery_wh"] = 2000
    with pytest.raises(ContractError, match="cost"):
        compile_design(document)


def test_excessive_ground_pressure_is_rejected() -> None:
    document = changed("wheels", {"count": 4, "radius_m": 0.1, "width_m": 0.05, "motor_w": 200})
    with pytest.raises(ContractError, match="ground pressure"):
        compile_design(document)


def scenario_with(document: dict, tmp_path: Path, name: str = "science_sprint"):
    path = tmp_path / f"{document['design_id']}.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return load_scenario(name, rover=str(path))


def test_design_file_with_broken_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(ContractError):
        load_scenario("science_sprint", rover=str(path))


def test_unknown_rover_is_rejected() -> None:
    with pytest.raises(ContractError, match="unknown rover"):
        load_scenario("science_sprint", rover="no_such_rover")


def drive_distance(scenario, seconds: float = 40.0) -> float:
    sim = RoverSim(scenario, 1)
    for _ in range(round(seconds / 0.1)):
        sim.step(Action(10.0, 0.0), 0.1)
    return sim.state.pose.x_m


def test_wheel_radius_changes_speed(tmp_path: Path) -> None:
    small = changed("wheels", {"count": 6, "radius_m": 0.15, "width_m": 0.2, "motor_w": 90})
    small["design_id"] = "small"
    assert drive_distance(scenario_with(small, tmp_path)) < drive_distance(
        scenario_with(design(), tmp_path)
    )


def test_sensor_configuration_changes_observation(tmp_path: Path) -> None:
    wide = changed(
        "sensors",
        {"range_max_m": 20, "range_beams": 15, "range_fov_rad": 3, "pose_grade": "standard"},
    )
    wide["design_id"] = "wide"
    brief = scenario_with(wide, tmp_path).brief()
    assert brief.sensor_max_range_m == 20
    seen = []

    class Recorder:
        def reset(self, b, s) -> None:
            pass

        def act(self, observation):
            seen.append(observation)
            return Action(0, 0)

    session = MissionSession(scenario_with(wide, tmp_path), {"agent": Recorder()}, "agent")
    for _ in range(10):
        session.step()
    assert len(seen[0].range_scan) == 15


def test_compute_tier_changes_control_rate(tmp_path: Path) -> None:
    fast = changed("compute", "high")
    fast["design_id"] = "fast"
    slow = changed("compute", "low")
    slow["design_id"] = "slow"
    assert scenario_with(fast, tmp_path).brief().control_period_s == 0.2
    assert scenario_with(slow, tmp_path).brief().control_period_s == 1.0


def energy_after(document: dict, tmp_path: Path) -> float:
    sim = RoverSim(scenario_with(document, tmp_path), 1)
    for _ in range(600):
        sim.step(Action(0, 0), 0.1)
    return sim.state.battery_wh


def test_power_system_changes_energy(tmp_path: Path) -> None:
    batt = changed("power", {"kind": "battery_only"})
    batt["design_id"] = "batt"
    solar = changed("power", {"kind": "solar", "panel_m2": 15})
    solar["design_id"] = "solar"
    assert energy_after(solar, tmp_path) > energy_after(batt, tmp_path)


def test_generation_never_overfills_the_battery(tmp_path: Path) -> None:
    rover = changed("power", {"kind": "rtg", "output_w": 150})
    rover["design_id"] = "big_rtg"
    assert energy_after(rover, tmp_path) <= rover["battery_wh"]


def test_rover_has_declared_wheels_and_faults_map_onto_them() -> None:
    sim = RoverSim(load_scenario("science_sprint", rover="scout_4w"), 1)
    sim.fail_wheel("middle_left")  # This rover has no middle wheels.
    assert sim.state.failed_wheels == {"rear_left"}
    for wheel in ("middle_right", "middle2_left", "middle2_right"):
        sim.fail_wheel(wheel)
    assert sim.state.failed_wheels <= set(load_rover_document("scout_4w")["wheels"])


def test_same_rover_agent_seed_reproduces(tmp_path: Path) -> None:
    digests = [
        logs_digest(
            run_mission(
                load_scenario("science_sprint", rover="hauler_8w"),
                create_agent("mission-planner"),
                "m",
                tmp_path / name,
                4,
            ).manifest
        )
        for name in ("a", "b")
    ]
    assert digests[0] == digests[1]


def test_different_rovers_give_different_results(tmp_path: Path) -> None:
    results = {
        rover: run_mission(
            load_scenario("science_sprint", rover=rover),
            create_agent("mission-planner"),
            "m",
            tmp_path / rover,
            4,
        ).metrics
        for rover in list_designs()
    }
    assert len({m.energy_used_wh for m in results.values()}) == len(results)
    assert results["scout_4w"].science_value < results["pathfinder_6w"].science_value  # No arm.


def test_random_fault_schedule_is_the_same_for_every_rover() -> None:
    schedules = [
        build_fault_schedule(load_scenario("science_campaign", rover=rover), 9)
        for rover in list_designs()
    ]
    assert schedules[0] == schedules[1] == schedules[2]


def test_manifest_records_versions(tmp_path: Path) -> None:
    result = run_mission(
        load_scenario("science_sprint"), create_agent("mission-planner"), "m", tmp_path / "r", 1
    )
    assert result.manifest["rover_version"] == "1.0.0"
    assert result.manifest["scenario_version"] == "1.0.0"
    assert result.manifest["agent_version"] == "1.0.0"
    assert result.metrics.design_cost is not None


def test_tutorial_rover_compiles_and_records_its_origin() -> None:
    document = load_json_file(repo_root() / "python" / "examples" / "rovers" / "my_scout.json")
    assert compile_design(document)["has_sample_tool"] is True
    assert document["provenance"]["derived_from"] == "scout_4w@1.0.0"


def test_legacy_parameter_rover_still_loads(make_scenario: MakeScenario) -> None:
    assert make_scenario().rover.rover_id == "standard_6w"
    assert load_scenario("demo_traverse").rover.rover_id == "standard_6w"
