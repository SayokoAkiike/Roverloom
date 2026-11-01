"""Runs complete missions and writes sealed, scored run directories."""

import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from roverloom.agents import create_agent
from roverloom.contract import JsonDict, dump_json
from roverloom.evaluate import Metrics, aggregate, evaluate_run
from roverloom.runlog import RunWriter, load_run
from roverloom.session import CommandSource, MissionSession
from roverloom.world import Scenario, load_scenario


@dataclass(frozen=True)
class RunResult:
    directory: Path
    manifest: JsonDict
    metrics: Metrics


def finalize_run(
    writer: RunWriter,
    session: MissionSession,
    agent_name: str,
    wall_time_s: float,
    source: object = None,
) -> RunResult:
    version = getattr(source, "VERSION", None)
    manifest = writer.finish(
        session.scenario, agent_name, session.seed, session.step_index, wall_time_s, version
    )
    metrics = evaluate_run(load_run(writer.directory, trusted=True))
    (writer.directory / "metrics.json").write_text(
        dump_json(metrics.to_dict()) + "\n", encoding="utf-8", newline="\n"
    )
    return RunResult(writer.directory, manifest, metrics)


def run_mission(
    scenario: Scenario,
    source: CommandSource,
    agent_name: str,
    out_dir: Path,
    seed: int | None = None,
    overwrite: bool = False,
) -> RunResult:
    writer = RunWriter(out_dir, overwrite=overwrite)
    started = time.perf_counter()
    try:
        session = MissionSession(
            scenario,
            {"agent": source},
            "agent",
            seed=seed,
            on_telemetry=writer.telemetry,
            on_command=writer.command,
            on_event=writer.event,
            on_decision=writer.decision,
        )
        while not session.mission.finished:
            session.step()
    except BaseException:
        writer.close_files()
        raise
    return finalize_run(writer, session, agent_name, time.perf_counter() - started, source)


@dataclass(frozen=True)
class Comparison:
    rows: list[JsonDict]
    results: dict[tuple[str, str, int], RunResult]


def compare_agents(
    scenarios: Sequence[str],
    agents: Sequence[str],
    seeds: Sequence[int],
    out_dir: Path,
    overwrite: bool = False,
) -> Comparison:
    """Run every combination. All agents face the same faults for each seed."""
    results: dict[tuple[str, str, int], RunResult] = {}
    rows: list[JsonDict] = []
    for scenario_name in scenarios:
        scenario = load_scenario(scenario_name)
        for agent_name in agents:
            metrics: list[Metrics] = []
            for seed in seeds:
                directory = out_dir / scenario.scenario_id / _safe_name(agent_name) / f"seed-{seed}"
                result = run_mission(
                    scenario, create_agent(agent_name), agent_name, directory, seed, overwrite
                )
                results[(scenario.scenario_id, agent_name, seed)] = result
                metrics.append(result.metrics)
            rows.append(
                {"scenario": scenario.scenario_id, "agent": agent_name, **aggregate(metrics)}
            )
    return Comparison(rows, results)


def _safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
