"""Build the two materials of the rover effects: M_DustParticle and M_RutDecal. Unreal Editor Python.

    UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script="scripts/unreal/build_effect_materials.py" -unattended -nullrhi

Output: /Game/Licensed/Gale/, which Git ignores (the rest of the Gale content is there too). RoverEffects.cpp loads both by path.

M_DustParticle: a translucent, lit sphere that is dense in the middle and soft at the edge (a fresnel), that fades where it meets
the ground (depth fade), and whose opacity comes from each instance's custom data, so that the C++ can fade every puff by its age.
M_RutDecal: a deferred decal that darkens and presses the sand: a groove across the width, tread bars along the length, soft ends so
that overlapping decals blend into one track. Colours are chosen by eye, not measured.
"""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

import sys

import unreal  # type: ignore[import-not-found]

mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
FOLDER = "/Game/Licensed/Gale"
material = None


def make(name):
    path = f"{FOLDER}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        asset = unreal.EditorAssetLibrary.load_asset(path)
        mel.delete_all_material_expressions(asset)  # Rebuilt in place: no asset is deleted
        return asset
    return tools.create_asset(name, FOLDER, unreal.Material, unreal.MaterialFactoryNew())


def node(cls, x=0, y=0):
    return mel.create_material_expression(material, cls, x, y)


def link(source, target, pin="", out=""):
    mel.connect_material_expressions(source, out, target, pin)
    return target


def const(value, x=0, y=0):
    n = node(unreal.MaterialExpressionConstant, x, y)
    n.set_editor_property("r", float(value))
    return n


def const3(r, g, b):
    n = node(unreal.MaterialExpressionConstant3Vector)
    n.set_editor_property("constant", unreal.LinearColor(r, g, b, 1.0))
    return n


def op(cls, a, b):
    n = node(cls)
    link(a, n, "A")
    link(b, n, "B")
    return n


def mul(a, b):
    return op(unreal.MaterialExpressionMultiply, a, b)


def add(a, b):
    return op(unreal.MaterialExpressionAdd, a, b)


def sub(a, b):
    return op(unreal.MaterialExpressionSubtract, a, b)


def saturate(a):
    n = node(unreal.MaterialExpressionClamp)
    link(a, n, "")
    n.set_editor_property("min_default", 0.0)
    n.set_editor_property("max_default", 1.0)
    return n


def mask(source, channel):
    n = node(unreal.MaterialExpressionComponentMask)
    for name in ("r", "g", "b", "a"):
        n.set_editor_property(name, name == channel)
    link(source, n, "")
    return n


def dust() -> None:
    global material
    material = make("M_DustParticle")
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    material.set_editor_property(
        "translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_VOLUMETRIC_NON_DIRECTIONAL
    )
    material.set_editor_property("used_with_instanced_static_meshes", True)
    material.set_editor_property("two_sided", True)

    per_instance = node(unreal.MaterialExpressionPerInstanceCustomData)
    per_instance.set_editor_property("data_index", 0)
    fresnel = node(unreal.MaterialExpressionFresnel)
    fresnel.set_editor_property("exponent", 1.4)
    centre = sub(const(1.0), fresnel)  # Dense in the middle, thin at the edge
    centre = mul(centre, centre)  # Squared, so the edge fades out with no visible rim
    opacity = mul(mul(per_instance, centre), const(0.9))
    fade = node(unreal.MaterialExpressionDepthFade)
    fade.set_editor_property(
        "fade_distance_default", 140.0
    )  # Where a puff meets the ground, it fades instead of cutting
    link(opacity, fade, "Opacity")
    colour = const3(0.66, 0.44, 0.31)
    mel.connect_material_property(colour, "", unreal.MaterialProperty.MP_BASE_COLOR)
    # Sun-lit edges: a puff between the camera and the sun glows at its rim, from the dust scattering the light forward. The glow is the rim
    # (fresnel) times how directly the camera looks toward the sun, in the sun's own colour. RimSign flips which way the engine's light
    # direction points, if it points the other way.
    to_sun = node(unreal.MaterialExpressionSkyAtmosphereLightDirection)
    rim_sign = node(unreal.MaterialExpressionScalarParameter)
    rim_sign.set_editor_property("parameter_name", "RimSign")
    rim_sign.set_editor_property("default_value", 1.0)
    camera_vector = node(unreal.MaterialExpressionCameraVectorWS)
    facing = node(unreal.MaterialExpressionDotProduct)
    link(camera_vector, facing, "A")
    link(mul(to_sun, rim_sign), facing, "B")
    toward_sun = saturate(
        mul(facing, const(-1.0))
    )  # The camera vector points back at the camera, so looking toward the sun is negative
    toward_sun = mul(
        toward_sun, mul(toward_sun, toward_sun)
    )  # Cubed: only close to the sun's direction
    sun_colour = node(unreal.MaterialExpressionSkyAtmosphereLightIlluminanceOnGround)
    rim = mul(mul(fresnel, toward_sun), mul(sun_colour, const(0.9)))
    mel.connect_material_property(
        add(mul(colour, const(0.12)), rim), "", unreal.MaterialProperty.MP_EMISSIVE_COLOR
    )  # Not black in shade, and a lit rim
    mel.connect_material_property(const(1.0), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(fade, "", unreal.MaterialProperty.MP_OPACITY)
    mel.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)


def ruts() -> None:
    global material
    material = make("M_RutDecal")
    material.set_editor_property("material_domain", unreal.MaterialDomain.MD_DEFERRED_DECAL)
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)

    uv = node(unreal.MaterialExpressionTextureCoordinate)
    across = mask(uv, "r")  # 0 to 1 across the track
    along = mask(uv, "g")  # 0 to 1 along it
    centred = sub(mul(across, const(2.0)), const(1.0))  # -1 to 1
    profile = sub(const(1.0), mul(centred, centred))  # A groove: 1 in the middle, 0 at the edges
    # Soft ends: min(along, 1 - along) * 5, so that neighbouring decals blend
    ends = saturate(
        mul(op(unreal.MaterialExpressionMin, along, sub(const(1.0), along)), const(5.0))
    )
    opacity = mul(mul(saturate(mul(profile, const(1.5))), ends), const(0.95))

    bars = node(unreal.MaterialExpressionSine)
    bars.set_editor_property("period", 1.0)
    link(mul(along, const(5.0)), bars, "")  # Five tread bars along 26 cm
    bar_light = add(const(0.5), mul(bars, const(0.5)))  # 0 to 1
    pressed = const3(0.04, 0.02, 0.014)
    colour = mul(pressed, add(const(0.8), mul(bar_light, const(0.4))))

    # Tangent-space normal: the groove tilts toward its middle, and the bars tilt along the track
    groove_slope = mul(centred, const(0.55))
    cosine = node(unreal.MaterialExpressionCosine)
    cosine.set_editor_property("period", 1.0)
    link(mul(along, const(5.0)), cosine, "")
    tilt_along = mul(cosine, const(0.28))
    xy = node(unreal.MaterialExpressionAppendVector)
    link(groove_slope, xy, "A")
    link(tilt_along, xy, "B")
    normal = node(unreal.MaterialExpressionAppendVector)
    link(xy, normal, "A")
    link(const(1.0), normal, "B")

    mel.connect_material_property(colour, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(normal, "", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(const(0.95), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY)
    mel.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)


def main() -> int:
    dust()
    ruts()
    unreal.log("EFFECT_MATERIALS_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
