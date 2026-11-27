"""Build a site level, by default /Game/Licensed/Gale/Gale: the 1 km site Landscape and a horizon Landscape around it. Unreal Editor Python.

    UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script="scripts/unreal/build_gale_level.py" -unattended -nullrhi
    UnrealEditor unreal/Roverloom.uproject -run=pythonscript -script="scripts/unreal/build_gale_level.py noctis" -unattended -nullrhi

Other sites come from scripts/terrain/sites.json (level, material, origin). The text below describes Gale.

Needs scripts/terrain/hirise_site.py and hirise_horizon.py (the .r16 files and their json), then build_gale_material.py.

The site-frame origin, where the rover starts, is not the Landscape's center. It is the calmest patch near the center:
2 m west and 38 m south of it, where the largest slope over a 20 m window is 4.8 degrees at a 4 m baseline (the center's own
window reaches 11.4). That patch is put at the world origin, on the ground at z = 0. The horizon Landscape is moved the same
way, and shares the site's vertical datum: both were cut from one DTM, so it is placed by the difference of the two heights
at the origin, minus a small sink so that the sharper site surface lies on top inside its own square. The horizon has no
collision: the rover never reaches it. Rocks, lights, and effects are added by other scripts. Visual only: no physics value
is set here.
"""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

import array
import json
import os
import sys
from pathlib import Path

import unreal  # type: ignore[import-not-found]

SITE = next((a for a in sys.argv[1:] if not a.startswith("-")), "gale")
_SITES = json.loads(
    (Path(unreal.Paths.project_dir()).parent / "scripts/terrain/sites.json").read_text()
)
LEVEL = _SITES[SITE]["level"]
MATERIAL = _SITES[SITE]["material"]
SAMPLES = 1009
# Relative to the Landscape center, contract frame (east, north). Gale: -2.0, -38.0
ORIGIN_EAST_M, ORIGIN_NORTH_M = (float(v) for v in _SITES[SITE]["origin_m"])
LABEL = SITE.capitalize()
HORIZON_SINK_CM = 60.0


def read_r16(path: str) -> "array.array":
    data = array.array("H")
    with open(path, "rb") as stream:
        data.frombytes(stream.read())
    if sys.byteorder == "big":
        data.byteswap()
    return data


def height_at_origin_m(path: str, info: dict, spacing_m: float) -> float:
    """Bilinear height, in meters on the DTM's own datum, at the origin point."""
    heights = read_r16(path)
    quads = SAMPLES - 1
    col = 0.5 * quads + ORIGIN_EAST_M / spacing_m
    row = 0.5 * quads - ORIGIN_NORTH_M / spacing_m
    c0, r0 = int(col), int(row)
    fc, fr = col - c0, row - r0

    def at(r: int, c: int) -> float:
        return heights[r * SAMPLES + c]

    value = (at(r0, c0) * (1 - fc) + at(r0, c0 + 1) * fc) * (1 - fr) + (
        at(r0 + 1, c0) * (1 - fc) + at(r0 + 1, c0 + 1) * fc
    ) * fr
    return info["height_min_m"] + value / 65535.0 * (info["height_max_m"] - info["height_min_m"])


def main() -> int:
    terrain = os.path.join(unreal.Paths.project_dir(), "Saved/Terrain", SITE)
    site = json.loads(Path(terrain, f"{SITE}_site.json").read_text())
    repo = Path(unreal.Paths.project_dir().rstrip("/")).parent
    report = repo / _SITES[SITE]["report"]
    horizon = json.loads((report / "horizon.json").read_text())
    material = unreal.EditorAssetLibrary.load_asset(MATERIAL)
    if material is None:
        unreal.log_error(f"{MATERIAL} is missing: run build_gale_material.py {SITE}")
        return 1

    # A blank map saved over the same path replaces the level without deleting anything
    world = unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
    if world is None:
        unreal.log_error("Could not create a blank map")
        return 1

    site_landscape = unreal.RoverloomLandscapeLibrary.import_r16_landscape(
        world,
        os.path.join(terrain, f"{SITE}_site.r16"),
        SAMPLES,
        site["unreal_xy_scale_percent"],
        site["unreal_z_scale_percent"],
        ORIGIN_EAST_M,
        ORIGIN_NORTH_M,
        0.0,
        material,
    )
    if site_landscape is None:
        unreal.log_error("Site Landscape import failed")
        return 1

    site_origin = height_at_origin_m(
        os.path.join(terrain, f"{SITE}_site.r16"), site, site["spacing_m"]
    )
    horizon_origin = height_at_origin_m(
        os.path.join(terrain, f"{SITE}_horizon.r16"), horizon, horizon["spacing_m"]
    )
    offset_cm = (horizon_origin - site_origin) * 100.0 - HORIZON_SINK_CM
    horizon_landscape = unreal.RoverloomLandscapeLibrary.import_r16_landscape(
        world,
        os.path.join(terrain, f"{SITE}_horizon.r16"),
        SAMPLES,
        horizon["unreal_xy_scale_percent"],
        horizon["unreal_z_scale_percent"],
        ORIGIN_EAST_M,
        ORIGIN_NORTH_M,
        offset_cm,
        material,
    )
    if horizon_landscape is not None:
        horizon_landscape.set_actor_label(f"{LABEL}Horizon")
        horizon_landscape.set_actor_enable_collision(False)
    # The far field: 200 km square at about 198 m a sample, from the public MOLA DEM (scripts/terrain/mola_far.py), with Aeolis Mons
    # (Mount Sharp) 33 km away. It follows the horizon field 12 m beneath it inside it, so the two never share a surface. No collision.
    far_path = os.path.join(terrain, f"{SITE}_far.r16")
    far_report = Path(terrain, f"{SITE}_far.json")
    if not far_report.exists():
        far_report = report / "far.json"
    if os.path.exists(far_path) and far_report.exists():
        far = json.loads(far_report.read_text())
        far_origin = height_at_origin_m(far_path, far, far["spacing_m"])
        far_landscape = unreal.RoverloomLandscapeLibrary.import_r16_landscape(
            world,
            far_path,
            SAMPLES,
            far["unreal_xy_scale_percent"],
            far["unreal_z_scale_percent"],
            ORIGIN_EAST_M,
            ORIGIN_NORTH_M,
            (far_origin - site_origin) * 100.0,
            material,
        )
        if far_landscape is not None:
            far_landscape.set_actor_label(f"{LABEL}Far")
            far_landscape.set_actor_enable_collision(False)
        unreal.log(
            f"LEVEL_FAR far_origin={far_origin:.3f} m, offset={(far_origin - site_origin) * 100.0:.1f} cm, imported={far_landscape is not None}"
        )
    unreal.log(
        f"LEVEL_BUILT site_origin={site_origin:.3f} m, horizon_origin={horizon_origin:.3f} m, horizon offset={offset_cm:.1f} cm"
    )

    saved = unreal.EditorLoadingAndSavingUtils.save_map(world, LEVEL)
    unreal.log(f"LEVEL_SAVED {LEVEL} ok={saved}")
    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
