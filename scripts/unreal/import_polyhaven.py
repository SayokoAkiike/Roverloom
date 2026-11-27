"""Import the Poly Haven textures and rocks fetched by scripts/assets/polyhaven_fetch.py. Unreal Editor Python.

    UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script="scripts/unreal/import_polyhaven.py" -unattended -nullrhi

Everything goes under /Game/Licensed/PolyHaven/, which Git ignores. Rocks are imported without collision: they are visual
only, and the rover's physics never sees them.
"""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

import os
import sys

import unreal  # type: ignore[import-not-found]

SOURCE = os.path.join(
    unreal.Paths.project_dir(), "Content/Licensed/PolyHaven"
)  # The cwd is the editor's, not ours
DEST = "/Game/Licensed/PolyHaven"
TEXTURES = ["dry_ground_01", "dense_sand", "rock_boulder_cracked", "rocks_ground_03"]
ROCKS = [
    # The first four are also the race's solid rocks (build_rock_collision.py); the rest are small stones only, for variety
    "namaqualand_boulder_02",
    "namaqualand_boulder_04",
    "namaqualand_boulder_06",
    "rock_09",
    "namaqualand_boulder_03",
    "namaqualand_boulder_05",
    "rock_07",
    "stone_01",
    "moon_rock_01",
    "moon_rock_03",
]
tools = unreal.AssetToolsHelpers.get_asset_tools()


def task(filename: str, folder: str, options=None) -> "unreal.AssetImportTask":
    t = unreal.AssetImportTask()
    t.filename = filename
    t.destination_path = folder
    t.automated = True
    t.replace_existing = True
    t.save = True
    if options is not None:
        t.options = options
    return t


def configure(path: str, normal: bool = False, linear: bool = False) -> None:
    texture = unreal.EditorAssetLibrary.load_asset(path)
    if texture is None:
        unreal.log_error(f"Missing texture {path}")
        return
    if normal:
        texture.set_editor_property(
            "compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP
        )
        texture.set_editor_property("srgb", False)
    elif linear:
        texture.set_editor_property(
            "compression_settings", unreal.TextureCompressionSettings.TC_MASKS
        )
        texture.set_editor_property("srgb", False)
    unreal.EditorAssetLibrary.save_loaded_asset(texture)


def main() -> int:
    tasks = []
    for asset in TEXTURES:
        for kind in ("diff", "nor_gl", "arm"):
            tasks.append(
                task(os.path.join(SOURCE, asset, f"{asset}_{kind}_2k.jpg"), f"{DEST}/{asset}")
            )
    tools.import_asset_tasks(tasks)
    for asset in TEXTURES:
        configure(f"{DEST}/{asset}/{asset}_diff_2k.{asset}_diff_2k")
        configure(f"{DEST}/{asset}/{asset}_nor_gl_2k.{asset}_nor_gl_2k", normal=True)
        configure(f"{DEST}/{asset}/{asset}_arm_2k.{asset}_arm_2k", linear=True)

    rocks = []
    for asset in ROCKS:
        options = unreal.FbxImportUI()
        options.import_mesh = True
        options.import_as_skeletal = False
        options.import_animations = False
        options.import_materials = False
        options.import_textures = False
        options.static_mesh_import_data.combine_meshes = True
        options.static_mesh_import_data.auto_generate_collision = False
        rocks.append(
            task(os.path.join(SOURCE, asset, f"{asset}_1k.fbx"), f"{DEST}/{asset}", options)
        )
        rocks.append(
            task(os.path.join(SOURCE, asset, "textures", f"{asset}_diff_1k.jpg"), f"{DEST}/{asset}")
        )
    tools.import_asset_tasks(rocks)

    failed = 0
    for asset in TEXTURES:
        for kind in ("diff", "nor_gl", "arm"):
            if not unreal.EditorAssetLibrary.does_asset_exist(f"{DEST}/{asset}/{asset}_{kind}_2k"):
                unreal.log_error(f"Import failed: {asset} {kind}")
                failed += 1
    for asset in ROCKS:
        path = f"{DEST}/{asset}/{asset}_1k"
        mesh = unreal.EditorAssetLibrary.load_asset(path)
        if mesh is None:
            unreal.log_error(f"Import failed: rock {asset}")
            failed += 1
            continue
        box = mesh.get_bounding_box()
        unreal.log(
            f"IMPORTED rock {asset}: size {box.max - box.min} cm, collision {mesh.get_editor_property('body_setup').get_editor_property('collision_trace_flag')}"
        )
    unreal.log(f"IMPORT_POLYHAVEN_DONE failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
