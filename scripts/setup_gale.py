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
    # Imported assets, not the downloaded files beside them: polyhaven_fetch.py writes the .jpg and .fbx
    # into the same folders, so a folder alone does not mean the import ran.
    (
        "import_polyhaven",
        CONTENT / "PolyHaven" / "rocks_ground_03" / "rocks_ground_03_arm_2k.uasset",
    ),
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
            "far field (200 km, MOLA or HRSC blend)",
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


def polyhaven_complete() -> bool:
    """True when downloaded.json lists a file for every asset polyhaven_fetch.py asks for."""
    log = CONTENT / "PolyHaven" / "downloaded.json"
    if not log.exists():
        return False
    sys.path.insert(0, str(ROOT / "scripts" / "assets"))
    import polyhaven_fetch

    text = log.read_text(encoding="utf-8")
    return all(f'"{name}/' in text for name in [*polyhaven_fetch.MODELS, *polyhaven_fetch.TEXTURES])


def ambientcg_complete() -> bool:
    """True when downloaded.json lists every material ambientcg_fetch.py asks for."""
    log = CONTENT / "AmbientCG" / "downloaded.json"
    if not log.exists():
        return False
    sys.path.insert(0, str(ROOT / "scripts" / "assets"))
    import ambientcg_fetch

    have = {entry["asset"] for entry in json.loads(log.read_text(encoding="utf-8"))}
    return set(ambientcg_fetch.MATERIALS) <= have


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
    parser.add_argument(
        "--materials-only",
        action="store_true",
        help="rebuild only the sites' ground materials (after a change to build_gale_material.py)",
    )
    parser.add_argument(
        "--far-only",
        action="store_true",
        help="recut the far field and rebuild the level (after a change to mola_far.py or sites.json)",
    )
    parser.add_argument(
        "--staged-backdrop",
        action="store_true",
        help="with --far-only: draw the region's landmarks closer beyond the walls (staging, not a real view)",
    )
    args = parser.parse_args()
    if not args.ue_root:
        print("Pass --ue-root with your UE 5.8 directory.", file=sys.stderr)
        return 2
    ue_root = Path(args.ue_root).expanduser()
    sites = list(SITES) if args.site == "all" else [args.site]
    if args.materials_only:
        for site in sites:
            editor(
                ue_root, "build_gale_material", site
            )  # rebuilt in place; the levels keep using it
        print(f"Ready: {', '.join(sites)} materials rebuilt.")
        return 0
    if args.far_only:
        python = gdal_python()
        if not python:
            print("GDAL for Python is missing: brew install gdal", file=sys.stderr)
            return 2
        staged = ["--staged"] if args.staged_backdrop else []
        for site in sites:
            run(
                [python, "scripts/terrain/mola_far.py", "--site", site, *staged],
                f"{site}: far field",
            )
            editor(ue_root, "build_gale_level", site)
        print(f"Ready: {', '.join(sites)} far fields and levels rebuilt.")
        return 0
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
        fetched = False
        if args.force or not polyhaven_complete():
            run(
                [sys.executable, "scripts/assets/polyhaven_fetch.py"],
                "Poly Haven rocks and textures",
            )
            fetched = True
        else:
            print("== Poly Haven: every listed asset is downloaded, skipped")
        if args.force or not ambientcg_complete():
            uv = shutil.which("uv")
            if not uv:
                print("uv is missing: https://docs.astral.sh/uv/", file=sys.stderr)
                return 2
            run(
                [
                    uv,
                    "run",
                    "--project",
                    "python",
                    "--with",
                    "pillow",
                    "python",
                    "scripts/assets/ambientcg_fetch.py",
                ],
                "ambientCG ground and rock materials",
            )
            fetched = True
        else:
            print("== ambientCG: every listed material is downloaded, skipped")
        # Once a step runs, every later Unreal step runs too: its output may have been built from
        # missing or older inputs (a material made before its textures were imported, for example).
        rerun = args.force or fetched
        for script, output in SHARED_STEPS:
            if output.exists() and not rerun:
                print(f"== Unreal: {script}: {output.name} exists, skipped")
                continue
            editor(ue_root, script)
            rerun = True
        # Rock collision for races. Not a cascade: levels and materials do not depend on it.
        marker = ROOT / "unreal" / "Saved" / "Roverloom" / "rock_collision.json"
        if marker.exists() and not rerun:
            print("== Unreal: build_rock_collision: rock_collision.json exists, skipped")
        else:
            editor(ue_root, "build_rock_collision")
        for site in sites:
            site_rerun = rerun
            for script, output in (
                ("build_gale_material", asset_file(SITES[site]["material"], ".uasset")),
                ("build_gale_level", asset_file(SITES[site]["level"], ".umap")),
            ):
                if output.exists() and not site_rerun:
                    print(f"== Unreal: {script} {site}: {output.name} exists, skipped")
                    continue
                editor(ue_root, script, site)
                site_rerun = True
        if not args.no_rover:
            rover(ue_root, args.force)
    except subprocess.CalledProcessError as error:
        print(f"\nA step failed (exit {error.returncode}); see its output above.", file=sys.stderr)
        return 1
    print(f"\nReady: {', '.join(sites)}. Courses: see docs/race.md (gale_*, noctis_*, amazonis_*).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
