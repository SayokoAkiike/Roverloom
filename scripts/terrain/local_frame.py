"""A local, true-to-scale frame for terrain sites away from the equator.

The HiRISE DTMs come in equirectangular metres (true scale only on the equator) or, near the
poles, in polar stereographic metres. Cutting a 1 km square in equirectangular metres at 49 deg
latitude would stretch the ground 1.5 times east to west. A site in sites.json with
`center_lonlat` is therefore cut in a stereographic projection centred on that point, where a
metre is a metre in every direction within a few kilometres, and its centre is (0, 0). Sites
without it (Gale, Noctis, Amazonis, close to the equator) keep their original equirectangular
cut, so their outputs do not change.
"""

from __future__ import annotations

from typing import Any

MARS_RADIUS_M = 3396190.0


def is_local(site: dict[str, Any]) -> bool:
    return "center_lonlat" in site


def srs(site: dict[str, Any]) -> str:
    lon, lat = (float(v) for v in site["center_lonlat"])
    return (
        f"+proj=stere +lat_0={lat} +lon_0={lon} +k=1 +x_0=0 +y_0=0 "
        f"+R={MARS_RADIUS_M} +units=m +no_defs"
    )


def center(site: dict[str, Any]) -> tuple[float, float]:
    """The site's centre in the frame its cuts use."""
    if is_local(site):
        return (0.0, 0.0)
    x, y = site["center_projected_m"]
    return (float(x), float(y))


def warp_options(site: dict[str, Any]) -> dict[str, Any]:
    """Extra gdal.Warp options: the local frame as the target, for a local site."""
    return {"dstSRS": srs(site)} if is_local(site) else {}


def local_source(path: Any, site: dict[str, Any], out_dir: Any) -> str:
    """For a local site, a warped VRT of `path` in the local frame (for checks that sample the
    source at frame coordinates); otherwise `path` itself."""
    if not is_local(site):
        return str(path)
    from pathlib import Path

    from osgeo import gdal

    target = Path(out_dir) / f"{Path(str(path)).stem}_local.vrt"
    if not target.exists():
        gdal.Warp(str(target), str(path), format="VRT", dstSRS=srs(site), resampleAlg="cubic")
    return str(target)
