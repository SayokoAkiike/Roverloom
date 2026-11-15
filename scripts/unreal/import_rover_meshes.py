"""Import the V2 rover meshes into the Unreal project, under /Game/Rover. Unreal Editor Python.

Run inside the editor (Tools > Execute Python Script), or headless from the repository root:

    "$UE_ROOT/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" \
        "$PWD/unreal/Roverloom.uproject" -run=pythonscript \
        -script="$PWD/scripts/unreal/import_rover_meshes.py $PWD/unreal/Saved/RoverModel"

The FBX files come from scripts/blender/build_rover.py. The meshes are visual only: collision is not
generated, and the pawn disables it on every component that shows them. After importing, start the
game and read the log line "Rover model: V2 ..."; it reports the imported bounds and warns if the
axes or units differ from the generator's.

Not yet run: written in a cloud session without Unreal. Record the first run's result in
docs/results/v2-rover-model/README.md.
"""

import os
import sys

import unreal  # type: ignore[import-not-found]

NAMES = ("SM_RoverBody", "SM_RoverWheel", "SM_RoverStrut", "SM_RoverAxle")
DESTINATION = "/Game/Rover"


def import_task(source_dir: str, name: str) -> "unreal.AssetImportTask":
    options = unreal.FbxImportUI()
    options.import_mesh = True
    options.import_as_skeletal = False
    options.import_animations = False
    options.import_materials = True
    options.import_textures = False
    options.static_mesh_import_data.combine_meshes = True
    options.static_mesh_import_data.auto_generate_collision = False
    options.static_mesh_import_data.generate_lightmap_u_vs = True

    task = unreal.AssetImportTask()
    task.filename = os.path.join(source_dir, f"{name}.fbx")
    task.destination_path = DESTINATION
    task.destination_name = name
    task.automated = True
    task.replace_existing = True
    task.save = True
    task.options = options
    return task


def main(argv: list[str]) -> int:
    source_dir = os.path.abspath(argv[0] if argv else "unreal/Saved/RoverModel")
    missing = [n for n in NAMES if not os.path.isfile(os.path.join(source_dir, f"{n}.fbx"))]
    if missing:
        unreal.log_error(f"Missing in {source_dir}: {', '.join(missing)}; run build_rover.py")
        return 1
    tasks = [import_task(source_dir, n) for n in NAMES]
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
    failed = 0
    for name in NAMES:
        mesh = unreal.EditorAssetLibrary.load_asset(f"{DESTINATION}/{name}.{name}")
        if mesh is None:
            unreal.log_error(f"Import failed: {name}")
            failed += 1
            continue
        box = mesh.get_bounding_box()
        unreal.log(f"Imported {name}: min {box.min}, max {box.max} (cm)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
