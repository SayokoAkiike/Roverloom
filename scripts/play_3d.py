"""Launch the first 3D mission on one Mac using an existing Unreal installation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
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


def supervise(
    game: list[str],
    link: list[str],
    out: Path,
    timeout: float = 420,
    scenario: str = SCENARIO,
) -> int:
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
            if final.get("scenario") != scenario:
                raise RuntimeError("Unexpected scenario in the mission result.")
            print(json.dumps(final, indent=2))
            need = {"rally": 4, "race": final.get("targets_total")}.get(scenario, 1)
            return (
                0
                if final.get("outcome") == "success" and final.get("targets_reached") == need
                else 1
            )
    finally:
        for child in reversed(children):
            stop(child)


# Stones per stage, in percent of the Gale scatter. Amazonis is a dust-mantled plain with few rocks.
STAGE_ROCKS = {"gale": 100, "noctis": 70, "amazonis": 25, "lyot": 40, "olympia": 10}
# A stage's own light when --light is not given: Lyot in northern winter, the sun low in the south,
# the polar dunes under a pale, low polar sun (RoverPlaygroundGameMode's light presets).
STAGE_LIGHT = {"lyot": "winter", "olympia": "polar"}


def stage_level(name: str) -> tuple[str, Path] | None:
    """The Unreal level and its .umap for a real-terrain stage (scripts/terrain/sites.json)."""
    if name == "generated":
        return None
    sites = json.loads((ROOT / "scripts" / "terrain" / "sites.json").read_text(encoding="utf-8"))
    level = sites[name]["level"]
    return level, ROOT / "unreal" / "Content" / (level.removeprefix("/Game/") + ".umap")


def write_course(out: Path, course: str) -> None:
    """Unreal reads the course before Python connects, so write it before launching."""
    from roverloom.contract import dump_json
    from roverloom.race import COURSES

    (out / "course.json").write_text(dump_json(COURSES[course].document()) + "\n", encoding="utf-8")


def start_recording(out: Path, seconds: int) -> subprocess.Popen[bytes]:
    """macOS screencapture video. Needs Screen Recording permission for the terminal."""
    movie = out / "race.mov"
    print(f"Recording the screen for {seconds} s to {movie}", flush=True)
    return subprocess.Popen(["screencapture", "-v", "-V", str(seconds), "-x", str(movie)])


def print_diagnosis(out: Path) -> None:
    from roverloom.race_diagnose import report

    try:
        print("\n===== Contact report (paste this) =====\n" + report(out), flush=True)
    except (OSError, ValueError) as error:
        print(f"No contact report: {error}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ue-root", type=Path, default=os.environ.get("UE_ROOT"))
    parser.add_argument("--build", action="store_true", help="build the editor target first")
    parser.add_argument("--check", action="store_true", help="preflight only; launch nothing")
    parser.add_argument("--rally", action="store_true")
    parser.add_argument("--garage", type=Path)
    parser.add_argument("--ghost", type=Path)
    parser.add_argument("--difficulty", choices=("easy", "standard", "hard"), default="easy")
    parser.add_argument("--seed", type=int, default=1)
    race = parser.add_argument_group("race (experimental kart-style race, docs/race.md)")
    race.add_argument("--race", action="store_true", help="lap race against NPCs and ghosts")
    race.add_argument(
        "--course", default="crater_loop", help="crater_loop, dune_sprint, gale_sprint, gale_links"
    )
    race.add_argument("--laps", type=int)
    race.add_argument("--npcs", type=int, default=3)
    race.add_argument("--ghosts", type=int, default=0, help="add your best saved runs as ghosts")
    race.add_argument("--name", default="You")
    race.add_argument("--agent", default="none", help="none, pursuit, cap or external (Advanced)")
    race.add_argument(
        "--map",
        choices=("generated", "gale", "noctis", "amazonis", "lyot", "olympia"),
        default="generated",
    )
    race.add_argument(
        "--light",
        help="noon, afternoon, sunset, winter, polar or default "
        "(default: the stage's own, else afternoon)",
    )
    race.add_argument("--res", default="1280x720")
    race.add_argument("--profile", choices=("dev", "capture"), default="dev")
    race.add_argument("--demo", action="store_true", help="hands-free: the pursuit agent drives")
    race.add_argument("--record", type=int, metavar="SECONDS", help="record the screen (macOS)")
    race.add_argument(
        "--diagnose",
        action="store_true",
        help="contact check: the agent drives at 35%% so rivals overtake, the screen is "
        "recorded, the race stops after 80 s, and a report is printed",
    )
    args = parser.parse_args(argv)
    if args.diagnose:
        args.race = args.demo = True
        args.difficulty = "hard"
        args.npcs = max(args.npcs, 4)
        args.record = args.record or 150
    if args.demo and args.agent == "none":
        args.agent = "pursuit"
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
        if args.race and args.rally:
            raise RuntimeError("choose --rally or --race")
        if args.ghost and not args.rally:
            raise RuntimeError("--ghost requires --rally; races use --ghosts N")
        if args.garage and not (args.rally or args.race):
            raise RuntimeError("--garage requires --rally or --race")
        if args.race:
            from roverloom.race import COURSES
            from roverloom.rally import load_garage as load_race_garage

            if args.course not in COURSES:
                raise RuntimeError(f"unknown course; choose {', '.join(COURSES)}")
            ground = COURSES[args.course].ground
            if ground != "generated":
                args.map = ground  # Courses routed on a real site race on that site's level
            args.light = args.light or STAGE_LIGHT.get(args.map, "afternoon")
            level = stage_level(args.map)
            if level and not level[1].exists():
                raise RuntimeError(
                    f"The {args.map} level is not built on this Mac yet."
                    " Run once (about an hour):\n"
                    "  uv run --project python python scripts/setup_gale.py"
                    f' --site {args.map} --ue-root "<your UE_5.8>"\n'
                    "or use --course crater_loop on the generated ground (docs/race.md)."
                )
            race_design = load_race_garage(args.garage)
        if args.rally:
            from roverloom.rally import Ghost, load_garage

            design = load_garage(args.garage)
            if args.seed < 0:
                raise ValueError("seed must be non-negative")
            if args.ghost:
                Ghost(args.ghost, args.difficulty, args.seed)
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
        if args.rally:
            from roverloom.rally import PAINTS

            game = [a for a in game if a not in ("-RoverTutorial", "-RoverBench=150")]
            game += [
                "-RoverRally",
                "-RoverBench=300",
                f"-RoverPaint={PAINTS[design['paint']]}",
            ]
            link = [
                sys.executable,
                "-m",
                "roverloom.rally_link",
                "--out",
                str(out),
                "--difficulty",
                args.difficulty,
                "--seed",
                str(args.seed),
            ]
            if args.garage:
                link += ["--garage", str(args.garage.resolve())]
            if args.ghost:
                link += ["--ghost", str(args.ghost.resolve())]
        if args.race:
            from roverloom.rally import PAINTS as RACE_PAINTS

            width, height = args.res.lower().split("x")
            game = [a for a in game if a not in ("-RoverTutorial", "-RoverBench=150")]
            game = [a for a in game if not a.startswith(("-ResX=", "-ResY=", "-RoverProfile="))]
            # The V2 rover with PBR materials if imported; otherwise the pawn uses greybox.
            game = [a for a in game if a != "-RoverModel=greybox"]
            level = stage_level(args.map)
            if level:
                game[2] = f"{level[0]}?game=/Script/Roverloom.RoverPlaygroundGameMode"
            course = COURSES[args.course]
            if course.start_point:
                sx, sy = course.start
                ax, ay = course.path[1]
                yaw = -math.degrees(
                    math.atan2(ay - sy, ax - sx)
                )  # Unreal yaw: the site's y is Unreal's -y
                game += [f"-RoverStartM={sx},{sy}", f"-RoverStartYawDeg={yaw:.1f}"]
            game += [f"-RoverRockScale={STAGE_ROCKS.get(args.map, 100)}"]
            game += [
                "-RoverRally",
                "-RoverRace",
                f"-RoverCourseFile={out / 'course.json'}",
                "-RoverBench=900",
                f"-RoverPaint={RACE_PAINTS[race_design['paint']]}",
                f"-RoverLight={args.light}",
                f"-RoverProfile={args.profile}",
                f"-ResX={int(width)}",
                f"-ResY={int(height)}",
            ]
            link = [sys.executable, "-m", "roverloom.race_cli", "link", "--out", str(out)]
            link += [
                "--course",
                args.course,
                "--npcs",
                str(args.npcs),
                "--ghosts",
                str(args.ghosts),
            ]
            link += ["--difficulty", args.difficulty, "--seed", str(args.seed), "--name", args.name]
            link += [
                "--agent",
                args.agent,
                "--board",
                str(ROOT / "runs" / "race" / "leaderboard.json"),
            ]
            if args.laps:
                link += ["--laps", str(args.laps)]
            if args.diagnose:
                link += ["--agent-speed", "0.35", "--stop-after", "80"]
                game += [f"-RoverRaceDiagnose={out}"]
            if args.garage:
                link += ["--garage", str(args.garage.resolve())]
            write_course(out, args.course)
        print(f"Logs and result: {out}", flush=True)
        print(
            "Click the window: W/S drive, A/D turn, C camera. "
            "Follow the gates; SPACE boosts in rally.",
            flush=True,
        )
        print(
            "The Python verdict appears on the HUD. "
            "The window closes after the result. Ctrl+C cancels.",
            flush=True,
        )
        if args.race:
            mode = f"agent '{args.agent}' drives" if args.agent != "none" else "you drive"
            print(
                f"RACE: {args.course}, {args.npcs} NPCs, {args.ghosts} ghosts, {mode}.", flush=True
            )
            print(
                "W/S drive, A/D turn, Q/E speed level, SPACE boost, C camera, R rescue (+30 s).",
                flush=True,
            )
            if args.agent == "external":
                print("Start your agent now: python -m roverloom.race_agent_example", flush=True)
        recorder = start_recording(out, args.record) if args.record else None
        try:
            scenario = "rally" if args.rally else "race" if args.race else SCENARIO
            return supervise(game, link, out, timeout=1200 if args.race else 420, scenario=scenario)
        finally:
            if recorder:
                stop(recorder)
            if args.diagnose:
                print_diagnosis(out)
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Cannot complete the 3D mission: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
