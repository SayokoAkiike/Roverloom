"""Write vork scenes that show Roverloom's V2 rover model in a Mars-inspired setting.

These are concept renders for the README and promotion. They are **not game screenshots**:
nothing here runs the simulator, the Unreal client, or any physics. Every image made from them
must be labeled "Concept render (vork), not a game screenshot".

The rover comes from scripts/blender/build_rover.py (rover_preview.glb). The ground, rocks,
mesas, sky, and dust haze are generated here from vork's own shapes and programs, with a fixed
seed, and use no third-party assets. Colors and haze are mars_inspired choices by eye, not
measurements.

Requires vork (https://github.com/voyager-so/vork), 0.5.1 or a compatible version, which is used
to expand its physical sky. vork is under its own preview license and is not part of Roverloom.

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
from pathlib import Path
from typing import Any

GROUND_Y = -0.70  # the glb's origin is the rover body's center, 0.70 m above flat ground
REGOLITH = [0.46, 0.21, 0.10]  # V1b's regolith color, linear
BASALT = [0.13, 0.09, 0.07]  # V1b's rock color, linear
MESA = [0.30, 0.15, 0.08]
SUN_COLOR = [1.0, 0.93, 0.82]  # set by eye; vork's sky computes an Earth-like sun color

# The dust haze: an exponential-height medium in the form vork admits for world fog.
DUST_PROGRAM = """// Mars-inspired dust haze for Roverloom concept renders, chosen by eye.
import vork;
struct Inputs {
    float3 absorption = float3(0.0002, 0.0006, 0.0012);
    float3 scattering = float3(0.0030, 0.0024, 0.0018);
    float base_height = -0.7;
    float falloff = 0.002;
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
SHOTS: dict[str, dict[str, Any]] = {
    "hero": {
        "about": "Low front three-quarter, late afternoon, sun behind the camera's left",
        "camera": [5.2, 0.35, 4.6],
        "target": [0.0, 0.05, 0.0],
        "lens_mm": 35,
        "sun_elevation_deg": 22,
        "sun_rotation_deg": 125,
    },
    "side": {
        "about": "Side view at mast height, midday",
        "camera": [0.4, 0.6, 8.5],
        "target": [0.0, 0.2, 0.0],
        "lens_mm": 40,
        "sun_elevation_deg": 55,
        "sun_rotation_deg": 150,
    },
    "sunset": {
        "about": "Low chase toward a sun 4 degrees above the horizon, rover nearly in silhouette",
        "camera": [-7.0, 0.1, 3.2],
        "target": [0.0, 0.4, 0.0],
        "lens_mm": 32,
        "sun_elevation_deg": 4,
        "sun_rotation_deg": 80,
    },
}


def vork_sky(vork: str, elevation: float, rotation: float) -> dict[str, Any]:
    """vork's own sky fragment: an environment light with std/sky, and a matching sun."""
    options = {
        "sun_elevation": elevation,
        "sun_rotation": rotation,
        "air_density": 0.2,  # thin air: less blue Rayleigh scattering
        "aerosol_density": 6.0,  # dusty
        "ozone_density": 0.0,
    }
    result = subprocess.run(
        [vork, "std", "sky", json.dumps(options)], check=True, capture_output=True, text=True
    )
    fragment: dict[str, Any] = json.loads(result.stdout)
    for node in fragment["nodes"]:
        if node.get("shape") == "sun":
            node["color"] = SUN_COLOR
            node["angle"] = 0.006  # Mars's sun is smaller than Earth's
    return fragment


def rock_nodes(seed: int) -> list[dict[str, Any]]:
    """Partly buried, squashed spheres; few large and many small, kept off the rover's spot."""
    rng = random.Random(seed)
    nodes = []
    while len(nodes) < 140:
        x, z = rng.uniform(-60.0, 60.0), rng.uniform(-60.0, 60.0)
        if math.hypot(x, z) < 3.5:
            continue
        size = min(0.08 * (1.0 - rng.random()) ** -0.9, 1.6)  # power-law sizes, 8 cm and up
        sx, sy, sz = (size * rng.uniform(0.7, 1.3) for _ in range(3))
        sy *= 0.6
        yaw = rng.uniform(0.0, math.pi)
        shade = rng.uniform(0.8, 1.25)
        nodes.append(
            {
                "type": "mesh",
                "name": f"rock_{len(nodes)}",
                "geometry": "rock",
                "translation": [x, GROUND_Y + sy * 0.35, z],
                "rotation": [0.0, math.sin(yaw / 2), 0.0, math.cos(yaw / 2)],
                "scale": [sx, sy, sz],
                "materials": [
                    {
                        "inputs": {
                            "base_color": [round(c * shade, 4) for c in BASALT],
                            "specular_roughness": 0.85,
                        }
                    }
                ],
            }
        )
    return nodes


def mesa_nodes(seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed + 1)
    nodes = []
    for i in range(7):
        angle = rng.uniform(-1.2, 1.2) + (math.pi if i % 3 == 2 else 0.0)
        dist = rng.uniform(220.0, 420.0)
        w, h, d = rng.uniform(60, 160), rng.uniform(12, 35), rng.uniform(60, 140)
        nodes.append(
            {
                "type": "mesh",
                "name": f"mesa_{i}",
                "geometry": "mesa",
                "translation": [
                    dist * math.cos(angle),
                    GROUND_Y + h / 2 - 2.0,
                    dist * math.sin(angle),
                ],
                "scale": [w, h, d],
                "materials": [{"inputs": {"base_color": MESA, "specular_roughness": 0.95}}],
            }
        )
    return nodes


def scene(
    shot: dict[str, Any],
    glb: str,
    fragment: dict[str, Any],
    fog: bool,
    seed: int,
    resolution: tuple[int, int],
    exposure: float,
) -> dict[str, Any]:
    environment = next(n for n in fragment["nodes"] if n.get("shape") == "environment")
    if fog:
        environment["medium"] = "dust"
    materials = dict(fragment["materials"])
    programs = {}
    if fog:
        programs["dust"] = {"file": "dust.slang"}
        materials["dust"] = {"program": "dust"}
    materials["regolith"] = {"inputs": {"base_color": REGOLITH, "specular_roughness": 0.95}}
    return {
        "version": 2,
        "render": {
            "resolution": list(resolution),
            "background": "environment",
            "display": {"program": "std/agx", "inputs": {"exposure": exposure}},
        },
        "programs": programs,
        "materials": materials,
        "geometry": {
            "rock": {"std": "sphere", "radius": 1.0, "segments": 14, "rings": 8},
            "mesa": {"std": "rounded_box", "size": [1, 1, 1], "radius": 0.15, "segments": 4},
            "ground": {"std": "grid", "size": [3000, 3000], "segments": [1, 1]},
        },
        "nodes": [
            {
                "type": "camera",
                "name": "camera",
                "translation": shot["camera"],
                "target": shot["target"],
                "material": {"program": "std/camera", "inputs": {"lens": shot["lens_mm"]}},
            },
            *fragment["nodes"],
            {"type": "asset", "name": "rover", "file": glb},
            {
                "type": "mesh",
                "name": "ground",
                "geometry": "ground",
                "translation": [0.0, GROUND_Y, 0.0],
                "materials": ["regolith"],
            },
            *rock_nodes(seed),
            *mesa_nodes(seed),
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
    parser.add_argument("--exposure", type=float, default=0.0, help="AgX exposure, in stops")
    args = parser.parse_args(argv)
    if not args.glb.is_file():
        print(f"Missing {args.glb}; run scripts/blender/build_rover.py first.", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    glb = os.path.relpath(args.glb.resolve(), args.out.resolve())
    if not args.no_fog:
        (args.out / "dust.slang").write_text(DUST_PROGRAM, encoding="utf-8")
    for name, shot in SHOTS.items():
        fragment = vork_sky(
            args.vork,
            math.radians(shot["sun_elevation_deg"]),
            math.radians(shot["sun_rotation_deg"]),
        )
        data = scene(
            shot, glb, fragment, not args.no_fog, args.seed, args.resolution, args.exposure
        )
        path = args.out / f"{name}.json"
        path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
        print(f"{path}: {shot['about']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
