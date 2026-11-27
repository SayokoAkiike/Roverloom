"""Build the real-terrain stages on this Mac: Gale, Noctis Labyrinthus and Amazonis Planitia.

For each stage: terrain from HiRISE and MOLA, ground brightness from the HiRISE orthoimage (new
stages), rocks, materials, effects, the level, and once the V2 rover.

Everything it makes stays outside Git (unreal/Saved/ and unreal/Content/Licensed/). It runs the
existing steps in the order the results documents used (docs/results/gale-landscape/README.md),
and skips a step whose output already exists. From the repository root, with the editor closed:

    uv run --project python python scripts/setup_gale.py --ue-root "/Users/Shared/Epic Games/UE_5.8"
    uv run --project python python scripts/setup_gale.py --site all --ue-root "..."

Needs GDAL's Python bindings for the terrain step (`brew install gdal`), network access to USGS,
Poly Haven and (for the far field) the MOLA mosaic, and about an hour on the first run.
"""

# ruff: noqa: E501  (long command lines read better unwrapped)

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "unreal" / "Content" / "Licensed"
PROJECT = ROOT / "unreal" / "Roverloom.uproject"
SITES = {
    k: v
    for k, v in json.loads((ROOT / "scripts/terrain/sites.json").read_text()).items()
    if not k.startswith("_")
}
# Shared by every stage: rocks, their materials and the dust and rut effects live in the Gale folder
SHARED_STEPS = [
    ("import_polyhaven", CONTENT / "PolyHaven" / "rock_09"),
    ("build_rock_materials", CONTENT / "Gale" / "M_PHRock.uasset"),
    ("build_effect_materials", CONTENT / "Gale" / "M_DustParticle.uasset"),
]


def asset_file(path: str, suffix: str) -> Path:
    return ROOT / "unreal" / "Content" / (path.removeprefix("/Game/") + suffix)


def gdal_python() -> str | None:
    """A Python that can import GDAL: Homebrew's first, then whatever python3 is on PATH."""
    candidates = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "python3"]
    for exe in candidates:
        path = (
            shutil.which(exe) if not exe.startswith("/") else (exe if Path(exe).exists() else None)
        )
        if not path:
            continue
        check = subprocess.run(
            [path, "-c", "from osgeo import gdal; import numpy"], capture_output=True
        )
        if check.returncode == 0:
            return path
    return None


def run(command: list[str], what: str) -> None:
    print(f"\n== {what}\n   {' '.join(command)}", flush=True)
    subprocess.run(command, check=True, cwd=ROOT)


def terrain(python: str, site: str, force: bool) -> None:
    data = ROOT / "unreal" / "Saved" / "Terrain" / site
    pick = ["--site", site]
    steps = [
        (
            ["scripts/terrain/hirise_site.py", *pick, "--download"],
            data / f"{site}_site.r16",
            "HiRISE site (1 km)",
        ),
        (
            ["scripts/terrain/hirise_horizon.py", *pick],
            data / f"{site}_horizon.r16",
            "HiRISE horizon",
        ),
        (
            ["scripts/terrain/mola_far.py", *pick],
            data / f"{site}_far.r16",
            "MOLA far field (200 km)",
        ),
    ]
    if "ortho" in SITES[site]:
        steps.append(
            (
                ["scripts/terrain/hirise_albedo.py", *pick, "--download"],
                data / f"{site}_albedo.png",
                "HiRISE ground brightness",
            )
        )
    for args, output, what in steps:
        if output.exists() and not force:
            print(f"== {what}: {output.name} exists, skipped")
            continue
        run([python, *args], f"{site}: {what}")


def editor(ue_root: Path, script: str, *extra: str) -> None:
    exe = ue_root / "Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
    target = " ".join([str(ROOT / "scripts" / "unreal" / f"{script}.py"), *extra])
    run(
        [
            str(exe),
            str(PROJECT),
            "-run=pythonscript",
            f"-script={target}",
            "-unattended",
            "-nullrhi",
        ],
        f"Unreal: {script}",
    )


def rover(ue_root: Path, force: bool) -> None:
    meshes = CONTENT.parent / "Rover"
    if meshes.exists() and not force:
        print("== V2 rover: /Game/Rover exists, skipped")
    else:
        blender = shutil.which("blender") or "/Applications/Blender.app/Contents/MacOS/Blender"
        if not Path(blender).exists():
            print("== V2 rover: Blender not found, skipped. The race uses the greybox rover.")
            return
        out = ROOT / "unreal" / "Saved" / "RoverModel"
        run(
            [blender, "-b", "-P", "scripts/blender/build_rover.py", "--", "--out", str(out)],
            "V2 rover meshes",
        )
        editor(ue_root, "import_rover_meshes", str(out))
    editor(ue_root, "build_rover_materials")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--ue-root", type=Path, default=os.environ.get("UE_ROOT"), required=False)
    parser.add_argument("--site", choices=[*SITES, "all"], default="gale")
    parser.add_argument("--force", action="store_true", help="redo steps whose output exists")
    parser.add_argument("--no-rover", action="store_true", help="skip the V2 rover (needs Blender)")
    args = parser.parse_args()
    if not args.ue_root:
        print("Pass --ue-root with your UE 5.8 directory.", file=sys.stderr)
        return 2
    ue_root = Path(args.ue_root).expanduser()
    sites = list(SITES) if args.site == "all" else [args.site]
    try:
        python = gdal_python()
        if not python:
            print(
                "GDAL for Python is missing. Install it, then run this again:\n  brew install gdal",
                file=sys.stderr,
            )
            return 2
        for site in sites:
            terrain(python, site, args.force)
        if args.force or not (CONTENT / "PolyHaven" / "downloaded.json").exists():
            run(
                [sys.executable, "scripts/assets/polyhaven_fetch.py"],
                "Poly Haven rocks and textures",
            )
        else:
            print("== Poly Haven: downloaded.json exists, skipped")
        for script, output in SHARED_STEPS:
            if output.exists() and not args.force:
                print(f"== Unreal: {script}: {output.name} exists, skipped")
                continue
            editor(ue_root, script)
        for site in sites:
            for script, output in (
                ("build_gale_material", asset_file(SITES[site]["material"], ".uasset")),
                ("build_gale_level", asset_file(SITES[site]["level"], ".umap")),
            ):
                if output.exists() and not args.force:
                    print(f"== Unreal: {script} {site}: {output.name} exists, skipped")
                    continue
                editor(ue_root, script, site)
        if not args.no_rover:
            rover(ue_root, args.force)
    except subprocess.CalledProcessError as error:
        print(f"\nA step failed (exit {error.returncode}); see its output above.", file=sys.stderr)
        return 1
    print(f"\nReady: {', '.join(sites)}. Courses: see docs/race.md (gale_*, noctis_*, amazonis_*).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
