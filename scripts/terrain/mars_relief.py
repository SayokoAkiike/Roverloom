"""Write the whole-Mars relief that the race lobby's map and globe draw: MOLA elevation on a 0.5 degree grid.

    python3 scripts/terrain/mars_relief.py

Reads the USGS MOLA global DEM (463 m, NASA/JPL/GSFC, the same source as mola_far.py) over HTTP, four sampled rows
and 64 columns averaged per output cell, so about 130 MB is read instead of the whole 2 GB file. Writes
python/src/roverloom/preview/mars_relief.json: elevation in metres above -9 km as little-endian uint16, base64,
row 0 at 90 N, column 0 at 180 W. Text, so that it stays in plain Git. Needs GDAL's Python bindings and NumPy.
"""

# ruff: noqa: E501  (long prose lines in the docstring)

from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np
from osgeo import gdal

gdal.UseExceptions()
URL = "/vsicurl/https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif"
OUT = Path(__file__).resolve().parents[2] / "python/src/roverloom/preview/mars_relief.json"
WIDTH, HEIGHT = 720, 360
LOW_M, STEP_M = (
    -9000.0,
    1.0,
)  # uint16: -9 km to +56 km in 1 m steps, the whole planet (Olympus Mons is about +21 km)
SAMPLED_ROWS = 4


def main() -> None:
    dataset = gdal.Open(URL)
    band = dataset.GetRasterBand(1)
    cols, rows = dataset.RasterXSize, dataset.RasterYSize
    fy, fx = rows // HEIGHT, cols // WIDTH
    grid = np.zeros((HEIGHT, WIDTH))
    peak = np.full((HEIGHT, WIDTH), -1e9)
    for r in range(HEIGHT):
        acc = np.zeros(WIDTH)
        for k in range(SAMPLED_ROWS):
            row = r * fy + (2 * k + 1) * fy // (2 * SAMPLED_ROWS)
            line = band.ReadAsArray(0, row, cols, 1)[0].astype(np.float64)[: WIDTH * fx]
            blocks = line.reshape(WIDTH, fx)
            acc += blocks.mean(axis=1)
            peak[r] = np.maximum(peak[r], blocks.max(axis=1))
        grid[r] = acc / SAMPLED_ROWS
        if r % 60 == 0:
            print(f"row {r}/{HEIGHT}", flush=True)
    q = np.clip(np.round((grid - LOW_M) / STEP_M), 0, 65535).astype("<u2")
    doc = {
        "source": "MOLA MEGDR global DEM 463 m, mosaic by USGS Astrogeology (https://astrogeology.usgs.gov/search/map/mars_mgs_mola_dem_463m)",
        "credit": "NASA/JPL/GSFC (MOLA Science Team), USGS",
        "license": "Public domain (NASA data)",
        "grid": "0.5 degree cells, row 0 at 90 N, column 0 at 180 W, planetocentric, east-positive longitude",
        "width": WIDTH,
        "height": HEIGHT,
        "encoding": "uint16 little-endian; elevation_m = low_m + value * step_m (MOLA areoid datum)",
        "low_m": LOW_M,
        "step_m": STEP_M,
        # Range of the cell means stored here, and the highest sample read (cells average it away)
        "elevation_min_m": round(float(grid.min()), 1),
        "elevation_max_m": round(float(grid.max()), 1),
        "highest_sample_m": round(float(peak.max()), 1),
        "data": base64.b64encode(q.tobytes()).decode("ascii"),
    }
    OUT.write_text(json.dumps(doc) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB), {grid.min():.0f} to {grid.max():.0f} m")


if __name__ == "__main__":
    main()
