"""A local mock of Codabench-style evaluation: ingestion, then separate scoring.

This has never run on Codabench. Agents run in a separate process with reply and total time limits,
memory and file limits, and a guard that refuses common forbidden actions. THAT IS NOT A SANDBOX:
Python's own documentation says that hooks like this cannot contain malicious code, and native code
can bypass them. Only use this on code you trust. See docs/evaluator-safety.md.
"""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from roverloom.bridge import RemoteAgent
from roverloom.contract import ContractError, JsonDict, dump_json, load_json_file, validate
from roverloom.evaluate import aggregate, evaluate_run
from roverloom.guard import GUARD_ROOT_VARIABLE
from roverloom.rover_builder import require_design
from roverloom.runlog import load_run
from roverloom.runner import run_mission
from roverloom.world import load_scenario

MAX_SUBMISSION_BYTES = 20 * 1024 * 1024
MAX_SUBMISSION_FILES = 200
REPLY_TIMEOUT_S = 10.0
TOTAL_THINKING_S = 300.0
_ALLOWED_SUFFIXES = {".py", ".json", ".txt", ".md", ".csv", ".yaml", ".yml"}
SCORE_KEYS = (
    "mean_score",
    "success_rate",
    "mean_science_value",
    "mean_time_s",
    "mean_energy_wh",
    "mean_collisions",
)


def extract_submission(archive: Path, destination: Path) -> Path:
    """Extract a zip safely, refusing path traversal, links, and oversized content."""
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if len(members) > MAX_SUBMISSION_FILES:
                raise ContractError("submission has too many files")
            if sum(m.file_size for m in members) > MAX_SUBMISSION_BYTES:
                raise ContractError("submission is too large")
            for member in members:
                name = member.filename
                is_link = (member.external_attr >> 16) & 0o170000 == 0o120000
                target = (root / name).resolve()
                if is_link or not target.is_relative_to(root) or Path(name).is_absolute():
                    raise ContractError(f"unsafe path in submission: {name}")
                if member.is_dir():
                    continue
                # Compiled code would skip every review of the source.
                if Path(name).suffix.lower() not in _ALLOWED_SUFFIXES:
                    raise ContractError(f"file type not allowed in submission: {name}")
            bundle.extractall(root)
    except zipfile.BadZipFile as error:
        raise ContractError(f"submission is not a valid zip: {error}") from error
    return root


def load_submission(directory: Path) -> JsonDict:
    """Check a submission's shape. Does not run or import its code."""
    metadata = load_json_file(directory / "metadata.json")
    validate("submission_metadata", metadata, "metadata.json")
    if not (directory / "agent.py").is_file():
        raise ContractError("submission has no agent.py")
    if metadata["league"] != "autonomy":
        path = directory / "rover.json"
        if not path.is_file():
            raise ContractError(f"{metadata['league']} submissions need a rover.json")
        # Plain rover parameters would skip every design budget.
        require_design(str(path))
    return metadata


def load_reference(directory: Path) -> JsonDict:
    reference = load_json_file(directory / "reference.json")
    if (
        not isinstance(reference.get("scenarios"), list)
        or not reference["scenarios"]
        or not isinstance(reference.get("seeds"), list)
        or not reference["seeds"]
        or not isinstance(reference.get("rover"), str)
    ):
        raise ContractError("reference.json needs scenarios, seeds, and rover")
    return reference


def _scenario_name(directory: Path, name: str) -> str:
    # Hidden scenarios live with the reference data, and shadow public ones of the same name.
    private = directory / "scenarios" / f"{name}.json"
    return str(private) if private.is_file() else name


def ingest(submission: Path, reference_dir: Path, output_dir: Path) -> list[JsonDict]:
    """Run a submission over the reference scenarios and seeds, each in a new process."""
    metadata = load_submission(submission)
    reference = load_reference(reference_dir)
    rover = reference["rover"]
    if metadata["league"] != "autonomy":
        rover = str(submission / "rover.json")
    spec = f"{(submission / 'agent.py').resolve()}:{metadata['agent_class']}"
    summary: list[JsonDict] = []
    for name in reference["scenarios"]:
        scenario = load_scenario(_scenario_name(reference_dir, name), rover=rover)
        for seed in reference["seeds"]:
            remote = RemoteAgent(timeout_s=REPLY_TIMEOUT_S, total_budget_s=TOTAL_THINKING_S)
            process = subprocess.Popen(
                [sys.executable, "-m", "roverloom.bridge", spec, str(remote.port), "--guarded"],
                cwd=submission,
                # A minimal environment, so that secrets in variables are not handed over.
                env={
                    **{
                        k: os.environ[k]
                        for k in ("PATH", "SYSTEMROOT", "HOME", "PYTHONPATH", "ROVERLOOM_HOME")
                        if k in os.environ
                    },
                    GUARD_ROOT_VARIABLE: str(submission),
                },
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            directory = output_dir / scenario.scenario_id / f"seed-{seed}"
            try:
                result = run_mission(scenario, remote, metadata["name"], directory, seed, True)
                summary.append(
                    {
                        "scenario": scenario.scenario_id,
                        "seed": seed,
                        "outcome": result.metrics.outcome,
                        "thinking_s": round(remote.thinking_s, 3),
                    }
                )
            finally:
                remote.close()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    return summary


def score(reference_dir: Path, results_dir: Path, output_dir: Path) -> JsonDict:
    """Score logs without running any submitted code. A missing or bad run scores zero."""
    reference = load_reference(reference_dir)
    metrics, errors = [], []
    for name in reference["scenarios"]:
        scenario_id = load_json_file(Path(_scenario_path(reference_dir, name)))["scenario_id"]
        expected = load_json_file(Path(_scenario_path(reference_dir, name)))
        for seed in reference["seeds"]:
            directory = results_dir / scenario_id / f"seed-{seed}"
            try:
                run = load_run(directory)
                if (
                    run.manifest["seed"] != seed
                    or run.scenario.document["mission"] != expected["mission"]
                ):
                    raise ContractError("run does not match the reference scenario and seed")
                metrics.append(evaluate_run(run))
            except ContractError as error:
                # The message must not reveal hidden seeds or scenario content.
                errors.append(
                    {
                        "scenario_index": reference["scenarios"].index(name),
                        "error": type(error).__name__,
                    }
                )
    expected_runs = len(reference["scenarios"]) * len(reference["seeds"])
    summary = aggregate(metrics)
    scores: JsonDict = {key: summary.get(key) or 0.0 for key in SCORE_KEYS}
    # Failed runs count as zero rather than disappearing from the average.
    if expected_runs:
        scores["mean_score"] = round(sum(m.score for m in metrics) / expected_runs, 3)
        scores["success_rate"] = round(sum(m.success for m in metrics) / expected_runs, 3)
    scores["runs_scored"] = len(metrics)
    scores["runs_expected"] = expected_runs
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "scores.json").write_text(
        dump_json(scores) + "\n", encoding="utf-8", newline="\n"
    )
    (output_dir / "errors.json").write_text(
        dump_json(errors) + "\n", encoding="utf-8", newline="\n"
    )
    return scores


def _scenario_path(reference_dir: Path, name: str) -> str:
    from roverloom.world import resolve_scenario_path

    return str(resolve_scenario_path(_scenario_name(reference_dir, name)))


def mock_submission(submission: Path, reference_dir: Path, out_dir: Path) -> JsonDict:
    """Run the whole flow locally. Accepts a directory or a zip."""
    if out_dir.exists() and (out_dir / "input").exists():
        shutil.rmtree(out_dir / "input")
    source = submission
    if submission.is_file():
        source = extract_submission(submission, out_dir / "input" / "submission")
    results = out_dir / "input" / "res"
    ingest(source.resolve(), reference_dir, results)
    return score(reference_dir, results, out_dir / "output")
