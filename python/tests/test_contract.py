"""Checks that schemas are valid and that repository data and typed messages conform to them."""

import json
import math
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from roverloom.api import Action, MissionBrief, Observation, Pose, RangeReading, Target
from roverloom.contract import ContractError, load_json_file, parse_json, repo_root, validate
from roverloom.world import list_practice_scenarios, load_scenario

REPO_ROOT = repo_root()
SCHEMA_PATHS = sorted((REPO_ROOT / "schemas").glob("*.schema.json"))
TERRAIN_PATHS = sorted((REPO_ROOT / "scenarios" / "terrains").glob("*.json"))
ROVER_PATHS = sorted((REPO_ROOT / "rovers").glob("*.json"))

POSE = {"position_m": [1.0, 2.0, 3.0], "orientation_xyzw": [0, 0, 0, 1]}
VALID_SAMPLES = {
    "action": {"schema_version": 0, "linear_velocity_mps": 0.5, "yaw_rate_radps": 0.1},
    "observation": {
        "schema_version": 0,
        "time_s": 1.0,
        "estimated_pose": POSE,
        "battery_fraction": 0.9,
    },
    "telemetry": {
        "schema_version": 0,
        "time_s": 1.0,
        "pose": POSE,
        "linear_velocity_mps": [0.5, 0, 0],
        "battery_fraction": 0.9,
        "energy_used_wh": 0.1,
    },
}


@pytest.mark.parametrize("path", SCHEMA_PATHS, ids=lambda p: p.name)
def test_schema_is_valid(path: Path) -> None:
    Draft202012Validator.check_schema(load_json_file(path))


def test_practice_scenarios_exist() -> None:
    assert len(list_practice_scenarios()) >= 3


@pytest.mark.parametrize("name", list_practice_scenarios())
def test_scenario_loads_and_passes_all_checks(name: str) -> None:
    scenario = load_scenario(name)
    assert scenario.document.get("tier", "practice") == "practice"


@pytest.mark.parametrize("path", TERRAIN_PATHS, ids=lambda p: p.name)
def test_terrain_conforms(path: Path) -> None:
    validate("terrain", load_json_file(path))


@pytest.mark.parametrize("path", ROVER_PATHS, ids=lambda p: p.name)
def test_rover_conforms(path: Path) -> None:
    validate("rover", load_json_file(path))


@pytest.mark.parametrize("name", VALID_SAMPLES)
def test_valid_sample_conforms(name: str) -> None:
    validate(name, VALID_SAMPLES[name])


@pytest.mark.parametrize("name", VALID_SAMPLES)
def test_unknown_field_is_rejected(name: str) -> None:
    with pytest.raises(ContractError):
        validate(name, {**VALID_SAMPLES[name], "unexpected": 1})


def test_nested_ref_is_enforced() -> None:
    document = load_json_file(REPO_ROOT / "scenarios" / "practice" / "example_reach_position.json")
    document["faults"][0]["wheel"] = "seventh_wheel"
    with pytest.raises(ContractError):
        validate("scenario", document)


def test_v0_documents_from_before_the_extensions_still_load() -> None:
    # The initial schema had only these fields. They must keep working.
    observation = Observation.from_dict(VALID_SAMPLES["observation"])
    assert observation.estimated_speed_mps == 0.0
    assert observation.range_scan == ()


def test_action_round_trip() -> None:
    action = Action(0.25, -0.5)
    assert Action.from_dict(action.to_dict()) == action


def test_observation_round_trip_matches_schema() -> None:
    observation = Observation(
        time_s=2.5,
        estimated_pose=Pose(1.0, -2.0, 0.5, 0.75),
        battery_fraction=0.5,
        estimated_speed_mps=0.2,
        targets_reached=1,
        range_scan=(RangeReading(0.1, 3.5), RangeReading(-0.1, None)),
    )
    restored = Observation.from_dict(json.loads(json.dumps(observation.to_dict())))
    assert restored.range_scan == observation.range_scan
    assert restored.estimated_pose.x_m == pytest.approx(1.0)
    assert restored.estimated_pose.yaw_rad == pytest.approx(0.75, abs=1e-5)


def test_brief_round_trip_matches_schema() -> None:
    brief = MissionBrief(
        "m", Pose(0, 0, 0, 0), (Target(1, 2, 3),), 10.0, None, 0.5, 1.0, 1.0, 1.0, 12.0,
        (-1.0, -1.0), (1.0, 1.0),
    )  # fmt: skip
    assert MissionBrief.from_dict(brief.to_dict()).targets == brief.targets


@pytest.mark.parametrize("yaw", [0.0, 1.0, -2.5, 3.1])
def test_pose_yaw_survives_quaternion(yaw: float) -> None:
    assert Pose.from_dict(Pose(0, 0, 0, yaw).to_dict()).yaw_rad == pytest.approx(yaw, abs=1e-5)


def test_non_unit_quaternion_is_rejected() -> None:
    with pytest.raises(ContractError, match="unit quaternion"):
        Pose.from_dict({"position_m": [0, 0, 0], "orientation_xyzw": [0, 0, 0, 2]})


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_action_rejects_non_finite(value: float) -> None:
    with pytest.raises(ContractError):
        Action(value, 0.0)


@pytest.mark.parametrize("text", ['{"a": NaN}', '{"a": Infinity}', '{"a": 1, "a": 2}', "{broken"])
def test_parser_rejects_bad_json(text: str) -> None:
    with pytest.raises(ContractError):
        parse_json(text)
