"""The Mission Control API: what a browser, or later Unreal, relies on."""

import http.client
import json
import threading
import time
from pathlib import Path

import pytest

from roverloom.contract import validate
from roverloom.preview.server import LiveMission, make_server
from roverloom.world import load_scenario


@pytest.fixture
def live(tmp_path: Path):
    mission = LiveMission(
        load_scenario("science_sprint"), "mission-planner", 1, tmp_path, speed=50.0
    )
    server = make_server(mission, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    mission.start()
    yield mission, server.server_address[1]
    server.shutdown()
    server.server_close()
    mission.stop()


def request(port: int, method: str, path: str, body: object = None, headers: dict | None = None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    send = dict(headers or {})
    payload = None
    if body is not None:
        payload = json.dumps(body)
        send.setdefault("Content-Type", "application/json")
    connection.request(method, path, payload, send)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, data


def control(port: int) -> dict:
    return json.loads(request(port, "GET", "/api/state")[1])["control"]


def wait_for(port: int, condition, seconds: float = 30.0) -> dict:
    deadline = time.monotonic() + seconds
    current = control(port)
    while time.monotonic() < deadline:
        current = control(port)
        if condition(current):
            return current
        time.sleep(0.05)
    raise AssertionError(current)


def test_state_matches_the_published_contract(live) -> None:
    _, port = live
    validate("mission_control_state", control(port))
    wait_for(port, lambda c: c["time_s"] > 1)
    validate("mission_control_state", control(port))


def test_contract_holds_through_a_whole_autonomous_mission(live) -> None:
    _, port = live
    request(port, "POST", "/api/mode", {"source": "agent"})
    finished = wait_for(port, lambda c: c["saved_to"], 60)
    validate("mission_control_state", finished)
    assert finished["mission"]["outcome"] == "success"
    assert finished["mission"]["science_value"] > 0
    assert finished["metrics"]["success"] is True
    assert finished["decisions"], "the agent's decisions are shown"
    status, page = request(port, "GET", "/replay")
    assert status == 200
    assert b"Mission Control" in page


def test_replay_before_any_finished_run_is_404(live) -> None:
    _, port = live
    assert request(port, "GET", "/replay")[0] == 404


def test_options_list_real_choices(live) -> None:
    _, port = live
    options = json.loads(request(port, "GET", "/api/options")[1])
    assert "science_sprint" in options["scenarios"]
    assert "scout_4w" in options["rovers"]
    assert "cap-mock" in options["agents"]
    assert options["current"]["scenario"] == "science_sprint"


def test_configure_starts_a_new_mission(live) -> None:
    _, port = live
    body = {"scenario": "boulder_gap", "rover": "scout_4w", "agent": "reactive", "speed": 32}
    assert request(port, "POST", "/api/configure", body)[0] == 200
    state = control(port)
    assert state["mission"]["scenario_id"] == "boulder_gap"
    assert state["rover"]["rover_id"] == "scout_4w"
    assert state["agent"] == "reactive"
    world = json.loads(request(port, "GET", "/api/world")[1])
    assert world["terrain_id"] == "practice_boulder_wall"


@pytest.mark.parametrize(
    "change",
    [
        {"scenario": "../../secrets"},
        {"scenario": "C:/Windows/win.ini"},
        {"rover": "../../rovers/evil"},
        {"agent": "evil.py:Agent"},
        {"agent": "os:system"},
        {"speed": 9999},
        {"speed": "fast"},
    ],
)
def test_configure_accepts_only_published_choices(live, change: dict) -> None:
    mission, port = live
    body = {
        "scenario": "science_sprint",
        "rover": "pathfinder_6w",
        "agent": "stop",
        "speed": 4,
        **change,
    }
    before = mission.session
    assert request(port, "POST", "/api/configure", body)[0] == 400
    assert mission.session is before, "a refused request must not disturb the mission"


def test_stop_ends_the_mission_and_saves(live) -> None:
    _, port = live
    assert request(port, "POST", "/api/stop", {})[0] == 200
    state = control(port)
    assert state["mission"]["outcome"] == "aborted"
    assert state["saved_to"]
    assert request(port, "GET", "/replay")[0] == 200


def test_rerun_after_stop_gives_a_running_mission(live) -> None:
    _, port = live
    request(port, "POST", "/api/stop", {})
    request(port, "POST", "/api/reset", {})
    assert control(port)["mission"]["outcome"] == "running"
    assert control(port)["saved_to"] is None


def test_manual_task_goes_through_the_rover_checks(live) -> None:
    mission, port = live
    assert request(port, "POST", "/api/task", {"type": "inspect", "target_id": "near"})[0] == 200
    state = wait_for(port, lambda c: any(e["type"] == "task_rejected" for e in c["events"]))
    rejected = next(e for e in state["events"] if e["type"] == "task_rejected")
    assert rejected["data"]["reason"] == "out_of_range"


@pytest.mark.parametrize(
    "body",
    [{"type": "self_destruct"}, {"type": "inspect", "target_id": 5}, {"target_id": "near"}],
)
def test_bad_task_is_refused(live, body: dict) -> None:
    _, port = live
    assert request(port, "POST", "/api/task", body)[0] == 400


def test_approval_flow(tmp_path: Path) -> None:
    mission = LiveMission(
        load_scenario("science_sprint"), "human-approval", 1, tmp_path, speed=50.0
    )
    server = make_server(mission, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    mission.start()
    port = server.server_address[1]
    try:
        request(port, "POST", "/api/mode", {"source": "agent"})
        pending = wait_for(port, lambda c: c["pending_approval"], 40)["pending_approval"]
        assert pending in ("collect_sample", "transmit_data")
        assert request(port, "POST", "/api/approve", {"approved": True})[0] == 200
        wait_for(port, lambda c: c["pending_approval"] != pending or c["time_s"] > 690, 20)
    finally:
        server.shutdown()
        server.server_close()
        mission.stop()


def test_approve_without_an_approval_agent_is_refused(live) -> None:
    _, port = live
    assert request(port, "POST", "/api/approve", {"approved": True})[0] == 400


def test_decisions_are_saved_and_replayable(live) -> None:
    from roverloom.runlog import load_run

    _, port = live
    request(port, "POST", "/api/mode", {"source": "agent"})
    finished = wait_for(port, lambda c: c["saved_to"], 60)
    run = load_run(Path(finished["saved_to"]))
    assert run.decisions
    for decision in run.decisions:
        validate("decision", decision)


def test_refusing_a_request_never_resets_the_client(live) -> None:
    # Regression: replying without reading the body reset connections on Windows at random.
    _, port = live
    for _ in range(40):
        status, _body = request(
            port, "POST", "/api/reset", {"x": 1}, {"Content-Type": "text/plain"}
        )
        assert status == 400
    for _ in range(40):
        assert request(port, "POST", "/api/command", {"x": "y" * 10000})[0] == 400


def test_new_endpoints_also_refuse_other_sites(live) -> None:
    _, port = live
    for path, body in (
        ("/api/configure", {}),
        ("/api/task", {}),
        ("/api/stop", {}),
        ("/api/approve", {}),
    ):
        assert request(port, "POST", path, body, {"Origin": "http://evil.example"})[0] == 403
    assert request(port, "GET", "/replay", None, {"Host": "evil.example"})[0] == 403


def test_page_does_not_contain_hidden_science_values(live) -> None:
    _, port = live
    assert b"true_value" not in request(port, "GET", "/")[1]
    assert b"true_value" not in request(port, "GET", "/api/world")[1]
