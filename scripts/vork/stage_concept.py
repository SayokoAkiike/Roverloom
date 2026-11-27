"""Write vork scenes of the race stages on real HiRISE terrain: Noctis Labyrinthus and Amazonis Planitia.

Concept renders for the stage select and promotion. They are **not game screenshots**: nothing here runs the
simulator or Unreal. Every image made from them must be labeled "Concept render (vork), not a game screenshot"
(ADR 0015).

What is measured and what is not:
  * the ground's shape is the HiRISE DTM: the 1 km site at 1 m posts near the rover, and the horizon square
    (about 5 km) around it, from scripts/terrain/hirise_site.py and hirise_horizon.py;
  * the ground's light and dark pattern is the HiRISE orthoimage with its shading divided out
    (scripts/terrain/hirise_albedo.py), a relative brightness from one greyscale photo;
  * the colours, the sky, the dust haze and the rocks are chosen by eye (mars_inspired), as in rover_concept.py.

    python3 scripts/vork/stage_concept.py --out unreal/Saved/StageConcept
    vork check unreal/Saved/StageConcept/noctis_spur.json
    vork render unreal/Saved/StageConcept/noctis_spur.json --profile std/final --out noctis_spur.png

Needs the rover glTF (scripts/blender/build_rover.py), the terrain files above, and vork. Standard library only.
"""

# ruff: noqa: E501  (long prose lines in the docstring; wrapping them would not help the reader)

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import struct
import sys
import zlib
from array import array
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rover_concept as rc  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SAMPLES = 1009

# Each shot puts the rover on a race course (python/src/roverloom/race.py), in the site frame: metres east and
# north of the site Landscape's center. yaw_deg is the rover's heading, counter-clockwise from east.
STAGES: dict[str, dict[str, Any]] = {
    "noctis": {
        # Floor of a trough: dark sand, light-toned layered rock, a trough wall a few hundred metres east.
        "palette": {
            "dark": [0.13, 0.085, 0.06],
            "mid": [0.33, 0.20, 0.12],
            "light": [0.62, 0.50, 0.34],
        },
        "rocks": 420,
        "shots": {
            "noctis_spur": {
                "about": "Noctis Spur, flag 3, looking east across the layered spur toward the trough wall",
                "spot": [-115.0, 60.0],
                "yaw_deg": 5.0,
                "camera": [-9.0, 2.6, 3.5],
                "target": [30.0, 6.0, -4.0],
                "lens_mm": 28,
                "sun_elevation_deg": 22,
                "sun_rotation_deg": 140,
                "tau": 0.5,
                "haze": 0.6,
                "exposure": -3.2,
            },
            "noctis_start": {
                "about": "Noctis Spur start, the rover facing flag 1, the spur's hook behind",
                "spot": [-190.0, -90.0],
                "yaw_deg": 124.0,
                "camera": [5.5, 1.4, -6.0],
                "target": [-6.0, 1.0, 4.0],
                "lens_mm": 32,
                "sun_elevation_deg": 30,
                "sun_rotation_deg": 230,
                "tau": 0.5,
                "haze": 0.6,
                "exposure": -3.4,
            },
        },
    },
    "amazonis": {
        # Smooth dust-mantled plains; a pit chain. Few rocks, a thicker haze.
        "palette": {
            "dark": [0.20, 0.11, 0.055],
            "mid": [0.44, 0.26, 0.13],
            "light": [0.56, 0.36, 0.19],
        },
        "rocks": 90,
        "shots": {
            "amazonis_rim": {
                "about": "Amazonis Rim finish, the rover at the pit's edge, looking south into the pit",
                "spot": [175.0, -405.0],
                "yaw_deg": -92.0,
                "camera": [-3.5, 3.2, -9.0],
                "target": [2.0, -10.0, 60.0],
                "lens_mm": 24,
                "sun_elevation_deg": 26,
                "sun_rotation_deg": 300,
                "tau": 0.8,
                "haze": 1.0,
                "exposure": -3.0,
            },
            "amazonis_plain": {
                "about": "Amazonis Rim start, the open plain toward the channel",
                "spot": [60.0, -130.0],
                "yaw_deg": -23.0,
                "camera": [-8.0, 1.8, -3.0],
                "target": [20.0, 0.6, 8.0],
                "lens_mm": 30,
                "sun_elevation_deg": 18,
                "sun_rotation_deg": 60,
                "tau": 0.8,
                "haze": 1.0,
                "exposure": -3.0,
            },
        },
    },
}
# The two winter and spring stages take their frost and streak rules from the Unreal material's LOOKS
# (scripts/unreal/build_gale_material.py), so that the concept renders and the game follow the same rules.
STAGES["lyot"] = {
    # Lyot Crater in northern winter: dark barchans on a bright crater floor; frost on the north-facing halves.
    "palette": {
        "dark": [0.18, 0.12, 0.10],
        "mid": [0.42, 0.25, 0.19],
        "light": [0.62, 0.40, 0.32],
    },
    "rocks": 160,
    "frost": {
        "facing_from": 0.05,
        "facing_gain": 5.0,
        "slope_cover": 0.0,
        "flat_cover": 0.0,
        "dune_frost": 0.72,
        "color": [0.78, 0.78, 0.80],
        "strength": 0.92,
    },
    "streaks": {
        "surface": "flat",
        "downslope_deg": 80.0,
        "spacing_m": 3.0,
        "thin": 0.75,
        "color": [0.78, 0.78, 0.80],
        "strength": 0.3,
    },
    "shots": {
        "lyot_slalom": {
            "about": "Lyot Frost Slalom start, the rover facing flag 1 between frosted barchans",
            "spot": [-180.0, 20.0],
            "yaw_deg": 40.0,
            "camera": [-7.0, 1.7, 5.0],
            "target": [20.0, 0.8, -16.0],
            "lens_mm": 30,
            "sun_elevation_deg": 7,
            "sun_rotation_deg": 220,
            "tau": 0.6,
            "haze": 0.9,
            "exposure": -2.4,
        },
        "lyot_frost": {
            "about": "Lyot Frost Slalom flag 1, looking south at the frosted north faces of the dunes",
            "spot": [-60.0, 120.0],
            "yaw_deg": -90.0,
            "camera": [-3.0, 2.4, -9.0],
            "target": [6.0, 0.0, 40.0],
            "lens_mm": 28,
            "sun_elevation_deg": 7,
            "sun_rotation_deg": 220,
            "tau": 0.6,
            "haze": 0.9,
            "exposure": -2.4,
        },
    },
}
STAGES["olympia"] = {
    # North polar dunes in spring: frost over the ground, dark dune sand clearing, dark streaks down the slip faces.
    "palette": {
        "dark": [0.07, 0.06, 0.06],
        "mid": [0.24, 0.21, 0.20],
        "light": [0.50, 0.46, 0.44],
    },
    "rocks": 40,
    "frost": {
        "facing_from": 0.0,
        "facing_gain": 0.0,
        "slope_cover": 0.0,
        "flat_cover": 0.9,
        "dark_clears": 0.9,
        "color": [0.74, 0.71, 0.71],
        "strength": 0.78,
    },
    "streaks": {
        "downslope_deg": 135.0,
        "spacing_m": 4.0,
        "thin": 0.5,
        "color": [0.05, 0.045, 0.04],
        "strength": 1.0,
    },
    "shots": {
        "ghost_forest": {
            "about": "Ghost Forest flag 1, looking south-east at dark streaks on the frosted dunes",
            "spot": [-148.0, -164.0],
            "yaw_deg": -45.0,
            "camera": [-6.0, 2.2, -6.0],
            "target": [30.0, -1.5, 30.0],
            "lens_mm": 28,
            "sun_elevation_deg": 13,
            "sun_rotation_deg": 45,
            "tau": 0.3,
            "haze": 0.5,
            "exposure": -2.8,
        },
        "ghost_start": {
            "about": "Ghost Forest start, on the tail of a linear dune, looking along the course",
            "spot": [-250.0, -250.0],
            "yaw_deg": 40.0,
            "camera": [-6.5, 1.8, 5.5],
            "target": [22.0, 0.5, -18.0],
            "lens_mm": 30,
            "sun_elevation_deg": 13,
            "sun_rotation_deg": 45,
            "tau": 0.3,
            "haze": 0.5,
            "exposure": -2.8,
        },
    },
}
NEAR_LIMIT = (
    480.0  # The 1 m site mesh reaches this far from the rover, then the horizon mesh takes over
)
FAR_STRIDE = 3  # Horizon posts used, every third (about 15 m)


def read_png_grey(path: Path) -> tuple[int, int, list[int]]:
    """A minimal decoder for the 8-bit greyscale, non-interlaced PNGs that hirise_albedo.py writes."""
    data = path.read_bytes()
    pos, width, height, chunks = 8, 0, 0, b""
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos : pos + 8])
        body = data[pos + 8 : pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, colour, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or colour != 0 or interlace:
                raise SystemExit(f"{path}: expected an 8-bit greyscale, non-interlaced PNG")
        elif kind == b"IDAT":
            chunks += body
        pos += 12 + length
    raw = zlib.decompress(chunks)
    out: list[int] = []
    prior = [0] * width
    for row in range(height):
        start = row * (width + 1)
        kind, line = raw[start], list(raw[start + 1 : start + 1 + width])
        for i in range(width):
            left = line[i - 1] if i else 0
            up, corner = prior[i], prior[i - 1] if i else 0
            if kind == 1:
                line[i] = (line[i] + left) & 255
            elif kind == 2:
                line[i] = (line[i] + up) & 255
            elif kind == 3:
                line[i] = (line[i] + (left + up) // 2) & 255
            elif kind == 4:
                p = left + up - corner
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - corner)
                line[i] = (
                    line[i] + (left if pa <= pb and pa <= pc else up if pb <= pc else corner)
                ) & 255
        out += line
        prior = line
    return width, height, out


class Grid:
    """A square heightfield or brightness map around the site's center, sampled bilinearly in the site frame."""

    def __init__(self, values: list[float], n: int, spacing: float):
        self.values, self.n, self.spacing = values, n, spacing
        self.half = (n - 1) * spacing / 2

    def inside(self, east: float, north: float) -> bool:
        return abs(east) < self.half - self.spacing and abs(north) < self.half - self.spacing

    def at(self, east: float, north: float) -> float:
        col = min(max((east + self.half) / self.spacing, 0.0), self.n - 1.001)
        row = min(max((self.half - north) / self.spacing, 0.0), self.n - 1.001)
        c, r = int(col), int(row)
        fc, fr = col - c, row - r
        k = r * self.n + c
        v = self.values
        return (v[k] * (1 - fc) + v[k + 1] * fc) * (1 - fr) + (
            v[k + self.n] * (1 - fc) + v[k + self.n + 1] * fc
        ) * fr


def heights(r16: Path, meta: dict[str, Any]) -> Grid:
    raw = array("H")
    raw.frombytes(r16.read_bytes())
    if sys.byteorder == "big":
        raw.byteswap()
    low, span = meta["height_min_m"], meta["height_max_m"] - meta["height_min_m"]
    return Grid([low + v / 65535.0 * span for v in raw], meta["samples"], meta["spacing_m"])


def brightness(png: Path, extent_m: float) -> Grid:
    width, _, grey = read_png_grey(png)
    return Grid([g / 128.0 for g in grey], width, extent_m / (width - 1))


def load(site: str) -> dict[str, Any]:
    data = REPO / "unreal/Saved/Terrain" / site
    info = json.loads((REPO / "scripts/terrain/sites.json").read_text())[site]
    horizon_meta = json.loads((REPO / info["report"] / "horizon.json").read_text())
    if tuple(info["origin_m"]) != (0.0, 0.0):
        raise SystemExit(f"{site}: stage shots assume the site frame is the Landscape's center")
    return {
        "site": heights(
            data / f"{site}_site.r16", json.loads((data / f"{site}_site.json").read_text())
        ),
        "horizon": heights(data / f"{site}_horizon.r16", horizon_meta),
        "site_albedo": brightness(data / f"{site}_albedo.png", (SAMPLES - 1) * 1.0),
        "horizon_albedo": brightness(data / f"{site}_horizon_albedo.png", horizon_meta["extent_m"]),
    }


def ground_functions(
    terrain: dict[str, Any], stage: dict[str, Any], shot: dict[str, Any], seed: int
):
    """Height and colour in the scene frame: x east and z south of the rover, y up, the rover's spot at y = GROUND_Y."""
    e0, n0 = shot["spot"]
    base = terrain["site"].at(e0, n0)
    noise = rc.value_noise(seed)
    palette = stage["palette"]

    def absolute(east: float, north: float) -> float:
        site = terrain["site"]
        return (
            site.at(east, north) if site.inside(east, north) else terrain["horizon"].at(east, north)
        )

    def height(x: float, z: float) -> float:
        r = math.hypot(x, z)
        near = min(1.0, max(0.0, (r - 3.0) / 6.0))  # level under the wheels, as rover_concept.py
        bumps = 0.10 * (noise(x / 3.1, z / 3.1) - 0.5) + 0.04 * (noise(x / 1.1, z / 1.1) - 0.5)
        return rc.GROUND_Y + near * (absolute(e0 + x, n0 - z) - base + bumps)

    def far_height(x: float, z: float) -> float:
        east, north = e0 + x, n0 - z
        sink = (
            4.0 if terrain["site"].inside(east, north) else 0.0
        )  # under the near mesh where both exist, even where the ground under the rover is levelled below a dune
        return rc.GROUND_Y + terrain["horizon"].at(east, north) - base - sink

    def colour(x: float, z: float) -> list[float]:
        east, north = e0 + x, n0 - z
        site = terrain["site_albedo"]
        a = (
            site.at(east, north)
            if site.inside(east, north)
            else terrain["horizon_albedo"].at(east, north)
        )
        t = min(1.0, max(0.0, (a - 0.6) / 0.9))  # dark sand to light-toned ground
        fine = 0.9 + 0.2 * noise(x * 0.7, z * 0.7)
        lo, hi = (
            (palette["dark"], palette["mid"]) if t < 0.45 else (palette["mid"], palette["light"])
        )
        u = t / 0.45 if t < 0.45 else (t - 0.45) / 0.55
        rgb = [min(1.0, (lo[k] + (hi[k] - lo[k]) * u) * fine) for k in range(3)]
        if "frost" not in stage and "streaks" not in stage:
            return rgb
        # The ground's slope at this point, from the heights, in the site frame (east, north, up)
        dzde = (absolute(east + 1.0, north) - absolute(east - 1.0, north)) / 2.0
        dzdn = (absolute(east, north + 1.0) - absolute(east, north - 1.0)) / 2.0
        norm = math.sqrt(dzde * dzde + dzdn * dzdn + 1.0)
        n_east, n_north, n_up = -dzde / norm, -dzdn / norm, 1.0 / norm
        steep = 1.0 - n_up
        if "frost" in stage:
            f = stage["frost"]
            pole = min(1.0, max(0.0, (n_north - f["facing_from"]) * f["facing_gain"]))
            patches = min(
                1.0, max(0.0, (noise(x / 25.0 + 41.0, z / 25.0) - (1.0 - f["flat_cover"])) * 4.0)
            )
            cover = min(1.0, pole * f["slope_cover"] + patches)
            if "dune_frost" in f:
                dune = min(1.0, max(0.0, (f["dune_frost"] - a) * 2.0))
                not_slip = 1.0 - min(1.0, max(0.0, (steep - 0.10) * 20.0))
                cover = min(1.0, cover + dune * not_slip * (0.6 + 0.4 * pole))
            if "dark_clears" in f:
                cleared = min(1.0, max(0.0, (f["dark_clears"] - a) * 2.5))
                slip_face = min(1.0, max(0.0, (steep - 0.03) * 15.0))
                spots = min(1.0, max(0.0, (noise(x / 3.3 + 29.0, z / 3.3) - 0.4) * 3.0))
                cover *= 1.0 - cleared * (1.0 - slip_face) * spots
            amount = cover * f["strength"]
            rgb = [rgb[k] * (1.0 - amount) + f["color"][k] * fine * amount for k in range(3)]
        if "streaks" in stage:
            k_ = stage["streaks"]
            theta = math.radians(k_["downslope_deg"])
            de, dn = math.cos(theta), math.sin(theta)
            toward = n_east * de + n_north * dn
            if k_.get("surface") == "flat":
                on_face = min(1.0, max(0.0, 1.0 - steep * 30.0))
            else:
                on_face = min(1.0, max(0.0, (toward - 0.08) * 6.0))
            across = east * (-dn) + north * de
            along = east * de + north * dn
            n = noise(across / k_["spacing_m"] + 7.0, along / (k_["spacing_m"] * 6.0))
            stripe = min(1.0, max(0.0, (n - k_["thin"]) / (1.0 - k_["thin"])))
            broken = min(1.0, max(0.0, (noise(x / 66.0 + 13.0, z / 66.0) - 0.3) * 3.0))
            amount = stripe * on_face * broken * k_["strength"]
            rgb = [rgb[k] * (1.0 - amount) + k_["color"][k] * amount for k in range(3)]
        return rgb

    return height, far_height, colour


def vork_version(vork: str) -> tuple[int, int]:
    """(major, minor) of the installed vork; scenes for 0.5.1 and 0.6 differ in one field."""
    import re
    import subprocess

    out = subprocess.run([vork, "--version"], capture_output=True, text=True).stdout
    match = re.search(r"vork (\d+)\.(\d+)", out)
    return (int(match.group(1)), int(match.group(2))) if match else (0, 6)


def far_lines(half: float, step: float, x0: float) -> list[float]:
    out, v = [], -half - x0
    while v <= half - x0:
        out.append(v)
        v += step
    return out


def scene(
    stage: dict[str, Any],
    shot: dict[str, Any],
    terrain: dict[str, Any],
    glb: str,
    vork: str,
    fog: bool,
    seed: int,
    resolution: tuple[int, int],
    exposure: float,
) -> dict[str, Any]:
    lights, sky_material = rc.sky(vork, shot)
    height, far_height, colour = ground_functions(terrain, stage, shot, seed)
    lines = rc.geometric(NEAR_LIMIT, 0.5, 14.0, 0.06)
    near_mesh = rc.heightfield(height, lines, lines, colour)
    horizon = terrain["horizon"]
    e0, n0 = shot["spot"]
    step = horizon.spacing * FAR_STRIDE
    far_mesh = rc.heightfield(
        far_height, far_lines(horizon.half, step, e0), far_lines(horizon.half, step, -n0), colour
    )
    yaw = math.radians(shot["yaw_deg"])
    materials: dict[str, Any] = {
        "sky": sky_material,
        "ground": {"inputs": {"base_color": {"attribute": "COLOR_0"}, "specular_roughness": 0.95}},
        "rock": {"inputs": {"base_color": {"attribute": "COLOR_0"}, "specular_roughness": 0.8}},
    }
    programs: dict[str, Any] = {"mars_sky": {"file": "mars_sky.slang"}}
    if fog:
        lights[0]["medium"] = "dust"
        programs["dust"] = {"file": "dust.slang"}
        materials["dust"] = {
            "program": "dust",
            "inputs": {
                "scattering": [round(c * shot["haze"], 6) for c in (0.0012, 0.0009, 0.0006)],
                "absorption": [round(c * shot["haze"], 6) for c in (0.0001, 0.0003, 0.0006)],
            },
        }
    geometry: dict[str, Any] = {"near": near_mesh, "far": far_mesh}
    for i in range(rc.ROCK_SHAPES):
        geometry[f"rock{i}"] = rc.rock_shape(seed * 100 + i)
    view = {"program": "std/agx", "inputs": {"exposure": exposure}}
    render: dict[str, Any] = {"resolution": list(resolution), "background": "environment"}
    layout: dict[str, Any] = {"render": render}
    if vork_version(vork) >= (0, 6):
        layout["composition"] = {"space": "3d", "view": view}  # vork 0.6: render.display moved here
    else:
        render["display"] = view
    return {
        "version": 2,
        **layout,
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
            # The glb's +X is the rover's front; vork's y is up, so a heading counter-clockwise from east is a
            # rotation about +y by the same angle (z points south)
            {
                "type": "asset",
                "name": "rover",
                "file": glb,
                "rotation": [0.0, math.sin(yaw / 2), 0.0, math.cos(yaw / 2)],
            },
            {"type": "mesh", "name": "near", "geometry": "near", "materials": ["ground"]},
            {"type": "mesh", "name": "far", "geometry": "far", "materials": ["ground"]},
            *rc.rock_nodes(seed, height, shot["camera"])[: stage["rocks"]],
        ],
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--glb", type=Path, default=Path("unreal/Saved/RoverModel/rover_preview.glb")
    )
    parser.add_argument("--out", type=Path, default=Path("unreal/Saved/StageConcept"))
    parser.add_argument("--vork", default=shutil.which("vork") or "vork")
    parser.add_argument("--stage", choices=sorted(STAGES), action="append", help="default: all")
    parser.add_argument("--only", help="write one shot only")
    parser.add_argument("--no-fog", action="store_true", help="omit the dust haze (faster renders)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--resolution", type=int, nargs=2, default=(1600, 900))
    parser.add_argument(
        "--exposure", type=float, default=0.0, help="AgX stops added to each shot's"
    )
    args = parser.parse_args(argv)
    if not args.glb.is_file():
        print(f"Missing {args.glb}; run scripts/blender/build_rover.py first.", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    glb = os.path.relpath(args.glb.resolve(), args.out.resolve())
    (args.out / "mars_sky.slang").write_text(rc.SKY_PROGRAM, encoding="utf-8")
    if not args.no_fog:
        (args.out / "dust.slang").write_text(rc.DUST_PROGRAM, encoding="utf-8")
    for name in args.stage or sorted(STAGES):
        stage = STAGES[name]
        terrain = load(name)
        for shot_name, shot in stage["shots"].items():
            if args.only and shot_name != args.only:
                continue
            data = scene(
                stage,
                shot,
                terrain,
                glb,
                args.vork,
                not args.no_fog,
                args.seed,
                tuple(args.resolution),
                shot["exposure"] + args.exposure,
            )
            path = args.out / f"{shot_name}.json"
            path.write_text(json.dumps(data) + "\n", encoding="utf-8")
            print(f"{path}: {shot['about']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
