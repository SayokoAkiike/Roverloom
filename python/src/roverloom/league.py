"""Offline leagues: fixed, versioned batch evaluation, and local leaderboards.

Autonomy League: same rover, different agents.
Rover Design League: same agent, different rovers.
Full Mission League: both free. See docs/competition-rules.md.
"""

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import roverloom
from roverloom import MODEL_VERSION, SCORING_VERSION
from roverloom.agents import BUILTIN_AGENTS, create_agent
from roverloom.contract import (
    ContractError,
    JsonDict,
    dump_json,
    load_json_file,
    repo_root,
    sha256_bytes,
    validate,
)
from roverloom.evaluate import Metrics, aggregate
from roverloom.rover_builder import (
    BUILDER_VERSION,
    DESIGN_CLASSES,
    designs_dir,
    load_rover_document,
    require_design,
)
from roverloom.runner import run_mission
from roverloom.study import pareto_front
from roverloom.world import load_scenario, resolve_scenario_path

_CODE_PINNED = (
    "api.py",
    "command.py",
    "evaluate.py",
    "rover_builder.py",
    "science.py",
    "session.py",
    "sim.py",
    "world.py",
)

LEAGUES = ("autonomy", "rover_design", "full_mission")
_CSV_FIELDS = (
    "league",
    "scenario",
    "rover",
    "agent",
    "seed",
    "outcome",
    "success",
    "score",
    "science_value",
    "science_fraction",
    "returned_to_base",
    "mission_time_s",
    "distance_m",
    "energy_used_wh",
    "min_battery_fraction",
    "collisions",
    "watchdog_stops",
    "faults",
    "faults_recovered",
    "design_cost",
    "achievement",
)
_BOARD_FIELDS = (
    "rank",
    "entry",
    "runs",
    "mean_score",
    "mean_achievement",
    "success_rate",
    "mean_science_value",
    "mean_time_s",
    "mean_energy_wh",
    "mean_collisions",
    "fault_recovery_rate",
)


_DESIGN_FIELDS = (
    "design_class",
    "rank",
    "entry",
    "design_cost",
    "mass_kg",
    "mean_achievement",
    "robustness",
    "mean_score",
    "success_rate",
    "pareto",
)


def benchmark_path(name: str) -> Path:
    candidate = Path(name)
    if candidate.is_file():
        return candidate
    path = repo_root() / "benchmarks" / f"{name}.json"
    if not path.is_file():
        raise ContractError(f"benchmark not found: {name}")
    return path


def _document_pin(path: Path) -> str:
    return sha256_bytes(dump_json(load_json_file(path)).encode("utf-8"))


def _rover_path(name: str) -> Path:
    design = designs_dir() / f"{name}.json"
    return design if design.is_file() else repo_root() / "rovers" / f"{name}.json"


def _source_pin(paths: Sequence[Path]) -> str:
    joined = "\n".join(path.read_text(encoding="utf-8").replace("\r\n", "\n") for path in paths)
    return sha256_bytes(joined.encode("utf-8"))


def compute_pins(benchmark: JsonDict) -> dict[str, str]:
    """Hash everything a benchmark depends on, in forms that do not depend on line endings."""
    pins: dict[str, str] = {}
    package = Path(roverloom.__file__).parent
    # Agents import each other, so one agent's behavior can depend on any file in the package.
    agents_pin = _source_pin(sorted((package / "agents").glob("*.py")))
    pins["code:core"] = _source_pin([package / name for name in _CODE_PINNED])
    leagues = benchmark["leagues"]
    scenario_names = {name for league in leagues.values() for name in league["scenarios"]}
    for names in benchmark.get("tracks", {}).values():
        scenario_names.update(names)
    for name in sorted(scenario_names):
        path = resolve_scenario_path(name)
        document = load_json_file(path)
        pins[f"scenario:{name}"] = _document_pin(path)
        terrain_id = document["mission"]["terrain_id"]
        terrain = repo_root() / "scenarios" / "terrains" / f"{terrain_id}.json"
        pins[f"terrain:{terrain_id}"] = _document_pin(terrain)
    study_agents = benchmark.get("study", {}).get("agents", [])
    for league in leagues.values():
        for name in league["rovers"]:
            pins[f"rover:{name}"] = _document_pin(_rover_path(name))
        for name in [*league["agents"], *study_agents]:
            if name not in BUILTIN_AGENTS:
                raise ContractError(f"benchmarks may list only built-in agents, not {name}")
            pins[f"agent:{name}"] = agents_pin
    return dict(sorted(pins.items()))


def load_benchmark(name: str, verify: bool = True) -> JsonDict:
    """Load a benchmark, refusing it if anything it depends on has changed."""
    document = load_json_file(benchmark_path(name))
    validate("benchmark", document, name)
    if verify:
        problems = []
        for label, found, expected in (
            ("model version", MODEL_VERSION, document["model_version"]),
            ("scoring version", SCORING_VERSION, document["scoring_version"]),
            ("builder version", BUILDER_VERSION, document["builder_version"]),
        ):
            if found != expected:
                problems.append(f"{label} is {found}, benchmark needs {expected}")
        pins = compute_pins(document)
        for key in sorted(set(pins) | set(document["pins"])):
            if pins.get(key) != document["pins"].get(key):
                problems.append(f"{key} has changed")
        if problems:
            raise ContractError(
                f"benchmark {document['benchmark_id']} {document['version']} does not match this "
                "code. Results would not be comparable: " + "; ".join(problems)
            )
    return document


def lock_benchmark(name: str) -> dict[str, str]:
    """Rewrite pins and versions. A deliberate step, made with a new benchmark version."""
    path = benchmark_path(name)
    document = load_benchmark(name, verify=False)
    document["pins"] = compute_pins(document)
    document["model_version"] = MODEL_VERSION
    document["scoring_version"] = SCORING_VERSION
    document["builder_version"] = BUILDER_VERSION
    validate("benchmark", document, name)
    import json

    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n")
    pins: dict[str, str] = document["pins"]
    return pins


def load_seeds_file(path: Path) -> list[int]:
    """Read seeds an organizer keeps outside the repository."""
    document = load_json_file(path)
    seeds = document.get("seeds")
    if (
        not isinstance(seeds, list)
        or not seeds
        or not all(isinstance(s, int) and not isinstance(s, bool) and s >= 0 for s in seeds)
        or len(set(seeds)) != len(seeds)
    ):
        raise ContractError(f"{path}: expected unique non-negative integers under 'seeds'")
    return seeds


@dataclass(frozen=True)
class LeagueResult:
    league: str
    runs: list[JsonDict]
    board: list[JsonDict]
    out_dir: Path


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in Path(name).stem or name)


def _entries(league_name: str, spec: JsonDict) -> list[tuple[str, str]]:
    if league_name == "autonomy" and len(spec["rovers"]) != 1:
        raise ContractError("the Autonomy League must use exactly one rover")
    if league_name == "rover_design" and len(spec["agents"]) != 1:
        raise ContractError("the Rover Design League must use exactly one agent")
    return [(rover, agent) for rover in spec["rovers"] for agent in spec["agents"]]


def _entry_name(league: str, rover: str, agent: str) -> str:
    if league == "autonomy":
        return agent
    if league == "rover_design":
        return rover
    return f"{rover} + {agent}"


def rank_board(metrics: dict[str, list[Metrics]]) -> list[JsonDict]:
    """Rank entries. Ties fall to success, then lower energy, then the entry name."""
    rows = [{"entry": entry, **aggregate(values)} for entry, values in metrics.items()]
    rows.sort(key=lambda r: (-r["mean_score"], -r["success_rate"], r["mean_energy_wh"], r["entry"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def check_fair(runs: Sequence[JsonDict]) -> None:
    """Every entry must have run every scenario and seed exactly once."""
    sets: dict[tuple[str, str], set[tuple[str, int]]] = {}
    for run in runs:
        key = (run["rover"], run["agent"])
        item = (run["scenario"], run["seed"])
        if item in sets.setdefault(key, set()):
            raise ContractError(f"unfair league: {key} ran {item} twice")
        sets[key].add(item)
    if len({frozenset(value) for value in sets.values()}) > 1:
        raise ContractError("unfair league: entries did not run the same scenarios and seeds")


def run_league(
    benchmark: JsonDict,
    league: str,
    out_dir: Path,
    seeds: Sequence[int] | None = None,
    extra_agents: Sequence[str] = (),
    extra_rovers: Sequence[str] = (),
    overwrite: bool = False,
) -> LeagueResult:
    """Run a league. Private seeds can be passed in without changing the benchmark."""
    if league not in LEAGUES:
        raise ContractError(f"unknown league: {league}")
    spec = dict(benchmark["leagues"][league])
    spec["agents"] = [*spec["agents"], *extra_agents]
    spec["rovers"] = [*spec["rovers"], *extra_rovers]
    if league != "autonomy":
        # Plain parameters would bypass every budget.
        for rover in spec["rovers"]:
            require_design(rover)
    used_seeds = list(seeds) if seeds is not None else benchmark["seeds"]
    runs: list[JsonDict] = []
    metrics: dict[str, list[Metrics]] = {}
    for rover, agent in _entries(league, spec):
        entry = _entry_name(league, rover, agent)
        for name in spec["scenarios"]:
            scenario = load_scenario(name, rover=rover)
            for seed in used_seeds:
                directory = (
                    out_dir
                    / "runs"
                    / _safe(rover)
                    / _safe(agent)
                    / scenario.scenario_id
                    / f"seed-{seed}"
                )
                result = run_mission(
                    scenario, create_agent(agent), agent, directory, seed, overwrite
                )
                metrics.setdefault(entry, []).append(result.metrics)
                data = result.metrics.to_dict()
                runs.append(
                    {
                        "league": league,
                        "scenario": name,
                        "rover": rover,
                        "agent": agent,
                        "seed": seed,
                        **data,
                    }
                )
    check_fair(runs)
    board = rank_board(metrics)
    if league == "rover_design":
        board = design_board(board, runs)
    _write_results(benchmark, league, runs, board, out_dir, seeds is not None, used_seeds)
    return LeagueResult(league, runs, board, out_dir)


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[JsonDict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _csv_safe(row.get(k)) for k in fields})


def _csv_safe(value: object) -> object:
    # Agent names come from users. A leading symbol could run as a spreadsheet formula.
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return "" if value is None else value


def _write_results(
    benchmark: JsonDict,
    league: str,
    runs: Sequence[JsonDict],
    board: Sequence[JsonDict],
    out_dir: Path,
    private_seeds: bool,
    seeds: Sequence[int],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    header: JsonDict = {
        "benchmark_id": benchmark["benchmark_id"],
        "benchmark_version": benchmark["version"],
        "model_version": benchmark["model_version"],
        "scoring_version": benchmark["scoring_version"],
        "league": league,
        "seed_source": "private" if private_seeds else "public",
        "seed_count": len(seeds),
        # A hash identifies the seed set without revealing private seeds on a shared board.
        "seed_set_sha256": sha256_bytes(dump_json(sorted(seeds)).encode("utf-8")),
    }
    shareable_runs = [
        {k: v for k, v in r.items() if not (private_seeds and k == "seed")} for r in runs
    ]
    (out_dir / "results.json").write_text(
        dump_json({**header, "runs": shareable_runs}) + "\n", encoding="utf-8", newline="\n"
    )
    fields = [f for f in _CSV_FIELDS if not (private_seeds and f == "seed")]
    _write_csv(out_dir / "results.csv", fields, shareable_runs)
    (out_dir / "leaderboard.json").write_text(
        dump_json({**header, "board": list(board)}) + "\n", encoding="utf-8", newline="\n"
    )
    board_fields = _DESIGN_FIELDS if board and "design_class" in board[0] else _BOARD_FIELDS
    _write_csv(out_dir / "leaderboard.csv", board_fields, board)


def design_board(board: Sequence[JsonDict], runs: Sequence[JsonDict]) -> list[JsonDict]:
    """Rank designs inside their class, and keep achievement, cost, and robustness apart.

    No formula converts cost into points. Cost decides who competes with whom, and the
    Pareto front shows which designs no other design beats on all of the three measures.
    """
    rows: list[JsonDict] = []
    for row in board:
        rover = row["entry"]
        own = [run for run in runs if run["rover"] == rover]
        scenarios = sorted({run["scenario"] for run in own})
        profile = {
            name: round(
                sum(run["achievement"] for run in own if run["scenario"] == name)
                / sum(1 for run in own if run["scenario"] == name),
                2,
            )
            for name in scenarios
        }
        report = load_rover_document(rover)["design_report"]
        rows.append(
            {
                **row,
                "design_class": report["design_class"],
                "design_cost": report["cost"],
                "mass_kg": report["mass_kg"],
                "robustness": min(profile.values()),
                "scenario_achievement": profile,
            }
        )
    front = pareto_front(
        rows, minimize=("design_cost",), maximize=("mean_achievement", "robustness")
    )
    for row in rows:
        row["pareto"] = row["entry"] in front
    order = list(DESIGN_CLASSES)
    rows.sort(key=lambda r: (order.index(r["design_class"]), -r["mean_score"], r["mean_energy_wh"]))
    for name in order:
        for rank, row in enumerate((r for r in rows if r["design_class"] == name), start=1):
            row["rank"] = rank
    return rows


def format_board(board: Sequence[JsonDict]) -> str:
    fields = _DESIGN_FIELDS if board and "design_class" in board[0] else _BOARD_FIELDS
    table = [list(fields)]
    table += [["-" if r.get(k) is None else str(r.get(k)) for k in fields] for r in board]
    widths = [max(len(line[i]) for line in table) for i in range(len(fields))]
    return "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True))
        for line in table
    )
