"""The command line and the local preview server, used the way people use them."""

import http.client
import json
import shutil
import threading
import time
from pathlib import Path

import pytest

from roverloom.cli import main
from roverloom.contract import repo_root
from roverloom.preview.server import LiveMission, make_server
from roverloom.world import load_scenario


def test_run_score_and_replay(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "r"
    assert (
        main(
            [
                "run",
                "--scenario",
                "example_reach_position",
                "--agent",
                "waypoint",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    assert "success" in capsys.readouterr().out
    assert main(["score", str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["success"] is True
    html = tmp_path / "view.html"
    assert main(["replay", str(out), "--at", "50", "--html", str(html)]) == 0
    printed = capsys.readouterr().out
    assert "At 50.0 s" in printed
    assert "fault_started" in printed
    assert "not the Unreal renderer" in html.read_text(encoding="utf-8")


def test_compare_writes_table_and_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main([
        "compare", "--scenarios", "example_reach_position", "--agents", "stop,waypoint",
        "--seeds", "1,2", "--out", str(tmp_path),
    ])  # fmt: skip
    assert code == 0
    printed = capsys.readouterr().out
    assert "waypoint" in printed
    rows = json.loads((tmp_path / "comparison.json").read_text(encoding="utf-8"))
    by_agent = {row["agent"]: row for row in rows}
    assert by_agent["waypoint"]["success_rate"] == 1.0
    assert by_agent["stop"]["success_rate"] == 0.0
    assert by_agent["waypoint"]["mean_score"] > by_agent["stop"]["mean_score"]
    assert (tmp_path / "report.html").is_file()


def test_report_cannot_be_broken_by_embedded_text(tmp_path: Path) -> None:
    out = tmp_path / "r"
    assert main(["run", "--scenario", "example_reach_position", "--agent", "stop",
                 "--out", str(out)]) == 0  # fmt: skip
    from roverloom.preview.report import viewer_html

    page = viewer_html({"mode": "report", "note": "</script><script>alert(1)</script>"})
    assert "</script><script>alert(1)" not in page


def test_plan_option(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(
        '{"schema_version":0,"steps":[{"skill":"go_to_next_target"}]}', encoding="utf-8"
    )
    assert main(["run", "--scenario", "example_reach_position", "--agent", "skill-plan",
                 "--plan", str(plan), "--out", str(tmp_path / "r")]) == 0  # fmt: skip


@pytest.mark.parametrize(
    "arguments",
    [
        ["run", "--scenario", "missing"],
        ["run", "--agent", "missing"],
        ["compare", "--seeds", "x"],
        ["compare", "--seeds", "-1"],
        ["replay", "does-not-exist"],
        ["score", "does-not-exist"],
        ["validate", "missing"],
    ],
)
def test_bad_input_gives_a_clean_error(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(arguments) == 2
    assert "error:" in capsys.readouterr().err


def test_validate_rejects_a_broken_scenario_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = repo_root() / "scenarios" / "practice" / "boulder_gap.json"
    broken = tmp_path / "broken.json"
    shutil.copy(source, broken)
    broken.write_text(
        broken.read_text(encoding="utf-8").replace('"seed": 11', '"seed": "x"'), encoding="utf-8"
    )
    assert main(["validate", str(broken)]) == 2
    assert "seed" in capsys.readouterr().err


def test_private_scenario_uses_terrain_beside_it(tmp_path: Path) -> None:
    root = repo_root() / "scenarios"
    document = json.loads((root / "practice" / "boulder_gap.json").read_text(encoding="utf-8"))
    document["tier"] = "evaluation"
    document["mission"]["terrain_id"] = "hidden_terrain"
    terrain = json.loads((root / "terrains" / "flat_test.json").read_text(encoding="utf-8"))
    terrain["terrain_id"] = "hidden_terrain"
    (tmp_path / "terrains").mkdir()
    (tmp_path / "terrains" / "hidden_terrain.json").write_text(
        json.dumps(terrain), encoding="utf-8"
    )
    path = tmp_path / "hidden.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert load_scenario(str(path)).terrain.terrain_id == "hidden_terrain"


def test_no_evaluation_scenario_is_in_the_repository() -> None:
    for path in (repo_root() / "scenarios").glob("practice/*.json"):
        assert json.loads(path.read_text(encoding="utf-8")).get("tier", "practice") == "practice"


def test_benchmark_runs(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["benchmark", "--agents", "stop", "--steps", "50"]) == 0
    assert "steps/s" in capsys.readouterr().out


@pytest.fixture
def live(tmp_path: Path):
    mission = LiveMission(
        load_scenario("example_reach_position"), "waypoint", 1, tmp_path, speed=50.0
    )
    server = make_server(mission, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    mission.start()
    yield mission, server.server_address[1]
    server.shutdown()
    server.server_close()
    mission.stop()


def request(port: int, method: str, path: str, body: object = None, headers: dict | None = None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    send_headers = dict(headers or {})
    payload = None
    if body is not None:
        payload = json.dumps(body)
        send_headers.setdefault("Content-Type", "application/json")
    connection.request(method, path, payload, send_headers)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, data


def state(port: int) -> dict:
    return json.loads(request(port, "GET", "/api/state")[1])


def wait_for(condition, port: int, seconds: float = 15.0) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        current = state(port)
        if condition(current):
            return current
        time.sleep(0.05)
    raise AssertionError(f"condition not met: {current}")


def test_page_is_labelled_as_a_preview(live) -> None:
    _, port = live
    status, page = request(port, "GET", "/")
    assert status == 200
    assert b"not the Unreal renderer" in page


def test_manual_driving_moves_rover_through_the_same_path(live) -> None:
    _, port = live
    assert state(port)["source"] == "manual"
    command = {"schema_version": 0, "linear_velocity_mps": 0.5, "yaw_rate_radps": 0.0}
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and state(port)["x"] < 2:
        assert request(port, "POST", "/api/command", command)[0] == 200
        time.sleep(0.02)
    current = state(port)
    assert current["x"] >= 2
    assert current["commands"] > 0


def test_switching_to_agent_finishes_mission_and_saves_run(live, tmp_path: Path) -> None:
    _, port = live
    assert request(port, "POST", "/api/mode", {"source": "agent"})[0] == 200
    assert state(port)["source"] == "agent"
    finished = wait_for(lambda s: s["saved_to"], port, 30)
    assert finished["outcome"] == "success"
    assert finished["metrics"]["success"] is True
    assert main(["score", finished["saved_to"]]) == 0


def test_restart_starts_a_new_run(live) -> None:
    _, port = live
    command = {"schema_version": 0, "linear_velocity_mps": 0.5, "yaw_rate_radps": 0.0}
    request(port, "POST", "/api/command", command)
    before = wait_for(lambda s: s["t"] > 20, port)["t"]
    assert request(port, "POST", "/api/reset", {})[0] == 200
    assert state(port)["t"] < before  # At 50x, a loaded machine can pass a second immediately.


def test_abandoned_keyboard_stops_the_rover(live) -> None:
    mission, port = live
    command = {"schema_version": 0, "linear_velocity_mps": 0.5, "yaw_rate_radps": 0.0}
    request(port, "POST", "/api/command", command)
    # Input goes stale after 0.6 s of wall time, and then the rover is commanded to stop.
    time.sleep(1.0)
    wait_for(lambda s: s["speed"] == 0, port)


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/command", {"linear_velocity_mps": 1}),
        ("/api/command", {"schema_version": 0, "linear_velocity_mps": "fast", "yaw_rate_radps": 0}),
        ("/api/mode", {"source": "root"}),
        ("/api/mode", [1, 2]),
        ("/api/unknown", {}),
    ],
)
def test_bad_requests_are_refused(live, path: str, body: object) -> None:
    _, port = live
    assert request(port, "POST", path, body)[0] in (400, 404)


def test_wrong_content_type_is_refused(live) -> None:
    _, port = live
    status, _ = request(port, "POST", "/api/reset", {}, {"Content-Type": "text/plain"})
    assert status == 400


def test_oversized_body_is_refused(live) -> None:
    _, port = live
    assert request(port, "POST", "/api/command", {"x": "y" * 10000})[0] == 400


@pytest.mark.parametrize(
    "headers",
    [{"Host": "evil.example"}, {"Origin": "http://evil.example"}, {"Origin": "null"}],
)
def test_other_sites_are_refused(live, headers: dict) -> None:
    _, port = live
    assert request(port, "POST", "/api/reset", {}, headers)[0] == 403
    assert request(port, "GET", "/api/state", None, headers)[0] == 403


def test_invalid_speed_is_refused(tmp_path: Path) -> None:
    from roverloom.contract import ContractError

    with pytest.raises(ContractError):
        LiveMission(load_scenario("boulder_gap"), "stop", 1, tmp_path, speed=1000)


def test_quick_start_commands_exist() -> None:
    readme = (repo_root() / "README.md").read_text(encoding="utf-8")
    assert "uv run roverloom demo" in readme
    assert "uv run roverloom play" in readme


def test_default_port_moves_when_busy() -> None:
    import contextlib
    import socket

    from roverloom.preview.server import DEFAULT_PORT, _bind

    blocker = socket.socket()
    try:
        with contextlib.suppress(OSError):  # already busy elsewhere is the case under test
            blocker.bind(("127.0.0.1", DEFAULT_PORT))
        blocker.listen()
        server = _bind(None)
        try:
            assert server.server_address[1] != DEFAULT_PORT
        finally:
            server.server_close()
        with pytest.raises(OSError):
            _bind(DEFAULT_PORT)
    finally:
        blocker.close()
