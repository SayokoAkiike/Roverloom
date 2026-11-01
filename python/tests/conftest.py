"""Shared helpers: small in-memory scenarios that can be changed freely by each test."""

import copy
from collections.abc import Callable
from typing import Any

import pytest

from roverloom.contract import JsonDict, load_json_file, repo_root
from roverloom.world import Scenario, build_scenario


def base_documents() -> tuple[JsonDict, JsonDict, JsonDict]:
    scenario: JsonDict = {
        "schema_version": 0,
        "scenario_id": "unit",
        "seed": 5,
        "mission": {
            "schema_version": 0,
            "mission_id": "unit",
            "terrain_id": "unit_flat",
            "start_pose": {"position_m": [0, 0, 0], "orientation_xyzw": [0, 0, 0, 1]},
            "time_limit_s": 120,
            "objectives": [{"type": "reach_position", "position_m": [20, 0, 0], "radius_m": 2}],
        },
        "environment": {"gravity_mps2": 3.71},
        "faults": [],
    }
    terrain: JsonDict = {
        "schema_version": 0,
        "terrain_id": "unit_flat",
        "source": {"kind": "procedural", "note": "test"},
        "extent_m": {"min_xy": [-30, -30], "max_xy": [60, 30]},
        "grid_spacing_m": 5,
        "height": {"seed": 0, "amplitude_m": 0, "feature_size_m": 20, "octaves": 1},
    }
    rover = copy.deepcopy(load_json_file(repo_root() / "rovers" / "standard_6w.json"))
    return scenario, terrain, rover


MakeScenario = Callable[..., Scenario]


@pytest.fixture
def make_scenario() -> MakeScenario:
    """Build a flat scenario, applying optional changes to its documents."""

    def build(
        scenario: dict[str, Any] | None = None,
        mission: dict[str, Any] | None = None,
        terrain: dict[str, Any] | None = None,
        rover: dict[str, Any] | None = None,
    ) -> Scenario:
        scenario_doc, terrain_doc, rover_doc = base_documents()
        scenario_doc.update(scenario or {})
        scenario_doc["mission"].update(mission or {})
        terrain_doc.update(terrain or {})
        rover_doc.update(rover or {})
        return build_scenario(scenario_doc, terrain_doc, rover_doc)

    return build
