"""Build Roverloom's original six-wheel rover as visual meshes, with Blender.

V2 of the visual roadmap (docs/visual-roadmap.md). The meshes are visual only: they never carry
collision, and their sizes come from the Unreal pawn's constants, which come from
rovers/designs/pathfinder_6w.json. Changing a number here never changes physics, scoring, or the
contract.

Frame: metres, origin at the rig body's center, +X forward, +Y left, +Z up (the contract's
right-handed frame). Unreal's importer converts to centimetres and its left-handed frame; check the
orientation on import.

Outputs, written to --out (default unreal/Saved/RoverModel, which Git ignores):
    SM_RoverBody.fbx      everything rigid on the body, origin at the body's center
    SM_RoverWheel.fbx     one wheel, origin at the axle's center, axle along Y; it spins
    SM_RoverStrut.fbx     a 1 m leg, centered; the pawn scales Z by the wheel's drop
    SM_RoverAxle.fbx      from the wheel's center to the strut; mirrored in Y for the other side
    rover_preview.glb     the assembled rover at rest, for viewing
    report.json           sizes, triangle counts, and checks
    preview_*.jpg         Cycles renders, with --render

Run with Blender 4.2 or later, or with the bpy module:
    blender -b -P scripts/blender/build_rover.py -- --out unreal/Saved/RoverModel --render
    python -I scripts/blender/build_rover.py --out unreal/Saved/RoverModel --render
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

# isort: off
import bpy  # type: ignore[import-not-found]  # must come first: it makes bmesh and mathutils importable
import bmesh  # type: ignore[import-not-found]
from mathutils import Matrix, Vector  # type: ignore[import-not-found]

# isort: on

# Copied from unreal/Source/Roverloom/Rover/RoverDrive.h (centimetres there, metres here).
WHEEL_RADIUS = 0.25
WHEEL_WIDTH = 0.20
HALF_TRACK = 1.037
MOUNT_X = 0.976
MOUNT_Z = -0.20
BODY_SIZE = (2.00, 1.50, 0.40)
REST_DROP = 0.25  # WheelModel rest length 30 cm less 5 cm static compression
BODY_CENTER_HEIGHT = 0.70  # above flat ground at rest
MAST_X = 0.85
MAST_TOP_Z = 1.30  # camera at 2.0 m above flat ground
PANEL_AREA_M2 = 6.0  # pathfinder_6w power.panel_m2
# Arms and struts run inboard of the wheels, so that no part enters a wheel as it spins or drops.
ARM_Y = HALF_TRACK - WHEEL_WIDTH / 2 - 0.06

MATERIALS: dict[str, tuple[tuple[float, float, float], float, float]] = {
    # name: (base color, metallic, roughness). Preview colors only; Unreal makes its own materials.
    "M_RoverBody": ((0.74, 0.71, 0.65), 0.0, 0.55),
    "M_RoverFoil": ((0.80, 0.58, 0.22), 1.0, 0.35),
    "M_RoverAluminum": ((0.70, 0.70, 0.72), 1.0, 0.40),
    "M_RoverDark": ((0.05, 0.05, 0.055), 0.0, 0.50),
    "M_RoverSolar": ((0.03, 0.05, 0.12), 0.3, 0.20),
    "M_RoverGlass": ((0.01, 0.01, 0.015), 0.0, 0.05),
}


class MeshBuilder:
    """Collects primitives into one bmesh, with one material slot per name."""

    def __init__(self) -> None:
        self.bm = bmesh.new()
        self.slots: list[str] = []

    def _finish(self, verts: list[Any], material: str, matrix: Matrix, smooth: bool) -> None:
        bmesh.ops.transform(self.bm, matrix=matrix, verts=verts)
        if material not in self.slots:
            self.slots.append(material)
        index = self.slots.index(material)
        for face in {f for v in verts for f in v.link_faces}:
            face.material_index = index
            face.smooth = smooth

    def box(
        self,
        size: tuple[float, float, float],
        at: tuple[float, float, float],
        material: str,
        rotation: Matrix | None = None,
    ) -> None:
        verts = bmesh.ops.create_cube(self.bm, size=1.0)["verts"]
        bmesh.ops.scale(self.bm, vec=Vector(size), verts=verts)
        rot = rotation if rotation is not None else Matrix.Identity(4)
        self._finish(verts, material, Matrix.Translation(at) @ rot, smooth=False)

    def cylinder(
        self,
        radius: float,
        length: float,
        at: tuple[float, float, float],
        axis: str,
        material: str,
        segments: int = 32,
    ) -> None:
        verts = bmesh.ops.create_cone(
            self.bm, cap_ends=True, segments=segments, radius1=radius, radius2=radius, depth=length
        )["verts"]
        turn = {
            "x": Matrix.Rotation(math.pi / 2, 4, "Y"),
            "y": Matrix.Rotation(math.pi / 2, 4, "X"),
            "z": Matrix.Identity(4),
        }[axis]
        self._finish(verts, material, Matrix.Translation(at) @ turn, smooth=True)

    def tube_y(
        self, r_out: float, r_in: float, width: float, y: float, material: str, segments: int = 64
    ) -> None:
        """A hollow ring whose axis is Y."""
        rings = []
        for radius, yy in (
            (r_out, -width / 2),
            (r_out, width / 2),
            (r_in, width / 2),
            (r_in, -width / 2),
        ):
            ring = []
            for i in range(segments):
                a = 2 * math.pi * i / segments
                ring.append(self.bm.verts.new((radius * math.cos(a), yy, radius * math.sin(a))))
            rings.append(ring)
        for k in range(4):
            a_ring, b_ring = rings[k], rings[(k + 1) % 4]
            for i in range(segments):
                j = (i + 1) % segments
                self.bm.faces.new((a_ring[i], a_ring[j], b_ring[j], b_ring[i]))
        verts = [v for ring in rings for v in ring]
        self._finish(verts, material, Matrix.Translation((0.0, y, 0.0)), smooth=True)

    def beam(
        self,
        a: tuple[float, float, float],
        b: tuple[float, float, float],
        thickness: float,
        material: str,
    ) -> None:
        """A square beam from a to b."""
        va, vb = Vector(a), Vector(b)
        d = vb - va
        rot = d.normalized().to_track_quat("X", "Z").to_matrix().to_4x4()
        self.box((d.length, thickness, thickness), tuple((va + vb) / 2), material, rot)

    def to_object(self, name: str) -> Any:
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        mesh = bpy.data.meshes.new(name)
        self.bm.to_mesh(mesh)
        self.bm.free()
        for slot in self.slots:
            mesh.materials.append(material(slot))
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        return obj


def material(name: str) -> Any:
    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing
    color, metallic, roughness = MATERIALS[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    mat.diffuse_color = (*color, 1.0)
    return mat


def build_wheel() -> Any:
    """Origin at the axle's center, axle along Y. Spokes show spin; grousers reach the radius."""
    m = MeshBuilder()
    rim_out, rim_in, grouser = WHEEL_RADIUS - 0.012, WHEEL_RADIUS - 0.022, 0.012
    m.tube_y(rim_out, rim_in, WHEEL_WIDTH, 0.0, "M_RoverAluminum")
    for y in (-WHEEL_WIDTH / 2 + 0.004, WHEEL_WIDTH / 2 - 0.004):
        m.tube_y(rim_out, rim_in - 0.02, 0.008, y, "M_RoverAluminum")
    for i in range(24):
        a = 2 * math.pi * i / 24
        r = rim_out + grouser / 2 - 0.001
        m.box(
            (0.008, WHEEL_WIDTH, grouser + 0.002),
            (r * math.cos(a), 0.0, r * math.sin(a)),
            "M_RoverAluminum",
            Matrix.Rotation(-a + math.pi / 2, 4, "Y"),
        )
    m.cylinder(0.055, 0.14, (0.0, 0.0, 0.0), "y", "M_RoverDark")
    m.cylinder(0.03, 0.17, (0.0, 0.0, 0.0), "y", "M_RoverAluminum", segments=16)
    for i in range(6):
        # Two segments per spoke, offset in angle, like a flexure.
        a0 = 2 * math.pi * i / 6
        a1 = a0 + 0.25
        mid = (0.055 + rim_in) / 2
        p0 = (0.05 * math.cos(a0), 0.0, 0.05 * math.sin(a0))
        p1 = (mid * math.cos(a0 + 0.18), 0.0, mid * math.sin(a0 + 0.18))
        p2 = ((rim_in + 0.004) * math.cos(a1), 0.0, (rim_in + 0.004) * math.sin(a1))
        m.beam(p0, p1, 0.016, "M_RoverAluminum")
        m.beam(p1, p2, 0.016, "M_RoverAluminum")
    return m.to_object("SM_RoverWheel")


def build_body() -> Any:
    """Everything rigid on the body: chassis, deck, mast, rocker-bogies, arm, antenna, cameras."""
    m = MeshBuilder()
    bx, by, bz = BODY_SIZE
    top = bz / 2
    # Chassis, inside the rig's 2.0 x 1.5 x 0.4 m body box.
    m.box((1.90, 1.40, 0.36), (0.0, 0.0, 0.0), "M_RoverBody")
    for s in (-1, 1):
        m.box((1.60, 0.012, 0.26), (0.0, s * 0.706, 0.0), "M_RoverFoil")
    m.box((0.012, 1.10, 0.22), (0.951, 0.0, 0.02), "M_RoverFoil")
    for i in range(13):
        m.box((0.08, 0.01, 0.26), (-0.99, -0.6 + i * 0.1, 0.0), "M_RoverAluminum")
    # Solar deck: pathfinder_6w has 6 m^2. Behind the mast, raised on posts.
    panel_x0, panel_x1 = -1.75, 0.60
    panel_len = panel_x1 - panel_x0
    panel_w = PANEL_AREA_M2 / panel_len
    panel_z = top + 0.12
    panel_cx = (panel_x0 + panel_x1) / 2
    m.box((panel_len, panel_w, 0.03), (panel_cx, 0.0, panel_z), "M_RoverDark")
    nx, ny, gap = 8, 9, 0.012
    cell_x, cell_y = (panel_len - gap) / nx - gap, (panel_w - gap) / ny - gap
    for i in range(nx):
        for j in range(ny):
            cx = panel_x0 + gap + cell_x / 2 + i * (cell_x + gap)
            cy = -panel_w / 2 + gap + cell_y / 2 + j * (cell_y + gap)
            m.box((cell_x, cell_y, 0.006), (cx, cy, panel_z + 0.017), "M_RoverSolar")
    for px in (panel_x0 + 0.85, 0.45):
        for py in (-0.55, 0.55):
            m.cylinder(0.025, 0.12, (px, py, top + 0.05), "z", "M_RoverAluminum", segments=12)
    m.beam(
        (panel_x0 + 0.25, 0.0, top + 0.02),
        (panel_x0 + 0.25, 0.0, panel_z - 0.02),
        0.04,
        "M_RoverAluminum",
    )
    # Mast and camera head; the camera sits 2.0 m above flat ground, as in the pawn.
    m.cylinder(
        0.04,
        MAST_TOP_Z - top - 0.04,
        (MAST_X, 0.0, (top + MAST_TOP_Z - 0.04) / 2),
        "z",
        "M_RoverAluminum",
    )
    m.cylinder(0.06, 0.05, (MAST_X, 0.0, MAST_TOP_Z - 0.03), "z", "M_RoverDark")
    m.box((0.16, 0.36, 0.12), (MAST_X, 0.0, MAST_TOP_Z + 0.04), "M_RoverBody")
    m.box((0.20, 0.40, 0.01), (MAST_X + 0.02, 0.0, MAST_TOP_Z + 0.105), "M_RoverDark")
    for y in (-0.11, 0.11):
        m.cylinder(0.032, 0.04, (MAST_X + 0.09, y, MAST_TOP_Z + 0.04), "x", "M_RoverDark")
        m.cylinder(0.022, 0.006, (MAST_X + 0.112, y, MAST_TOP_Z + 0.04), "x", "M_RoverGlass")
    m.cylinder(0.018, 0.03, (MAST_X + 0.09, 0.0, MAST_TOP_Z + 0.07), "x", "M_RoverGlass")
    # Hazard cameras, front and rear.
    for x, d in ((bx / 2 - 0.03, 1), (-bx / 2 + 0.02, -1)):
        for y in (-0.12, 0.12):
            m.box((0.05, 0.09, 0.05), (x, y, -0.15), "M_RoverDark")
            m.cylinder(0.015, 0.01, (x + d * 0.028, y, -0.15), "x", "M_RoverGlass")
    # Rocker-bogie arms: static here, like the pawn's greybox. Wheels hang from the mounts on struts
    # (SM_RoverStrut) and axles (SM_RoverAxle), which the pawn moves with each wheel's drop.
    for s in (-1, 1):
        y = s * ARM_Y
        f, p, b = (MOUNT_X, y, MOUNT_Z), (0.20, y, 0.02), (-0.50, y, -0.06)
        mid, rear = (0.0, y, MOUNT_Z), (-MOUNT_X, y, MOUNT_Z)
        for a, c in ((f, p), (p, b), (b, mid), (b, rear)):
            m.beam(a, c, 0.05, "M_RoverAluminum")
        m.cylinder(0.035, ARM_Y - 0.70, (0.20, s * (0.70 + ARM_Y) / 2, 0.02), "y", "M_RoverDark")
        m.cylinder(0.045, 0.08, p, "y", "M_RoverDark")
        m.cylinder(0.04, 0.07, b, "y", "M_RoverDark")
        for mx in (MOUNT_X, 0.0, -MOUNT_X):
            m.box((0.08, 0.08, 0.06), (mx, y, MOUNT_Z), "M_RoverDark")
    # Sample arm, stowed across the front.
    m.cylinder(0.05, 0.06, (bx / 2 + 0.02, -0.45, 0.0), "x", "M_RoverDark")
    m.beam((bx / 2 + 0.05, -0.45, 0.0), (bx / 2 + 0.05, 0.35, 0.02), 0.045, "M_RoverAluminum")
    m.cylinder(0.035, 0.06, (bx / 2 + 0.05, 0.35, 0.02), "x", "M_RoverDark")
    m.beam((bx / 2 + 0.09, 0.35, 0.02), (bx / 2 + 0.09, -0.08, -0.08), 0.04, "M_RoverAluminum")
    m.box((0.09, 0.11, 0.09), (bx / 2 + 0.09, -0.10, -0.08), "M_RoverDark")
    # Low-gain antenna on the deck's rear left.
    ax, ay = panel_x0 + 0.15, 0.9
    m.cylinder(0.015, 0.22, (ax, ay, panel_z + 0.12), "z", "M_RoverAluminum", segments=12)
    m.cylinder(0.10, 0.015, (ax, ay, panel_z + 0.24), "z", "M_RoverBody")
    return m.to_object("SM_RoverBody")


def build_strut() -> Any:
    """A vertical leg 1 m tall, centered, so that the pawn scales its Z by the wheel's drop."""
    m = MeshBuilder()
    m.box((0.05, 0.05, 1.0), (0.0, 0.0, 0.0), "M_RoverAluminum")
    return m.to_object("SM_RoverStrut")


def build_axle() -> Any:
    """Origin at the wheel's center; reaches from the hub to the strut along -Y (left wheels here).

    The pawn mirrors it in Y for the other side. It does not spin."""
    m = MeshBuilder()
    reach = HALF_TRACK - ARM_Y
    m.cylinder(0.028, reach, (0.0, -reach / 2, 0.0), "y", "M_RoverDark", segments=16)
    m.box((0.07, 0.04, 0.07), (0.0, -reach, 0.0), "M_RoverDark")
    return m.to_object("SM_RoverAxle")


WHEEL_CENTERS = [
    (x, s * HALF_TRACK, MOUNT_Z - REST_DROP) for s in (-1, 1) for x in (MOUNT_X, 0.0, -MOUNT_X)
]


def measure(obj: Any) -> dict[str, Any]:
    vs = [obj.matrix_world @ v.co for v in obj.data.vertices]
    lo = [min(v[i] for v in vs) for i in range(3)]
    hi = [max(v[i] for v in vs) for i in range(3)]
    obj.data.calc_loop_triangles()
    return {
        "min_m": [round(x, 4) for x in lo],
        "max_m": [round(x, 4) for x in hi],
        "triangles": len(obj.data.loop_triangles),
        "materials": [m.name for m in obj.data.materials],
    }


def check(body: Any, wheel: Any, axle: Any) -> dict[str, Any]:
    wverts = [v.co for v in wheel.data.vertices]
    radius = max(math.hypot(v.x, v.z) for v in wverts)
    half_width = max(abs(v.y) for v in wverts)
    b = measure(body)
    ground = -BODY_CENTER_HEIGHT
    checks = {
        "wheel_outer_radius_m": round(radius, 4),
        "wheel_radius_matches": abs(radius - WHEEL_RADIUS) <= 0.002,
        "wheel_half_width_m": round(half_width, 4),
        "wheel_hub_within": half_width <= WHEEL_WIDTH / 2 + 0.04,
        "wheel_bottom_on_ground": abs((MOUNT_Z - REST_DROP - WHEEL_RADIUS) - ground) <= 1e-6,
        "body_ground_clearance_m": round(b["min_m"][2] - ground, 4),
        "body_clear_of_ground": b["min_m"][2] - ground >= 0.3,
        "mast_top_above_ground_m": round(b["max_m"][2] - ground, 4),
        "panel_area_m2": PANEL_AREA_M2,
    }
    for x, y, z in WHEEL_CENTERS:
        # No body part may sit inside a wheel's swept cylinder at rest.
        inside = [
            v
            for v in body.data.vertices
            if abs(v.co.y - y) < WHEEL_WIDTH / 2 - 0.005
            and math.hypot(v.co.x - x, v.co.z - z) < WHEEL_RADIUS - 0.005
        ]
        checks.setdefault("body_vertices_inside_wheels", 0)
        checks["body_vertices_inside_wheels"] += len(inside)
    checks["wheels_unobstructed"] = checks["body_vertices_inside_wheels"] == 0
    # The axle must end at the strut, outside the wheel's inner face.
    reach = max(-v.co.y for v in axle.data.vertices)
    checks["axle_reaches_strut"] = abs(reach - (HALF_TRACK - ARM_Y) - 0.02) <= 1e-4
    checks["struts_clear_of_wheels_m"] = round(HALF_TRACK - WHEEL_WIDTH / 2 - (ARM_Y + 0.025), 4)
    checks["struts_clear_of_wheels"] = checks["struts_clear_of_wheels_m"] > 0.0
    return checks


def export(obj: Any, path: Path) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(
        filepath=str(path),
        use_selection=True,
        apply_unit_scale=True,
        object_types={"MESH"},
        mesh_smooth_type="FACE",
        add_leaf_bones=False,
        bake_anim=False,
        path_mode="STRIP",
    )


def assemble(wheel: Any, strut: Any, axle: Any) -> None:
    """Places wheels, struts, and axles at rest, as the pawn would. For previews only."""
    for x, y, z in WHEEL_CENTERS:
        side = 1.0 if y > 0 else -1.0
        for name, data, loc, scale in (
            ("Wheel", wheel.data, (x, y, z), (1.0, 1.0, 1.0)),
            (
                "Strut",
                strut.data,
                (x, side * ARM_Y, MOUNT_Z - REST_DROP / 2),
                (1.0, 1.0, REST_DROP),
            ),
            ("Axle", axle.data, (x, y, z), (1.0, side, 1.0)),
        ):
            inst = bpy.data.objects.new(name, data)
            inst.location = loc
            inst.scale = scale
            bpy.context.scene.collection.objects.link(inst)


def render(out: Path) -> list[str]:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 48
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 88
    scene.view_settings.view_transform = "AgX"
    ground = MeshBuilder()
    ground.box((40.0, 40.0, 0.02), (0.0, 0.0, -BODY_CENTER_HEIGHT - 0.01), "M_Ground")
    MATERIALS["M_Ground"] = ((0.46, 0.21, 0.10), 0.0, 0.95)  # V1b's regolith color
    ground.to_object("PreviewGround")
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.66, 0.51, 0.38, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    scene.world = world
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.5
    sun.data.angle = math.radians(1.0)
    sun.rotation_euler = (math.radians(50), 0.0, math.radians(-35))
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    shots = {
        "front_three_quarter": ((6.4, -5.0, 2.1), (0.0, 0.0, 0.35), 40),
        "side": ((0.0, -9.0, 0.8), (0.0, 0.0, 0.45), 35),
        "rear_high": ((-6.0, 4.4, 4.0), (0.0, 0.0, 0.3), 40),
        "chase": ((-9.0, 0.0, 2.4), (0.0, 0.0, 0.3), 70),
    }
    written = []
    for name, (loc, target, fov) in shots.items():
        cam.location = loc
        direction = Vector(target) - Vector(loc)
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        cam.data.angle = math.radians(fov)
        path = out / f"preview_{name}.jpg"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        written.append(path.name)
    return written


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("unreal/Saved/RoverModel"))
    parser.add_argument(
        "--render", action="store_true", help="also render preview images (slow on CPU)"
    )
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    wheel = build_wheel()
    body = build_body()
    strut = build_strut()
    axle = build_axle()
    checks = check(body, wheel, axle)
    sizes = {obj.name: measure(obj) for obj in (body, wheel, strut, axle)}
    for obj in (body, wheel, strut, axle):
        export(obj, args.out / f"{obj.name}.fbx")
    assemble(wheel, strut, axle)
    for obj in (wheel, strut, axle):
        obj.hide_render = True
        obj.location = (0.0, 0.0, -50.0)  # the originals stay out of previews
    bpy.ops.export_scene.gltf(filepath=str(args.out / "rover_preview.glb"), export_format="GLB")
    report: dict[str, Any] = {
        "blender": bpy.app.version_string,
        "frame": "metres; origin at the rig body's center; +X forward, +Y left, +Z up",
        "meshes": sizes,
        "checks": checks,
    }
    if args.render:
        report["previews"] = render(args.out)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["checks"], indent=2))
    failed = [k for k, v in checks.items() if v is False]
    if failed:
        print("FAILED:", ", ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    sys.exit(main(argv))
