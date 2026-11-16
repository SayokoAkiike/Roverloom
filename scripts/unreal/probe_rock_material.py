"""Print whether the rock material says it may be drawn by Nanite. Read-only. Unreal Editor Python."""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

import unreal  # type: ignore[import-not-found]

material = unreal.EditorAssetLibrary.load_asset("/Game/Licensed/Gale/M_PHRock")
print("PROBE M_PHRock used_with_nanite =", material.get_editor_property("used_with_nanite"))
instance = unreal.EditorAssetLibrary.load_asset("/Game/Licensed/Gale/MI_rock_09")
print("PROBE MI_rock_09 parent =", instance.get_editor_property("parent"))
mesh = unreal.EditorAssetLibrary.load_asset("/Game/Licensed/PolyHaven/rock_09/rock_09_1k")
print("PROBE mesh material 0 =", mesh.get_material(0))
