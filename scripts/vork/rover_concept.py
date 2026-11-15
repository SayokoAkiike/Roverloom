"""Write vork scenes that show Roverloom's V2 rover model in a Mars-inspired setting.

These are concept renders for the README and promotion. They are **not game screenshots**:
nothing here runs the simulator, the Unreal client, or any physics. Every image made from them
must be labeled "Concept render (vork), not a game screenshot".

The rover comes from scripts/blender/build_rover.py (rover_preview.glb). The ground, rocks,
mesas, sky, and dust haze are generated here, with a fixed seed, from vork's own shapes and
programs written for this project. No third-party assets. Colors, haze, and the sky are
mars_inspired choices made by eye, not measurements.

Requires vork (https://github.com/voyager-so/vork), 0.5.1 or a compatible version, which is used
to place its sun. vork is under its own preview license and is not part of Roverloom.

    python3 scripts/vork/rover_concept.py --glb unreal/Saved/RoverModel/rover_preview.glb \
        --out unreal/Saved/RoverConcept
    vork check unreal/Saved/RoverConcept/hero.json
    vork render unreal/Saved/RoverConcept/hero.json --profile std/final --out hero.png
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys
from array import array
from collections.abc import Callable
from pathlib import Path
from typing import Any

GROUND_Y = -0.70  # the glb's origin is the rover body's center, 0.70 m above flat ground
REGOLITH = [0.40, 0.18, 0.085]  # linear; a little darker than V1b's, which read too pale here
REGOLITH_DARK = [0.20, 0.10, 0.055]
BASALT = [0.085, 0.05, 0.035]
MESA = [0.30, 0.15, 0.08]
SUN_COLOR = [1.0, 0.95, 0.88]  # set by eye
SOLAR_IRRADIANCE = 590.0  # W/m², at Mars's mean distance from the Sun

# Sky: a butterscotch dome, paler toward the horizon, with a forward-scattering glow around the
# Sun and a bluish aureole close to it when the Sun is low. A look chosen by eye, not a model.
SKY_PROGRAM = """// Mars-inspired sky for Roverloom concept renders, chosen by eye.
import vork;
struct Inputs {
    float3 sun_direction = float3(0.0, 1.0, 0.0);
    float sun_elevation = 0.4;
    float3 zenith = float3(0.30, 0.19, 0.12);
    float3 horizon = float3(0.80, 0.56, 0.37);
    float3 glow = float3(0.95, 0.66, 0.42);
    float3 aureole = float3(0.55, 0.70, 1.0);
    float glow_strength = 1.2;
    float aureole_strength = 2.5;
    float disk_cos = 0.99999;  // cosine of the visible disk's angular radius
    float disk = 40.0;  // bright enough to clip, too small to light the scene
};
float3 environment(EnvironmentContext ctx, Inputs inputs) {
    let d = normalize(ctx.direction);
    let s = normalize(inputs.sun_direction);
    let up = max(d.y, 0.0);
    let cos_sun = dot(d, s);
    var c = lerp(inputs.horizon, inputs.zenith, pow(up, 0.4));
    let low = 1.0 - smoothstep(0.0, 0.45, inputs.sun_elevation);
    c += inputs.glow * inputs.glow_strength * exp((cos_sun - 1.0) * 5.0) * (0.4 + 0.6 * low);
    let near = exp((cos_sun - 1.0) * 70.0);
    c += lerp(inputs.glow, inputs.aureole, low) * inputs.aureole_strength * near;
    c += inputs.disk * smoothstep(inputs.disk_cos - 0.000004, inputs.disk_cos, cos_sun);
    if (d.y < 0.0) {
        c = inputs.horizon * 0.25;
    }
    return c;
}
"""

# The dust haze: an exponential-height medium in the form vork admits for world fog.
DUST_PROGRAM = """// Mars-inspired dust haze for Roverloom concept renders, chosen by eye.
import vork;
struct Inputs {
    float3 absorption = float3(0.00010, 0.00030, 0.00060);
    float3 scattering = float3(0.0012, 0.0009, 0.0006);
    float base_height = -0.7;
    float falloff = 0.02;
    float anisotropy = 0.6;
};
MediumCoefficients medium(MediumContext ctx, Inputs inputs) {
    let density = exp(-inputs.falloff * (ctx.world_position.y - inputs.base_height));
    MediumCoefficients m;
    m.absorption = inputs.absorption * density;
    m.scattering = inputs.scattering * density;
    m.emission = float3(0.0);
    m.anisotropy = inputs.anisotropy;
    return m;
}
"""

# vork is +Y up. The rover faces +X, and its left side is -Z.
# tau is the dust's optical depth, which dims the Sun and brightens the sky; haze scales the fog.
SHOTS: dict[str, dict[str, Any]] = {
    "hero": {
        "about": "Low front three-quarter, late afternoon, sun behind the camera's left",
        "camera": [5.2, 0.35, 4.6],
        "target": [0.0, 0.05, 0.0],
        "lens_mm": 35,
        "sun_elevation_deg": 22,
        "sun_rotation_deg": 125,
        "tau": 0.5,
        "haze": 1.0,
        "exposure": -3.6,
    },
    "side": {
        "about": "Side view at mast height, midday",
        "camera": [0.4, 0.6, 8.5],
        "target": [0.0, 0.2, 0.0],
        "lens_mm": 40,
        "sun_elevation_deg": 55,
        "sun_rotation_deg": 150,
        "tau": 0.4,
        "haze": 0.7,
        "exposure": -4.8,
    },
    "sunset": {
        "about": "Low chase toward a sun 4 degrees above the horizon, rover nearly in silhouette",
        "camera": [-7.0, 0.1, 3.2],
        "target": [0.0, 0.4, 0.0],
        "lens_mm": 32,
        "sun_elevation_deg": 4,
        "sun_rotation_deg": 73,
        "tau": 0.45,
        "haze": 1.0,
        "exposure": -1.2,
    },
}


# Shots on the Gale site from scripts/terrain/hirise_site.py. The rover stands on the flattest
# spot found within the site, 144 m west and 24 m north of its center, facing a ridge that rises
# about 24 m some 250 m away to the north-northeast. Positions are relative to the rover.
GALE_SPOT = (360.0, 480.0)  # meters east and south of the heightfield's northwest corner
GALE_YAW_DEG = 59.0  # the rover's +X turned from east toward north
GALE_SHOTS: dict[str, dict[str, Any]] = {
    "gale": {
        "about": "Gale site from behind the rover's right, late afternoon, the ridge ahead",
        "camera": [1.7, 0.6, 6.9],
        "target": [0.4, 0.6, -2.6],
        "lens_mm": 30,
        "sun_elevation_deg": 18,
        "sun_rotation_deg": 200,
        "tau": 0.5,
        "haze": 0.8,
        "exposure": -3.4,
    },
}


def air_mass(elevation: float) -> float:
    """Kasten and Young's air mass, used only to dim the Sun with elevation."""
    degrees = math.degrees(elevation)
    return 1.0 / (math.sin(elevation) + 0.50572 * (degrees + 6.07995) ** -1.6364)


def rotate(q: list[float], v: list[float]) -> list[float]:
    x, y, z, w = q
    u = [x, y, z]
    uv = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
    uuv = [u[1] * uv[2] - u[2] * uv[1], u[2] * uv[0] - u[0] * uv[2], u[0] * uv[1] - u[1] * uv[0]]
    return [v[k] + 2.0 * (w * uv[k] + uuv[k]) for k in range(3)]


def sky(vork: str, shot: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The sun placed by vork's std/sky, with this project's sky program and Sun strength."""
    elevation = math.radians(shot["sun_elevation_deg"])
    options = {
        "sun_elevation": elevation,
        "sun_rotation": math.radians(shot["sun_rotation_deg"]),
    }
    result = subprocess.run(
        [vork, "std", "sky", json.dumps(options)], check=True, capture_output=True, text=True
    )
    sun = next(n for n in json.loads(result.stdout)["nodes"] if n.get("shape") == "sun")
    sun["color"] = SUN_COLOR
    sun["angle"] = 0.006  # Mars's sun is smaller than Earth's
    direct = SOLAR_IRRADIANCE * math.exp(-shot["tau"] * air_mass(elevation))
    sun["energy"] = round(direct, 3)
    # Sunlight scattered by dust lights the sky; most of it stays near the Sun's direction.
    scattered = SOLAR_IRRADIANCE * max(math.sin(elevation), 0.02) * (1.0 - math.exp(-shot["tau"]))
    toward_sun = rotate(sun["rotation"], [0.0, 0.0, 1.0])
    environment = {
        "type": "light",
        "name": "sky",
        "shape": "environment",
        "material": "sky",
        "energy": round(0.35 * scattered / math.pi + 1.0, 4),
    }
    material = {
        "program": "mars_sky",
        "inputs": {"sun_direction": [round(c, 6) for c in toward_sun], "sun_elevation": elevation},
    }
    return [environment, sun], material


def value_noise(seed: int) -> Callable[[float, float], float]:
    def hashed(i: int, j: int) -> float:
        h = (i * 374761393 + j * 668265263 + seed * 2147483647) & 0xFFFFFFFF
        h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
        return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0

    def noise(x: float, z: float) -> float:
        i, j = math.floor(x), math.floor(z)
        fx, fz = x - i, z - j
        ux, uz = fx * fx * (3 - 2 * fx), fz * fz * (3 - 2 * fz)
        a, b = hashed(i, j), hashed(i + 1, j)
        c, d = hashed(i, j + 1), hashed(i + 1, j + 1)
        return (a + (b - a) * ux) * (1 - uz) + (c + (d - c) * ux) * uz

    return noise


def heightfield(
    height: Callable[[float, float], float],
    xs: list[float],
    zs: list[float],
    color: Callable[[float, float], list[float]] | None = None,
) -> dict[str, Any]:
    """A triangle mesh over a grid, with smooth normals from finite differences."""
    positions, normals, colors, indices = [], [], [], []
    for z in zs:
        for x in xs:
            y = height(x, z)
            e = 0.25
            dx = (height(x + e, z) - height(x - e, z)) / (2 * e)
            dz = (height(x, z + e) - height(x, z - e)) / (2 * e)
            n = math.sqrt(dx * dx + 1 + dz * dz)
            positions.append([round(x, 3), round(y, 4), round(z, 3)])
            normals.append([round(-dx / n, 4), round(1 / n, 4), round(-dz / n, 4)])
            if color:
                colors.append([round(c, 4) for c in color(x, z)])
    width = len(xs)
    for r in range(len(zs) - 1):
        for c in range(width - 1):
            a = r * width + c
            indices += [a, a + width, a + 1, a + 1, a + width, a + width + 1]
    attributes = {
        "POSITION": {"type": "vec3", "data": positions},
        "NORMAL": {"type": "vec3", "data": normals},
    }
    if color:
        attributes["COLOR_0"] = {"type": "vec3", "data": colors}
    return {"attributes": attributes, "indices": {"type": "u32", "data": indices}}


def spaced(limit: float, fine: float, coarse: float, flat: float) -> list[float]:
    """Grid lines from -limit to limit: fine near the rover, coarser farther out."""
    out, x = [0.0], 0.0
    while x < limit:
        x += fine if x < flat else coarse
        out.append(min(x, limit))
    return [-v for v in reversed(out[1:])] + out


TERRAIN_LIMIT = 160.0
GALE_LIMIT = 480.0


def geometric(limit: float, fine: float, flat: float, growth: float) -> list[float]:
    """Grid lines from -limit to limit: fine near the rover, then spacing growing with distance."""
    out, x = [0.0], 0.0
    while x < limit:
        x += fine if x < flat else max(fine, x * growth)
        out.append(min(x, limit))
    return [-v for v in reversed(out[1:])] + out


def gale_height(site: Path, seed: int) -> Callable[[float, float], float]:
    """Measured HiRISE shape at about 1 m, plus generated bumps finer than the DTM resolves.

    x is east and z is south of the rover's spot, which is leveled within 3 m of the wheels.
    """
    meta = json.loads(site.with_suffix(".json").read_text(encoding="utf-8"))
    n, spacing = meta["samples"], meta["spacing_m"]
    low, span = meta["height_min_m"], meta["height_max_m"] - meta["height_min_m"]
    raw = array("H")
    raw.frombytes(site.read_bytes())
    if sys.byteorder == "big":
        raw.byteswap()

    def measured(x: float, z: float) -> float:
        col = min(max((GALE_SPOT[0] + x) / spacing, 0.0), n - 1.001)
        row = min(max((GALE_SPOT[1] + z) / spacing, 0.0), n - 1.001)
        c, r = int(col), int(row)
        fc, fr = col - c, row - r
        k = r * n + c
        top = raw[k] * (1 - fc) + raw[k + 1] * fc
        bottom = raw[k + n] * (1 - fc) + raw[k + n + 1] * fc
        return low + (top * (1 - fr) + bottom * fr) / 65535.0 * span

    base = measured(0.0, 0.0)
    noise = value_noise(seed)

    def height(x: float, z: float) -> float:
        r = math.hypot(x, z)
        near = min(1.0, max(0.0, (r - 3.0) / 6.0))
        bumps = 0.12 * (noise(x / 3.1, z / 3.1) - 0.5) + 0.05 * (noise(x / 1.1, z / 1.1) - 0.5)
        return GROUND_Y + near * (measured(x, z) - base + bumps)

    return height


def terrain_height(seed: int) -> Callable[[float, float], float]:
    """Gentle swells and small bumps, flat under the rover, falling to the plain at the edge."""
    noise = value_noise(seed)

    def height(x: float, z: float) -> float:
        r = math.hypot(x, z)
        near = min(1.0, max(0.0, (r - 3.0) / 6.0))  # flat under the rover's wheels
        edge = min(1.0, max(0.0, (TERRAIN_LIMIT - r) / 40.0))
        swell = 1.6 * (noise(x / 45.0, z / 45.0) - 0.5) + 0.7 * (noise(x / 17.0, z / 17.0) - 0.5)
        bumps = 0.12 * (noise(x / 3.1, z / 3.1) - 0.5) + 0.05 * (noise(x / 1.1, z / 1.1) - 0.5)
        return GROUND_Y + near * edge * (swell + bumps)

    return height


def regolith_color(seed: int) -> Callable[[float, float], list[float]]:
    """Two scales of noise vary the regolith's color, so that no repeat shows."""
    noise = value_noise(seed + 50)

    def color(x: float, z: float) -> list[float]:
        broad = 0.6 * noise(x * 0.035, z * 0.035) + 0.4 * noise(x * 0.11, z * 0.11)
        fine = 0.6 * noise(x * 0.9, z * 0.9) + 0.4 * noise(x * 2.1, z * 2.1)
        t = min(1.0, max(0.0, 0.3 + 0.55 * broad + 0.3 * (fine - 0.5)))
        return [d + (li - d) * t for d, li in zip(REGOLITH_DARK, REGOLITH, strict=True)]

    return color


def terrain(seed: int) -> dict[str, Any]:
    lines = spaced(TERRAIN_LIMIT, 0.5, 2.0, 14.0)
    return heightfield(terrain_height(seed), lines, lines, regolith_color(seed))


def rock_shape(seed: int, subdivisions: int = 3) -> dict[str, Any]:
    """An icosphere pushed out by noise and cut by a few random planes, so that it has faces.

    Its color is dark rock with dust settled on the faces that look up.
    """
    rng = random.Random(seed)
    t = (1 + math.sqrt(5)) / 2
    verts = [
        [-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0],
        [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
        [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1],
    ]  # fmt: skip
    faces = [
        [0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4],
        [11, 10, 2], [10, 7, 6], [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8],
        [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1],
    ]  # fmt: skip
    vs = [[c / math.sqrt(1 + t * t) for c in v] for v in verts]
    # Every edge is split at each level, so no edge recurs and one cache serves all levels.
    cache: dict[tuple[int, int], int] = {}

    def mid(a: int, b: int) -> int:
        key = (min(a, b), max(a, b))
        if key not in cache:
            m = [(vs[a][k] + vs[b][k]) / 2 for k in range(3)]
            n = math.sqrt(sum(c * c for c in m))
            vs.append([c / n for c in m])
            cache[key] = len(vs) - 1
        return cache[key]

    for _ in range(subdivisions):
        faces = [
            f
            for a, b, c in faces
            for f in (
                [a, mid(a, b), mid(c, a)],
                [b, mid(b, c), mid(a, b)],
                [c, mid(c, a), mid(b, c)],
                [mid(a, b), mid(b, c), mid(c, a)],
            )
        ]
    noise = value_noise(seed)
    planes = []
    for _ in range(rng.randint(7, 11)):
        u, v = rng.uniform(-1, 1), rng.uniform(0, 2 * math.pi)
        s = math.sqrt(1 - u * u)
        planes.append(([s * math.cos(v), u, s * math.sin(v)], rng.uniform(0.5, 0.78)))
    out = []
    for p in vs:
        r = 0.8 + 0.45 * noise(p[0] * 1.7 + 5, p[2] * 1.7 + p[1] * 1.3 + 5)
        q = [c * r for c in p]
        for n, d in planes:
            excess = sum(q[k] * n[k] for k in range(3)) - d
            if excess > 0:
                q = [q[k] - excess * n[k] for k in range(3)]
        q[1] = max(q[1], -0.45)  # a flat underside to sit on
        out.append([round(c, 4) for c in q])
    tint = rng.uniform(0.8, 1.3)
    rock = [c * tint for c in BASALT]
    colors = []
    for p in vs:
        dust = min(1.0, max(0.0, (p[1] - 0.5) * 1.6)) * 0.45
        colors.append([round(r + (d - r) * dust, 4) for r, d in zip(rock, REGOLITH, strict=True)])
    return {
        "attributes": {
            "POSITION": {"type": "vec3", "data": out},
            "COLOR_0": {"type": "vec3", "data": colors},
        },
        "indices": {"type": "u32", "data": [i for f in faces for i in f]},
    }


ROCK_SHAPES = 6


def rock_nodes(
    seed: int, ground: Callable[[float, float], float], camera: list[float]
) -> list[dict[str, Any]]:
    """Few large rocks and many small ones, kept off the rover's spot and the camera's foot."""
    rng = random.Random(seed)
    nodes: list[dict[str, Any]] = []
    while len(nodes) < 420:
        r = 3.2 + 90.0 * rng.random() ** 1.6  # denser near the rover, where the camera looks
        a = rng.uniform(0.0, 2 * math.pi)
        x, z = r * math.cos(a), r * math.sin(a)
        if math.hypot(x - camera[0], z - camera[2]) < 3.0:
            rng.random()  # keep the sequence the same for every shot
            continue
        size = min(0.05 * (1.0 - rng.random()) ** -0.75, 1.4)  # power-law sizes, 5 cm and up
        sx, sy, sz = (size * rng.uniform(0.75, 1.25) for _ in range(3))
        sy *= rng.uniform(0.5, 0.8)
        yaw = rng.uniform(0.0, math.pi)
        nodes.append(
            {
                "type": "mesh",
                "name": f"rock_{len(nodes)}",
                "geometry": f"rock{rng.randrange(ROCK_SHAPES)}",
                "translation": [x, ground(x, z) + sy * 0.2, z],
                "rotation": [0.0, math.sin(yaw / 2), 0.0, math.cos(yaw / 2)],
                "scale": [sx, sy, sz],
                "materials": ["rock"],
            }
        )
    return nodes


def mesa(seed: int) -> dict[str, Any]:
    """A flat-topped hill with a ragged rim and a talus slope, in a unit square."""
    noise = value_noise(seed)

    def height(x: float, z: float) -> float:
        a = math.atan2(z, x)
        rim = 0.62 + 0.18 * (noise(math.cos(a) * 2 + 3, math.sin(a) * 2 + 3) - 0.5)
        r = math.hypot(x, z)
        top = 1.0 - 0.06 * noise(x * 6 + 1, z * 6 + 1)
        if r <= rim:
            return top
        fall = (r - rim) / (1.0 - rim)
        cliff = max(0.0, 1.0 - fall * 3.5)
        talus = 0.45 * max(0.0, 1.0 - fall) ** 1.5
        return max(cliff * top, talus) * (0.9 + 0.2 * noise(x * 9, z * 9))

    steps = [i / 30.0 - 1.0 for i in range(61)]
    return heightfield(height, steps, steps)


def mesa_nodes(seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed + 1)
    nodes = []
    for i in range(9):
        angle = (i + rng.uniform(-0.3, 0.3)) * 2 * math.pi / 9
        dist = rng.uniform(260.0, 520.0)
        w, h = rng.uniform(80, 220), rng.uniform(18, 45)
        nodes.append(
            {
                "type": "mesh",
                "name": f"mesa_{i}",
                "geometry": f"mesa{i % 3}",
                "translation": [dist * math.cos(angle), GROUND_Y - 1.0, dist * math.sin(angle)],
                "rotation": [0.0, math.sin(angle / 2), 0.0, math.cos(angle / 2)],
                "scale": [w, h, w * rng.uniform(0.6, 1.0)],
                "materials": [{"inputs": {"base_color": MESA, "specular_roughness": 0.95}}],
            }
        )
    return nodes


def scene(
    shot: dict[str, Any],
    glb: str,
    lights: list[dict[str, Any]],
    sky_material: dict[str, Any],
    fog: bool,
    seed: int,
    resolution: tuple[int, int],
    exposure: float,
    site: Path | None = None,
) -> dict[str, Any]:
    environment = lights[0]
    if site is None:
        ground = terrain_height(seed)
        ground_mesh = terrain(seed)
        far: list[dict[str, Any]] = mesa_nodes(seed)
        plain_y = GROUND_Y - 0.02
        rover: dict[str, Any] = {}
    else:
        ground = gale_height(site, seed)
        lines = geometric(GALE_LIMIT, 0.5, 14.0, 0.06)
        ground_mesh = heightfield(ground, lines, lines, regolith_color(seed))
        far = []
        edge = [
            ground(GALE_LIMIT * math.cos(a / 8), GALE_LIMIT * math.sin(a / 8)) for a in range(50)
        ]
        plain_y = min(edge) - 0.5
        yaw = math.radians(GALE_YAW_DEG)
        rover = {"rotation": [0.0, math.sin(yaw / 2), 0.0, math.cos(yaw / 2)]}
    programs: dict[str, Any] = {
        "mars_sky": {"file": "mars_sky.slang"},
    }
    materials: dict[str, Any] = {
        "sky": sky_material,
        "regolith": {
            "inputs": {"base_color": {"attribute": "COLOR_0"}, "specular_roughness": 0.95}
        },
        "plain": {"inputs": {"base_color": REGOLITH_DARK, "specular_roughness": 0.95}},
        "rock": {"inputs": {"base_color": {"attribute": "COLOR_0"}, "specular_roughness": 0.8}},
    }
    if fog:
        environment["medium"] = "dust"
        programs["dust"] = {"file": "dust.slang"}
        haze = shot["haze"]
        materials["dust"] = {
            "program": "dust",
            "inputs": {
                "scattering": [round(c * haze, 6) for c in (0.0012, 0.0009, 0.0006)],
                "absorption": [round(c * haze, 6) for c in (0.0001, 0.0003, 0.0006)],
            },
        }
    geometry: dict[str, Any] = {
        "terrain": ground_mesh,
        "plain": {"std": "grid", "size": [4000, 4000], "segments": [1, 1]},
    }
    for i in range(ROCK_SHAPES):
        geometry[f"rock{i}"] = rock_shape(seed * 100 + i)
    if site is None:
        for i in range(3):
            geometry[f"mesa{i}"] = mesa(seed * 10 + i)

    return {
        "version": 2,
        "render": {
            "resolution": list(resolution),
            "background": "environment",
            "display": {"program": "std/agx", "inputs": {"exposure": exposure}},
        },
        "programs": programs,
        "materials": materials,
        "geometry": geometry,
        "nodes": [
            {
                "type": "camera",
                "name": "camera",
                "translation": shot["camera"],
                "target": shot["target"],
                "material": {"program": "std/camera", "inputs": {"lens": shot["lens_mm"]}},
            },
            *lights,
            {"type": "asset", "name": "rover", "file": glb, **rover},
            {
                "type": "mesh",
                "name": "terrain",
                "geometry": "terrain",
                "materials": ["regolith"],
            },
            {
                "type": "mesh",
                "name": "plain",
                "geometry": "plain",
                "translation": [0.0, plain_y, 0.0],
                "materials": ["plain"],
            },
            *rock_nodes(seed, ground, shot["camera"]),
            *far,
        ],
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--glb", type=Path, default=Path("unreal/Saved/RoverModel/rover_preview.glb")
    )
    parser.add_argument("--out", type=Path, default=Path("unreal/Saved/RoverConcept"))
    parser.add_argument("--vork", default=shutil.which("vork") or "vork")
    parser.add_argument("--no-fog", action="store_true", help="omit the dust haze (faster renders)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--resolution", type=int, nargs=2, default=(1600, 900))
    parser.add_argument(
        "--exposure", type=float, default=0.0, help="AgX exposure, in stops, added to each shot's"
    )
    parser.add_argument("--only", choices=sorted(SHOTS | GALE_SHOTS), help="write one shot only")
    parser.add_argument(
        "--site",
        type=Path,
        help="a heightfield .r16 from scripts/terrain/hirise_site.py, with its .json beside it;"
        " writes the Gale shots instead",
    )
    args = parser.parse_args(argv)
    if not args.glb.is_file():
        print(f"Missing {args.glb}; run scripts/blender/build_rover.py first.", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    glb = os.path.relpath(args.glb.resolve(), args.out.resolve())
    (args.out / "mars_sky.slang").write_text(SKY_PROGRAM, encoding="utf-8")
    if not args.no_fog:
        (args.out / "dust.slang").write_text(DUST_PROGRAM, encoding="utf-8")
    for name, shot in (GALE_SHOTS if args.site else SHOTS).items():
        if args.only and name != args.only:
            continue
        lights, sky_material = sky(args.vork, shot)
        data = scene(
            shot,
            glb,
            lights,
            sky_material,
            not args.no_fog,
            args.seed,
            args.resolution,
            shot["exposure"] + args.exposure,
            args.site,
        )
        path = args.out / f"{name}.json"
        path.write_text(json.dumps(data) + "\n", encoding="utf-8")
        print(f"{path}: {shot['about']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
