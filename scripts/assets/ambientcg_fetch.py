"""Download a short, fixed list of CC0 ground and rock materials from ambientCG, outside Git.

    uv run --project python --with pillow python scripts/assets/ambientcg_fetch.py

License read on 2026-11-27 at https://docs.ambientcg.com/license/: "All ambientCG assets are provided under the
Creative Commons CC0 1.0 Universal License", including in a video game, and credit is not required. The API page
(https://docs.ambientcg.com/api/) asks users to remember that one person runs the site, so this is a short list of named
assets, one request at a time, never a crawl. Record every addition in docs/assets-and-sources.md.

Each material is written in the layout import_polyhaven.py and build_gale_material.py already use, under
unreal/Content/Licensed/AmbientCG/<id>/ (Git ignores it): <id>_diff_2k.jpg (colour), <id>_nor_gl_2k.jpg (OpenGL normal)
and <id>_arm_2k.jpg (red: ambient occlusion, green: roughness, blue: metal, always 0), packed here from ambientCG's
separate maps.
"""

# ruff: noqa: E501  (long prose lines in the docstring and comments; wrapping them would not help the reader)

from __future__ import annotations

import hashlib
import io
import json
import time
import urllib.request
import zipfile
from pathlib import Path

USER_AGENT = "Roverloom"
OUT = Path(__file__).resolve().parents[2] / "unreal/Content/Licensed/AmbientCG"
SIZE = "2K-JPG"

# Chosen by eye from the previews for Mars-like ground; build_gale_material.py's LOOKS say which stage uses which.
MATERIALS = {
    "Ground079S": "sandy ground with gravel: regolith",
    "Ground098": "wind-rippled sand: drifts",
    "Ground099": "fine, dry, eroded dust: dust-mantled plains",
    "Ground110": "dark gravel and grit: basaltic gravel",
    "Rock029": "layered red-orange rock: Gale's mudstone outcrops",
    "Rock061": "layered brown rock: Noctis's layered floor",
    "Rock062": "cracked grey rock: lava-plain bedrock",
}


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=300) as response:
        data: bytes = response.read()
    return data


def pack_arm(occlusion: bytes | None, roughness: bytes) -> bytes:
    from PIL import (
        Image,
    )  # only when fetching, so that setup_gale.py can read MATERIALS without Pillow

    rough = Image.open(io.BytesIO(roughness)).convert("L")
    ao = (
        Image.open(io.BytesIO(occlusion)).convert("L").resize(rough.size)
        if occlusion
        else Image.new("L", rough.size, 255)
    )
    metal = Image.new("L", rough.size, 0)
    out = io.BytesIO()
    Image.merge("RGB", (ao, rough, metal)).save(out, "JPEG", quality=95)
    return out.getvalue()


def fetch(asset: str) -> list[dict[str, object]]:
    data = get(f"https://ambientcg.com/get?file={asset}_{SIZE}.zip")
    time.sleep(1.0)  # One request at a time, politely
    with zipfile.ZipFile(io.BytesIO(data)) as archive:

        def part(kind: str) -> bytes | None:
            name = f"{asset}_{SIZE}_{kind}.jpg"
            return archive.read(name) if name in archive.namelist() else None

        color, normal, rough = part("Color"), part("NormalGL"), part("Roughness")
        if not (color and normal and rough):
            raise SystemExit(f"{asset}: the zip lacks a colour, OpenGL normal or roughness map")
        files = {
            "diff": color,
            "nor_gl": normal,
            "arm": pack_arm(part("AmbientOcclusion"), rough),
        }
    folder = OUT / asset
    folder.mkdir(parents=True, exist_ok=True)
    log = []
    for kind, content in files.items():
        target = folder / f"{asset}_{kind}_2k.jpg"
        target.write_bytes(content)
        log.append(
            {
                "asset": asset,
                "url": f"https://ambientcg.com/a/{asset}",
                "file": str(target.relative_to(OUT)),
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return log


def main() -> None:
    log = []
    for asset, role in MATERIALS.items():
        print(f"ambientCG {asset} ({role})", flush=True)
        log += fetch(asset)
    (OUT / "downloaded.json").write_text(json.dumps(log, indent=2) + "\n")
    print(f"Wrote {len(log)} files under {OUT}")


if __name__ == "__main__":
    main()
