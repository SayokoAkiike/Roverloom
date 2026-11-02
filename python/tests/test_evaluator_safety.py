"""Local evaluator behavior with hostile and broken submissions. The evaluator is NOT a sandbox.

These tests show the mock evaluator's limits work for what they cover. The last test documents
one way past the guard, so that nobody mistakes it for isolation.
"""

import hashlib
import json
import socket
import threading
import zipfile
from pathlib import Path

import pytest

from roverloom.competition import (
    extract_submission,
    ingest,
    load_submission,
    mock_submission,
    score,
)
from roverloom.contract import ContractError, repo_root

SUBMISSION = repo_root() / "python" / "examples" / "submission"
HEADER = """
from roverloom.api import STOP, Action
"""
AGENT = (
    HEADER
    + """
class Agent:
    def reset(self, brief, seed):
        pass
    def act(self, observation):
        {body}
        return STOP
"""
)


def metadata(**changes: object) -> dict:
    return {
        "schema_version": 0,
        "name": "t",
        "authors": ["t"],
        "agent_class": "Agent",
        "league": "autonomy",
        **changes,
    }


def submit(tmp_path: Path, code: str, extra: dict[str, str] | None = None) -> Path:
    directory = tmp_path / "submission"
    directory.mkdir(exist_ok=True)
    (directory / "agent.py").write_text(code, encoding="utf-8")
    (directory / "metadata.json").write_text(json.dumps(metadata()), encoding="utf-8")
    for name, text in (extra or {}).items():
        (directory / name).write_text(text, encoding="utf-8")
    return directory


def reference(tmp_path: Path, seeds=(1,), scenarios=("science_sprint",)) -> Path:
    directory = tmp_path / "ref"
    directory.mkdir(exist_ok=True)
    (directory / "reference.json").write_text(
        json.dumps({"scenarios": list(scenarios), "seeds": list(seeds), "rover": "pathfinder_6w"}),
        encoding="utf-8",
    )
    return directory


def outcome(tmp_path: Path, code: str, limits: dict | None = None) -> str:
    return ingest(submit(tmp_path, code).resolve(), reference(tmp_path), tmp_path / "res")[0][
        "outcome"
    ]


def act(body: str) -> str:
    return AGENT.format(body=body)


def attempt(tmp_path: Path, statement: str, ref: Path | None = None) -> str:
    """Run a statement inside a mission, and report what the agent itself saw happen.

    A plain agent_error could also mean that the agent never started, so these tests check that
    the mission ran normally and that the guard's own exception was the result.
    """
    report = tmp_path / "submission" / "attempt.txt"
    code = (
        HEADER
        + f"""
class Agent:
    def reset(self, brief, seed):
        try:
            {statement}
            result = "allowed"
        except BaseException as error:
            result = type(error).__name__
        open({str(report)!r}, "w").write(result)
    def act(self, observation):
        return STOP
"""
    )
    summary = ingest(submit(tmp_path, code).resolve(), ref or reference(tmp_path), tmp_path / "res")
    assert summary[0]["outcome"] != "agent_error"
    return report.read_text(encoding="utf-8")


@pytest.fixture
def quick(monkeypatch):
    monkeypatch.setattr("roverloom.competition.REPLY_TIMEOUT_S", 3.0)


# Abnormal termination.
@pytest.mark.parametrize(
    "body",
    [
        "raise RuntimeError('crash during a mission')",
        "import os; os._exit(3)",
        "import sys; sys.exit(0)",
        "raise SystemExit(1)",
    ],
    ids=["exception", "hard-exit", "clean-exit", "system-exit"],
)
def test_agent_ending_abnormally_scores_as_an_error(tmp_path: Path, quick, body: str) -> None:
    assert outcome(tmp_path, act(body)) == "agent_error"


def test_crash_while_importing_scores_as_an_error(tmp_path: Path, quick) -> None:
    assert outcome(tmp_path, "this is not python") == "agent_error"


def test_missing_class_scores_as_an_error(tmp_path: Path, quick) -> None:
    assert outcome(tmp_path, "x = 1\n") == "agent_error"


# Time limits.
def test_slow_reply_is_stopped(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("roverloom.competition.REPLY_TIMEOUT_S", 1.0)
    assert outcome(tmp_path, act("import time; time.sleep(30)")) == "agent_error"


def test_total_thinking_time_is_limited(tmp_path: Path, monkeypatch) -> None:
    # Each reply stays inside its limit, so only the total budget can stop this agent.
    monkeypatch.setattr("roverloom.competition.REPLY_TIMEOUT_S", 2.0)
    monkeypatch.setattr("roverloom.competition.TOTAL_THINKING_S", 1.5)
    assert outcome(tmp_path, act("import time; time.sleep(0.3)")) == "agent_error"


def test_slow_trickle_cannot_keep_a_reply_alive(tmp_path: Path, monkeypatch) -> None:
    # A timeout per read would let this stretch to hours. The limit is per whole message.
    monkeypatch.setattr("roverloom.competition.REPLY_TIMEOUT_S", 1.5)
    code = """
import socket, time
_send = socket.socket.sendall
def slow(self, data):
    for piece in data:
        _send(self, bytes([piece]))
        time.sleep(0.2)
socket.socket.sendall = slow
""" + act("pass")
    assert outcome(tmp_path, code) == "agent_error"


# Invalid actions.
@pytest.mark.parametrize(
    "line",
    [
        "not json at all",
        '{"type": "action"}',
        '{"type": "action", "body": {"linear_velocity_mps": 1}}',
        '{"type": "action", "body": {"schema_version": 0, "linear_velocity_mps": "fast", "yaw_rate_radps": 0}}',
        '{"type": "action", "body": {"schema_version": 0, "linear_velocity_mps": NaN, "yaw_rate_radps": 0}}',
        '{"type": "action", "body": {"schema_version": 0, "linear_velocity_mps": 1e999, "yaw_rate_radps": 0}}',
        '{"type": "wrong", "body": {}}',
        '{"type": "action", "body": {"schema_version": 0, "linear_velocity_mps": 0, "yaw_rate_radps": 0, "extra": 1}}',
    ],
    ids=["text", "no-body", "partial", "string", "nan", "infinite", "wrong-type", "extra-field"],
)
def test_invalid_action_on_the_wire_ends_the_mission_safely(
    tmp_path: Path, quick, line: str
) -> None:
    code = f"""
import socket
_send = socket.socket.sendall
def replace_reply(self, data):
    if b'"type":"action"' in data:
        data = {line!r}.encode() + b"\\n"
    _send(self, data)
socket.socket.sendall = replace_reply
""" + act("pass")
    assert outcome(tmp_path, code) == "agent_error"


def test_reply_of_the_wrong_python_type_is_an_error(tmp_path: Path, quick) -> None:
    code = (
        HEADER
        + """
class Agent:
    def reset(self, brief, seed):
        pass
    def act(self, observation):
        return "go fast"
"""
    )
    assert outcome(tmp_path, code) == "agent_error"


def test_huge_reply_is_refused(tmp_path: Path, quick) -> None:
    code = """
import socket
_send = socket.socket.sendall
socket.socket.sendall = lambda self, data: _send(self, b"x" * 3_000_000)
""" + act("pass")
    assert outcome(tmp_path, code) == "agent_error"


def test_over_limit_commands_are_clamped_not_obeyed(tmp_path: Path) -> None:
    code = (
        HEADER
        + """
class Agent:
    def reset(self, brief, seed):
        pass
    def act(self, observation):
        return Action(1000.0, 1000.0)
"""
    )
    directory = submit(tmp_path, code).resolve()
    ingest(directory, reference(tmp_path), tmp_path / "res")
    lines = (tmp_path / "res" / "science_sprint" / "seed-1" / "commands.jsonl").read_text(
        encoding="utf-8"
    )
    record = json.loads(lines.splitlines()[0])
    assert record["clamped"] is True
    assert record["applied"]["linear_velocity_mps"] < 1.0


# Invalid files.
def make_zip(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    path = tmp_path / "submission.zip"
    with zipfile.ZipFile(path, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    return path


@pytest.mark.parametrize(
    "name", ["native.pyd", "native.so", "cached.pyc", "tool.exe", "lib.dll", "script.bat"]
)
def test_compiled_and_executable_files_are_refused(tmp_path: Path, name: str) -> None:
    with pytest.raises(ContractError, match="not allowed"):
        extract_submission(make_zip(tmp_path, {name: b"\x00"}), tmp_path / "out")


def test_an_empty_archive_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ContractError):
        mock_submission(make_zip(tmp_path, {}), reference(tmp_path), tmp_path / "o")


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ({"agent.py": ""}, "metadata"),
        ({"metadata.json": json.dumps(metadata())}, "agent.py"),
        ({"agent.py": "", "metadata.json": "{not json"}, "metadata"),
        ({"agent.py": "", "metadata.json": "[]"}, "metadata"),
    ],
    ids=["no-metadata", "no-agent", "broken-metadata", "metadata-not-object"],
)
def test_malformed_submission_is_refused_before_running(tmp_path: Path, files, message) -> None:
    with pytest.raises(ContractError, match=message):
        mock_submission(make_zip(tmp_path, files), reference(tmp_path), tmp_path / "o")


def test_plain_rover_parameters_cannot_bypass_the_budgets(tmp_path: Path) -> None:
    directory = submit(tmp_path, act("pass"))
    plain = (repo_root() / "rovers" / "standard_6w.json").read_text(encoding="utf-8")
    (directory / "rover.json").write_text(plain, encoding="utf-8")
    (directory / "metadata.json").write_text(
        json.dumps(metadata(league="full_mission")), encoding="utf-8"
    )
    with pytest.raises(ContractError, match="must be a rover design"):
        load_submission(directory)


def test_over_budget_rover_design_is_refused(tmp_path: Path) -> None:
    directory = submit(tmp_path, act("pass"))
    design = json.loads(
        (repo_root() / "rovers" / "designs" / "pathfinder_6w.json").read_text(encoding="utf-8")
    )
    design["chassis_kg"] = 1500
    (directory / "rover.json").write_text(json.dumps(design), encoding="utf-8")
    (directory / "metadata.json").write_text(
        json.dumps(metadata(league="full_mission")), encoding="utf-8"
    )
    with pytest.raises(ContractError, match="exceeds"):
        load_submission(directory)


def test_unicode_and_odd_file_names_stay_inside(tmp_path: Path) -> None:
    root = extract_submission(
        make_zip(tmp_path, {"データ/メモ.txt": "x", "a b/c d.json": "{}"}), tmp_path / "out"
    )
    assert (root / "データ" / "メモ.txt").is_file()


# Resource use.
def test_memory_bomb_is_stopped_without_harming_the_evaluator(tmp_path: Path, quick) -> None:
    code = act("data = bytearray(8 * 1024 * 1024 * 1024); data[0] = 1")
    assert outcome(tmp_path, code) == "agent_error"
    # The evaluator itself carries on and can score the next submission.
    scores = mock_submission(SUBMISSION, reference(tmp_path), tmp_path / "next")
    assert scores["runs_scored"] == 1


def test_memory_limit_is_what_stops_the_bomb(tmp_path: Path) -> None:
    assert attempt(tmp_path, "bytearray(8 * 1024 * 1024 * 1024)") == "MemoryError"


def test_memory_limit_is_near_the_documented_size(tmp_path: Path) -> None:
    assert attempt(tmp_path, "bytearray(2 * 1024 * 1024 * 1024)") == "MemoryError"


def test_ordinary_memory_use_is_allowed(tmp_path: Path) -> None:
    assert attempt(tmp_path, "bytearray(64 * 1024 * 1024)") == "allowed"


def test_writing_outside_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "outside.bin"
    result = attempt(tmp_path, f"open({str(target)!r}, 'wb').write(b'x')")
    assert result == "GuardViolation"
    assert not target.exists()


def test_spawning_processes_is_refused(tmp_path: Path) -> None:
    statement = "import subprocess, sys; subprocess.run([sys.executable, '--version'])"
    assert attempt(tmp_path, statement) == "GuardViolation"


def test_os_system_is_refused(tmp_path: Path) -> None:
    assert attempt(tmp_path, "import os; os.system('echo hello')") == "GuardViolation"


def test_native_call_modules_are_refused(tmp_path: Path) -> None:
    assert attempt(tmp_path, "import ctypes") == "GuardViolation"


# Access to answers.
@pytest.mark.parametrize("target", ["reference", "public_scenario", "terrain", "results"])
def test_reading_answer_files_is_refused(tmp_path: Path, target: str) -> None:
    ref = reference(tmp_path)
    run_dir = tmp_path / "res" / "science_sprint" / "seed-1"
    paths = {
        "reference": ref / "reference.json",
        "public_scenario": repo_root() / "scenarios" / "practice" / "science_sprint.json",
        "terrain": repo_root() / "scenarios" / "terrains" / "flat_test.json",
        "results": run_dir / "events.jsonl",
    }
    assert attempt(tmp_path, f"open({str(paths[target])!r}).read()", ref) == "GuardViolation"


def test_low_level_open_of_answers_is_refused(tmp_path: Path) -> None:
    ref = reference(tmp_path)
    statement = f"import os; os.close(os.open({str(ref / 'reference.json')!r}, os.O_RDONLY))"
    assert attempt(tmp_path, statement, ref) == "GuardViolation"


def test_network_connections_are_refused(tmp_path: Path) -> None:
    listener = socket.create_server(("127.0.0.1", 0))
    listener.settimeout(1.0)
    port = listener.getsockname()[1]
    contacted: list[bool] = []

    def watch() -> None:
        try:
            listener.accept()
            contacted.append(True)
        except OSError:
            pass

    thread = threading.Thread(target=watch)
    thread.start()
    statement = f"import socket; socket.create_connection(('127.0.0.1', {port}), timeout=1)"
    try:
        assert attempt(tmp_path, statement) == "GuardViolation"
    finally:
        thread.join()
        listener.close()
    assert not contacted


def test_external_name_lookup_is_refused(tmp_path: Path) -> None:
    statement = "import socket; socket.create_connection(('example.com', 80), timeout=1)"
    assert attempt(tmp_path, statement) == "GuardViolation"


def test_guarded_agent_can_still_read_its_own_files(tmp_path: Path) -> None:
    code = act("import pathlib; open(pathlib.Path(__file__).with_name('table.json')).read()")
    directory = submit(tmp_path, code, {"table.json": "{}"})
    summary = ingest(directory.resolve(), reference(tmp_path), tmp_path / "res")
    assert summary[0]["outcome"] != "agent_error"


# Scenario leaks.
def test_hidden_seed_and_scenario_are_not_in_what_a_submission_receives(tmp_path: Path) -> None:
    capture = tmp_path / "submission" / "seen.txt"
    code = (
        HEADER
        + f"""
class Agent:
    def reset(self, brief, seed):
        self.out = open({str(capture)!r}, "a")
        self.out.write(f"seed={{seed}}\\n")
        self.out.write(str(brief.to_dict()))
    def act(self, observation):
        self.out.write(str(observation.to_dict()) + "\\n")
        self.out.flush()
        return STOP
"""
    )
    ref = reference(tmp_path, seeds=(424242,), scenarios=("hidden_one",))
    hidden = ref / "scenarios"
    hidden.mkdir()
    document = json.loads(
        (repo_root() / "scenarios" / "practice" / "science_sprint.json").read_text(encoding="utf-8")
    )
    document["scenario_id"] = "secret_name_xyz"
    document["mission"]["mission_id"] = "public_mission_name"
    document["mission"]["science"]["targets"][0]["true_value"] = 98.76
    document["faults"] = [{"type": "dust_storm", "start_time_s": 654.32, "duration_s": 5}]
    (hidden / "hidden_one.json").write_text(json.dumps(document), encoding="utf-8")
    ingest(submit(tmp_path, code).resolve(), ref, tmp_path / "res")
    seen = capture.read_text(encoding="utf-8")
    assert "seed=" in seen
    for secret in ("424242", "secret_name_xyz", "98.76", "654.32", "hidden_one"):
        assert secret not in seen, secret


def test_score_output_does_not_name_hidden_data(tmp_path: Path) -> None:
    ref = reference(tmp_path, seeds=(424242,))
    ingest(SUBMISSION.resolve(), ref, tmp_path / "res")
    score(ref, tmp_path / "res", tmp_path / "out")
    for name in ("scores.json", "errors.json"):
        assert "424242" not in (tmp_path / "out" / name).read_text(encoding="utf-8")


# Same submission, same result.
def digest(directory: Path) -> dict[str, str]:
    return {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in ("telemetry.jsonl", "events.jsonl", "commands.jsonl")
    }


def test_same_submission_reproduces_exactly(tmp_path: Path) -> None:
    ref = reference(tmp_path, seeds=(1, 2))
    first = mock_submission(SUBMISSION, ref, tmp_path / "a")
    second = mock_submission(SUBMISSION, ref, tmp_path / "b")
    assert first == second
    for seed in (1, 2):
        path = Path("input") / "res" / "science_sprint" / f"seed-{seed}"
        assert digest(tmp_path / "a" / path) == digest(tmp_path / "b" / path)


def test_directory_and_zip_of_one_submission_match(tmp_path: Path) -> None:
    ref = reference(tmp_path)
    archive = tmp_path / "s.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name in ("agent.py", "metadata.json"):
            bundle.write(SUBMISSION / name, name)
    assert mock_submission(SUBMISSION, ref, tmp_path / "a") == mock_submission(
        archive, ref, tmp_path / "b"
    )


# What this is not.
def test_guard_is_not_a_sandbox_a_few_lines_of_python_defeat_it(tmp_path: Path) -> None:
    """Documents a known hole. If this ever fails, update docs/evaluator-safety.md.

    The hook is ordinary Python in the same process as the agent, so the agent can replace what it
    relies on. This is why the mock evaluator must never run code from someone you do not trust.
    """
    secret = tmp_path / "secret.txt"
    secret.write_text("the answer", encoding="utf-8")
    statement = (
        "import roverloom.guard as g; g._within = lambda *a: True; "
        f"open('leak.txt', 'w').write(open({str(secret)!r}).read())"
    )
    assert attempt(tmp_path, statement) == "allowed"
    assert (tmp_path / "submission" / "leak.txt").read_text(encoding="utf-8") == "the answer"
