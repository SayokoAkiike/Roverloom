"""Build a site's Landscape material: four Poly Haven layers on slope, drift, gravel, and noise, with ripples and micro relief.

    UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script="scripts/unreal/build_gale_material.py" -unattended -nullrhi
    UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script="scripts/unreal/build_gale_material.py noctis" -unattended -nullrhi

Without a site argument it builds M_GaleLandscape exactly as before. For another site of scripts/terrain/sites.json it builds
that site's material with its own look (LOOKS below) and, when hirise_albedo.py has run, multiplies the colour by the ground
brightness from the HiRISE orthoimage: the real pattern of light and dark ground, from one greyscale photo.

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

import json
import math
import sys
from pathlib import Path

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
# Per-site looks. Colours are chosen by eye against HiRISE colour products and published descriptions, never measured.
#  tints/patch: as above. drift_bias: more (positive) or fewer wind-drifted fines. gravel_bias: the same for gravel.
#  bands_cm: thickness of horizontal layering painted on steep rock by world height (0 = none). albedo: strength of the
#  HiRISE brightness map (0..1).
LOOKS = {
    "gale": {
        "tints": TINTS,
        "patch": ((1.12, 0.78, 0.60), (1.0, 0.98, 0.84)),
        "drift_bias": 0.0,
        "gravel_bias": 0.0,
        "bands_cm": 0.0,
        "albedo": 0.0,
    },
    # Noctis Labyrinthus: light-toned layered deposits (pale buff to yellowish) exposed on slopes, darker basaltic sand on the
    # floor, and wind-blown ridges. HiRISE captions: PSP_005400_1685, ESP_014353_1685, ESP_027526_1685.
    "noctis": {
        "tints": [(1.05, 0.70, 0.48), (0.62, 0.50, 0.44), (1.30, 1.06, 0.78), (0.80, 0.58, 0.44)],
        "patch": ((1.10, 0.84, 0.66), (1.04, 1.0, 0.86)),
        "drift_bias": 0.05,
        "gravel_bias": -0.05,
        "bands_cm": 420.0,
        "albedo": 0.85,
    },
    # Amazonis Planitia: smooth, dust-mantled lava plains, bright and uniform butterscotch, few rocks; the pit walls darker.
    # HiRISE captions: ESP_025893_2025, ESP_026249_2025.
    "amazonis": {
        "tints": [(1.22, 0.80, 0.52), (1.34, 0.92, 0.60), (0.66, 0.46, 0.36), (0.86, 0.60, 0.44)],
        "patch": ((1.08, 0.84, 0.64), (1.02, 0.96, 0.82)),
        "drift_bias": 0.18,
        "gravel_bias": -0.2,
        "bands_cm": 0.0,
        "albedo": 0.5,
    },
    # Lyot Crater, 49 N, in northern winter: dark basaltic barchans on a bright, dusty crater floor (the HiRISE brightness
    # map carries the dunes). Frost, a mix of CO2 and water ice, lies on the pole-facing (north) half of each dune but not on
    # the warmer south-facing half, and in patches on the floor. HiRISE captions: ESP_074942_2295, ESP_053406_2295.
    "lyot": {
        "tints": [(1.12, 0.84, 0.66), (0.70, 0.58, 0.52), (0.92, 0.74, 0.60), (0.78, 0.62, 0.52)],
        "patch": ((1.04, 0.92, 0.82), (1.0, 0.98, 0.94)),
        "drift_bias": 0.0,
        "gravel_bias": -0.1,
        "bands_cm": 0.0,
        "albedo": 1.0,
        # facing: north-facing share of the normal where frost starts, and how fast it gets full (a 20 degree slope is 0.34)
        "frost": {
            "pole": "north",
            "facing_from": 0.05,
            "facing_gain": 5.0,
            # 0: the floor's own small slopes (much of them stereo noise) never frost; on the dunes, the north-facing
            # half is whiter (dune frost below). 1 frosted every north-facing facet, which spotted the floor white.
            "slope_cover": 0.0,
            "flat_cover": 0.0,
            # Dune sand (dark in the brightness map) loses its heat fastest at night and frosts over first, all but
            # its steep slip face; the crater floor stays bare apart from thin frosted streaks (ESP_074942_2295)
            "dune_frost": 0.72,  # clearly dark ground only: the floor's dark specks stay bare (Mac look check)
            "color": (0.86, 0.86, 0.88),
            "strength": 0.92,
        },
        # Thin frosted streaks on the floor, running about north-south as in the winter image
        "streaks": {
            "surface": "flat",
            "downslope_deg": 80.0,
            "spacing_cm": 300.0,
            "thin": 0.75,
            "color": (0.86, 0.86, 0.88),
            "strength": 0.3,
        },
    },
    # North polar dunes, 80 N (Olympia Undae), in spring: the seasonal CO2 frost still covers the ground; the dark dune sand,
    # absorbing more sunlight, clears first in spots, and dark sand streaks down the frosted slip faces. Seen from orbit these
    # streaks, which cast no shadow, look like trees: the "ghost forest". HiRISE captions: ESP_062937_2605, and the 2008
    # north polar dune image explained by the HiRISE team (dark basaltic sand sliding down the frosted dunes).
    "olympia": {
        "tints": [(1.04, 0.92, 0.84), (0.46, 0.43, 0.43), (0.84, 0.76, 0.70), (0.62, 0.54, 0.50)],
        "patch": ((1.0, 0.95, 0.90), (0.96, 0.97, 1.0)),
        "drift_bias": -0.1,
        "gravel_bias": -0.2,
        "bands_cm": 0.0,
        "albedo": 1.0,
        "frost": {
            "pole": "north",
            "facing_from": 0.0,
            "facing_gain": 0.0,
            "slope_cover": 0.0,
            "flat_cover": 0.9,
            "dark_clears": 0.9,  # where the measured brightness is under this, the dune sand has cleared,
            # except on slip faces steeper than about 15 degrees, which keep their frost longest: the streaks run there
            "color": (0.80, 0.77, 0.77),  # dust-laden CO2 frost: a warm, pinkish grey-white
            "strength": 0.78,
        },
        # Dark streaks down the slip faces. downslope_deg: the direction the steep faces mostly face, measured on the site
        # heightfield (degrees from east, toward north); a fixed direction keeps the stripes steady far from the origin.
        "streaks": {
            "downslope_deg": 135.0,
            "spacing_cm": 400.0,
            "thin": 0.5,
            "color": (0.10, 0.085, 0.08),
            "strength": 1.0,
        },
    },
}
SITE = next((a for a in sys.argv[1:] if not a.startswith("-")), "gale")
LOOK = LOOKS[SITE]
SITE_INFO = json.loads(
    (Path(unreal.Paths.project_dir()).parent / "scripts/terrain/sites.json").read_text()
)[SITE]
FOLDER, NAME = SITE_INFO["material"].rsplit("/", 1)
TINTS = LOOK["tints"]
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


def apply_albedo(base, world):
    """Multiply by the HiRISE brightness map (hirise_albedo.py) over the site and the horizon squares, if it exists."""
    if not LOOK["albedo"]:
        return base, None
    terrain = Path(unreal.Paths.project_dir(), "Saved/Terrain", SITE)
    textures = {}
    for key, file in (("site", f"{SITE}_albedo.png"), ("horizon", f"{SITE}_horizon_albedo.png")):
        if not (terrain / file).exists():
            unreal.log_warning(
                f"{file} is missing: run scripts/terrain/hirise_albedo.py --site {SITE}"
            )
            return base, None
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(terrain / file))
        task.set_editor_property("destination_path", FOLDER)
        task.set_editor_property(
            "destination_name", f"T_{SITE.capitalize()}Albedo{'' if key == 'site' else 'Horizon'}"
        )
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("automated", True)
        task.set_editor_property("save", False)
        tools.import_asset_tasks([task])
        texture = unreal.EditorAssetLibrary.load_asset(
            f"{FOLDER}/{task.get_editor_property('destination_name')}"
        )
        texture.set_editor_property("srgb", False)
        texture.set_editor_property(
            "compression_settings", unreal.TextureCompressionSettings.TC_GRAYSCALE
        )
        texture.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
        texture.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
        unreal.EditorAssetLibrary.save_loaded_asset(texture)
        textures[key] = texture
    repo = Path(unreal.Paths.project_dir()).parent
    horizon = json.loads((repo / SITE_INFO["report"] / "horizon.json").read_text())
    east, north = SITE_INFO["origin_m"]
    wx, wy = mask(world, "r"), mask(world, "g")

    def uv_over(extent_m):
        # World cm to the square's 0..1, row 0 north (Unreal Y is the site's -north)
        u = div(add(div(wx, const(100.0)), const(extent_m / 2 + east)), const(extent_m))
        v = div(add(div(wy, const(100.0)), const(extent_m / 2 - north)), const(extent_m))
        out = node(unreal.MaterialExpressionAppendVector)
        link(u, out, "A")
        link(v, out, "B")
        return out, u, v

    def brightness(texture, uv):
        n = node(unreal.MaterialExpressionTextureSample)
        n.set_editor_property("texture", texture)
        n.set_editor_property(
            "sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE
        )
        n.set_editor_property(
            "sampler_source", unreal.SamplerSourceMode.SSM_CLAMP_WORLD_GROUP_SETTINGS
        )
        link(uv, n, "UVs")
        return mul(mask(n, "r"), const(255.0 / 128.0))  # 128 is the mean, 1.0

    site_uv, su, sv = uv_over(1008.0)
    horizon_uv, _, _ = uv_over(horizon["extent_m"])
    inside = mul(
        mul(saturate(mul(su, const(50.0))), saturate(mul(sub(const(1.0), su), const(50.0)))),
        mul(saturate(mul(sv, const(50.0))), saturate(mul(sub(const(1.0), sv), const(50.0)))),
    )  # 1 inside the site square, fading over its outer 2 %
    measured = lerp(
        brightness(textures["horizon"], horizon_uv), brightness(textures["site"], site_uv), inside
    )
    return mul(base, lerp(const(1.0), measured, const(LOOK["albedo"]))), measured


def main() -> int:
    global material
    if unreal.EditorAssetLibrary.does_asset_exist(f"{FOLDER}/{NAME}"):
        material = unreal.EditorAssetLibrary.load_asset(f"{FOLDER}/{NAME}")
        mel.delete_all_material_expressions(material)  # Rebuilt in place: no asset is deleted
    else:
        material = tools.create_asset(NAME, FOLDER, unreal.Material, unreal.MaterialFactoryNew())

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
    vertex_normal = node(unreal.MaterialExpressionVertexNormalWS)
    normal_z = mask(vertex_normal, "b")
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

    drift_at = 0.5 - LOOK["drift_bias"]
    drift = mul(saturate(mul(sub(drift_noise, const(drift_at)), const(5.0))), mul(gentle, flat))
    gravel_patch = mul(
        mul(
            saturate(mul(sub(patch_noise, const(0.5 - LOOK["gravel_bias"])), const(5.0))),
            sub(const(1.0), drift),
        ),
        flat,
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
    patch_tint = lerp(const3(*LOOK["patch"][0]), const3(*LOOK["patch"][1]), macro_noise)
    base = mul(base, patch_tint)
    if LOOK["bands_cm"]:
        # Layered beds on steep rock: brightness bands by world height, a few metres thick, their thickness and phase
        # wandering with noise so that they read as strata, not stripes
        wz = mask(world, "b")
        phase = add(div(wz, const(LOOK["bands_cm"])), mul(sub(low_noise, const(0.5)), const(1.6)))
        band = add(const(0.82), mul(cycles("cos", phase), const(0.18)))
        fine_band = add(const(0.94), mul(cycles("cos", mul(phase, const(3.7))), const(0.06)))
        base = lerp(base, mul(base, mul(band, fine_band)), weights[2])
    base, measured = apply_albedo(base, world)
    frost_cover = None
    if "frost" in LOOK:
        # Seasonal frost. The site's north is Unreal's -Y, so a slope faces the pole when its normal points that way.
        f = LOOK["frost"]
        nx, ny = mask(vertex_normal, "r"), mask(vertex_normal, "g")
        facing = mul(ny, const(-1.0 if f["pole"] == "north" else 1.0))
        pole_slope = saturate(mul(sub(facing, const(f["facing_from"])), const(f["facing_gain"])))
        patches = saturate(
            mul(sub(noise(shifted(700.0, 3300.0), 0.004), const(1.0 - f["flat_cover"])), const(4.0))
        )
        frost_cover = saturate(add(mul(pole_slope, const(f["slope_cover"])), patches))
        if measured is not None and f.get("dune_frost"):
            dune = saturate(mul(sub(const(f["dune_frost"]), measured), const(2.0)))
            not_slip = sub(const(1.0), saturate(mul(sub(steep, const(0.10)), const(20.0))))
            pole_whiter = add(
                const(0.6), mul(pole_slope, const(0.4))
            )  # the north half of each dune whiter
            frost_cover = saturate(add(frost_cover, mul(mul(dune, not_slip), pole_whiter)))
        if measured is not None and f.get("dark_clears"):
            # Dark sand warms first: where the measured ground is dark, the frost has gone
            cleared = saturate(mul(sub(const(f["dark_clears"]), measured), const(2.5)))
            slip_face = saturate(mul(sub(steep, const(0.03)), const(15.0)))
            cleared = mul(cleared, sub(const(1.0), slip_face))
            # Defrosting starts in discrete spots, metres across (HiRISE ESP_081492_1215, "Spotted Dunes"), so the dune
            # sand shows through the frost in dark spots rather than all at once
            spots = saturate(
                mul(sub(noise(shifted(1300.0, 5200.0), 0.003), const(0.4)), const(3.0))
            )
            cleared = mul(cleared, spots)
            frost_cover = mul(frost_cover, sub(const(1.0), cleared))
        frost_color = mul(const3(*f["color"]), add(const(0.92), mul(fine_noise, const(0.16))))
        base = lerp(base, frost_color, mul(frost_cover, const(f["strength"])))
    if "streaks" in LOOK:
        # Dark sand streaks down the slip faces facing one way: stripes running downslope, broken and wavering
        k = LOOK["streaks"]
        theta = math.radians(k["downslope_deg"])
        dx, dy = math.cos(theta), -math.sin(theta)  # in Unreal's frame
        nx, ny = mask(vertex_normal, "r"), mask(vertex_normal, "g")
        toward = add(mul(nx, const(dx)), mul(ny, const(dy)))
        if k.get("surface") == "flat":
            on_face = saturate(
                sub(const(1.0), mul(steep, const(30.0)))
            )  # flat ground only, under about 8 degrees
        else:
            on_face = saturate(
                mul(sub(toward, const(0.08)), const(6.0))
            )  # slopes over about 5 degrees facing that way
        across = add(mul(wx, const(-dy)), mul(wy, const(dx)))
        along = add(mul(wx, const(dx)), mul(wy, const(dy)))
        # Noise stretched sixfold downslope: streaks of uneven width and spacing, not a regular hatching
        stretched = node(unreal.MaterialExpressionAppendVector)
        link(div(across, const(k["spacing_cm"])), stretched, "A")
        link(div(along, const(k["spacing_cm"] * 6.0)), stretched, "B")
        streak_pos = node(unreal.MaterialExpressionAppendVector)
        link(stretched, streak_pos, "A")
        link(const(0.0), streak_pos, "B")
        stripe = saturate(
            mul(sub(noise(streak_pos, 1.0, 2), const(k["thin"])), const(1.0 / (1.0 - k["thin"])))
        )
        broken = saturate(mul(sub(noise(shifted(2600.0, 8800.0), 0.0015), const(0.3)), const(3.0)))
        streak = mul(mul(stripe, on_face), mul(broken, const(k["strength"])))
        streak_color = mul(const3(*k["color"]), add(const(0.8), mul(fine_noise, const(0.4))))
        base = lerp(base, streak_color, streak)
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
    if frost_cover is not None:
        roughness = lerp(roughness, const(0.45), mul(frost_cover, const(0.6)))  # Frost is smoother

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
