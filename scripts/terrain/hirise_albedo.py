"""Turn a HiRISE orthoimage into a ground-brightness map for a site Landscape, with the photo's own shading divided out.

The HiRISE RED orthoimage that comes with each DTM is a greyscale photo, aligned with the DTM. Its brightness is
the ground's own brightness (light-toned layers, dark sand, dust) times the shading of the moment it was taken.
Unreal lights the Landscape again, so the shading would count twice. Here the sun direction is fitted: the
azimuth and elevation whose Lambert shading of the DTM best explains the photo, with an ambient term
(I = albedo * (a * cos i + b)). Dividing by that shading leaves a relative brightness, normalised to mean 1.

    python3 scripts/terrain/hirise_albedo.py --site noctis --download

Writes unreal/Saved/Terrain/<site>/<site>_albedo.png (the 1 km site) and <site>_horizon_albedo.png (the horizon
square), 1024 x 1024, 8-bit, where 128 is the mean. Needs GDAL and NumPy, and hirise_site.py and hirise_horizon.py
first. The fit and the division are approximations: shadows, the atmosphere, photometric effects and stereo noise
are not modelled, and the result is a relative brightness, not a measured albedo. The ortho is greyscale (RED
filter); colour comes from the material.
"""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

from __future__ import annotations

import argparse
import hashlib
import json
import math
import urllib.request
from pathlib import Path

import numpy as np
from osgeo import gdal

gdal.UseExceptions()

REPO = Path(__file__).resolve().parents[2]
SITES = json.loads(Path(__file__).with_name("sites.json").read_text())
SAMPLES = 1009
OUT_SIZE = 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def cut(source: Path, center: tuple[float, float], half: float, resample: str) -> np.ndarray:
    x, y = center
    dataset = gdal.Warp(
        "",
        str(source),
        format="MEM",
        outputBounds=(x - half, y - half, x + half, y + half),
        width=SAMPLES,
        height=SAMPLES,
        resampleAlg=resample,
        outputType=gdal.GDT_Float32,
        srcNodata=0,
        dstNodata=-1,
    )
    return dataset.GetRasterBand(1).ReadAsArray().astype(np.float64)


def heights(path: Path, info: dict) -> np.ndarray:
    raw = np.fromfile(path, dtype="<u2").reshape(SAMPLES, SAMPLES).astype(np.float64)
    return info["height_min_m"] + raw / 65535.0 * (info["height_max_m"] - info["height_min_m"])


def smooth(height: np.ndarray) -> np.ndarray:
    """A 5-post box blur, twice: the photo's shading is resolved more finely, but the DTM's 1 m slopes are noisy."""
    out = height
    for _ in range(2):
        padded = np.pad(out, 2, mode="edge")
        out = sum(padded[i : i + out.shape[0], 2 : 2 + out.shape[1]] for i in range(5)) / 5
        padded = np.pad(out, 2, mode="edge")
        out = sum(padded[2 : 2 + out.shape[0], j : j + out.shape[1]] for j in range(5)) / 5
    return out


def lambert(height: np.ndarray, spacing: float, azimuth: float, elevation: float) -> np.ndarray:
    gy, gx = np.gradient(height, spacing)  # rows run south, so gy is -d/dnorth
    nx, ny, nz = -gx, gy, np.ones_like(height)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    sx = math.cos(elevation) * math.sin(azimuth)  # east
    sy = math.cos(elevation) * math.cos(azimuth)  # north
    sz = math.sin(elevation)
    return np.clip((nx * sx + ny * sy + nz * sz) / norm, 0.0, None)


def fit_sun(image: np.ndarray, height: np.ndarray, spacing: float) -> dict:
    """Grid search for the sun direction whose shading best explains the photo (largest R^2 of a linear fit)."""
    image, height = image[::2, ::2], height[::2, ::2]
    spacing *= 2
    valid = image > 0
    best = None
    for elevation_deg in range(15, 81, 5):
        for azimuth_deg in range(0, 360, 10):
            shade = lambert(height, spacing, math.radians(azimuth_deg), math.radians(elevation_deg))
            x, y = shade[valid], image[valid]
            a, b = np.polyfit(x, y, 1)
            r2 = 1 - np.var(y - (a * x + b)) / np.var(y)
            if best is None or r2 > best["r2"]:
                best = {
                    "azimuth_deg": azimuth_deg,
                    "elevation_deg": elevation_deg,
                    "a": a,
                    "b": b,
                    "r2": r2,
                }
    assert best is not None
    # Refine around the best cell
    for elevation_deg in np.arange(best["elevation_deg"] - 4, best["elevation_deg"] + 4.1, 1.0):
        for azimuth_deg in np.arange(best["azimuth_deg"] - 8, best["azimuth_deg"] + 8.1, 2.0):
            shade = lambert(height, spacing, math.radians(azimuth_deg), math.radians(elevation_deg))
            x, y = shade[valid], image[valid]
            a, b = np.polyfit(x, y, 1)
            r2 = 1 - np.var(y - (a * x + b)) / np.var(y)
            if r2 > best["r2"]:
                best = {
                    "azimuth_deg": float(azimuth_deg),
                    "elevation_deg": float(elevation_deg),
                    "a": a,
                    "b": b,
                    "r2": r2,
                }
    # A dusty sky lights shadowed ground too. Where the free fit gives an ambient share outside 0.15..0.5, which happens
    # where brightness differences in the ground outweigh the shading, keep the direction and fix the share at the bound.
    share = best["b"] / (best["a"] + best["b"])
    best["ambient_fitted"] = share
    if not 0.15 <= share <= 0.5:
        share = min(0.5, max(0.15, share))
        shade = lambert(
            height, spacing, math.radians(best["azimuth_deg"]), math.radians(best["elevation_deg"])
        )
        model = (1 - share) * shade + share
        k = float(np.sum(image[valid] * model[valid]) / np.sum(model[valid] ** 2))
        best["a"], best["b"] = k * (1 - share), k * share
    best["ambient_used"] = share
    return best


def albedo(
    image: np.ndarray, height: np.ndarray, spacing: float, sun: dict
) -> tuple[np.ndarray, float]:
    shade = lambert(
        height, spacing, math.radians(sun["azimuth_deg"]), math.radians(sun["elevation_deg"])
    )
    model = np.clip(sun["a"] * shade + sun["b"], 1e-6, None)
    valid = image > 0
    # Cast shadows (pit floors, the lee of cliffs) are not in the Lambert model: they would come out as dark ground.
    # Ground darker than 45 % of the median photo brightness is treated as shadow and left at the mean brightness.
    shadow = valid & (image < 0.45 * np.median(image[valid]))
    result = np.where(valid & ~shadow, image / model, np.nan)
    result /= np.nanmean(result)
    missing = float(np.isnan(result).mean())
    return np.nan_to_num(np.clip(result, 0.35, 1.9), nan=1.0), missing


def write_png(values: np.ndarray, target: Path) -> None:
    grey = np.clip(np.round(values * 128.0), 0, 255).astype(np.uint8)
    memory = gdal.GetDriverByName("MEM").Create("", SAMPLES, SAMPLES, 1, gdal.GDT_Byte)
    memory.GetRasterBand(1).WriteArray(grey)
    gdal.Translate(
        str(target), memory, format="PNG", width=OUT_SIZE, height=OUT_SIZE, resampleAlg="bilinear"
    )
    target.with_suffix(target.suffix + ".aux.xml").unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--site",
        choices=sorted(k for k, v in SITES.items() if isinstance(v, dict) and "ortho" in v),
        required=True,
    )
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--report", type=Path, help="write albedo.json here")
    args = parser.parse_args()
    site = SITES[args.site]
    data = REPO / "unreal/Saved/Terrain" / args.site
    source = data / f"{site['ortho']}.tif"
    if args.download and not source.exists():
        url = f"https://astrogeo-ard.s3-us-west-2.amazonaws.com/mars/mro/hirise/controlled/dtm/{site['pair']}/{site['ortho']}.tif"
        print(f"download {url}")
        urllib.request.urlretrieve(url, source)
    checksum = sha256(source)
    if checksum != site["ortho_sha256"]:
        raise SystemExit(f"{source} has SHA-256 {checksum}, expected {site['ortho_sha256']}")
    center = (float(site["center_projected_m"][0]), float(site["center_projected_m"][1]))
    site_info = json.loads((data / f"{args.site}_site.json").read_text())
    horizon_info = json.loads((REPO / site["report"] / "horizon.json").read_text())

    image = cut(source, center, (SAMPLES - 1) / 2 + 0.5, "bilinear")
    height = heights(data / f"{args.site}_site.r16", site_info)
    height = smooth(height)
    sun = fit_sun(image, height, 1.0)
    site_albedo, site_missing = albedo(image, height, 1.0, sun)
    write_png(site_albedo, data / f"{args.site}_albedo.png")

    half = horizon_info["extent_m"] / 2 + horizon_info["spacing_m"] / 2
    horizon_image = cut(source, center, half, "average")
    horizon_height = heights(data / f"{args.site}_horizon.r16", horizon_info)
    horizon_albedo, horizon_missing = albedo(
        horizon_image, horizon_height, horizon_info["spacing_m"], sun
    )
    write_png(horizon_albedo, data / f"{args.site}_horizon_albedo.png")

    report = {
        "source": f"{site['ortho']}.tif",
        "source_sha256": checksum,
        "license": "CC0-1.0 (HiRISE products are public domain); NASA/JPL/University of Arizona, distributed by USGS",
        "method": "albedo = photo / (a * cos i + b), with the sun direction fitted to the DTM's Lambert shading; normalised to mean 1, clipped to 0.35..1.9; cast shadows (under 45 % of the median) and gaps set to the mean",
        "fitted_sun_azimuth_deg_from_north": sun["azimuth_deg"],
        "fitted_sun_elevation_deg": sun["elevation_deg"],
        "fit_r2": round(float(sun["r2"]), 3),
        "ambient_share_fitted": round(float(sun["ambient_fitted"]), 3),
        "ambient_share_used": round(float(sun["ambient_used"]), 3),
        "site_shadow_or_missing_fraction": round(site_missing, 4),
        "horizon_shadow_or_missing_fraction": round(horizon_missing, 4),
        "output": f"{OUT_SIZE} x {OUT_SIZE} 8-bit PNG, 128 = mean brightness",
        "caveat": "A relative brightness from one greyscale photo with an approximate shading model. Not a measured albedo or colour.",
    }
    print(json.dumps(report, indent=2))
    (data / f"{args.site}_albedo.json").write_text(json.dumps(report, indent=2) + "\n")
    if args.report:
        args.report.mkdir(parents=True, exist_ok=True)
        (args.report / "albedo.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
