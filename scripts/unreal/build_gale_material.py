"""Build M_GaleLandscape: four Poly Haven layers blended by slope, height, and noise, at two tiling scales. Unreal Editor Python.

    UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script="scripts/unreal/build_gale_material.py" -unattended -nullrhi

Needs import_polyhaven.py first. The result is /Game/Licensed/Gale/M_GaleLandscape, which Git ignores. There are no painted
layers: the weights come from the surface itself, so the same material fits any heightfield.

    regolith  dry_ground_01        the background
    sand      dense_sand           low ground, patchy by noise
    bedrock   rock_boulder_cracked steep slopes
    gravel    rocks_ground_03      patches from fine noise

Repetition is hidden three ways: a coarse tile fades in with distance and replaces the fine one, a large noise varies the
brightness, and the fine and coarse tiles use unrelated scales. The colors are pulled toward a Mars-like tan. Nothing here
claims to be a measured Martian color.
"""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

import sys

import unreal  # type: ignore[import-not-found]

mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
FOLDER = "/Game/Licensed/Gale"
TEX = "/Game/Licensed/PolyHaven"
LAYERS = ["dry_ground_01", "dense_sand", "rock_boulder_cracked", "rocks_ground_03"]
NEAR_CM = 220.0  # One fine tile
FAR_CM = 5200.0  # One coarse tile, unrelated to the fine one

material = None
_x = [-2400]


def node(cls, x=None, y=0):
    _x[0] += 40
    return mel.create_material_expression(material, cls, _x[0] if x is None else x, y)


def link(source, target, pin="", out=""):
    mel.connect_material_expressions(source, out, target, pin)
    return target


def const(value):
    n = node(unreal.MaterialExpressionConstant)
    n.set_editor_property("r", float(value))
    return n


def const3(r, g, b):
    n = node(unreal.MaterialExpressionConstant3Vector)
    n.set_editor_property("constant", unreal.LinearColor(r, g, b, 1.0))
    return n


def op(cls, a, b=None, a_pin="A", b_pin="B"):
    n = node(cls)
    link(a, n, a_pin)
    if b is not None:
        link(b, n, b_pin)
    return n


def mul(a, b):
    return op(unreal.MaterialExpressionMultiply, a, b)


def add(a, b):
    return op(unreal.MaterialExpressionAdd, a, b)


def sub(a, b):
    return op(unreal.MaterialExpressionSubtract, a, b)


def lerp(a, b, alpha):
    n = node(unreal.MaterialExpressionLinearInterpolate)
    link(a, n, "A")
    link(b, n, "B")
    link(alpha, n, "Alpha")
    return n


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


def noise(position, scale):
    n = node(unreal.MaterialExpressionNoise)
    link(position, n, "Position")
    n.set_editor_property("scale", scale)
    n.set_editor_property("output_min", 0.0)
    n.set_editor_property("output_max", 1.0)
    n.set_editor_property("levels", 3)
    return n


def sample(texture_name, uv, kind):
    n = node(unreal.MaterialExpressionTextureSample)
    n.set_editor_property(
        "texture",
        unreal.EditorAssetLibrary.load_asset(f"{TEX}/{texture_name}/{texture_name}_{kind}_2k"),
    )
    n.set_editor_property(
        "sampler_source", unreal.SamplerSourceMode.SSM_WRAP_WORLD_GROUP_SETTINGS
    )  # Shared samplers: Metal allows 16
    n.set_editor_property(
        "sampler_type",
        {
            "diff": unreal.MaterialSamplerType.SAMPLERTYPE_COLOR,
            "nor_gl": unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL,
            "arm": unreal.MaterialSamplerType.SAMPLERTYPE_MASKS,
        }[kind],
    )
    link(uv, n, "UVs")
    return n


def weighted_sum(items):
    """items: list of (node, weight node). Returns the sum of node * weight."""
    total = mul(items[0][0], items[0][1])
    for value, weight in items[1:]:
        total = add(total, mul(value, weight))
    return total


def main() -> int:
    global material
    if unreal.EditorAssetLibrary.does_asset_exist(f"{FOLDER}/M_GaleLandscape"):
        unreal.EditorAssetLibrary.delete_asset(f"{FOLDER}/M_GaleLandscape")
    material = tools.create_asset(
        "M_GaleLandscape", FOLDER, unreal.Material, unreal.MaterialFactoryNew()
    )

    world = node(unreal.MaterialExpressionWorldPosition, -2400, 0)
    # World X and Y as a 2-vector for tiling
    wx = mask(world, "r")
    wy = mask(world, "g")
    wz = mask(world, "b")
    xy = node(unreal.MaterialExpressionAppendVector)
    link(wx, xy, "A")
    link(wy, xy, "B")

    def uv(cm, offset=0.0):
        scaled = mul(xy, const(1.0 / cm))
        return add(scaled, const(offset)) if offset else scaled

    # Weights from the surface
    normal_z = mask(node(unreal.MaterialExpressionVertexNormalWS), "b")
    steep = sub(const(1.0), normal_z)  # 0 flat, 1 vertical
    slope = saturate(
        mul(sub(steep, const(0.05)), const(5.0))
    )  # Rock from about 18 degrees, full by about 35
    low_noise = noise(world, 0.0004)
    mid_noise = noise(world, 0.0035)
    fine_noise = noise(world, 0.02)
    height01 = saturate(
        mul(add(wz, const(4500.0)), const(1.0 / 9000.0))
    )  # The Gale site spans about 90 m
    w_bedrock = saturate(add(mul(slope, const(1.4)), mul(sub(mid_noise, const(0.5)), const(0.6))))
    w_bedrock = mul(
        w_bedrock, saturate(mul(sub(steep, const(0.03)), const(8.0)))
    )  # Never on flat ground
    not_rock = sub(const(1.0), w_bedrock)
    w_sand = mul(
        saturate(
            add(
                sub(const(1.5), mul(height01, const(2.2))),
                mul(sub(low_noise, const(0.5)), const(1.6)),
            )
        ),
        not_rock,
    )
    gravel_noise = add(mul(fine_noise, const(0.6)), mul(mid_noise, const(0.4)))
    w_gravel = mul(
        mul(saturate(mul(sub(gravel_noise, const(0.55)), const(6.0))), not_rock), const(0.85)
    )
    others = add(add(w_bedrock, w_sand), w_gravel)
    w_regolith = saturate(sub(const(1.0), others))
    total = add(w_regolith, others)
    weights = [
        mul(w, op(unreal.MaterialExpressionDivide, const(1.0), total))
        for w in (w_regolith, w_sand, w_bedrock, w_gravel)
    ]

    depth = node(unreal.MaterialExpressionPixelDepth)
    far_blend = saturate(
        mul(sub(depth, const(1800.0)), const(1.0 / 5500.0))
    )  # Fine tile gives way to the coarse one with distance
    macro_light = add(
        const(0.78), mul(low_noise, const(0.44))
    )  # Large patches of lighter and darker ground

    colors, normals, arms = [], [], []
    for index, layer in enumerate(LAYERS):
        near_uv = uv(NEAR_CM)
        far_uv = uv(FAR_CM, 0.37 * (index + 1))
        near_color = sample(layer, near_uv, "diff")
        far_color = sample(layer, far_uv, "diff")
        colors.append(lerp(near_color, far_color, far_blend))
        normals.append(sample(layer, near_uv, "nor_gl"))
        arms.append(sample(layer, near_uv, "arm"))

    base = mul(weighted_sum(list(zip(colors, weights, strict=True))), macro_light)
    desaturated = node(unreal.MaterialExpressionDesaturation)
    link(base, desaturated, "")
    link(const(0.55), desaturated, "Fraction")
    tinted = mul(desaturated, const3(1.12, 0.78, 0.52))  # Toward a Mars-like tan
    normal = weighted_sum(list(zip(normals, weights, strict=True)))
    flat_normal = const3(0.0, 0.0, 1.0)
    normal = lerp(normal, flat_normal, mul(far_blend, const(0.85)))
    arm = weighted_sum(list(zip(arms, weights, strict=True)))
    roughness = lerp(const(0.85), mask(arm, "g"), const(0.5))  # Dust keeps it rough everywhere

    mel.connect_material_property(tinted, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(normal, "", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(mask(arm, "r"), "", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    mel.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)
    unreal.log(f"MATERIAL_DONE expressions={mel.get_num_material_expressions(material)}")
    try:
        stats = mel.get_statistics(material)
        unreal.log(f"MATERIAL_STATS {stats}")
    except Exception as error:  # Statistics are optional
        unreal.log_warning(f"MATERIAL_STATS unavailable: {error}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
