"""Launch the first 3D mission on one Mac using an existing Unreal installation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "g3_reach_target"
PORT = 8100


def commands(engine: Path, out: Path) -> tuple[list[str], list[str], list[str]]:
    project = ROOT / "unreal" / "Roverloom.uproject"
    build = [
        str(engine / "Engine/Build/BatchFiles/Mac/Build.sh"),
        "RoverloomEditor",
        "Mac",
        "Development",
        f"-project={project}",
        "-WaitMutex",
    ]
    game = [
        str(engine / "Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"),
        str(project),
        "/Engine/Maps/Entry?game=/Script/Roverloom.RoverPlaygroundGameMode",
        "-game",
        "-windowed",
        "-ResX=1280",
        "-ResY=720",
        "-RoverDrive=play-g3",
        "-RoverTutorial",
        "-RoverModel=greybox",
        "-RoverProfile=dev",
        "-RoverBench=150",
        "-nosplash",
        "-stdout",
        "-FullStdOutLogOutput",
    ]
    link = [
        sys.executable,
        "-m",
        "roverloom.unreal_link",
        "--scenario",
        SCENARIO,
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
        "--wait",
        "120",
        "--linger",
        "8",
        "--out",
        str(out),
    ]
    return build, game, link


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def supervise(game: list[str], link: list[str], out: Path, timeout: float = 300) -> int:
    """Own only these child processes; report success only from this run's Mission Core."""
    children: list[subprocess.Popen[bytes]] = []
    try:
        with (
            (out / "unreal.log").open("wb") as game_log,
            (out / "link.log").open("wb") as link_log,
        ):
            children.append(subprocess.Popen(game, stdout=game_log, stderr=subprocess.STDOUT))
            children.append(subprocess.Popen(link, stdout=link_log, stderr=subprocess.STDOUT))
            deadline = time.monotonic() + timeout
            while children[1].poll() is None:
                if children[0].poll() is not None:
                    raise RuntimeError("Unreal closed before the mission result was saved.")
                if time.monotonic() >= deadline:
                    raise RuntimeError("Mission timed out; inspect unreal.log and link.log.")
                time.sleep(0.1)
            if children[1].returncode != 0:
                raise RuntimeError("Mission link failed; inspect link.log.")
            final = json.loads((out / "final_state.json").read_text(encoding="utf-8"))
            if final.get("scenario") != SCENARIO:
                raise RuntimeError("Unexpected scenario in the mission result.")
            print(json.dumps(final, indent=2))
            return (
                0 if final.get("outcome") == "success" and final.get("targets_reached") == 1 else 1
            )
    finally:
        for child in reversed(children):
            stop(child)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ue-root", type=Path, default=os.environ.get("UE_ROOT"))
    parser.add_argument("--build", action="store_true", help="build the editor target first")
    parser.add_argument("--check", action="store_true", help="preflight only; launch nothing")
    args = parser.parse_args(argv)
    try:
        if platform.system() != "Darwin":
            raise RuntimeError("This first launcher targets macOS. Unreal playtesting is pending.")
        if not args.ue_root:
            raise RuntimeError(
                "Pass --ue-root with your installed UE 5.8.4 directory, or set UE_ROOT."
            )
        if importlib.util.find_spec("roverloom") is None:
            raise RuntimeError(
                "Run through uv: uv run --project python python scripts/play_3d.py ..."
            )
        engine = Path(args.ue_root).expanduser().resolve()
        build, game, _ = commands(engine, ROOT / "runs" / "first-3d")
        for executable in [game[0], *([build[0]] if args.build else [])]:
            if not os.access(executable, os.X_OK):
                raise RuntimeError(f"Missing or non-executable Unreal tool: {executable}")
        # Refuse another listener instead of connecting the Mission Core to an unrelated process.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", PORT))
        print(
            "Preflight passed: tools found and loopback port 8100 available.",
            flush=True,
        )
        if args.check:
            return 0
        if args.build:
            subprocess.run(build, check=True, cwd=ROOT / "unreal")
        parent = ROOT / "runs" / "first-3d"
        parent.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix="run-", dir=parent))
        _, game, link = commands(engine, out)
        print(f"Logs and result: {out}", flush=True)
        print(
            "Click the game window. W/S drive, A/D turn, C camera. Reach the green target ahead.",
            flush=True,
        )
        print(
            "The Python verdict appears on the HUD. "
            "The window closes after the result. Ctrl+C cancels.",
            flush=True,
        )
        return supervise(game, link, out)
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Cannot complete the 3D mission: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
