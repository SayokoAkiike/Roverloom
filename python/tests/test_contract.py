"""Checks that schemas are valid and that scenarios and samples conform to them."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry
from referencing.jsonschema import DRAFT202012

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATHS = sorted((REPO_ROOT / "schemas").glob("*.schema.json"))
SCENARIO_PATHS = sorted((REPO_ROOT / "scenarios").glob("*.json"))

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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validator_for(name: str) -> Draft202012Validator:
    resources = [
        (schema["$id"], DRAFT202012.create_resource(schema))
        for schema in map(load_json, SCHEMA_PATHS)
    ]
    schema = load_json(REPO_ROOT / "schemas" / f"{name}.schema.json")
    return Draft202012Validator(schema, registry=Registry().with_resources(resources))


@pytest.mark.parametrize("path", SCHEMA_PATHS, ids=lambda p: p.name)
def test_schema_is_valid(path: Path) -> None:
    Draft202012Validator.check_schema(load_json(path))


def test_scenarios_exist() -> None:
    assert SCENARIO_PATHS


@pytest.mark.parametrize("path", SCENARIO_PATHS, ids=lambda p: p.name)
def test_scenario_conforms(path: Path) -> None:
    validator_for("scenario").validate(load_json(path))


@pytest.mark.parametrize("name", VALID_SAMPLES)
def test_valid_sample_conforms(name: str) -> None:
    validator_for(name).validate(VALID_SAMPLES[name])


@pytest.mark.parametrize("name", VALID_SAMPLES)
def test_unknown_field_is_rejected(name: str) -> None:
    with pytest.raises(ValidationError):
        validator_for(name).validate({**VALID_SAMPLES[name], "unexpected": 1})


def test_nested_ref_is_enforced() -> None:
    scenario = load_json(SCENARIO_PATHS[0])
    scenario["faults"][0]["wheel"] = "seventh_wheel"
    with pytest.raises(ValidationError):
        validator_for("scenario").validate(scenario)
