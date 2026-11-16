"""Give the V2 rover PBR materials, with dust that settles by surface direction and height. Unreal Editor Python.

    UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script="scripts/unreal/build_rover_materials.py" -unattended -nullrhi

Output: materials under /Game/Licensed/Gale/Rover/ (Git ignores them), set on the slots of /Game/Rover/SM_Rover* (local, untracked). All
procedural: the meshes' UVs are not relied on, so the patterns use the mesh's own coordinates (a world-to-local transform), and nothing here
needs a texture. Visual only: no collision and no physics value is touched.

    Body      cream painted panels with seams every 50 cm
    Foil      thermal blanket: gold foil, crinkled by noise in the normal
    Aluminum  brushed aluminium: a noise stretched along one axis, in the roughness
    Dark      dark anodised metal
    Solar     a grid of cells 12 cm square, each a little different, with silver busbars between them
    Glass     lenses: near-black glass with a blue-violet coating that shows at grazing angles
    Rubber    the wheel's tyre: matt, slightly bumpy

Dust, on every material: it settles on faces that point up and on the low parts of each mesh (height below the mesh origin, so the wheels'
lower halves and the underside of the body gather most), broken up by noise. The DustAmount parameter (0 to 1, default 0.85) scales it.
Colours are chosen by eye, not measured.
"""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

import sys

import unreal  # type: ignore[import-not-found]

mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
FOLDER = "/Game/Licensed/Gale/Rover"
DUST = (0.50, 0.33, 0.23)  # Linear, a red-brown sand

material = None


def node(cls, x=0, y=0):
    return mel.create_material_expression(material, cls, x, y)


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


def op(cls, a, b, a_pin="A", b_pin="B"):
    n = node(cls)
    link(a, n, a_pin)
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


def noise(position, scale, levels=3):
    n = node(unreal.MaterialExpressionNoise)
    link(position, n, "Position")
    n.set_editor_property("scale", scale)
    n.set_editor_property("output_min", 0.0)
    n.set_editor_property("output_max", 1.0)
    n.set_editor_property("levels", levels)
    return n


def fract(a):
    n = node(unreal.MaterialExpressionFrac)
    link(a, n, "")
    return n


def floor(a):
    n = node(unreal.MaterialExpressionFloor)
    link(a, n, "")
    return n


def edge_distance(coordinate, pitch):
    """Distance to the nearest grid line, in grid cells (0 on a line, 0.5 in the middle of a cell)."""
    cell = fract(mul(coordinate, const(1.0 / pitch)))
    return op(unreal.MaterialExpressionMin, cell, sub(const(1.0), cell))


def make(name):
    global material
    path = f"{FOLDER}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        material = unreal.EditorAssetLibrary.load_asset(path)
        mel.delete_all_material_expressions(material)  # Rebuilt in place: no asset is deleted
    else:
        material = tools.create_asset(name, FOLDER, unreal.Material, unreal.MaterialFactoryNew())
    return material


def build(name, kind, low_range):
    make(name)
    world = node(unreal.MaterialExpressionWorldPosition)
    local = node(unreal.MaterialExpressionTransformPosition)
    local.set_editor_property(
        "transform_source_type", unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_WORLD
    )
    local.set_editor_property(
        "transform_type", unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_LOCAL
    )
    link(world, local, "")
    lx, ly = mask(local, "r"), mask(local, "g")
    n_fine = noise(local, 0.5)
    n_mid = noise(local, 0.09)

    base = const3(0.5, 0.5, 0.5)
    metallic = const(0.0)
    rough = const(0.5)
    normal = None
    emissive = None
    specular = None

    if kind == "body":
        seam = saturate(
            mul(
                sub(
                    const(0.02),
                    op(
                        unreal.MaterialExpressionMin,
                        edge_distance(lx, 50.0),
                        edge_distance(ly, 50.0),
                    ),
                ),
                const(70.0),
            )
        )
        base = mul(const3(0.78, 0.75, 0.68), sub(const(1.0), mul(seam, const(0.4))))
        metallic = const(0.25)
        rough = add(const(0.42), mul(n_mid, const(0.14)))
    elif kind == "foil":
        base = const3(0.86, 0.56, 0.20)
        metallic = const(1.0)
        rough = add(const(0.20), mul(n_fine, const(0.22)))
        step = 0.7
        dx = sub(noise(add(local, const3(step, 0.0, 0.0)), 0.5), n_fine)
        dy = sub(noise(add(local, const3(0.0, step, 0.0)), 0.5), n_fine)
        xy = node(unreal.MaterialExpressionAppendVector)
        link(mul(dx, const(3.0)), xy, "A")
        link(mul(dy, const(3.0)), xy, "B")
        normal = node(unreal.MaterialExpressionAppendVector)
        link(xy, normal, "A")
        link(const(1.0), normal, "B")
    elif kind == "aluminum":
        base = const3(0.84, 0.85, 0.88)
        metallic = const(1.0)
        brushed = noise(mul(local, const3(0.03, 2.0, 2.0)), 1.0, 2)
        rough = add(const(0.26), mul(brushed, const(0.22)))
    elif kind == "dark":
        base = const3(0.04, 0.04, 0.05)
        metallic = const(0.85)
        rough = add(const(0.34), mul(n_mid, const(0.14)))
    elif kind == "solar":
        pitch = 15.0
        cells = node(unreal.MaterialExpressionAppendVector)
        link(floor(mul(lx, const(1.0 / pitch))), cells, "A")
        link(floor(mul(ly, const(1.0 / pitch))), cells, "B")
        cell_id = node(unreal.MaterialExpressionAppendVector)
        link(cells, cell_id, "A")
        link(const(0.0), cell_id, "B")
        variation = noise(cell_id, 0.93, 1)  # A different tone for every cell
        silicon = lerp(const3(0.008, 0.016, 0.075), const3(0.02, 0.042, 0.17), variation)
        line = saturate(
            mul(
                sub(
                    const(0.035),
                    op(
                        unreal.MaterialExpressionMin,
                        edge_distance(lx, pitch),
                        edge_distance(ly, pitch),
                    ),
                ),
                const(45.0),
            )
        )
        base = lerp(silicon, const3(0.34, 0.36, 0.40), line)
        metallic = lerp(
            const(0.0), const(0.8), line
        )  # The silicon is a dielectric; only the busbars are metal
        rough = lerp(const(0.22), const(0.4), line)
        specular = lerp(
            const(0.12), const(0.5), line
        )  # Weaker reflection, so the sky does not wash the cells out to lavender
    elif kind == "glass":
        base = const3(0.004, 0.006, 0.014)
        rough = const(0.03)
        fresnel = node(unreal.MaterialExpressionFresnel)
        fresnel.set_editor_property("exponent", 2.5)
        emissive = mul(
            mul(fresnel, const3(0.22, 0.12, 0.55)), const(0.9)
        )  # A violet coating, seen at grazing angles
    elif kind == "rubber":
        base = const3(0.03, 0.03, 0.035)
        rough = add(const(0.86), mul(n_fine, const(0.1)))
        step = 0.6
        dx = sub(noise(add(local, const3(step, 0.0, 0.0)), 1.4, 2), noise(local, 1.4, 2))
        dy = sub(noise(add(local, const3(0.0, step, 0.0)), 1.4, 2), noise(local, 1.4, 2))
        xy = node(unreal.MaterialExpressionAppendVector)
        link(mul(dx, const(1.6)), xy, "A")
        link(mul(dy, const(1.6)), xy, "B")
        normal = node(unreal.MaterialExpressionAppendVector)
        link(xy, normal, "A")
        link(const(1.0), normal, "B")

    # Dust: up-facing faces and the low parts of the mesh, broken up by noise, scaled by DustAmount
    up = saturate(mask(node(unreal.MaterialExpressionPixelNormalWS), "b"))
    height = mask(
        sub(world, node(unreal.MaterialExpressionObjectPositionWS)), "b"
    )  # Above (+) or below (-) the mesh origin
    low = saturate(mul(sub(const(0.0), height), const(1.0 / low_range)))
    broken = mul(sub(noise(local, 0.14), const(0.5)), const(0.8))
    amount = node(unreal.MaterialExpressionScalarParameter)
    amount.set_editor_property("parameter_name", "DustAmount")
    amount.set_editor_property("default_value", 0.85)
    stickiness = {
        "body": 0.8,
        "foil": 0.5,
        "aluminum": 0.7,
        "dark": 0.7,
        "solar": 0.08,
        "glass": 0.1,
        "rubber": 1.0,
    }[kind]  # Panels and lenses are kept cleaner
    dust = saturate(
        mul(
            sub(add(add(mul(up, const(1.1)), mul(low, const(0.95))), broken), const(0.42)),
            mul(amount, const(stickiness)),
        )
    )
    color = lerp(base, const3(*DUST), mul(dust, const(0.9)))
    metallic = lerp(metallic, const(0.0), mul(dust, const(0.95)))
    rough = lerp(rough, const(0.95), dust)

    mel.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(metallic, "", unreal.MaterialProperty.MP_METALLIC)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    if specular is not None:
        mel.connect_material_property(specular, "", unreal.MaterialProperty.MP_SPECULAR)
    if normal is not None:
        mel.connect_material_property(normal, "", unreal.MaterialProperty.MP_NORMAL)
    if emissive is not None:
        mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)
    return material


# (mesh, slot name) -> (new material name, kind, how far below the origin the dust reaches full, cm)
PLAN = {
    "SM_RoverBody": {
        "M_RoverBody": ("M_RB_Body", "body", 45.0),
        "M_RoverFoil": ("M_RB_Foil", "foil", 45.0),
        "M_RoverAluminum": ("M_RB_Aluminum", "aluminum", 45.0),
        "M_RoverDark": ("M_RB_Dark", "dark", 45.0),
        "M_RoverSolar": ("M_RB_Solar", "solar", 200.0),
        "M_RoverGlass": ("M_RB_Glass", "glass", 45.0),
    },
    "SM_RoverWheel": {
        "M_RoverAluminum": ("M_RW_Aluminum", "aluminum", 22.0),
        "M_RoverDark": ("M_RW_Rubber", "rubber", 22.0),
    },
    "SM_RoverStrut": {"M_RoverAluminum": ("M_RS_Aluminum", "aluminum", 40.0)},
    "SM_RoverAxle": {"M_RoverDark": ("M_RA_Dark", "dark", 10.0)},
}


def restore_original() -> int:
    """Put the flat-colour materials of the first import back on the meshes, for a before image. The PBR assets are left as they are."""
    for mesh_name, slots in PLAN.items():
        mesh = unreal.EditorAssetLibrary.load_asset(f"/Game/Rover/{mesh_name}")
        names = [
            str(slot.get_editor_property("material_slot_name"))
            for slot in mesh.get_editor_property("static_materials")
        ]
        for slot_name in slots:
            mesh.set_material(
                names.index(slot_name),
                unreal.EditorAssetLibrary.load_asset(f"/Game/Rover/{slot_name}"),
            )
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    unreal.log("ROVER_MATERIALS_RESTORED the flat originals")
    return 0


def main() -> int:
    if "--restore-original" in sys.argv:
        return restore_original()
    failed = 0
    for mesh_name, slots in PLAN.items():
        mesh = unreal.EditorAssetLibrary.load_asset(f"/Game/Rover/{mesh_name}")
        names = [
            str(slot.get_editor_property("material_slot_name"))
            for slot in mesh.get_editor_property("static_materials")
        ]
        for slot_name, (new_name, kind, low_range) in slots.items():
            if slot_name not in names:
                unreal.log_error(f"{mesh_name} has no slot {slot_name}")
                failed += 1
                continue
            mesh.set_material(names.index(slot_name), build(new_name, kind, low_range))
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    unreal.log(f"ROVER_MATERIALS_DONE failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
