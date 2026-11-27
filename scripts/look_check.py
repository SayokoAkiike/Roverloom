"""Look check: race each stage hands-free, record it, and put the game's own screenshots on one sheet.

Run on the Mac, from the repository root (Pillow is fetched for this run only):

    uv run --project python --with pillow python scripts/look_check.py --ue-root "/Users/Shared/Epic Games/UE_5.8" --build

For each course, scripts/play_3d.py --look races it with the pursuit agent and three rivals, records the screen
(race.mov in the run directory) and has the game save a screenshot every 6 s, two from the chase camera and then one
from the mast camera. Then this script lays every screenshot on one contact sheet with the course and time on each,
saves it as runs/look/look-<time>.jpg, and opens it. Send that one file to check the looks. These are game screenshots
of real runs; nothing is retouched.
"""

# ruff: noqa: E501  (long command lines and prose read better unwrapped)

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "first-3d"
DEFAULT_COURSES = ["ghost_forest", "lyot_slalom"]


def race(course: str, seconds: int, ue_root: str, build: bool) -> Path | None:
    before = set(RUNS.glob("run-*")) if RUNS.exists() else set()
    command = [sys.executable, str(ROOT / "scripts" / "play_3d.py"), "--race", "--course", course]
    command += ["--look", str(seconds), "--npcs", "3", "--ue-root", ue_root]
    if build:
        command.append("--build")
    print(f"\n== {course}: racing {seconds} s hands-free", flush=True)
    subprocess.run(command, cwd=ROOT, check=False)
    new = sorted(set(RUNS.glob("run-*")) - before, key=lambda p: p.stat().st_mtime)
    return new[-1] if new else None


def sheet(shots: list[tuple[str, Path]], target: Path, width: int = 640) -> None:
    from PIL import Image, ImageDraw

    height = width * 9 // 16
    cols = 3
    rows = (len(shots) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * width, rows * height + 28), (0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    for i, (label, path) in enumerate(shots):
        image = Image.open(path).convert("RGB").resize((width, height))
        x, y = (i % cols) * width, (i // cols) * height
        canvas.paste(image, (x, y))
        draw.rectangle([x + 6, y + 6, x + 8 + 7 * len(label), y + 24], fill=(0, 0, 0))
        draw.text((x + 10, y + 9), label, fill=(255, 255, 255))
    draw.text((8, rows * height + 8), "Game screenshots (Unreal), look check", fill=(255, 255, 255))
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, quality=85)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--ue-root", required=True)
    parser.add_argument("--build", action="store_true", help="build the C++ before the first race")
    parser.add_argument("--courses", nargs="+", default=DEFAULT_COURSES)
    parser.add_argument("--seconds", type=int, default=70, help="race time per course")
    args = parser.parse_args()
    try:
        import PIL  # noqa: F401
    except ImportError:
        print(
            "Run with Pillow: uv run --project python --with pillow python scripts/look_check.py ..."
        )
        return 2
    shots: list[tuple[str, Path]] = []
    runs = []
    for i, course in enumerate(args.courses):
        run = race(course, args.seconds, args.ue_root, args.build and i == 0)
        if run is None:
            print(f"{course}: no run directory was made; see the output above")
            continue
        runs.append(run)
        found = sorted(run.glob("look-*.png"))
        print(f"{course}: {len(found)} screenshots in {run}")
        for path in found:
            parts = path.stem.split("-")  # look-01-t002-chase
            shots.append((f"{course}  {parts[2][1:].lstrip('0') or '0'} s  {parts[3]}", path))
    if not shots:
        print("No screenshots were saved. Check unreal.log in the run directories for 'Look shot'.")
        return 1
    target = ROOT / "runs" / "look" / f"look-{time.strftime('%Y%m%d-%H%M%S')}.jpg"
    sheet(shots, target)
    print(f"\nContact sheet: {target}")
    for run in runs:
        movie = run / "race.mov"
        if movie.exists():
            print(f"Video: {movie}")
    subprocess.run(["open", str(target)], check=False)
    print("Send the contact sheet to check the looks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
