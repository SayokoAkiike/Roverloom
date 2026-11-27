"""Cut a far-field heightfield around the Gale site from the public MOLA global DEM, for Aeolis Mons (Mount Sharp) in the distance.

    python3 scripts/terrain/mola_far.py --report docs/results/terrain-gale

Source: MGS MOLA DEM mosaic, global, 463 m per pixel (128 pixels per degree), 16-bit, from USGS Astrogeology
(https://astrogeology.usgs.gov/search/map/mars_mgs_mola_dem_463m), the PDS product MEGDR, edition 2003-03-21. The page lists access constraints
"CC0 (public domain)" and use constraints "None", read on 2026-11-16. Credit: NASA/GSFC/MOLA Science Team, USGS. Reference: Smith et al. (2001),
Mars Orbiter Laser Altimeter: Experiment summary after the first year of global mapping of Mars, Journal of Geophysical Research 106(E10),
23689-23722. Only a window is read, over HTTP, never the whole file (about 4 GB).

The window is 200 km square around the same center as the HiRISE site (hirise_site.py), in the same equirectangular projection on the same sphere,
so the coordinates agree. Heights are meters above the Mars aeroid, as in the HiRISE DTM. The grid is resampled to 1009 x 1009 (a valid Landscape
size, about 198 m a sample, finer than the 463 m source: that is interpolation, not new detail).

What is measured and what is not: the 463 m grid is MOLA's gridded map, which is interpolated between the laser tracks, and a resampling to 198 m
adds a second interpolation. The inner part is covered by the HiRISE horizon heightfield, so the far field follows it, 12 m beneath, and the
difference between the two (MOLA is higher by 66 m on average there) is faded out between 4 km and 12 km. That blend is generated, and the report records it.

Output stays outside Git, under unreal/Saved/Terrain/gale/. The report (docs/results/terrain-gale/far.json) is small and is committed.
"""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import local_frame
import numpy as np
from osgeo import gdal

gdal.UseExceptions()

REPO = Path(__file__).resolve().parents[2]
SITES = json.loads(Path(__file__).with_name("sites.json").read_text())
NAME = "gale"
DATA = REPO / "unreal/Saved/Terrain/gale"
REPORT = REPO / "docs/results/terrain-gale"
URL = "/vsicurl/https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif"
CENTER = (
    8139385.0,
    -327230.0,
)  # Same as hirise_site.py, in equirectangular meters on the Mars 3,396,190 m sphere
RADIUS_M = 3396190.0
HALF_M = 100_000.0
SAMPLES = 1009
UNREAL_Z_SPAN_M = 512.0
HORIZON_HALF_M = 2800.0  # The HiRISE horizon heightfield's half width (hirise_horizon.py)


def configure(name: str) -> None:
    global NAME, DATA, REPORT, CENTER, HORIZON_HALF_M
    site = SITES[name]
    NAME = name
    DATA = REPO / "unreal/Saved/Terrain" / name
    REPORT = REPO / site["report"]
    CENTER = local_frame.center(site)
    HORIZON_HALF_M = float(site["horizon_half_m"])


def lonlat(x: float, y: float) -> tuple[float, float]:
    return math.degrees(x / RADIUS_M), math.degrees(y / RADIUS_M)


def window(half: float, size: int) -> np.ndarray:
    x, y = CENTER
    dataset = gdal.Warp(
        "",
        URL,
        format="MEM",
        outputBounds=(x - half, y - half, x + half, y + half),
        width=size,
        height=size,
        resampleAlg="cubic",
        outputType=gdal.GDT_Float32,
        **local_frame.warp_options(SITES[NAME]),
    )
    return dataset.GetRasterBand(1).ReadAsArray().astype(np.float64)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site", choices=sorted(k for k in SITES if not k.startswith("_")), default="gale"
    )
    parser.add_argument("--report", type=Path, help="write far.json here")
    args = parser.parse_args()
    configure(args.site)

    far = window(HALF_M, SAMPLES)
    spacing = 2 * HALF_M / SAMPLES
    site = json.loads((DATA / f"{NAME}_site.json").read_text())
    horizon_info = json.loads((REPORT / "horizon.json").read_text())

    # Compare with the HiRISE horizon heightfield over its own area, on the same datum
    hz_size = SAMPLES
    mola_at_horizon = window(HORIZON_HALF_M, hz_size)
    raw = (
        np.frombuffer((DATA / f"{NAME}_horizon.r16").read_bytes(), dtype="<u2")
        .reshape(hz_size, hz_size)
        .astype(np.float64)
    )
    hirise = horizon_info["height_min_m"] + raw / 65535.0 * (
        horizon_info["height_max_m"] - horizon_info["height_min_m"]
    )
    difference = mola_at_horizon - hirise  # MOLA minus HiRISE, meters
    stats = {
        "mean_m": round(float(difference.mean()), 1),
        "p5_m": round(float(np.percentile(difference, 5)), 1),
        "p95_m": round(float(np.percentile(difference, 95)), 1),
        "std_m": round(float(difference.std()), 1),
    }
    # A blend, so that the far field meets the HiRISE horizon field with no step: inside the horizon field the far field is made to follow it, 12 m
    # beneath (so that the two never share a surface), and outside it the correction (HiRISE minus MOLA at the nearest point of the horizon field)
    # fades smoothly to nothing between 4 km and 12 km. The correction is generated, not measured.
    half = SAMPLES // 2
    index = np.arange(SAMPLES)
    coordinate = (
        index + 0.5 - SAMPLES / 2
    ) * spacing  # meters from the center, along x (east) and, negated, along y (north)
    east = np.broadcast_to(coordinate[None, :], (SAMPLES, SAMPLES))
    north = np.broadcast_to(-coordinate[:, None], (SAMPLES, SAMPLES))
    hz_step = 2 * HORIZON_HALF_M / hz_size

    def bilinear(
        grid: np.ndarray,
        x: np.ndarray,
        y: np.ndarray,
        x0: float,
        y0: float,
        step_x: float,
        step_y: float,
    ) -> np.ndarray:
        """Bilinear value of grid (row 0 north) at east x, north y; x0, y0 are the east and north edges of the grid."""
        col = np.clip((x - x0) / step_x - 0.5, 0, grid.shape[1] - 1.001)
        row = np.clip((y0 - y) / step_y - 0.5, 0, grid.shape[0] - 1.001)
        c0, r0 = col.astype(int), row.astype(int)
        fc, fr = col - c0, row - r0
        return (grid[r0, c0] * (1 - fc) + grid[r0, c0 + 1] * fc) * (1 - fr) + (
            grid[r0 + 1, c0] * (1 - fc) + grid[r0 + 1, c0 + 1] * fc
        ) * fr

    cx = np.clip(east, -HORIZON_HALF_M, HORIZON_HALF_M)
    cy = np.clip(north, -HORIZON_HALF_M, HORIZON_HALF_M)
    hirise_here = bilinear(hirise, cx, cy, -HORIZON_HALF_M, HORIZON_HALF_M, hz_step, hz_step)
    far_here = bilinear(far, cx, cy, -HALF_M, HALF_M, spacing, spacing)
    correction = hirise_here - far_here
    r = np.hypot(east, north)
    weight = np.clip((12000.0 - r) / (12000.0 - 4000.0), 0.0, 1.0)
    weight = weight * weight * (3 - 2 * weight)  # Smoothstep: 1 within 4 km, 0 beyond 12 km
    drop = 12.0
    shaped = far + weight * (correction - drop)

    low, high = float(shaped.min()), float(shaped.max())
    (DATA / f"{NAME}_far.r16").write_bytes(
        np.round((shaped - low) / (high - low) * 65535.0).astype("<u2").tobytes()
    )

    highest_row, highest_col = np.unravel_index(int(np.argmax(far)), far.shape)
    landmark: dict[str, object] = {}
    if NAME == "gale":
        # Aeolis Mons (Mount Sharp): the highest point within 20 km of where it is known to lie (about 5.08 S, 137.85 E)
        sharp_x = math.radians(137.85) * RADIUS_M
        sharp_y = math.radians(-5.08) * RADIUS_M
        near_sharp = np.hypot(east - (sharp_x - CENTER[0]), north - (sharp_y - CENTER[1])) < 20000.0
        masked = np.where(near_sharp, far, -1e9)
        peak_row, peak_col = np.unravel_index(int(np.argmax(masked)), far.shape)
        px = CENTER[0] + float(east[peak_row, peak_col])
        py = CENTER[1] + float(north[peak_row, peak_col])
        peak_lon, peak_lat = lonlat(px, py)
        east_km, north_km = (px - CENTER[0]) / 1000.0, (py - CENTER[1]) / 1000.0
        peak_height = float(far[peak_row, peak_col])
        landmark = {
            "aeolis_mons_peak_height_m": round(peak_height, 1),
            "aeolis_mons_peak_elevation_angle_deg": round(
                math.degrees(
                    math.atan2(
                        peak_height - site["height_min_m"], math.hypot(east_km, north_km) * 1000.0
                    )
                ),
                2,
            ),
            "aeolis_mons_peak_east_km": round(east_km, 1),
            "aeolis_mons_peak_north_km": round(north_km, 1),
            "aeolis_mons_peak_lon_lat_deg": [round(peak_lon, 3), round(peak_lat, 3)],
            "aeolis_mons_peak_distance_km": round(math.hypot(east_km, north_km), 1),
        }
    info = {
        "source": "MGS MOLA DEM mosaic, global, 463 m (MEGDR, 2003-03-21), USGS Astrogeology",
        "source_url": "https://astrogeology.usgs.gov/search/map/mars_mgs_mola_dem_463m",
        "license": "CC0 (public domain) per the product page, read 2026-11-16",
        "credit": "NASA/GSFC/MOLA Science Team; USGS Astrogeology",
        "reference": "Smith et al. 2001, J. Geophys. Res. 106(E10), 23689-23722",
        "source_pixel_m": 463.09,
        "samples": SAMPLES,
        "spacing_m": round(spacing, 2),
        "extent_m": round((SAMPLES - 1) * spacing, 0),
        "resampling": "cubic, from 463 m to about 198 m: interpolated, not new detail",
        "measured_note": "MOLA's gridded map is interpolated between laser tracks; every sample here is interpolated at least once",
        "height_min_m": round(low, 1),
        "height_max_m": round(high, 1),
        "highest_point_in_window_m": round(float(far.max()), 1),
        "highest_point_east_north_km": [
            round(float(east[highest_row, highest_col]) / 1000.0, 1),
            round(float(north[highest_row, highest_col]) / 1000.0, 1),
        ],
        **landmark,
        "site_origin_height_m": site["height_min_m"],
        "mola_minus_hirise_over_horizon_field": stats,
        "blend": "far field follows the HiRISE horizon field 12 m beneath it inside it; the correction fades from 4 km to 12 km (generated)",
        "blend_drop_below_horizon_m": drop,
        "blend_full_to_km": 4,
        "blend_ends_km": 12,
        "correction_at_edge_of_horizon_field_m_mean": round(
            float(np.mean([correction[half, :][abs(east[half, :]) > 0][0]])), 1
        ),
        "unreal_xy_scale_percent": round(spacing * 100.0, 2),
        "unreal_z_scale_percent": round((high - low) / UNREAL_Z_SPAN_M * 100.0, 2),
        "unreal_z_offset_m_above_site_datum": round(low - site["height_min_m"], 1),
    }
    print(json.dumps(info, indent=2))
    # Beside the heightfield too, so that a level can be built without writing into docs/
    (DATA / f"{NAME}_far.json").write_text(json.dumps(info, indent=2) + "\n")
    if args.report:
        args.report.mkdir(parents=True, exist_ok=True)
        (args.report / "far.json").write_text(json.dumps(info, indent=2) + "\n")


if __name__ == "__main__":
    main()
