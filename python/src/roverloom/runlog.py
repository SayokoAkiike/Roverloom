"""Writes and strictly reads run directories. A run can be re-scored from its files alone."""

import importlib.metadata
import platform
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from roverloom import BACKEND_NAME, MODEL_VERSION, SCORING_VERSION
from roverloom.api import SCHEMA_VERSION
from roverloom.contract import (
    ContractError,
    JsonDict,
    dump_json,
    load_json_file,
    parse_json,
    repo_root,
    sha256_bytes,
    validate,
)
from roverloom.frames import FRAME_NAME
from roverloom.world import SIM_STEP_S, Scenario, build_scenario

LOG_FILES = {"telemetry": "telemetry.jsonl", "commands": "commands.jsonl", "events": "events.jsonl"}
LOG_SCHEMAS = {"telemetry": "telemetry", "commands": "command_record", "events": "event"}
DECISIONS_FILE = "decisions.jsonl"
_RUN_FILES = (
    "run.json",
    "scenario.json",
    "terrain.json",
    "rover.json",
    "metrics.json",
    DECISIONS_FILE,
    *LOG_FILES.values(),
)


def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, encoding="utf-8", timeout=10, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def capture_environment() -> JsonDict:
    root = repo_root()
    lock = root / "python" / "uv.lock"
    commit = _git(root, "rev-parse", "HEAD")
    status = _git(root, "status", "--porcelain")
    packages = {}
    for name in ("roverloom", "jsonschema"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "unknown"
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
        "uv_lock_sha256": sha256_bytes(lock.read_bytes()) if lock.is_file() else None,
        "git_commit": commit,
        "git_dirty": None if status is None else bool(status),
    }


class RunWriter:
    """Streams logs to a run directory, then seals them with a manifest of their hashes."""

    def __init__(self, directory: Path, overwrite: bool = False) -> None:
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        existing = {path.name for path in directory.iterdir()}
        if existing and not overwrite:
            raise ContractError(f"run directory is not empty: {directory}")
        unknown = existing - set(_RUN_FILES)
        if unknown:
            # Overwriting only ever removes files that this class itself created.
            raise ContractError(f"refusing to overwrite unknown files: {sorted(unknown)}")
        for name in existing:
            (directory / name).unlink()
        self._files: dict[str, IO[str]] = {
            key: (directory / name).open("w", encoding="utf-8", newline="\n")
            for key, name in LOG_FILES.items()
        }
        self._started_at = datetime.now(UTC).isoformat(timespec="seconds")

    def _write(self, key: str, document: JsonDict) -> None:
        self._files[key].write(dump_json(document) + "\n")

    def telemetry(self, document: JsonDict) -> None:
        self._write("telemetry", document)

    def command(self, document: JsonDict) -> None:
        self._write("commands", document)

    def event(self, document: JsonDict) -> None:
        self._write("events", document)

    def decision(self, document: JsonDict) -> None:
        # The file exists only for agents that report decisions.
        if "decisions" not in self._files:
            self._files["decisions"] = (self.directory / DECISIONS_FILE).open(
                "w", encoding="utf-8", newline="\n"
            )
        self._write("decisions", document)

    def close_files(self) -> None:
        for handle in self._files.values():
            handle.close()

    def _extra_logs(self) -> dict[str, str]:
        return {"decisions": DECISIONS_FILE} if "decisions" in self._files else {}

    def finish(
        self,
        scenario: Scenario,
        agent: str,
        seed: int,
        steps: int,
        wall_time_s: float,
        agent_version: str | None = None,
        backend: str = BACKEND_NAME,
    ) -> JsonDict:
        self.close_files()
        for name, document in (
            ("scenario.json", scenario.document),
            ("terrain.json", scenario.terrain.document),
            ("rover.json", scenario.rover.document),
        ):
            (self.directory / name).write_text(
                dump_json(document) + "\n", encoding="utf-8", newline="\n"
            )
        manifest: JsonDict = {
            "schema_version": SCHEMA_VERSION,
            "backend": backend,
            "conventions": {"frame": FRAME_NAME, "quaternion": "xyzw", "body": "flu"},
            "model_version": MODEL_VERSION,
            "scoring_version": SCORING_VERSION,
            "scenario_id": scenario.scenario_id,
            "seed": seed,
            "agent": agent,
            "sim_step_s": SIM_STEP_S,
            "steps": steps,
            "inputs_sha256": scenario.inputs_sha256(),
            "rover_id": scenario.rover.rover_id,
            "rover_version": scenario.rover.document.get("version"),
            "scenario_version": scenario.document.get("version"),
            "agent_version": agent_version,
            "logs_sha256": {
                key: sha256_bytes((self.directory / name).read_bytes())
                for key, name in {**LOG_FILES, **self._extra_logs()}.items()
            },
            "environment": capture_environment(),
            "started_at_utc": self._started_at,
            "wall_time_s": round(wall_time_s, 3),
        }
        validate("run_manifest", manifest)
        (self.directory / "run.json").write_text(
            dump_json(manifest) + "\n", encoding="utf-8", newline="\n"
        )
        return manifest


def _read_jsonl(path: Path, schema: str, check_schema: bool) -> list[JsonDict]:
    documents: list[JsonDict] = []
    last_time = -1.0
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ContractError(f"cannot read {path}: {error}") from error
    if text and not text.endswith("\n"):
        raise ContractError(f"{path}: file is truncated (no final newline)")
    for number, line in enumerate(text.splitlines(), start=1):
        context = f"{path.name}:{number}"
        try:
            document = parse_json(line)
        except ContractError as error:
            raise ContractError(f"{context}: {error}") from error
        if check_schema:
            validate(schema, document, context)
        if document["time_s"] < last_time:
            raise ContractError(f"{context}: time went backwards")
        last_time = document["time_s"]
        documents.append(document)
    return documents


@dataclass(frozen=True)
class LoadedRun:
    directory: Path
    manifest: JsonDict
    scenario: Scenario
    telemetry: list[JsonDict]
    commands: list[JsonDict]
    events: list[JsonDict]
    decisions: tuple[JsonDict, ...] = ()


def load_run(directory: Path, trusted: bool = False) -> LoadedRun:
    """Load a run, rejecting missing, tampered, truncated, or malformed files.

    Set trusted only for a run this process just wrote. It skips per-line schema checks, which
    dominate load time. Hashes and ordering are still checked.
    """
    manifest_path = directory / "run.json"
    if not manifest_path.is_file():
        raise ContractError(f"not a finished run, no run.json: {directory}")
    manifest = load_json_file(manifest_path)
    validate("run_manifest", manifest, "run.json")
    for key, name in LOG_FILES.items():
        path = directory / name
        if not path.is_file():
            raise ContractError(f"{directory}: missing {name}")
        if sha256_bytes(path.read_bytes()) != manifest["logs_sha256"][key]:
            raise ContractError(f"{path}: hash does not match run.json; the log was modified")
    scenario = build_scenario(
        load_json_file(directory / "scenario.json"),
        load_json_file(directory / "terrain.json"),
        load_json_file(directory / "rover.json"),
    )
    if scenario.inputs_sha256() != manifest["inputs_sha256"]:
        raise ContractError(f"{directory}: scenario files do not match run.json")
    logs = {
        key: _read_jsonl(directory / name, LOG_SCHEMAS[key], not trusted)
        for key, name in LOG_FILES.items()
    }
    events = logs["events"]
    for expected, event in enumerate(events):
        if event["seq"] != expected:
            raise ContractError(f"events.jsonl:{expected + 1}: event sequence is broken")
    if not events or events[-1]["type"] != "mission_ended":
        raise ContractError(f"{directory}: events do not end with mission_ended")
    decisions: list[JsonDict] = []
    if "decisions" in manifest["logs_sha256"]:
        path = directory / DECISIONS_FILE
        if not path.is_file():
            raise ContractError(f"{directory}: missing {DECISIONS_FILE}")
        if sha256_bytes(path.read_bytes()) != manifest["logs_sha256"]["decisions"]:
            raise ContractError(f"{path}: hash does not match run.json; the log was modified")
        decisions = _read_jsonl(path, "decision", not trusted)
    return LoadedRun(
        directory,
        manifest,
        scenario,
        logs["telemetry"],
        logs["commands"],
        logs["events"],
        tuple(decisions),
    )


def logs_digest(manifest: JsonDict) -> str:
    """Identify a run's behavior. Excludes wall-clock time and machine details."""
    return sha256_bytes(dump_json(manifest["logs_sha256"]).encode("utf-8"))
