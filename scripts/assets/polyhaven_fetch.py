"""Download a short, fixed list of CC0 assets from Poly Haven's public API, outside Git.

    python3 scripts/assets/polyhaven_fetch.py

Terms read on 2026-11-16: https://github.com/Poly-Haven/Public-API/blob/master/ToS.md (API use is free, including
commercial; calls must carry a User-Agent that names the software, which is "Roverloom") and
https://polyhaven.com/license (assets are CC0, with no credit required). Scraping is prohibited by the site's terms, so
this is a short list of named assets, one request per file, never a crawl. Files go to unreal/Content/Licensed/PolyHaven/,
which Git ignores. Record every addition in docs/assets-and-sources.md.
"""

# ruff: noqa: E501  (long prose lines in the docstring and log messages; wrapping them would not help the reader)

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from pathlib import Path

USER_AGENT = "Roverloom"
API = "https://api.polyhaven.com"
OUT = Path(__file__).resolve().parents[2] / "unreal/Content/Licensed/PolyHaven"

# Terrain layers, each used at two tiling scales. Maps: diffuse, GL normal, and ARM (ambient occlusion, roughness, metal).
TEXTURES = ["dry_ground_01", "dense_sand", "rock_boulder_cracked", "rocks_ground_03"]
TEXTURE_MAPS = ["Diffuse", "nor_gl", "arm"]
TEXTURE_SIZE = "2k"
# Scatter rocks, as FBX with their textures, at 1k.
MODELS = ["namaqualand_boulder_02", "namaqualand_boulder_04", "namaqualand_boulder_06", "rock_09"]
MODEL_SIZE = "1k"


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def save(url: str, target: Path, md5: str | None) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    data = get(url)
    if md5 and hashlib.md5(data).hexdigest() != md5:
        raise SystemExit(f"md5 mismatch: {url}")
    target.write_bytes(data)
    time.sleep(0.5)  # One request at a time, politely
    return {
        "url": url,
        "file": str(target.relative_to(OUT)),
        "bytes": len(data),
        "md5": hashlib.md5(data).hexdigest(),
    }


def main() -> None:
    log = []
    for asset in TEXTURES:
        files = json.loads(get(f"{API}/files/{asset}"))
        for kind in TEXTURE_MAPS:
            entry = files[kind][TEXTURE_SIZE]["jpg"]
            log.append(save(entry["url"], OUT / asset / Path(entry["url"]).name, entry.get("md5")))
    for asset in MODELS:
        files = json.loads(get(f"{API}/files/{asset}"))
        entry = files["fbx"][MODEL_SIZE]["fbx"]
        log.append(save(entry["url"], OUT / asset / Path(entry["url"]).name, entry.get("md5")))
        for relative, part in entry.get("include", {}).items():
            log.append(save(part["url"], OUT / asset / relative, part.get("md5")))
    (OUT / "downloaded.json").write_text(json.dumps(log, indent=2) + "\n")
    print(f"{len(log)} files, {sum(item['bytes'] for item in log) / 1e6:.1f} MB, to {OUT}")


if __name__ == "__main__":
    main()
