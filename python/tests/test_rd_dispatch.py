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
