"""List the material slots and bounds of the V2 rover meshes, to plan their PBR materials. Read-only. Unreal Editor Python."""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

import unreal  # type: ignore[import-not-found]

for name in ("SM_RoverBody", "SM_RoverWheel", "SM_RoverStrut", "SM_RoverAxle"):
    mesh = unreal.EditorAssetLibrary.load_asset(f"/Game/Rover/{name}")
    slots = [
        str(slot.get_editor_property("material_slot_name"))
        for slot in mesh.get_editor_property("static_materials")
    ]
    box = mesh.get_bounding_box()
    print(f"PROBE {name}: slots {slots}; min {box.min}; max {box.max}")
