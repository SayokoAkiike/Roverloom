"""The launcher must not turn a lost link or failed child into a successful mission."""

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[2] / "scripts" / "play_3d.py"
launch = runpy.run_path(str(LAUNCHER))


@pytest.mark.parametrize(
    "outcome,targets,expected",
    [("success", 1, 0), ("running", 0, 1), ("time_limit", 0, 1), ("success", 0, 1)],
)
def test_only_completed_arrival_returns_success(tmp_path, outcome, targets, expected):
    final = {"scenario": "g3_reach_target", "outcome": outcome, "targets_reached": targets}
    writer = "from pathlib import Path; import sys; Path(sys.argv[1]).write_text(sys.argv[2])"
    game = [sys.executable, "-c", "import time; time.sleep(120)"]
    link = [sys.executable, "-c", writer, str(tmp_path / "final_state.json"), json.dumps(final)]
    assert launch["supervise"](game, link, tmp_path, timeout=10) == expected


@pytest.mark.parametrize(
    "link", [[sys.executable, "-c", "raise SystemExit(3)"], [sys.executable, "-c", "pass"]]
)
def test_link_failure_or_missing_result_cleans_up_children(tmp_path, monkeypatch, link):
    children = []
    real_popen = subprocess.Popen

    def spawn(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", spawn)
    with pytest.raises((RuntimeError, FileNotFoundError)):
        launch["supervise"]([sys.executable, "-c", "import time; time.sleep(120)"], link, tmp_path)
    assert len(children) == 2 and all(child.poll() is not None for child in children)


def test_timeout_stops_both_owned_processes(tmp_path, monkeypatch):
    children = []
    real_popen = subprocess.Popen

    def spawn(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", spawn)
    sleeper = [sys.executable, "-c", "import time; time.sleep(120)"]
    with pytest.raises(RuntimeError, match="timed out"):
        launch["supervise"](sleeper, sleeper, tmp_path, timeout=0.01)
    assert all(child.poll() is not None for child in children)


def test_engine_path_with_spaces_stays_one_argument(tmp_path):
    engine = tmp_path / "Epic Games" / "UE_5.8"
    build, game, link = launch["commands"](engine, tmp_path / "run")
    assert build[0].startswith(str(engine)) and game[0].startswith(str(engine))
    assert game[2] == "/Engine/Maps/Entry?game=/Script/Roverloom.RoverPlaygroundGameMode"
    assert link[link.index("--port") + 1] == "8100"
    assert "-RoverDrive=play-g3" in game and "-RoverTutorial" in game


@pytest.fixture
def mac_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(launch["platform"], "system", lambda: "Darwin")
    build, game, _ = launch["commands"](tmp_path, tmp_path / "run")
    for name in (build[0], game[0]):
        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test tool, never executed")
        path.chmod(0o700)
    return tmp_path


def test_check_mode_never_builds_or_launches(mac_tools, monkeypatch):
    monkeypatch.setitem(launch["main"].__globals__, "PORT", 0)

    def forbidden(*args, **kwargs):
        raise AssertionError("preflight launched a process")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert launch["main"](["--ue-root", str(mac_tools), "--build", "--check"]) == 0


def test_occupied_port_is_refused_before_launch(mac_tools, monkeypatch):
    import socket

    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        monkeypatch.setitem(launch["main"].__globals__, "PORT", occupied.getsockname()[1])
        assert launch["main"](["--ue-root", str(mac_tools), "--check"]) == 2


def test_missing_engine_reports_error_without_launch(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(launch["platform"], "system", lambda: "Darwin")
    assert launch["main"](["--ue-root", str(tmp_path), "--check"]) == 2
    assert "Missing or non-executable Unreal tool" in capsys.readouterr().err


def test_supervisor_runs_real_mission_core_with_telemetry_stand_in(tmp_path):
    """Two real subprocesses and TCP; still not an Unreal rendering/input test."""
    import socket

    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    server_code = """
import json, socket, sys, time
server = socket.socket()
server.bind(("127.0.0.1", int(sys.argv[1])))
server.listen()
conn, _ = server.accept()
reader = conn.makefile("rb")
for i in range(1, 6):
    body = {"time_s": i * 0.5, "position_m": [i * 2.0, 0.0, 0.7]}
    conn.sendall((json.dumps({"type": "telemetry", "body": body}) + "\\n").encode())
    message = json.loads(reader.readline())
    if message["body"]["outcome"] != "running":
        break
time.sleep(30)
"""
    game = [sys.executable, "-c", server_code, str(port)]
    link = [
        sys.executable,
        "-m",
        "roverloom.unreal_link",
        "--scenario",
        "g3_reach_target",
        "--port",
        str(port),
        "--wait",
        "5",
        "--linger",
        "0",
        "--out",
        str(tmp_path),
    ]
    assert launch["supervise"](game, link, tmp_path, timeout=10) == 0
    final = json.loads((tmp_path / "final_state.json").read_text())
    assert final["outcome"] == "success"
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert any(event["type"] == "target_reached" for event in events)
