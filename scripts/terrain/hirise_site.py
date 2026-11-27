"""Cut a 1 km site from a HiRISE DTM and write an Unreal Landscape heightfield.

Follows the terrain data pipeline in docs/unreal-production-plan.md. Raw downloads and the
heightfield stay outside Git, under unreal/Saved/Terrain/. The metadata and small previews are
written for docs/results/terrain-<site>/. Sites are listed in sites.json; the default is gale.

Needs GDAL's Python bindings and NumPy, for example Homebrew's `gdal` with its python3:

    python3 scripts/terrain/hirise_site.py --download
    python3 scripts/terrain/hirise_site.py --previews docs/results/terrain-gale
    python3 scripts/terrain/hirise_site.py --site noctis --download

Heights are relative to the Mars aeroid, in meters, as in the source. Detail finer than the
DTM's post spacing is not in the heightfield; anything finer in a scene is generated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import urllib.request
from pathlib import Path

import local_frame
import numpy as np
from osgeo import gdal

gdal.UseExceptions()

REPO = Path(__file__).resolve().parents[2]
SITES = json.loads((Path(__file__).with_name("sites.json")).read_text())
NAME = "gale"
PRODUCT = PAIR = BASE_URL = STAC_URL = SOURCE_SHA256 = ""
FILES: list[str] = []
CENTER = (0.0, 0.0)
SOURCE_GSD_M = 1.0


def configure(name: str) -> None:
    """Point the module at one site of sites.json. The default, gale, reproduces the original."""
    global NAME, PRODUCT, PAIR, BASE_URL, STAC_URL, SOURCE_SHA256, FILES, CENTER, SOURCE_GSD_M
    site = SITES[name]
    NAME, PRODUCT, PAIR = name, site["product"], site["pair"]
    BASE_URL = (
        f"https://astrogeo-ard.s3-us-west-2.amazonaws.com/mars/mro/hirise/controlled/dtm/{PAIR}"
    )
    STAC_URL = (
        f"https://stac.astrogeology.usgs.gov/api/collections/mro_hirise_socet_dtms/items/{PRODUCT}"
    )
    FILES = [f"{PRODUCT}.tif", f"{PRODUCT}.jpg"] + (["provenance.txt"] if name == "gale" else [])
    SOURCE_SHA256 = site["sha256"]
    CENTER = local_frame.center(site)
    SOURCE_GSD_M = float(site["source_gsd_m"])


configure("gale")
SAMPLES = 1009  # a valid Landscape size: 8 components of 2 x 63 quads, plus one
SPACING_M = 1.0
UNREAL_Z_SPAN_M = 512.0  # Landscape at 100% Z scale spans about 512 m; verify at import
DRIVABLE_DEG = 15.0
BASELINE_M = 4.0  # about rover length; 1 m slopes are dominated by stereo noise


def download(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = out / name
        if target.exists():
            continue
        print(f"download {BASE_URL}/{name}")
        urllib.request.urlretrieve(f"{BASE_URL}/{name}", target)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def slope_deg(height: np.ndarray, spacing: float) -> np.ndarray:
    gy, gx = np.gradient(height, spacing)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def slope_at_baseline(height: np.ndarray, spacing: float, baseline_m: float) -> np.ndarray:
    """Slope over a baseline, averaging blocks first. Near rover length, it skips DTM noise."""
    block = round(baseline_m / spacing)
    rows, cols = (s // block * block for s in height.shape)
    pooled = (
        height[:rows, :cols].reshape(rows // block, block, cols // block, block).mean(axis=(1, 3))
    )
    return slope_deg(pooled, block * spacing)


def crop(source: Path, out: Path) -> Path:
    half = (SAMPLES - 1) * SPACING_M / 2 + SPACING_M / 2
    x, y = CENTER
    target = out / f"{NAME}_site.tif"
    gdal.Warp(
        str(target),
        str(source),
        outputBounds=(x - half, y - half, x + half, y + half),
        width=SAMPLES,
        height=SAMPLES,
        resampleAlg="cubic",
        outputType=gdal.GDT_Float32,
        dstNodata=-3.4028227e38,
        **local_frame.warp_options(SITES[NAME]),
    )
    return target


def fill_nodata(path: Path) -> int:
    dataset = gdal.Open(str(path), gdal.GA_Update)
    band = dataset.GetRasterBand(1)
    missing = int((band.ReadAsArray() < -1e30).sum())
    if missing:
        gdal.FillNodata(band, None, maxSearchDist=50, smoothingIterations=0)
    dataset.FlushCache()
    return missing


def write_r16(height: np.ndarray, target: Path) -> tuple[float, float]:
    low, high = float(height.min()), float(height.max())
    scaled = np.round((height - low) / (high - low) * 65535.0).astype("<u2")
    target.write_bytes(scaled.tobytes())
    return low, high


def bilinear(dataset: gdal.Dataset, x: float, y: float) -> float:
    gt = dataset.GetGeoTransform()
    col = (x - gt[0]) / gt[1] - 0.5
    row = (y - gt[3]) / gt[5] - 0.5
    c0, r0 = math.floor(col), math.floor(row)
    window = dataset.GetRasterBand(1).ReadAsArray(c0, r0, 2, 2).astype(np.float64)
    fc, fr = col - c0, row - r0
    top = window[0, 0] * (1 - fc) + window[0, 1] * fc
    bottom = window[1, 0] * (1 - fc) + window[1, 1] * fc
    return float(top * (1 - fr) + bottom * fr)


def import_check(
    source: Path, r16: Path, low: float, high: float, seed: int = 7
) -> dict[str, float]:
    """Compare height differences between random point pairs: heightfield against source DTM."""
    heights = np.frombuffer(r16.read_bytes(), dtype="<u2").reshape(SAMPLES, SAMPLES)
    meters = low + heights.astype(np.float64) / 65535.0 * (high - low)
    dataset = gdal.Open(str(source))
    rng = np.random.default_rng(seed)
    half = (SAMPLES - 1) * SPACING_M / 2
    errors = []
    for _ in range(200):
        (r1, c1), (r2, c2) = rng.integers(2, SAMPLES - 2, size=(2, 2))
        points = []
        for row, col in ((r1, c1), (r2, c2)):
            x = CENTER[0] - half + col * SPACING_M
            y = CENTER[1] + half - row * SPACING_M
            points.append((meters[row, col], bilinear(dataset, x, y)))
        errors.append(abs((points[0][0] - points[1][0]) - (points[0][1] - points[1][1])))
    values = np.array(errors)
    return {
        "pairs": len(values),
        "median_abs_error_m": round(float(np.median(values)), 3),
        "max_abs_error_m": round(float(values.max()), 3),
        "quantization_step_m": round((high - low) / 65535.0, 4),
    }


def hillshade_jpeg(height: np.ndarray, spacing: float, target: Path, width: int) -> None:
    gy, gx = np.gradient(height, spacing)
    azimuth, altitude = math.radians(315.0), math.radians(45.0)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    shade = np.sin(altitude) * np.cos(slope) + np.cos(altitude) * np.sin(slope) * np.cos(
        azimuth - aspect
    )
    write_jpeg(np.clip(shade * 255, 0, 255).astype(np.uint8)[None], target, width)


def slope_jpeg(slope: np.ndarray, target: Path, width: int) -> None:
    """Grey under 15 degrees, shading to orange and red above it."""
    t = np.clip((slope - DRIVABLE_DEG) / 15.0, 0.0, 1.0)
    grey = np.clip(80 + slope / DRIVABLE_DEG * 120, 80, 200)
    steep = slope >= DRIVABLE_DEG
    red = np.where(steep, 230, grey)
    green = np.where(steep, 150 * (1 - t) + 40 * t, grey)
    blue = np.where(steep, 40, grey)
    write_jpeg(np.stack([red, green, blue]).astype(np.uint8), target, width)


def write_jpeg(bands: np.ndarray, target: Path, width: int) -> None:
    memory = gdal.GetDriverByName("MEM").Create(
        "", bands.shape[2], bands.shape[1], bands.shape[0], gdal.GDT_Byte
    )
    for index, band in enumerate(bands, start=1):
        memory.GetRasterBand(index).WriteArray(band)
    gdal.Translate(
        str(target), memory, format="JPEG", width=width, height=0, creationOptions=["QUALITY=85"]
    )
    target.with_suffix(target.suffix + ".aux.xml").unlink(missing_ok=True)


def locator_jpeg(source: Path, target: Path) -> None:
    """The whole product's hillshade at about 8 m, with the site outlined."""
    dataset = gdal.Open(str(source))
    band = dataset.GetRasterBand(1)
    overview = band.GetOverview(2)
    raw = overview.ReadAsArray().astype(np.float64)
    valid = raw > -1e30
    spacing = dataset.GetGeoTransform()[1] * dataset.RasterXSize / overview.XSize
    height = np.where(valid, raw, np.nanmean(np.where(valid, raw, np.nan)))
    gy, gx = np.gradient(height, spacing)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    shade = 0.707 * np.cos(slope) + 0.707 * np.sin(slope) * np.cos(math.radians(315) - aspect)
    grey = np.where(valid, np.clip(shade * 255, 0, 255), 255).astype(np.uint8)
    rgb = np.stack([grey, grey, grey])
    gt = dataset.GetGeoTransform()
    half = (SAMPLES - 1) * SPACING_M / 2
    c0 = int((CENTER[0] - half - gt[0]) / spacing)
    c1 = int((CENTER[0] + half - gt[0]) / spacing)
    r0 = int((CENTER[1] + half - gt[3]) / -spacing)
    r1 = int((CENTER[1] - half - gt[3]) / -spacing)
    for channel, value in zip(rgb, (230, 160, 0), strict=True):
        for edge in range(3):
            channel[r0 + edge, c0:c1] = channel[r1 - edge, c0:c1] = value
            channel[r0:r1, c0 + edge] = channel[r0:r1, c1 - edge] = value
    write_jpeg(rgb, target, 480)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--site", choices=sorted(k for k in SITES if not k.startswith("_")), default="gale"
    )
    parser.add_argument("--data", type=Path, help="default: unreal/Saved/Terrain/<site>")
    parser.add_argument(
        "--download", action="store_true", help="fetch the DTM from USGS if missing"
    )
    parser.add_argument("--previews", type=Path, help="write metadata and preview images here")
    args = parser.parse_args()
    configure(args.site)
    args.data = args.data or REPO / "unreal/Saved/Terrain" / args.site

    if args.download:
        download(args.data)
    source = args.data / f"{PRODUCT}.tif"
    checksum = sha256(source)
    if checksum != SOURCE_SHA256:
        raise SystemExit(f"{source} has SHA-256 {checksum}, expected {SOURCE_SHA256}")

    cropped = crop(source, args.data)
    filled = fill_nodata(cropped)
    site = gdal.Open(str(cropped))
    height = site.GetRasterBand(1).ReadAsArray().astype(np.float64)
    site = None
    r16 = args.data / f"{NAME}_site.r16"
    low, high = write_r16(height, r16)
    slope = slope_deg(height, SPACING_M)
    slope4 = slope_at_baseline(height, SPACING_M, BASELINE_M)
    check = import_check(
        Path(local_frame.local_source(source, SITES[NAME], args.data)), r16, low, high
    )

    extra = {} if NAME == "gale" else {"site": NAME, "rationale": SITES[NAME]["rationale"]}
    metadata = {
        **extra,
        "product": PRODUCT,
        "stac_item": STAC_URL,
        "source_url": f"{BASE_URL}/{PRODUCT}.tif",
        "source_sha256": checksum,
        "license": "CC0-1.0",
        "credit": "NASA/JPL/University of Arizona; DTM distributed by USGS",
        **(
            {
                "projection": "local stereographic on the Mars sphere: "
                + local_frame.srs(SITES[NAME]),
                "source_projection": gdal.Open(str(source)).GetSpatialRef().GetName(),
                "center_lon_lat_deg": list(SITES[NAME]["center_lonlat"]),
            }
            if local_frame.is_local(SITES[NAME])
            else {
                "projection": "Mars (2015) sphere, equirectangular, clon 0 (IAU_2015:49910)",
                "center_projected_m": list(CENTER),
                "center_lon_lat_deg": [
                    round(math.degrees(CENTER[0] / 3396190.0), 5),
                    round(math.degrees(CENTER[1] / 3396190.0), 5),
                ],
            }
        ),
        "samples": SAMPLES,
        "spacing_m": SPACING_M,
        "extent_m": (SAMPLES - 1) * SPACING_M,
        "resampling": f"cubic, from about {SOURCE_GSD_M} m",
        "nodata_filled_samples": filled,
        "height_min_m": round(low, 3),
        "height_max_m": round(high, 3),
        "height_reference": "Mars aeroid; heightfield is relative to height_min_m",
        "r16": "uint16 little-endian, row 0 north, 0 = height_min_m, 65535 = height_max_m",
        "unreal_z_scale_percent": round((high - low) / UNREAL_Z_SPAN_M * 100.0, 3),
        "unreal_xy_scale_percent": SPACING_M * 100.0,
        "slope_1m": {
            "under_15_deg_fraction": round(float((slope < DRIVABLE_DEG).mean()), 4),
            "p95_deg": round(float(np.percentile(slope, 95)), 2),
            "note": "Dominated by stereo noise; resolving power is coarser than the spacing",
        },
        "slope_4m": {
            "under_15_deg_fraction": round(float((slope4 < DRIVABLE_DEG).mean()), 4),
            "p95_deg": round(float(np.percentile(slope4, 95)), 2),
            "max_deg": round(float(slope4.max()), 2),
        },
        "import_check": check,
        "measured_vs_generated": (
            "Shape at about 1 m is measured; anything finer is generated"
            if SOURCE_GSD_M < 1.5
            else f"Shape at about {SOURCE_GSD_M:.0f} m is measured; "
            "the 1 m posts and anything finer are interpolated or generated"
        ),
    }
    print(json.dumps(metadata, indent=2))
    r16.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")

    if args.previews:
        args.previews.mkdir(parents=True, exist_ok=True)
        (args.previews / "site.json").write_text(json.dumps(metadata, indent=2) + "\n")
        hillshade_jpeg(height, SPACING_M, args.previews / "hillshade.jpg", 800)
        slope_jpeg(np.kron(slope4, np.ones((4, 4))), args.previews / "slope.jpg", 800)
        if not local_frame.is_local(SITES[NAME]):  # the locator outlines the site in source metres
            locator_jpeg(source, args.previews / "locator.jpg")


if __name__ == "__main__":
    main()
