"""G3 mission link against a stand-in for Unreal's loopback listener.

The stand-in plays the simulator's side: it listens, sends telemetry with a rover driving toward the
target, and reads the Mission Core's mission_state lines. The Mission Core alone judges the mission.
"""

import json
import socket
import threading
from pathlib import Path

from roverloom.unreal_link import run


def fake_unreal(server: socket.socket, positions: list[float], received: list[dict]) -> None:
    conn, _ = server.accept()
    with conn:
        reader = conn.makefile("rb")
        for i, x in enumerate(positions):
            body = {"time_s": round(0.5 * (i + 1), 3), "position_m": [x, 0.0, 0.7]}
            conn.sendall((json.dumps({"type": "telemetry", "body": body}) + "\n").encode())
            received.append(json.loads(reader.readline()))


def run_against(tmp_path: Path, positions: list[float]) -> tuple[dict, list[dict], list[dict]]:
    server = socket.create_server(("127.0.0.1", 0))
    port = server.getsockname()[1]
    received: list[dict] = []
    thread = threading.Thread(target=fake_unreal, args=(server, positions, received))
    thread.start()
    final = run("g3_reach_target", "127.0.0.1", port, tmp_path, wait_s=5.0, linger_s=0.0)
    thread.join(timeout=10)
    server.close()
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    return final, received, events


def test_reaching_the_target_in_unreal_is_judged_success_by_the_mission_core(
    tmp_path: Path,
) -> None:
    final, received, events = run_against(tmp_path, [0.0, 2.0, 4.0, 5.0, 6.5, 8.0, 8.0])
    assert all(m["type"] == "mission_state" for m in received)
    assert received[0]["body"]["outcome"] == "running"
    assert final["targets_reached"] == 1 and final["outcome"] == "success"
    names = [e["type"] for e in events]
    assert "target_reached" in names and names[-1] == "mission_ended"


def test_short_of_the_target_stays_running(tmp_path: Path) -> None:
    final, received, events = run_against(tmp_path, [0.0, 1.0, 2.0, 3.0])
    assert final["targets_reached"] == 0 and final["outcome"] == "running"
    assert "target_reached" not in [e["type"] for e in events]


def test_the_link_refuses_a_non_loopback_host(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(Exception, match="loopback"):
        run("g3_reach_target", "192.0.2.1", 1, tmp_path, wait_s=0.0, linger_s=0.0)
