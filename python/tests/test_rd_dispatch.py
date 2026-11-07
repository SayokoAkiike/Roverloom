"""Tests for the Mac mini dispatcher's stop logic, run against throwaway child processes only.

The dispatcher is loaded from a copy in tmp_path with the repository's charter beside it, as it is installed.
"""

import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def dispatch(tmp_path: Path):
    shutil.copy(ROOT / "rd" / "mini" / "dispatch.py", tmp_path / "dispatch.py")
    charter = json.loads((ROOT / "rd" / "charter.json").read_text())
    charter["mini"]["graceful_stop_wait_s"] = 2
    (tmp_path / "charter.json").write_text(json.dumps(charter))
    spec = importlib.util.spec_from_file_location("dispatch_under_test", tmp_path / "dispatch.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def child(code: str) -> subprocess.Popen:
    proc = subprocess.Popen([sys.executable, "-c", code], start_new_session=True)
    return proc


READY = "import signal, time\n"


def test_child_that_exits_on_sigint(dispatch) -> None:
    proc = child(READY + "time.sleep(60)")
    assert dispatch.stop_gracefully(proc.pid, proc) == "exited"
    assert proc.poll() is not None


def test_child_that_ignores_sigint_and_sigterm_is_killed(dispatch) -> None:
    proc = child(
        READY
        + "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
        + "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        + "time.sleep(120)"
    )
    time.sleep(0.5)  # let the child install its handlers
    assert dispatch.stop_gracefully(proc.pid, proc) == "killed"
    assert proc.poll() is not None


def test_already_exited_child_is_not_an_error(dispatch) -> None:
    proc = child("pass")
    time.sleep(0.5)  # exited but not reaped: a zombie
    assert dispatch.stop_gracefully(proc.pid, proc) in ("gone", "exited")


def test_preflight_refuses_while_a_forbidden_process_runs_as_this_user(dispatch) -> None:
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", "OneDrive Sync Service stand-in"]
    )
    try:
        time.sleep(0.5)
        assert proc.pid in dispatch.night_user_forbidden_processes()
        with pytest.raises(dispatch.Refused, match="isolation"):
            dispatch.preflight()
    finally:
        proc.kill()
        proc.wait()
    assert proc.pid not in dispatch.night_user_forbidden_processes()


def test_own_parent_shell_is_not_a_forbidden_process(dispatch) -> None:
    """A shell whose command line merely mentions a forbidden name, and runs the check, is not flagged."""
    code = (
        "import importlib.util,sys;"
        f"s=importlib.util.spec_from_file_location('d',{str(dispatch.__file__)!r});"
        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
        "print(m.night_user_forbidden_processes())"
    )
    out = subprocess.run(
        ["/bin/sh", "-c", f'{sys.executable} -c "{code}" # OneDrive'],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert out == "[]"


def test_one_run_id_serves_every_step(dispatch, tmp_path: Path) -> None:
    dispatch.EVIDENCE = str(tmp_path / "evidence")
    first = dispatch.step_dir("n1-c1-hud", "build")
    again = dispatch.step_dir("n1-c1-hud", "build")
    game = dispatch.step_dir("n1-c1-hud", "game")
    assert [Path(p).name for p in (first, again, game)] == ["build", "build-2", "game"]
    assert Path(first).parent == Path(game).parent == tmp_path / "evidence" / "n1-c1-hud"
    with pytest.raises(dispatch.Refused, match="bad run id"):
        dispatch.step_dir("../x", "build")


def test_owner_at_the_mac_mini_defers_only_gpu_steps(dispatch, monkeypatch) -> None:
    monkeypatch.setattr(dispatch, "night_user_forbidden_processes", lambda: [])
    monkeypatch.setattr(dispatch, "foreign_unreal", lambda: [])
    monkeypatch.setattr(dispatch, "memory", lambda: {"free_pct": 80, "swap_used_mb": 0})
    monkeypatch.setattr(dispatch, "OWNER_OVERRIDE", False)
    monkeypatch.setattr(dispatch, "owner_idle_s", lambda: 5.0)
    dispatch.preflight()  # build and test: allowed
    assert dispatch.niced(["x"])[:3] == ["/usr/sbin/taskpolicy", "-c", "utility"]
    with pytest.raises(dispatch.Refused, match="games and the editor wait"):
        dispatch.preflight(gpu=True)
    monkeypatch.setattr(dispatch, "owner_idle_s", lambda: 10_000.0)
    dispatch.preflight(gpu=True)
    assert dispatch.niced(["x"]) == ["x"]


def test_an_owner_unreal_process_refuses_every_step(dispatch, monkeypatch) -> None:
    monkeypatch.setattr(dispatch, "night_user_forbidden_processes", lambda: [])
    monkeypatch.setattr(dispatch, "foreign_unreal", lambda: [(123, "UnrealEditor")])
    with pytest.raises(dispatch.Refused, match="did not start"):
        dispatch.preflight()
