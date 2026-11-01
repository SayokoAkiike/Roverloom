"""The same inputs must give byte-identical logs, including across processes."""

import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from roverloom.agents import create_agent
from roverloom.bridge import RemoteAgent, run_client
from roverloom.contract import ContractError
from roverloom.runlog import logs_digest
from roverloom.runner import run_mission
from roverloom.world import load_scenario


def digest(tmp_path: Path, name: str, agent: str = "replanner", seed: int = 3) -> str:
    result = run_mission(
        load_scenario("demo_traverse"), create_agent(agent), agent, tmp_path / name, seed
    )
    return logs_digest(result.manifest)


@pytest.mark.parametrize("agent", ["waypoint", "reactive", "replanner"])
def test_same_seed_gives_identical_logs(tmp_path: Path, agent: str) -> None:
    assert digest(tmp_path, "a", agent) == digest(tmp_path, "b", agent)


def test_log_files_are_byte_identical(tmp_path: Path) -> None:
    digest(tmp_path, "a")
    digest(tmp_path, "b")
    for name in (
        "telemetry.jsonl",
        "commands.jsonl",
        "events.jsonl",
        "scenario.json",
        "terrain.json",
    ):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name


def test_different_seed_gives_different_logs(tmp_path: Path) -> None:
    assert digest(tmp_path, "a", seed=1) != digest(tmp_path, "b", seed=2)


def test_digest_ignores_time_and_machine_details(tmp_path: Path) -> None:
    first = run_mission(load_scenario("boulder_gap"), create_agent("stop"), "s", tmp_path / "a")
    second = run_mission(load_scenario("boulder_gap"), create_agent("stop"), "s", tmp_path / "b")
    assert logs_digest(first.manifest) == logs_digest(second.manifest)


@pytest.mark.parametrize("hash_seed", ["1", "2"])
def test_identical_across_processes_and_hash_seeds(tmp_path: Path, hash_seed: str) -> None:
    # Python randomizes string hashing per process, which would expose any set-order dependency.
    expected = digest(tmp_path, "local")
    out = tmp_path / f"process-{hash_seed}"
    environment = {**os.environ, "PYTHONHASHSEED": hash_seed}
    completed = subprocess.run(
        [sys.executable, "-m", "roverloom.cli", "run", "--scenario", "demo_traverse",
         "--agent", "replanner", "--seed", "3", "--out", str(out)],
        capture_output=True, encoding="utf-8", env=environment, check=True,
    )  # fmt: skip
    assert f"Digest:    {expected}" in completed.stdout


def test_faults_are_the_same_for_all_agents(tmp_path: Path) -> None:
    from roverloom.runlog import load_run

    def faults(agent: str, name: str) -> list[dict]:
        scenario = load_scenario("demo_traverse")
        directory = run_mission(scenario, create_agent(agent), agent, tmp_path / name, 5).directory
        run = load_run(directory, trusted=True)
        return [e["data"] for e in run.events if e["type"] == "fault_started"]

    # A shorter run may stop earlier, so compare the shared prefix.
    first, second = faults("stop", "a"), faults("replanner", "b")
    shared = min(len(first), len(second))
    assert shared >= 3
    assert first[:shared] == second[:shared]


def _bridge_digest(tmp_path: Path, name: str) -> str:
    remote = RemoteAgent()
    client_errors: list[Exception] = []

    def client() -> None:
        try:
            run_client(create_agent("replanner"), remote.port)
        except Exception as error:
            client_errors.append(error)

    thread = threading.Thread(target=client)
    thread.start()
    try:
        result = run_mission(load_scenario("demo_traverse"), remote, "bridge", tmp_path / name, 3)
    finally:
        remote.close()
        thread.join(timeout=30)
    assert not client_errors
    return logs_digest(result.manifest)


def test_bridge_runs_are_repeatable(tmp_path: Path) -> None:
    # Bridge messages are rounded to six decimals, so bridge runs are compared with each other.
    assert _bridge_digest(tmp_path, "a") == _bridge_digest(tmp_path, "b")


def test_bridge_refuses_non_loopback() -> None:
    with pytest.raises(ContractError, match="loopback"):
        RemoteAgent(host="0.0.0.0")
    with pytest.raises(ContractError, match="loopback"):
        run_client(create_agent("stop"), 1, host="example.com")


def test_bridge_rejects_bad_client_messages(tmp_path: Path) -> None:
    import socket

    remote = RemoteAgent(timeout_s=10)
    scenario = load_scenario("example_reach_position")

    def bad_client() -> None:
        with socket.create_connection(("127.0.0.1", remote.port)) as connection:
            connection.recv(65536)
            connection.recv(65536)
            connection.sendall(b'{"type":"action","body":{"linear_velocity_mps":"fast"}}\n')
            connection.recv(65536)

    thread = threading.Thread(target=bad_client)
    thread.start()
    try:
        result = run_mission(scenario, remote, "bad", tmp_path / "r")
    finally:
        remote.close()
        thread.join(timeout=15)
    assert result.metrics.outcome == "agent_error"
