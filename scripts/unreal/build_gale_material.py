"""Build M_GaleLandscape: four Poly Haven layers on slope, drift, gravel, and noise, with ripples and micro relief. Editor Python.

    UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script="scripts/unreal/build_gale_material.py" -unattended -nullrhi

Needs import_polyhaven.py first. The result is /Game/Licensed/Gale/M_GaleLandscape, which Git ignores. There are no painted
layers: the weights come from the surface itself, so the same material fits any heightfield.

    regolith  dry_ground_01        the background, a reddish dust
    sand      dense_sand           wind-drifted fine sand on gentle ground, smooth, with ripples
    bedrock   rock_boulder_cracked steep slopes
    gravel    rocks_ground_03      patches of gravelly ground, and stones scattered in the edges of the drifts

What makes it read as one surface and not a tiled texture:
  * a fine tile (2.2 m) and a coarse tile (52 m) with unrelated scales, the coarse one fading in with distance;
  * a micro-relief normal (37 cm tile) that only the first 25 m or so can see;
  * two large-scale color noises: one brightness, one that swings patches between reddish and ochre;
  * ripples in the drifts: a cosine in world space with a constant 17 cm wavelength and a phase that noise offsets, so the
    crests meander and fork instead of running in straight parallel lines; they fade out with distance. (A wavelength that
    varied by place drew concentric rings far from the origin, because the phase then grows with the world position.)
  * every layer is desaturated and given its own red-brown or ochre tint, then the whole is pushed in contrast.
The Earth textures are stand-ins, and the colors do the rest. Nothing here is a measured Martian color.
"""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

import sys

import unreal  # type: ignore[import-not-found]

mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
FOLDER = "/Game/Licensed/Gale"
TEX = "/Game/Licensed/PolyHaven"
LAYERS = ["dry_ground_01", "dense_sand", "rock_boulder_cracked", "rocks_ground_03"]
# Per-layer tint after desaturation, toward red-brown and ochre
TINTS = [
    (1.10, 0.62, 0.40),
    (1.38, 0.96, 0.58),
    (0.62, 0.42, 0.34),
    (0.70, 0.48, 0.36),
]  # Sand is a light ochre, gravel a dark brown
NEAR_CM = 220.0  # One fine tile
FAR_CM = 5200.0  # One coarse tile, unrelated to the fine one
MICRO_CM = 37.0  # Micro relief, for the first few meters
RIPPLE_CM = 17.0  # Ripple wavelength

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


def div(a, b):
    return op(unreal.MaterialExpressionDivide, a, b)


def power(a, exponent):
    return op(unreal.MaterialExpressionPower, a, const(exponent), "Base", "Exponent")


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


def noise(position, scale, levels=3):
    n = node(unreal.MaterialExpressionNoise)
    link(position, n, "Position")
    n.set_editor_property("scale", scale)
    n.set_editor_property("output_min", 0.0)
    n.set_editor_property("output_max", 1.0)
    n.set_editor_property("levels", levels)
    return n


def cycles(kind, source):
    """sin or cos of 2*pi*source, so that source counts whole cycles."""
    n = node(unreal.MaterialExpressionSine if kind == "sin" else unreal.MaterialExpressionCosine)
    n.set_editor_property("period", 1.0)
    link(source, n, "")
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
        material = unreal.EditorAssetLibrary.load_asset(f"{FOLDER}/M_GaleLandscape")
        mel.delete_all_material_expressions(material)  # Rebuilt in place: no asset is deleted
    else:
        material = tools.create_asset(
            "M_GaleLandscape", FOLDER, unreal.Material, unreal.MaterialFactoryNew()
        )

    world = node(unreal.MaterialExpressionWorldPosition, -2400, 0)
    wx, wy = mask(world, "r"), mask(world, "g")
    xy = node(unreal.MaterialExpressionAppendVector)
    link(wx, xy, "A")
    link(wy, xy, "B")

    def uv(cm, offset=0.0):
        scaled = mul(xy, const(1.0 / cm))
        return add(scaled, const(offset)) if offset else scaled

    def shifted(x, y):
        """The world position moved, so that two noises of one scale do not agree."""
        return add(world, const3(x, y, 0.0))

    # ---- Where each layer goes: from slope, from noise, never from a painted map
    normal_z = mask(node(unreal.MaterialExpressionVertexNormalWS), "b")
    steep = sub(const(1.0), normal_z)  # 0 flat, 1 vertical
    slope = saturate(
        mul(sub(steep, const(0.05)), const(5.0))
    )  # Rock from about 18 degrees, full by about 35
    gentle = saturate(
        sub(const(1.0), mul(steep, const(1.0 / 0.03)))
    )  # Drifts only lie on ground under about 14 degrees
    low_noise = noise(world, 0.0004)
    macro_noise = noise(shifted(9000.0, 4000.0), 0.00012, 2)  # Very large patches
    mid_noise = noise(world, 0.0035)
    fine_noise = noise(world, 0.02)
    drift_noise = noise(shifted(2300.0, 7100.0), 0.0011)  # Where the wind piled sand
    patch_noise = noise(shifted(5100.0, 900.0), 0.0065)  # Where gravel lies

    w_bedrock = saturate(add(mul(slope, const(1.4)), mul(sub(mid_noise, const(0.5)), const(0.6))))
    w_bedrock = mul(
        w_bedrock, saturate(mul(sub(steep, const(0.03)), const(8.0)))
    )  # Never on flat ground
    flat = sub(const(1.0), w_bedrock)

    drift = mul(saturate(mul(sub(drift_noise, const(0.5)), const(5.0))), mul(gentle, flat))
    gravel_patch = mul(
        mul(saturate(mul(sub(patch_noise, const(0.5)), const(5.0))), sub(const(1.0), drift)), flat
    )
    gravel_patch = mul(gravel_patch, add(const(0.6), mul(fine_noise, const(0.4))))  # Ragged edges
    # Stones in the edges of the drifts: gravelly sand
    stony = mul(drift, mul(const(0.4), saturate(mul(sub(fine_noise, const(0.55)), const(4.0)))))
    w_gravel = add(gravel_patch, stony)
    w_sand = sub(drift, stony)
    others = add(add(w_bedrock, w_sand), w_gravel)
    w_regolith = saturate(sub(const(1.0), others))
    total = add(w_regolith, others)
    weights = [mul(w, div(const(1.0), total)) for w in (w_regolith, w_sand, w_bedrock, w_gravel)]

    depth = node(unreal.MaterialExpressionPixelDepth)
    far_blend = saturate(
        mul(sub(depth, const(1800.0)), const(1.0 / 5500.0))
    )  # The fine tile gives way to the coarse one
    near_amount = sub(
        const(1.0), saturate(mul(depth, const(1.0 / 2500.0)))
    )  # Micro relief and ripples, the first 25 m

    # ---- Color: every layer desaturated and tinted red-brown or ochre
    colors, normals, arms = [], [], []
    for index, layer in enumerate(LAYERS):
        near_uv = uv(NEAR_CM)
        far_uv = uv(FAR_CM, 0.37 * (index + 1))
        near_color = sample(layer, near_uv, "diff")
        far_color = sample(layer, far_uv, "diff")
        mixed = lerp(near_color, far_color, far_blend)
        grey = node(unreal.MaterialExpressionDesaturation)
        link(mixed, grey, "")
        link(const(0.5), grey, "Fraction")
        colors.append(mul(grey, const3(*TINTS[index])))
        normals.append(sample(layer, near_uv, "nor_gl"))
        arms.append(sample(layer, near_uv, "arm"))

    base = weighted_sum(list(zip(colors, weights, strict=True)))
    brightness = add(
        const(0.72), mul(low_noise, const(0.56))
    )  # Patches of lighter and darker ground
    base = mul(base, brightness)
    # Patches swing between reddish and ochre, over hundreds of meters
    patch_tint = lerp(const3(1.12, 0.78, 0.60), const3(1.0, 0.98, 0.84), macro_noise)
    base = mul(base, patch_tint)
    # Real pebbles for the first few metres, around the wheels, where no stone instances may lie: the gravel texture again at 26 cm a
    # tile, laid over the gravelly ground and the drift edges, and fading out by about 10 m
    pebble_depth = sub(const(1.0), saturate(mul(depth, const(1.0 / 1000.0))))
    pebble_uv = uv(26.0, 0.57)
    pebble_color = sample(LAYERS[3], pebble_uv, "diff")
    pebble_grey = node(unreal.MaterialExpressionDesaturation)
    link(pebble_color, pebble_grey, "")
    link(const(0.5), pebble_grey, "Fraction")
    pebble_tinted = mul(mul(pebble_grey, const3(*TINTS[3])), const(1.5))
    gravel_amount = mul(
        pebble_depth,
        saturate(add(add(w_gravel, mul(w_sand, const(0.6))), mul(w_regolith, const(0.35)))),
    )
    base = lerp(base, mul(pebble_tinted, brightness), mul(gravel_amount, const(0.75)))
    final_color = mul(power(base, 1.12), const(1.12))  # Contrast, then a little back

    # ---- Normal: texture relief, micro relief, and ripples
    flat_normal = const3(0.0, 0.0, 1.0)
    normal = weighted_sum(list(zip(normals, weights, strict=True)))
    micro_uv = uv(MICRO_CM, 0.21)
    micro = lerp(
        sample(LAYERS[0], micro_uv, "nor_gl"), sample(LAYERS[3], micro_uv, "nor_gl"), weights[3]
    )
    normal = add(normal, mul(sub(micro, flat_normal), mul(near_amount, const(0.9))))
    grain_amount = sub(
        const(1.0), saturate(mul(depth, const(1.0 / 1100.0)))
    )  # Grain relief, to about 11 m
    grain = sample(
        LAYERS[1], uv(4.5, 0.13), "nor_gl"
    )  # The sand's own normal map, at 4.5 cm a tile
    normal = add(normal, mul(sub(grain, flat_normal), mul(grain_amount, const(0.9))))
    # Pebble relief from the gravel texture's own normal map, at the same scale as its colour above
    pebble_normal = sample(LAYERS[3], uv(26.0, 0.57), "nor_gl")
    normal = add(
        normal,
        mul(
            sub(pebble_normal, flat_normal),
            mul(grain_amount, mul(add(w_gravel, mul(w_sand, const(0.6))), const(1.0))),
        ),
    )
    # Ripples: crests run across the wind, here along world (0.44, -0.9). Their phase is warped by noise.
    along = add(mul(wx, const(0.9)), mul(wy, const(0.44)))
    # A constant wavelength, with the crests bent by noise as a phase offset. (A wavelength that varies by place makes the phase
    # depend on the world position times its change, which swings wildly far from the origin and draws rings.)
    warp = add(
        mul(sub(mid_noise, const(0.5)), const(2.6)), mul(sub(low_noise, const(0.5)), const(3.0))
    )  # Crests meander and fork
    crest = add(div(along, const(RIPPLE_CM)), warp)
    slope_of_ripple = mul(
        cycles("cos", crest), mul(const(0.75), mul(w_sand, near_amount))
    )  # Steepest on the drifts, fading out
    # The ripple's tilt as a vector (x, y, 0)
    xy_ripple = node(unreal.MaterialExpressionAppendVector)
    link(mul(slope_of_ripple, const(-0.9)), xy_ripple, "A")
    link(mul(slope_of_ripple, const(-0.44)), xy_ripple, "B")
    ripple_vector = node(unreal.MaterialExpressionAppendVector)
    link(xy_ripple, ripple_vector, "A")
    link(const(0.0), ripple_vector, "B")
    normal = add(normal, ripple_vector)
    normal = lerp(normal, flat_normal, mul(far_blend, const(0.85)))  # Far away the relief is flat

    arm = weighted_sum(list(zip(arms, weights, strict=True)))
    roughness = lerp(
        lerp(const(0.86), mask(arm, "g"), const(0.5)), const(0.72), mul(w_sand, const(0.6))
    )  # Sand a little smoother

    if "--debug-weights" in sys.argv:
        # A look at where the layers went: sand red, gravel green, bedrock blue, regolith dark. Not for use in the game.
        rg = node(unreal.MaterialExpressionAppendVector)
        link(weights[1], rg, "A")
        link(weights[3], rg, "B")
        rgb = node(unreal.MaterialExpressionAppendVector)
        link(rg, rgb, "A")
        link(weights[2], rgb, "B")
        final_color = rgb
    mel.connect_material_property(final_color, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(normal, "", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(mask(arm, "r"), "", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    mel.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)
    unreal.log(f"MATERIAL_DONE expressions={mel.get_num_material_expressions(material)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
