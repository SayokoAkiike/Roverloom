"""Give the imported Poly Haven rocks a material: their own diffuse map, kept rough, pulled toward a Mars-like tan.
Unreal Editor Python.

    UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script="scripts/unreal/build_rock_materials.py" -unattended -nullrhi

Needs import_polyhaven.py first. Output: /Game/Licensed/Gale/M_PHRock and one instance per rock, set on the rock's mesh
asset. Normal maps are not used: the source normal maps are EXR files, which this pipeline does not decode. The assets are Earth
rocks standing in for Martian ones.
"""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

import sys

import unreal  # type: ignore[import-not-found]

mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
FOLDER = "/Game/Licensed/Gale"
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


def main() -> int:
    path = f"{FOLDER}/M_PHRock"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        material = unreal.EditorAssetLibrary.load_asset(path)
        mel.delete_all_material_expressions(material)
    else:
        material = tools.create_asset(
            "M_PHRock", FOLDER, unreal.Material, unreal.MaterialFactoryNew()
        )

    texture = mel.create_material_expression(
        material, unreal.MaterialExpressionTextureSampleParameter2D, -700, 0
    )
    texture.set_editor_property("parameter_name", "Diffuse")
    texture.set_editor_property(
        "sampler_source", unreal.SamplerSourceMode.SSM_WRAP_WORLD_GROUP_SETTINGS
    )
    desaturate = mel.create_material_expression(
        material, unreal.MaterialExpressionDesaturation, -450, 0
    )
    mel.connect_material_expressions(texture, "", desaturate, "")
    fraction = mel.create_material_expression(
        material, unreal.MaterialExpressionConstant, -700, 200
    )
    fraction.set_editor_property("r", 0.5)
    mel.connect_material_expressions(fraction, "", desaturate, "Fraction")
    tint = mel.create_material_expression(
        material, unreal.MaterialExpressionConstant3Vector, -450, 200
    )
    tint.set_editor_property("constant", unreal.LinearColor(0.95, 0.70, 0.52, 1.0))
    color = mel.create_material_expression(material, unreal.MaterialExpressionMultiply, -200, 0)
    mel.connect_material_expressions(desaturate, "", color, "A")
    mel.connect_material_expressions(tint, "", color, "B")
    rough = mel.create_material_expression(material, unreal.MaterialExpressionConstant, -200, 300)
    rough.set_editor_property("r", 0.88)
    mel.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    # The rocks are Nanite meshes, and a material must say it may be drawn by Nanite or the default material is used
    material.set_editor_property("used_with_nanite", True)
    material.set_editor_property(
        "used_with_instanced_static_meshes", True
    )  # And as instances, which is how they are drawn
    mel.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)

    failed = 0
    for rock in ROCKS:
        instance_path = f"{FOLDER}/MI_{rock}"
        if unreal.EditorAssetLibrary.does_asset_exist(instance_path):
            instance = unreal.EditorAssetLibrary.load_asset(instance_path)
        else:
            instance = tools.create_asset(
                f"MI_{rock}",
                FOLDER,
                unreal.MaterialInstanceConstant,
                unreal.MaterialInstanceConstantFactoryNew(),
            )
        instance.set_editor_property("parent", material)
        diffuse = unreal.EditorAssetLibrary.load_asset(
            f"/Game/Licensed/PolyHaven/{rock}/{rock}_diff_1k"
        )
        if diffuse is None:
            unreal.log_error(f"Missing diffuse for {rock}")
            failed += 1
            continue
        mel.set_material_instance_texture_parameter_value(instance, "Diffuse", diffuse)
        unreal.EditorAssetLibrary.save_loaded_asset(instance)
        mesh = unreal.EditorAssetLibrary.load_asset(f"/Game/Licensed/PolyHaven/{rock}/{rock}_1k")
        mesh.set_material(0, instance)
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    unreal.log(f"ROCK_MATERIALS_DONE failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
