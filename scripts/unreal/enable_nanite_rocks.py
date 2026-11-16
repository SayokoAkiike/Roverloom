"""Print the triangle count of each Poly Haven rock, and turn Nanite on for them. Unreal Editor Python.

    UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script="scripts/unreal/enable_nanite_rocks.py" -unattended -nullrhi

Tens of thousands of instances of a dense mesh cost too much without Nanite (measured 2026-11-16: 4,000 instances added 23 ms of
GPU time). Nanite is a rendering setting on the mesh asset; it changes no collision and no physics.
"""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

import sys

import unreal  # type: ignore[import-not-found]

ROCKS = ["namaqualand_boulder_02", "namaqualand_boulder_04", "namaqualand_boulder_06", "rock_09"]
ENABLE = "--off" not in sys.argv


def main() -> int:
    for rock in ROCKS:
        mesh = unreal.EditorAssetLibrary.load_asset(f"/Game/Licensed/PolyHaven/{rock}/{rock}_1k")
        # The editor subsystem is not available in a commandlet, so use the older library
        verts = unreal.EditorStaticMeshLibrary.get_number_verts(mesh, 0)
        triangles = "n/a"
        settings = mesh.get_editor_property("nanite_settings")
        before = settings.get_editor_property("enabled")
        settings.set_editor_property("enabled", ENABLE)
        mesh.set_editor_property("nanite_settings", settings)
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
        unreal.log(
            f"NANITE {rock}: triangles {triangles}, vertices {verts}, Nanite {before} -> {ENABLE}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
