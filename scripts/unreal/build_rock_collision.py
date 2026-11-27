"""Give the Poly Haven rock meshes their own simple collision. Unreal Editor Python.

    UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script="scripts/unreal/build_rock_collision.py" -unattended -nullrhi

import_polyhaven.py imports the rocks without collision. A race makes every rock over 15 cm radius a solid body
(Source/Roverloom/Rover/Collision.h), wherever it lies, so the collision belongs to the mesh asset: a 26-sided hull
(k-DOP 26) fitted to the rock's vertices. Missions still turn rock collision off, so their physics does not change.
Writes unreal/Saved/Roverloom/rock_collision.json, which setup_gale.py checks.
"""

# ruff: noqa: E501  (long prose lines in the docstring and log messages)

import json
import os
import sys

import unreal  # type: ignore[import-not-found]

DEST = "/Game/Licensed/PolyHaven"
ROCKS = ["namaqualand_boulder_02", "namaqualand_boulder_04", "namaqualand_boulder_06", "rock_09"]


def shape_kdop26():
    for enum_name in ("ScriptCollisionShapeType", "ScriptingCollisionShapeType"):
        enum = getattr(unreal, enum_name, None)
        if enum is not None and hasattr(enum, "NDOP26"):
            return enum.NDOP26
    raise RuntimeError("this Unreal has no NDOP26 collision shape in its Python API")


def main() -> int:
    subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    shape = shape_kdop26()
    report = {}
    failed = 0
    for asset in ROCKS:
        path = f"{DEST}/{asset}/{asset}_1k"
        mesh = unreal.EditorAssetLibrary.load_asset(path)
        if mesh is None:
            unreal.log_error(f"Missing rock {path}: run import_polyhaven.py first")
            failed += 1
            continue
        before = subsystem.get_simple_collision_count(mesh)
        if before == 0:
            subsystem.add_simple_collisions(mesh, shape)
            unreal.EditorAssetLibrary.save_loaded_asset(mesh)
        after = subsystem.get_simple_collision_count(mesh)
        report[asset] = {"before": before, "after": after}
        unreal.log(f"ROCK_COLLISION {asset}: simple shapes {before} -> {after}")
        if after == 0:
            failed += 1
    out = os.path.join(unreal.Paths.project_saved_dir(), "Roverloom", "rock_collision.json")
    if not failed:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"shape": "NDOP26", "rocks": report}, f, indent=2)
    unreal.log(f"BUILD_ROCK_COLLISION_DONE failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
