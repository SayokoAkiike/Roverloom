"""Give the Poly Haven rock meshes their own simple collision. Unreal Editor Python.

    UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script="scripts/unreal/build_rock_collision.py" -unattended -nullrhi

import_polyhaven.py imports the rocks without collision. A race makes every rock over 15 cm radius a solid body
(Source/Roverloom/Rover/Collision.h), wherever it lies, so the collision belongs to the mesh asset: a 26-sided hull
(k-DOP 26) fitted to the rock's vertices where the editor's mesh tools are available in a commandlet, else two boxes
at 80 % of its bounds. Missions still turn rock collision off, so their physics does not change.
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
    return None


def editor_tools():
    """The editor's static mesh tools, if this editor offers them in a commandlet."""
    getter = getattr(unreal, "get_editor_subsystem", None)
    subsystem_class = getattr(unreal, "StaticMeshEditorSubsystem", None)
    if getter and subsystem_class:
        subsystem = getter(subsystem_class)
        if subsystem is not None:
            return subsystem, "StaticMeshEditorSubsystem"
    library = getattr(unreal, "EditorStaticMeshLibrary", None)
    if library is not None and hasattr(library, "add_simple_collisions"):
        return library, "EditorStaticMeshLibrary"
    return None, "none"


def element_count(mesh) -> int:
    agg = mesh.get_editor_property("body_setup").get_editor_property("agg_geom")
    return sum(
        len(agg.get_editor_property(name))
        for name in ("sphere_elems", "box_elems", "sphyl_elems", "convex_elems")
    )


def add_boxes(mesh) -> None:
    """Fallback without the editor tools: two boxes at 80 % of the rock's bounds, one turned 45 degrees,
    written into the mesh's own collision (simple shapes need no cooking)."""
    box = mesh.get_bounding_box()
    center = (box.min + box.max) * 0.5
    size = (box.max - box.min) * 0.8
    elems = []
    for yaw in (0.0, 45.0):
        e = unreal.KBoxElem()
        e.set_editor_property("center", center)
        e.set_editor_property("rotation", unreal.Rotator(0.0, 0.0, yaw))
        e.set_editor_property("x", size.x * (1.0 if yaw == 0.0 else 0.85))
        e.set_editor_property("y", size.y * (1.0 if yaw == 0.0 else 0.85))
        e.set_editor_property("z", size.z)
        elems.append(e)
    setup = mesh.get_editor_property("body_setup")
    agg = setup.get_editor_property("agg_geom")
    agg.set_editor_property("box_elems", elems)
    setup.set_editor_property("agg_geom", agg)


def main() -> int:
    tools, how = editor_tools()
    shape = shape_kdop26()
    unreal.log(f"ROCK_COLLISION tools: {how}, k-DOP 26: {shape is not None}")
    report = {}
    failed = 0
    for asset in ROCKS:
        path = f"{DEST}/{asset}/{asset}_1k"
        mesh = unreal.EditorAssetLibrary.load_asset(path)
        if mesh is None:
            unreal.log_error(f"Missing rock {path}: run import_polyhaven.py first")
            failed += 1
            continue
        before = element_count(mesh)
        method = "kept"
        if before == 0:
            done = False
            if tools is not None and shape is not None:
                try:
                    tools.add_simple_collisions(mesh, shape)
                    done = element_count(mesh) > 0
                    method = f"k-DOP 26 ({how})"
                except Exception as error:  # noqa: BLE001 - try the fallback, and say why
                    unreal.log_warning(f"ROCK_COLLISION {asset}: {how} failed: {error}")
            if not done:
                add_boxes(mesh)
                method = "two boxes"
            mesh.modify()
            unreal.EditorAssetLibrary.save_loaded_asset(mesh, False)
        after = element_count(mesh)
        report[asset] = {"before": before, "after": after, "method": method}
        unreal.log(f"ROCK_COLLISION {asset}: simple shapes {before} -> {after} ({method})")
        if after == 0:
            failed += 1
    out = os.path.join(unreal.Paths.project_saved_dir(), "Roverloom", "rock_collision.json")
    if not failed:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"rocks": report}, f, indent=2)
    unreal.log(f"BUILD_ROCK_COLLISION_DONE failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
