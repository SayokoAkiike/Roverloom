"""Cut a coarse horizon heightfield around the Gale site, for distant ridges in Unreal.

The near site is `gale_site.r16` from hirise_site.py (1 km, 1 m posts). This script cuts a wider area from
the same DTM at 10 m posts, so that the Landscape outside the site is measured relief at coarse resolution.
Heights are written relative to the *site's* height_min_m, so the two Landscapes share one vertical datum.

    python3 scripts/terrain/hirise_horizon.py --report docs/results/terrain-gale

Outputs stay outside Git, under unreal/Saved/Terrain/gale/. The DTM covers about 5.7 km by 10.7 km, and 23% of
its samples are nodata, so a square 10 km around the site reaches past its footprint to the east and west. Every
such sample is filled by interpolation from the nearest valid data and counted here. That is generated, not
measured, and the report says how much.
"""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from osgeo import gdal

gdal.UseExceptions()

REPO = Path(__file__).resolve().parents[2]
SITES = json.loads(Path(__file__).with_name("sites.json").read_text())
NAME = "gale"
DATA = REPO / "unreal/Saved/Terrain/gale"
SOURCE = DATA / "DTEEC_063319_1745_052242_1745_A01.tif"
SITE = DATA / "gale_site.json"
CENTER = (8139385.0, -327230.0)  # Same as hirise_site.py
GSD_M = 1.0126


def configure(name: str) -> None:
    global NAME, DATA, SOURCE, SITE, CENTER, GSD_M
    site = SITES[name]
    NAME = name
    DATA = REPO / "unreal/Saved/Terrain" / name
    SOURCE = DATA / f"{site['product']}.tif"
    SITE = DATA / f"{name}_site.json"
    CENTER = (float(site["center_projected_m"][0]), float(site["center_projected_m"][1]))
    GSD_M = float(site["source_gsd_m"])


SAMPLES = 1009  # A valid Landscape size
UNREAL_Z_SPAN_M = 512.0


def cut(target: Path, half: float, spacing: float) -> None:
    x, y = CENTER
    gdal.Warp(
        str(target),
        str(SOURCE),
        outputBounds=(x - half, y - half, x + half, y + half),
        width=SAMPLES,
        height=SAMPLES,
        resampleAlg="average",  # Averages the 1 m posts, which also damps stereo noise
        outputType=gdal.GDT_Float32,
        dstNodata=-3.4028227e38,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site", choices=sorted(k for k in SITES if not k.startswith("_")), default="gale"
    )
    parser.add_argument("--report", type=Path, help="write horizon.json here")
    parser.add_argument(
        "--half-m",
        type=float,
        default=None,
        help="half the side of the square, in meters. The DTM reaches 2.8 km east and west of the site and 3.0 km south",
    )
    args = parser.parse_args()
    configure(args.site)
    args.half_m = args.half_m or float(SITES[args.site]["horizon_half_m"])
    spacing = 2 * args.half_m / SAMPLES

    site = json.loads(SITE.read_text())
    tif = DATA / f"{NAME}_horizon.tif"
    cut(tif, args.half_m, spacing)
    dataset = gdal.Open(str(tif), gdal.GA_Update)
    band = dataset.GetRasterBand(1)
    heights = band.ReadAsArray().astype(np.float64)
    missing = heights < -1e30
    filled = int(missing.sum())
    if filled:
        gdal.FillNodata(band, None, maxSearchDist=400, smoothingIterations=3)
        dataset.FlushCache()
        heights = band.ReadAsArray().astype(np.float64)
    still = int((heights < -1e30).sum())
    if still:
        raise SystemExit(f"{still} samples remain nodata after filling; widen maxSearchDist")

    datum = site["height_min_m"]
    low, high = float(heights.min()), float(heights.max())
    # The 16-bit range spans the horizon's own min..max, so the Z offset places it against the site.
    scaled = np.round((heights - low) / (high - low) * 65535.0).astype("<u2")
    (DATA / f"{NAME}_horizon.r16").write_bytes(scaled.tobytes())

    info = {
        "samples": SAMPLES,
        "spacing_m": round(spacing, 4),
        "extent_m": round((SAMPLES - 1) * spacing, 1),
        "resampling": f"average, from about {GSD_M} m",
        "measured_samples": int(heights.size - filled),
        "measured_fraction": round(1 - filled / heights.size, 4),
        "filled_samples": filled,
        "filled_fraction": round(filled / heights.size, 4),
        "height_min_m": round(low, 3),
        "height_max_m": round(high, 3),
        "site_height_min_m": datum,
        "unreal_xy_scale_percent": round(spacing * 100.0, 2),
        "unreal_z_scale_percent": round((high - low) / UNREAL_Z_SPAN_M * 100.0, 3),
        "unreal_z_offset_m_above_site_datum": round(low - datum, 3),
        "note": "Filled samples are interpolated, not measured. The 1 km site lies inside, at the center.",
    }
    print(json.dumps(info, indent=2))
    if args.report:
        args.report.mkdir(parents=True, exist_ok=True)
        (args.report / "horizon.json").write_text(json.dumps(info, indent=2) + "\n")


if __name__ == "__main__":
    main()
