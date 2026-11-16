"""Measured-heightfield terrain: the loader checks its file, and orients rows north-up."""

import copy
import hashlib
import struct
from pathlib import Path

import pytest

from roverloom.contract import ContractError
from roverloom.world import Terrain

COLS, ROWS = 5, 4


def document(raw: bytes) -> dict:
    return {
        "schema_version": 0,
        "terrain_id": "field_test",
        "source": {"kind": "dataset", "note": "synthetic test data"},
        "extent_m": {"min_xy": [0.0, 0.0], "max_xy": [COLS - 1.0, ROWS - 1.0]},
        "grid_spacing_m": 1.0,
        "heightfield": {
            "file": "field.r16",
            "format": "r16",
            "samples_xy": [COLS, ROWS],
            "height_min_m": -10.0,
            "height_max_m": 55.535,  # 65535 steps of 1 mm
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
    }


def raw_field() -> bytes:
    # Row 0 is the northern row. Sample value encodes the row so that orientation is visible.
    values = [file_row * 1000 + col for file_row in range(ROWS) for col in range(COLS)]
    return struct.pack(f"<{len(values)}H", *values)


@pytest.fixture
def terrain_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "field.r16").write_bytes(raw_field())
    monkeypatch.setenv("ROVERLOOM_TERRAIN_DIR", str(tmp_path))
    return tmp_path


def test_rows_run_south_to_north_and_heights_are_relative(terrain_dir: Path) -> None:
    terrain = Terrain(document(raw_field()))
    assert terrain.height_at(0.0, 0.0) == pytest.approx(
        3000 * 0.001
    )  # file row 3 is the south edge
    assert terrain.height_at(0.0, ROWS - 1.0 - 0.002) == pytest.approx(0.0, abs=0.01)
    assert terrain.height_at(2.0, 0.0) == pytest.approx(3002 * 0.001)


def test_a_changed_file_is_refused(terrain_dir: Path) -> None:
    doc = document(raw_field())
    (terrain_dir / "field.r16").write_bytes(raw_field()[:-2] + b"\x01\x00")
    with pytest.raises(ContractError, match="SHA-256"):
        Terrain(doc)


def test_a_missing_file_names_where_to_put_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROVERLOOM_TERRAIN_DIR", str(tmp_path))
    with pytest.raises(ContractError, match="stays outside Git"):
        Terrain(document(raw_field()))


def test_sample_count_must_match_extent(terrain_dir: Path) -> None:
    doc = copy.deepcopy(document(raw_field()))
    doc["heightfield"]["samples_xy"] = [COLS + 1, ROWS]
    with pytest.raises(ContractError, match="need"):
        Terrain(doc)


def test_height_and_heightfield_are_exclusive(terrain_dir: Path) -> None:
    doc = document(raw_field())
    doc["height"] = {"seed": 1, "amplitude_m": 1.0, "feature_size_m": 5.0, "octaves": 1}
    with pytest.raises(ContractError):
        Terrain(doc)
