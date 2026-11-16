"""Repeated-run studies: tracks, confidence intervals, failure causes, and design interventions.

Results describe this simplified model only. A difference between two planners here is evidence
about those planners on these scenarios, and nothing more. See docs/scientific-benchmark.md.
"""

import csv
import json
import math
import os
import random
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from roverloom.contract import ContractError, JsonDict, dump_json, load_json_file
from roverloom.rover_builder import designs_dir
from roverloom.runlog import LoadedRun, load_run
from roverloom.world import load_scenario

TRACKS = ("standard", "stress", "out_of_distribution", "misestimated_uncertainty")
_BOOTSTRAP_DRAWS = 2000
_STALL_FRACTION = 0.25
_STALL_DISTANCE_M = 2.0
_COLLISIONS_BLOCKED = 3
FAILURE_CAUSES = (
    "success",
    "agent_error",
    "aborted",
    "energy_exhausted",
    "capability_missing",
    "did_not_return",
    "insufficient_science",
    "immobilized",
    "blocked_by_obstacles",
    "stalled",
    "degraded_mobility",
    "out_of_time",
)


def bootstrap_ci(
    values: Sequence[float], level: float = 0.95, seed: str = "ci"
) -> tuple[float, float, float]:
    """Mean with a percentile bootstrap interval. Seeded, so reports reproduce exactly.

    With few runs this interval is too narrow. Use it to compare, not as a guarantee.
    """
    if not values:
        raise ContractError("no values")
    count = len(values)
    mean = sum(values) / count
    if count == 1:
        return mean, mean, mean
    rng = random.Random(f"bootstrap:{seed}:{count}")
    draws = sorted(sum(rng.choices(values, k=count)) / count for _ in range(_BOOTSTRAP_DRAWS))
    low = draws[int((1.0 - level) / 2.0 * _BOOTSTRAP_DRAWS)]
    high = draws[min(int((1.0 + level) / 2.0 * _BOOTSTRAP_DRAWS), _BOOTSTRAP_DRAWS - 1)]
    return mean, low, high


def wilson_interval(successes: int, count: int, z: float = 1.96) -> tuple[float, float]:
    """Interval for a success rate. Unlike a normal approximation, it behaves near 0 and 1."""
    if count <= 0:
        raise ContractError("no runs")
    rate = successes / count
    denominator = 1.0 + z * z / count
    center = (rate + z * z / (2.0 * count)) / denominator
    margin = z * math.sqrt(rate * (1.0 - rate) / count + z * z / (4.0 * count * count))
    margin /= denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def pareto_front(
    rows: Sequence[JsonDict], minimize: Sequence[str], maximize: Sequence[str]
) -> set[str]:
    """Entries that no other entry beats or equals on every measure, and beats on at least one."""

    def dominates(a: JsonDict, b: JsonDict) -> bool:
        no_worse = all(a[k] <= b[k] for k in minimize) and all(a[k] >= b[k] for k in maximize)
        better = any(a[k] < b[k] for k in minimize) or any(a[k] > b[k] for k in maximize)
        return no_worse and better

    return {str(row["entry"]) for row in rows if not any(dominates(other, row) for other in rows)}


def classify_run(run: LoadedRun) -> JsonDict:
    """Name a run's main cause of ending, from its logs alone. A simple rule set, not a diagnosis.

    Contributing factors are facts from the log. The main cause is a judgment by these rules.
    """
    ended = run.events[-1]["data"]
    outcome = ended["outcome"]
    rejected = sorted({e["data"]["reason"] for e in run.events if e["type"] == "task_rejected"})
    faults = sorted({e["data"]["fault"] for e in run.events if e["type"] == "fault_started"})
    collisions = sum(1 for e in run.events if e["type"] == "collision")
    telemetry = run.telemetry
    tail_start = telemetry[int(len(telemetry) * (1.0 - _STALL_FRACTION))] if telemetry else None
    moved = telemetry[-1]["distance_m"] - tail_start["distance_m"] if tail_start else 0.0
    active_at_end = telemetry[-1].get("active_faults", []) if telemetry else []
    failed_wheels = telemetry[-1].get("failed_wheels", []) if telemetry else []
    science = run.scenario.mission.get("science")
    base_required = bool(science and science.get("base", {}).get("required"))

    cause: str
    if outcome == "success":
        cause = "success"
    elif outcome == "agent_error":
        cause = "agent_error"
    elif outcome == "aborted":
        cause = "aborted"
    elif outcome in ("battery_depleted", "energy_limit"):
        cause = "energy_exhausted"
    elif outcome == "ended_early":
        if "no_sample_tool" in rejected or (
            science and not run.scenario.rover.document.get("has_sample_tool", True)
        ):
            cause = "capability_missing"
        elif base_required and not ended.get("at_base"):
            cause = "did_not_return"
        else:
            cause = "insufficient_science"
    elif moved >= _STALL_DISTANCE_M:
        cause = "degraded_mobility" if failed_wheels else "out_of_time"
    elif "immobilized" in active_at_end:
        cause = "immobilized"
    elif collisions >= _COLLISIONS_BLOCKED:
        cause = "blocked_by_obstacles"
    else:
        cause = "stalled"
    decisions: dict[str, int] = {}
    for decision in run.decisions:
        kind = decision.get("kind")
        if kind:
            decisions[kind] = decisions.get(kind, 0) + 1
    return {
        "cause": cause,
        "faults": faults,
        "task_rejections": rejected,
        "collisions": collisions,
        "failed_wheels": len(failed_wheels),
        "decisions": decisions,
    }


def _relief_m(terrain: JsonDict) -> float:
    if "heightfield" in terrain:
        field = terrain["heightfield"]
        return float(field["height_max_m"]) - float(field["height_min_m"])
    return float(terrain["height"]["amplitude_m"])


_ENVELOPE: dict[str, Callable[[JsonDict, JsonDict], float]] = {
    "gravity_mps2": lambda s, _: float(s["environment"]["gravity_mps2"]),
    "solar_factor": lambda s, _: float(s["environment"].get("solar_factor", 1.0)),
    "latency_s": lambda s, _: float(s.get("comms", {}).get("latency_s", 0.0)),
    "loss_probability": lambda s, _: float(s.get("comms", {}).get("loss_probability", 0.0)),
    "pose_noise_m": lambda s, _: float(s.get("sensors", {}).get("pose_noise_m", 0.0)),
    "range_noise_m": lambda s, _: float(s.get("sensors", {}).get("range_noise_m", 0.0)),
    "terrain_relief_m": lambda _, t: _relief_m(t),
    "generated_rocks": lambda _, t: float(t.get("rocks", {}).get("generated", {}).get("count", 0)),
    "max_soil_slip": lambda _, t: max(
        (float(s["slip_fraction"]) for s in t.get("soft_soil", [])), default=0.0
    ),
}


def _documents(name: str) -> tuple[JsonDict, JsonDict]:
    scenario = load_scenario(name)
    return scenario.document, scenario.terrain.document


def distribution_report(benchmark: JsonDict) -> dict[str, list[str]]:
    """For each out-of-distribution scenario, name the parameters outside the standard range."""
    tracks = benchmark["tracks"]
    standard = [_documents(name) for name in tracks["standard"]]
    envelope = {
        key: (min(read(*d) for d in standard), max(read(*d) for d in standard))
        for key, read in _ENVELOPE.items()
    }
    report: dict[str, list[str]] = {}
    for name in tracks["out_of_distribution"]:
        documents = _documents(name)
        outside = []
        for key, read in _ENVELOPE.items():
            value = read(*documents)
            low, high = envelope[key]
            if value < low or value > high:
                outside.append(f"{key}={value:g} (standard {low:g} to {high:g})")
        report[name] = outside
    return report


def _run_one(job: tuple[str, str, str, int, str]) -> JsonDict:
    # Imported here because this runs in worker processes, and runner imports agents.
    from roverloom.agents import create_agent
    from roverloom.runner import run_mission

    track, scenario_name, agent, seed, out = job
    rover, agent_name = agent.split("|", 1)
    scenario = load_scenario(scenario_name, rover=rover)
    directory = (
        Path(out) / track / Path(rover).stem / scenario.scenario_id / agent_name / f"seed-{seed}"
    )
    result = run_mission(
        scenario, create_agent(agent_name), agent_name, directory, seed, overwrite=True
    )
    classified = classify_run(load_run(result.directory, trusted=True))
    data = result.metrics
    return {
        "track": track,
        "scenario": scenario_name,
        "agent": agent_name,
        "rover": rover,
        "seed": seed,
        "outcome": data.outcome,
        "success": data.success,
        "score": data.score,
        "achievement": data.achievement,
        "science_value": data.science_value,
        "energy_used_wh": data.energy_used_wh,
        "mission_time_s": data.mission_time_s,
        "cause": classified["cause"],
        "reobserve": classified["decisions"].get("reobserve", 0),
        "replan": classified["decisions"].get("replan", 0),
        "withdraw": classified["decisions"].get("withdraw", 0),
        "uncertainty_mismatch": classified["decisions"].get("uncertainty_mismatch", 0),
        "digest": result.manifest["logs_sha256"]["telemetry"],
    }


def run_jobs(jobs: Sequence[tuple[str, str, str, int, str]], workers: int) -> list[JsonDict]:
    """Run jobs, in parallel when asked. The result order and contents do not depend on workers."""
    if workers <= 1:
        return [_run_one(job) for job in jobs]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_run_one, jobs))


def summarize(rows: Sequence[JsonDict]) -> JsonDict:
    achievement = [r["achievement"] for r in rows]
    score = [r["score"] for r in rows]
    wins = sum(1 for r in rows if r["success"])
    mean, low, high = bootstrap_ci(achievement, seed="achievement")
    score_mean, score_low, score_high = bootstrap_ci(score, seed="score")
    rate_low, rate_high = wilson_interval(wins, len(rows))
    causes: dict[str, int] = {}
    for row in rows:
        causes[row["cause"]] = causes.get(row["cause"], 0) + 1
    return {
        "runs": len(rows),
        "achievement": round(mean, 2),
        "achievement_ci95": [round(low, 2), round(high, 2)],
        "score": round(score_mean, 2),
        "score_ci95": [round(score_low, 2), round(score_high, 2)],
        "success_rate": round(wins / len(rows), 3),
        "success_ci95": [round(rate_low, 3), round(rate_high, 3)],
        "causes": dict(sorted(causes.items())),
        "reobserve_per_run": round(sum(r["reobserve"] for r in rows) / len(rows), 2),
        "replan_per_run": round(sum(r["replan"] for r in rows) / len(rows), 2),
        "withdraw_per_run": round(sum(r["withdraw"] for r in rows) / len(rows), 2),
        "mismatch_per_run": round(sum(r["uncertainty_mismatch"] for r in rows) / len(rows), 2),
    }


def paired_difference(
    rows: Sequence[JsonDict], agent: str, baseline: str, measure: str = "achievement"
) -> JsonDict:
    """Compare two agents on identical scenario and seed pairs, which removes shared luck."""
    by_key = {(r["scenario"], r["seed"], r["agent"]): r[measure] for r in rows}
    differences = [
        by_key[(scenario, seed, agent)] - by_key[(scenario, seed, baseline)]
        for scenario, seed, name in by_key
        if name == agent and (scenario, seed, baseline) in by_key
    ]
    if not differences:
        raise ContractError(f"no shared runs between {agent} and {baseline}")
    mean, low, high = bootstrap_ci(differences, seed=f"{agent}:{baseline}:{measure}")
    return {
        "agent": agent,
        "baseline": baseline,
        "measure": measure,
        "pairs": len(differences),
        "mean_difference": round(mean, 2),
        "ci95": [round(low, 2), round(high, 2)],
        "wins": sum(1 for d in differences if d > 0),
        "losses": sum(1 for d in differences if d < 0),
        "ties": sum(1 for d in differences if d == 0),
        "interval_excludes_zero": low > 0 or high < 0,
    }


def run_study(
    benchmark: JsonDict,
    out_dir: Path,
    tracks: Sequence[str] = TRACKS,
    agents: Sequence[str] | None = None,
    rover: str | None = None,
    seed_count: int | None = None,
    workers: int | None = None,
) -> JsonDict:
    """Run every agent on every scenario and seed of the chosen tracks, and write a report."""
    spec = benchmark["study"]
    used_agents = list(agents or spec["agents"])
    used_rover = rover or spec["rover"]
    count = seed_count or spec["seed_count"]
    seeds = [spec["first_seed"] + index for index in range(count)]
    jobs = [
        (track, scenario, f"{used_rover}|{agent}", seed, str(out_dir / "runs"))
        for track in tracks
        for scenario in benchmark["tracks"][track]
        for agent in used_agents
        for seed in seeds
    ]
    default_workers = max(1, (os.cpu_count() or 2) - 1)
    rows = run_jobs(jobs, default_workers if workers is None else workers)
    baseline = used_agents[0]
    report: JsonDict = {
        "benchmark_id": benchmark["benchmark_id"],
        "benchmark_version": benchmark["version"],
        "model_version": benchmark["model_version"],
        "scoring_version": benchmark["scoring_version"],
        "rover": used_rover,
        "seeds": seeds,
        "baseline": baseline,
        "note": "Simplified model. Results compare these planners on these scenarios only.",
        "tracks": {},
    }
    for track in tracks:
        own = [r for r in rows if r["track"] == track]
        report["tracks"][track] = {
            "scenarios": list(benchmark["tracks"][track]),
            "agents": {
                agent: summarize([r for r in own if r["agent"] == agent]) for agent in used_agents
            },
            "by_scenario": {
                scenario: {
                    agent: summarize(
                        [r for r in own if r["agent"] == agent and r["scenario"] == scenario]
                    )
                    for agent in used_agents
                }
                for scenario in benchmark["tracks"][track]
            },
            "paired_vs_baseline": [
                paired_difference(own, agent, baseline)
                for agent in used_agents
                if agent != baseline
            ],
        }
    if "out_of_distribution" in tracks:
        report["out_of_distribution_parameters"] = distribution_report(benchmark)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "study.json").write_text(dump_json(report) + "\n", encoding="utf-8", newline="\n")
    fields = [key for key in rows[0] if key != "digest"] if rows else []
    with (out_dir / "study_runs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return report


def format_study(report: JsonDict) -> str:
    lines = [f"Rover {report['rover']}, {len(report['seeds'])} seeds. {report['note']}"]
    for track, data in report["tracks"].items():
        lines.append(f"\n{track}: {', '.join(data['scenarios'])}")
        for agent, row in data["agents"].items():
            low, high = row["achievement_ci95"]
            rate_low, rate_high = row["success_ci95"]
            causes = ", ".join(f"{k} {v}" for k, v in row["causes"].items())
            lines.append(
                f"  {agent:<24} achievement {row['achievement']:6.2f} [{low:.2f}, {high:.2f}]  "
                f"success {row['success_rate']:.2f} [{rate_low:.2f}, {rate_high:.2f}]  "
                f"re-obs {row['reobserve_per_run']} replan {row['replan_per_run']} "
                f"withdraw {row['withdraw_per_run']}  ({causes})"
            )
        for pair in data["paired_vs_baseline"]:
            low, high = pair["ci95"]
            lines.append(
                f"  {pair['agent']} - {pair['baseline']}: {pair['mean_difference']:+.2f} "
                f"[{low:+.2f}, {high:+.2f}], wins {pair['wins']}, losses {pair['losses']}, "
                f"ties {pair['ties']}"
            )
    return "\n".join(lines)


def _with_arm(design: JsonDict) -> None:
    if design["tools"]["sample_arm"]:
        return
    design["tools"]["sample_arm"] = True
    design["chassis_kg"] = max(design["chassis_kg"], 260)
    design["battery_wh"] = max(design["battery_wh"], 320)


def _without_arm(design: JsonDict) -> None:
    design["tools"]["sample_arm"] = False


def _solar_to_rtg(design: JsonDict) -> None:
    if design["power"]["kind"] != "solar":
        return
    design["power"] = {"kind": "rtg", "output_w": 90}
    design["chassis_kg"] = max(design["chassis_kg"], 400)


def _rtg_to_solar(design: JsonDict) -> None:
    if design["power"]["kind"] != "rtg":
        return
    design["power"] = {"kind": "solar", "panel_m2": 6}


def _less_battery(design: JsonDict) -> None:
    design["battery_wh"] = design["battery_wh"] * 0.75


def _four_wheels(design: JsonDict) -> None:
    design["wheels"]["count"] = 4


INTERVENTIONS: dict[str, Callable[[JsonDict], None]] = {
    "add_arm": _with_arm,
    "remove_arm": _without_arm,
    "solar_to_rtg": _solar_to_rtg,
    "rtg_to_solar": _rtg_to_solar,
    "less_battery": _less_battery,
    "four_wheels": _four_wheels,
}


def design_study(
    benchmark: JsonDict,
    rovers: Sequence[str],
    out_dir: Path,
    agent: str = "mission-planner",
    seed_count: int = 5,
    workers: int | None = None,
) -> JsonDict:
    """Change one design choice at a time and rerun, so that an effect has a demonstrated cause.

    A correlation across finished designs cannot say why one wins. An intervention can, within
    this model. A variant the builder refuses is reported with its reason.
    """
    from roverloom.rover_builder import compile_design

    scenarios = benchmark["leagues"]["rover_design"]["scenarios"]
    seeds = benchmark["seeds"][:seed_count]
    runs_dir = out_dir / "runs"
    variants_dir = out_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    report: JsonDict = {
        "agent": agent,
        "seeds": list(seeds),
        "scenarios": list(scenarios),
        "note": "Changes within a simplified game model. Not evidence about real rovers.",
        "rovers": {},
    }
    default_workers = max(1, (os.cpu_count() or 2) - 1)
    for rover in rovers:
        base_document = load_json_file(designs_dir() / f"{rover}.json")
        candidates: dict[str, str] = {"baseline": rover}
        refused: dict[str, str] = {}
        for name, change in INTERVENTIONS.items():
            variant = json.loads(json.dumps(base_document))
            change(variant)
            if variant == base_document:
                continue
            variant["design_id"] = f"{rover}_{name}"
            try:
                compile_design(variant)
            except ContractError as error:
                refused[name] = str(error).split(": ", 1)[-1]
                continue
            path = variants_dir / f"{variant['design_id']}.json"
            path.write_text(json.dumps(variant, indent=2) + "\n", encoding="utf-8", newline="\n")
            candidates[name] = str(path)
        jobs = [
            (name, scenario, f"{source}|{agent}", seed, str(runs_dir / rover))
            for name, source in candidates.items()
            for scenario in scenarios
            for seed in seeds
        ]
        rows = run_jobs(jobs, default_workers if workers is None else workers)

        def profile(name: str, rows: Sequence[JsonDict] = rows) -> JsonDict:
            own = [r for r in rows if r["track"] == name]
            result: JsonDict = {}
            for scenario in scenarios:
                values = [r["achievement"] for r in own if r["scenario"] == scenario]
                result[scenario] = round(sum(values) / len(values), 2)
            return result

        baseline = profile("baseline")
        changes: JsonDict = {}
        for name in candidates:
            if name == "baseline":
                continue
            current = profile(name)
            cost = compile_design(load_json_file(Path(candidates[name])))["design_report"]["cost"]
            changes[name] = {
                "design_cost": cost,
                "achievement_change": {
                    scenario: round(current[scenario] - baseline[scenario], 2)
                    for scenario in scenarios
                },
            }
        base_cost = compile_design(base_document)["design_report"]["cost"]
        report["rovers"][rover] = {
            "design_cost": base_cost,
            "baseline_achievement": baseline,
            "interventions": changes,
            "refused": refused,
        }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "design_study.json").write_text(
        dump_json(report) + "\n", encoding="utf-8", newline="\n"
    )
    return report
