"""Command line entry point: `uv run roverloom --help`."""

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from roverloom import BACKEND_NAME, MODEL_VERSION
from roverloom.agents import Agent, create_agent
from roverloom.agents.sdk import describe_skills
from roverloom.agents.skills import SkillPlanAgent, load_plan
from roverloom.contract import ContractError, JsonDict, dump_json, repo_root
from roverloom.evaluate import evaluate_run
from roverloom.replay import Replay
from roverloom.rover_builder import list_designs, load_rover_document
from roverloom.runlog import LoadedRun, load_run, logs_digest
from roverloom.runner import Comparison, compare_agents, run_mission
from roverloom.session import MissionSession
from roverloom.world import SIM_STEP_S, list_practice_scenarios, load_scenario

DEFAULT_AGENTS = "stop,waypoint,reactive,replanner"


def _runs_dir() -> Path:
    return repo_root() / "runs"


def _print_metrics(metrics: JsonDict) -> None:
    for key, value in metrics.items():
        print(f"  {key:<22} {value}")


def _print_table(rows: Sequence[JsonDict]) -> None:
    columns = [
        ("scenario", "scenario"),
        ("agent", "agent"),
        ("runs", "runs"),
        ("success_rate", "success"),
        ("mean_score", "score"),
        ("mean_success_time_s", "time_s"),
        ("mean_distance_m", "dist_m"),
        ("mean_success_energy_wh", "energy_Wh"),
        ("mean_collisions", "collisions"),
        ("fault_recovery_rate", "recovery"),
    ]
    table = [[label for _, label in columns]]
    table += [
        ["-" if row.get(key) is None else str(row.get(key)) for key, _ in columns] for row in rows
    ]
    widths = [max(len(line[i]) for line in table) for i in range(len(columns))]
    for line in table:
        print("  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)))


def _parse_seeds(text: str) -> list[int]:
    try:
        seeds = [int(part) for part in text.split(",") if part.strip()]
    except ValueError as error:
        raise ContractError(f"invalid seeds: {text}") from error
    if not seeds or min(seeds) < 0:
        raise ContractError(f"seeds must be non-negative integers: {text}")
    return seeds


def _write_report(comparison: Comparison, out_dir: Path) -> Path:
    from roverloom.preview.report import write_report

    runs = [
        (key, load_run(result.directory, trusted=True))
        for key, result in comparison.results.items()
    ]
    return write_report(comparison.rows, runs, out_dir / "report.html")


def cmd_run(args: argparse.Namespace) -> int:
    scenario = load_scenario(args.scenario, rover=args.rover)
    agent: Agent = (
        SkillPlanAgent(load_plan(Path(args.plan))) if args.plan else create_agent(args.agent)
    )
    seed = scenario.seed if args.seed is None else args.seed
    out = (
        Path(args.out)
        if args.out
        else (
            _runs_dir()
            / scenario.scenario_id
            / args.agent.replace(":", "_").replace("/", "_")
            / f"seed-{seed}"
        )
    )
    result = run_mission(scenario, agent, args.agent, out, seed, args.overwrite)
    print(f"Run saved: {result.directory}")
    print(f"Digest:    {logs_digest(result.manifest)}")
    _print_metrics(result.metrics.to_dict())
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    scenarios = args.scenarios.split(",")
    agents = args.agents.split(",")
    out = Path(args.out) if args.out else _runs_dir() / "compare"
    comparison = compare_agents(scenarios, agents, _parse_seeds(args.seeds), out, args.overwrite)
    _print_table(comparison.rows)
    (out / "comparison.json").write_text(
        dump_json(comparison.rows) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"\nReport: {_write_report(comparison, out)}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    out = Path(args.out) if args.out else _runs_dir() / "demo"
    print(f"Running sample missions on the {BACKEND_NAME} preview model.")
    print("This model is an approximation for games and early research, not validated physics.\n")
    comparison = compare_agents(
        list_practice_scenarios(), DEFAULT_AGENTS.split(","), [1, 2, 3], out, overwrite=True
    )
    _print_table(comparison.rows)
    (out / "comparison.json").write_text(
        dump_json(comparison.rows) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"\nOpen this report in a browser: {_write_report(comparison, out)}")
    print("Drive it yourself: uv run roverloom play")
    return 0


def _describe_replay(run: LoadedRun, at: float | None) -> None:
    replay = Replay(run)
    manifest = run.manifest
    print(f"Scenario {manifest['scenario_id']}, agent {manifest['agent']}, seed {manifest['seed']}")
    print(f"Model {manifest['model_version']}, duration {replay.duration_s:.1f} s")
    print("Events:")
    for event in run.events:
        print(f"  {event['time_s']:8.1f} s  {event['type']:<18} {dump_json(event['data'])}")
    if at is not None:
        frame = replay.frame_at(at)
        pose = frame.pose
        print(
            f"At {frame.time_s:.1f} s: x={pose.x_m:.2f} y={pose.y_m:.2f} yaw={pose.yaw_rad:.3f} "
            f"battery={frame.battery_fraction:.3f} targets={frame.targets_reached} "
            f"failed_wheels={list(frame.failed_wheels)}"
        )


def cmd_replay(args: argparse.Namespace) -> int:
    run = load_run(Path(args.run))
    _describe_replay(run, args.at)
    if args.html:
        from roverloom.preview.report import write_report

        key = (run.manifest["scenario_id"], run.manifest["agent"], run.manifest["seed"])
        path = write_report([], [(key, run)], Path(args.html))
        print(f"Viewer: {path}")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    metrics = evaluate_run(load_run(Path(args.run)))
    print(dump_json(metrics.to_dict()))
    return 0


def cmd_play(args: argparse.Namespace) -> int:
    from roverloom.preview.server import serve

    scenario = load_scenario(args.scenario, rover=args.rover)
    out = Path(args.out) if args.out else _runs_dir() / "live"
    serve(
        scenario,
        args.agent,
        args.seed,
        args.port,
        out,
        not args.no_browser,
        args.speed,
        args.scenario,
        args.rover,
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    names = args.scenarios or list_practice_scenarios()
    for name in names:
        scenario = load_scenario(name)
        print(f"OK {scenario.scenario_id}: {len(scenario.terrain.rocks)} rocks")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    scenario = load_scenario(args.scenario)
    print(f"Model {MODEL_VERSION}, scenario {scenario.scenario_id}, {args.steps} steps maximum")
    for name in args.agents.split(","):
        session = MissionSession(scenario, {"agent": create_agent(name)}, "agent")
        started = time.perf_counter()
        while not session.mission.finished and session.step_index < args.steps:
            session.step()
        elapsed = time.perf_counter() - started
        rate = session.step_index / elapsed if elapsed > 0 else 0.0
        print(
            f"  {name:<12} {session.step_index:>6} steps in {elapsed:7.3f} s = {rate:9.0f} steps/s "
            f"({rate * SIM_STEP_S:7.1f} x real time)"
        )
    return 0


def cmd_rover(args: argparse.Namespace) -> int:
    names = args.designs or list_designs()
    rows = []
    for name in names:
        rover = load_rover_document(name)
        report = rover["design_report"]
        rows.append(
            {
                "rover": rover["rover_id"],
                "wheels": len(rover["wheels"]),
                "mass_kg": report["mass_kg"],
                "cost": report["cost"],
                "speed_mps": rover["max_speed_mps"],
                "climb": rover["max_climb_slope"],
                "soil_scale": rover["soil_slip_scale"],
                "idle_w": rover["idle_power_w"],
                "solar_w": rover["solar_panel_w"],
                "rtg_w": rover["rtg_w"],
                "range_m": rover["range_sensor"]["max_range_m"],
                "beams": len(rover["range_sensor"]["bearings_rad"]),
                "period_s": rover["control_period_s"],
                "arm": rover["has_sample_tool"],
            }
        )
    fields = list(rows[0])
    table = [fields] + [[str(row[f]) for f in fields] for row in rows]
    widths = [max(len(line[i]) for line in table) for i in range(len(fields))]
    for line in table:
        print("  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)))
    print("\nSimplified game model. Not a validated wheel, soil, or power model.")
    return 0


def cmd_skills(args: argparse.Namespace) -> int:
    print(json.dumps(describe_skills(), indent=2))
    return 0


def cmd_league(args: argparse.Namespace) -> int:
    from roverloom.league import (
        format_board,
        load_benchmark,
        load_seeds_file,
        lock_benchmark,
        run_league,
    )

    if args.action == "lock":
        pins = lock_benchmark(args.benchmark)
        print(f"Locked {len(pins)} pins in {args.benchmark}. Increase its version if they changed.")
        return 0
    benchmark = load_benchmark(args.benchmark)
    print(f"Benchmark {benchmark['benchmark_id']} {benchmark['version']} matches this code.")
    if args.action == "verify":
        return 0
    if args.action == "show":
        board = json.loads((Path(args.out) / "leaderboard.json").read_text(encoding="utf-8"))
        print(format_board(board["board"]))
        return 0
    seeds = load_seeds_file(Path(args.seeds_file)) if args.seeds_file else None
    leagues = (
        [args.league] if args.league != "all" else ["autonomy", "rover_design", "full_mission"]
    )
    root = Path(args.out) if args.out else _runs_dir() / "league"
    for league in leagues:
        result = run_league(
            benchmark,
            league,
            root / league,
            seeds,
            extra_agents=args.add_agent,
            extra_rovers=args.add_rover,
            overwrite=True,
        )
        print(f"\n{league} ({len(result.runs)} runs), saved to {result.out_dir}")
        print(format_board(result.board))
    return 0


def cmd_competition(args: argparse.Namespace) -> int:
    from roverloom.competition import mock_submission

    reference = (
        Path(args.reference) if args.reference else repo_root() / "competition" / "reference_data"
    )
    out = Path(args.out) if args.out else _runs_dir() / "competition"
    print("Local mock only. NOT A SANDBOX: the submission runs with your permissions.")
    print(json.dumps(mock_submission(Path(args.submission), reference, out), indent=2))
    print(f"Saved: {out / 'output' / 'scores.json'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roverloom",
        description="Roverloom lightweight mission core. Not the future Unreal renderer.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    demo = commands.add_parser("demo", help="run sample missions and write a comparison report")
    demo.add_argument("--out")
    demo.set_defaults(func=cmd_demo)

    run = commands.add_parser("run", help="run one mission")
    run.add_argument("--scenario", default="demo_traverse")
    run.add_argument("--agent", default="replanner", help="built-in name or path.py:ClassName")
    run.add_argument("--rover", help="rover name or design file; replaces the scenario's rover")
    run.add_argument("--plan", help="skill plan JSON, used with --agent skill-plan")
    run.add_argument("--seed", type=int)
    run.add_argument("--out")
    run.add_argument("--overwrite", action="store_true")
    run.set_defaults(func=cmd_run)

    compare = commands.add_parser("compare", help="compare agents over scenarios and seeds")
    compare.add_argument("--scenarios", default="demo_traverse")
    compare.add_argument("--agents", default=DEFAULT_AGENTS)
    compare.add_argument("--seeds", default="1,2,3")
    compare.add_argument("--out")
    compare.add_argument("--overwrite", action="store_true")
    compare.set_defaults(func=cmd_compare)

    replay = commands.add_parser("replay", help="check a run and print or view its history")
    replay.add_argument("run")
    replay.add_argument("--at", type=float, help="print the state at this time")
    replay.add_argument("--html", help="write a self-contained viewer to this file")
    replay.set_defaults(func=cmd_replay)

    score = commands.add_parser("score", help="recompute metrics from a run's logs")
    score.add_argument("run")
    score.set_defaults(func=cmd_score)

    play = commands.add_parser("play", help="drive manually or watch an agent in a browser")
    play.add_argument("--scenario", default="demo_traverse")
    play.add_argument(
        "--agent", default="replanner", help="agent available through the mode switch"
    )
    play.add_argument("--rover", help="rover name or design file")
    play.add_argument("--seed", type=int)
    play.add_argument("--port", type=int, default=8770)
    play.add_argument("--speed", type=float, default=4.0, help="simulation speed multiplier")
    play.add_argument("--out")
    play.add_argument("--no-browser", action="store_true")
    play.set_defaults(func=cmd_play)

    validate_parser = commands.add_parser("validate", help="check scenario files")
    validate_parser.add_argument("scenarios", nargs="*")
    validate_parser.set_defaults(func=cmd_validate)

    benchmark = commands.add_parser("benchmark", help="measure simulation speed on this machine")
    benchmark.add_argument("--scenario", default="demo_traverse")
    benchmark.add_argument("--agents", default=DEFAULT_AGENTS)
    benchmark.add_argument("--steps", type=int, default=3000)
    benchmark.set_defaults(func=cmd_benchmark)

    rover = commands.add_parser("rover", help="compile rover designs and compare their budgets")
    rover.add_argument("designs", nargs="*", help="names or design files; all standard by default")
    rover.set_defaults(func=cmd_rover)

    skills = commands.add_parser("skills", help="print the skill contract as JSON")
    skills.set_defaults(func=cmd_skills)

    league = commands.add_parser("league", help="run or check offline leagues")
    league.add_argument("action", choices=["run", "verify", "lock", "show"])
    league.add_argument("--benchmark", default="roverloom-bench-v1")
    league.add_argument(
        "--league", default="all", choices=["all", "autonomy", "rover_design", "full_mission"]
    )
    league.add_argument("--seeds-file", help="private seeds, kept outside the repository")
    league.add_argument("--add-agent", action="append", default=[], help="repeatable")
    league.add_argument("--add-rover", action="append", default=[], help="repeatable")
    league.add_argument("--out")
    league.set_defaults(func=cmd_league)

    competition = commands.add_parser("competition", help="local mock of a Codabench submission")
    competition.add_argument("submission", help="submission directory or zip")
    competition.add_argument("--reference")
    competition.add_argument("--out")
    competition.set_defaults(func=cmd_competition)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result: int = args.func(args)
        return result
    except ContractError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        # The reader of the output went away, as with `| head`. Nothing is wrong.
        sys.stderr.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
