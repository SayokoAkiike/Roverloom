"""Frames, units, timing, and a stand-in backend that works internally the way Unreal does.

No Unreal Engine is involved. The stand-in shows that the contract is sufficient for a backend with
left-handed centimeters inside, and that Python's agents and evaluator work with it unchanged.
"""

import contextlib
import json
import math
import random
import socket
import threading
import time
from pathlib import Path

import pytest
from conftest import MakeScenario

from roverloom.agents import create_agent
from roverloom.api import STOP, Action, Observation, Pose, RangeReading
from roverloom.bridge import PROTOCOL_VERSION, RealtimeCommandLink, RemoteAgent, run_client
from roverloom.command import WATCHDOG_TIMEOUT_S, CommandRouter
from roverloom.conformance import check_run_contract
from roverloom.contract import ContractError, dump_json, load_json_file, repo_root, validate
from roverloom.evaluate import evaluate_run
from roverloom.frames import (
    FRAME_NAME,
    enu_to_ned_quat,
    enu_to_ned_vector,
    enu_yaw_to_ned_heading,
    golden_vectors,
    ned_to_enu_quat,
    quat_multiply,
    quat_rotate,
    quat_to_yaw,
    site_to_unreal_angular_velocity,
    site_to_unreal_position,
    site_to_unreal_quat,
    site_yaw_rate_to_unreal,
    site_yaw_to_unreal_degrees,
    unreal_to_site_position,
    unreal_to_site_quat,
    unreal_yaw_degrees_to_site,
    yaw_to_quat,
)
from roverloom.runlog import RunWriter, load_run
from roverloom.runner import run_mission
from roverloom.world import SIM_STEP_S, load_scenario

VECTORS = repo_root() / "schemas" / "conformance" / "frame_vectors.json"
rng = random.Random(7)


def random_quaternion() -> tuple[float, float, float, float]:
    values = [rng.gauss(0, 1) for _ in range(4)]
    norm = math.sqrt(sum(v * v for v in values))
    x, y, z, w = (v / norm for v in values)
    return (x, y, z, w)


def random_vector() -> tuple[float, float, float]:
    return (rng.uniform(-9, 9), rng.uniform(-9, 9), rng.uniform(-9, 9))


def close(a, b, tolerance: float = 1e-9) -> bool:
    return all(abs(x - y) <= tolerance for x, y in zip(a, b, strict=True))


# Units and axes.
def test_one_meter_east_north_up_in_unreal() -> None:
    assert site_to_unreal_position((1, 0, 0)) == (100, 0, 0)
    assert site_to_unreal_position((0, 1, 0)) == (0, -100, 0)
    assert site_to_unreal_position((0, 0, 1)) == (0, 0, 100)


def test_one_meter_east_north_up_in_ned() -> None:
    assert enu_to_ned_vector((1, 0, 0)) == (0, 1, 0)
    assert enu_to_ned_vector((0, 1, 0)) == (1, 0, 0)
    assert enu_to_ned_vector((0, 0, 1)) == (0, 0, -1)


@pytest.mark.parametrize("_", range(20))
def test_conversions_round_trip(_: int) -> None:
    v, q = random_vector(), random_quaternion()
    assert close(unreal_to_site_position(site_to_unreal_position(v)), v)
    assert close(enu_to_ned_vector(enu_to_ned_vector(v)), v)
    assert close(unreal_to_site_quat(site_to_unreal_quat(q)), q)
    assert close(ned_to_enu_quat(enu_to_ned_quat(q)), q)


# Rotations must act consistently with positions, in every frame.
@pytest.mark.parametrize("_", range(30))
def test_unreal_rotation_matches_the_mirrored_position(_: int) -> None:
    q, v = random_quaternion(), random_vector()
    site = quat_rotate(q, v)
    unreal = quat_rotate(site_to_unreal_quat(q), site_to_unreal_position(v))
    assert close(unreal, site_to_unreal_position(site), 1e-7)


@pytest.mark.parametrize("_", range(30))
def test_ned_rotation_matches_with_an_frd_body(_: int) -> None:
    q, body_flu = random_quaternion(), random_vector()
    site = quat_rotate(q, body_flu)
    body_frd = (body_flu[0], -body_flu[1], -body_flu[2])
    assert close(quat_rotate(enu_to_ned_quat(q), body_frd), enu_to_ned_vector(site), 1e-9)


def test_yaw_signs_and_units() -> None:
    assert site_yaw_to_unreal_degrees(math.pi / 2) == pytest.approx(-90)
    assert unreal_yaw_degrees_to_site(-90) == pytest.approx(math.pi / 2)
    assert site_yaw_rate_to_unreal(0.5) == -0.5  # Turning left in both, written with opposite sign.
    # A rover yawed left of east points toward +Y in the site frame, and -Y in Unreal.
    forward = quat_rotate(yaw_to_quat(0.5), (1, 0, 0))
    assert forward[1] > 0 and site_to_unreal_position(forward)[1] < 0


def test_ned_heading_cases() -> None:
    assert enu_yaw_to_ned_heading(0.0) == pytest.approx(math.pi / 2)  # East.
    assert enu_yaw_to_ned_heading(math.pi / 2) == pytest.approx(0.0)  # North.
    assert enu_yaw_to_ned_heading(math.pi) == pytest.approx(1.5 * math.pi)  # West.


def test_ned_quaternion_agrees_with_ned_heading() -> None:
    for degrees in (0, 20, 90, 135, -60):
        yaw = math.radians(degrees)
        heading = quat_to_yaw(enu_to_ned_quat(yaw_to_quat(yaw)))
        assert (heading % (2 * math.pi)) == pytest.approx(enu_yaw_to_ned_heading(yaw), abs=1e-9)


def test_angular_velocity_conversion_matches_quaternion_change() -> None:
    q, omega = random_quaternion(), (0.2, -0.3, 0.4)
    dt = 1e-5
    half = (omega[0] * dt / 2, omega[1] * dt / 2, omega[2] * dt / 2, 1.0)
    after = quat_multiply(half, q)  # A rotation about omega, expressed in the outer frame.
    unreal_omega = site_to_unreal_angular_velocity(omega)
    half_ue = (unreal_omega[0] * dt / 2, unreal_omega[1] * dt / 2, unreal_omega[2] * dt / 2, 1.0)
    assert close(quat_multiply(half_ue, site_to_unreal_quat(q)), site_to_unreal_quat(after), 1e-9)


def test_golden_vectors_are_committed_and_current() -> None:
    assert load_json_file(VECTORS) == json.loads(json.dumps(golden_vectors()))


def test_golden_vectors_catch_the_classic_mistakes() -> None:
    data = load_json_file(VECTORS)
    north = next(c for c in data["position"] if c["site_m"] == [0.0, 1.0, 0.0])
    assert north["unreal_cm"] == [0.0, -100.0, 0.0]  # Not +100, and not -1.
    left = next(c for c in data["yaw"] if c["site_yaw_rad"] == pytest.approx(math.pi / 2))
    assert left["unreal_yaw_deg"] == pytest.approx(-90)  # Degrees, with the sign flipped.


def test_pose_serialization_uses_the_contract_quaternion_order() -> None:
    pose = Pose(1, 2, 3, math.pi / 2).to_dict()
    assert close(pose["orientation_xyzw"], yaw_to_quat(math.pi / 2), 1e-6)
    assert Pose.from_dict(pose).yaw_rad == pytest.approx(math.pi / 2, abs=1e-5)


# Time and commands.
def test_action_applies_after_the_round_trip_delay(make_scenario: MakeScenario, tmp_path) -> None:
    scenario = make_scenario(scenario={"comms": {"latency_s": 1.5, "loss_probability": 0.0}})
    result = run_mission(scenario, create_agent("waypoint"), "w", tmp_path / "r", 1)
    run = load_run(result.directory)
    # Sensed at t=0, down 1.5 s, decided, up 1.5 s: the earliest possible command is at 3 s.
    assert run.commands[0]["time_s"] == pytest.approx(3.0, abs=SIM_STEP_S)
    assert run.telemetry[0]["linear_velocity_mps"][0] == 0


def test_time_is_derived_from_whole_steps(make_scenario: MakeScenario, tmp_path) -> None:
    result = run_mission(make_scenario(), create_agent("waypoint"), "w", tmp_path / "r", 1)
    for index, record in enumerate(load_run(result.directory).telemetry, start=1):
        assert record["step"] == index
        assert record["time_s"] == pytest.approx(index * SIM_STEP_S, abs=1e-6)


def test_blackout_drops_commands_and_the_watchdog_stops_the_rover(
    make_scenario: MakeScenario, tmp_path
) -> None:
    scenario = make_scenario(
        scenario={"faults": [{"type": "comm_blackout", "start_time_s": 5, "duration_s": 10}]},
        mission={
            "objectives": [{"type": "reach_position", "position_m": [55, 0, 0], "radius_m": 1}]
        },
    )
    run = load_run(
        run_mission(scenario, create_agent("waypoint"), "w", tmp_path / "r", 1).directory
    )
    assert [e for e in run.events if e["type"] == "watchdog_stop"]
    # The watchdog fires at about 7 s, and the rover then needs a moment to slow down.
    during = [r for r in run.telemetry if 10.0 < r["time_s"] < 14.5]
    assert during and all(abs(r["linear_velocity_mps"][0]) < 0.01 for r in during)
    assert not [c for c in run.commands if 5.1 < c["time_s"] < 15.0]


def test_conformance_passes_for_the_lightweight_backend(tmp_path) -> None:
    result = run_mission(
        load_scenario("science_sprint"), create_agent("mission-planner"), "m", tmp_path / "r", 1
    )
    assert check_run_contract(result.directory) == []


# A stand-in backend. It simulates in Unreal's units, and converts only at the boundary.
class UnrealStandIn:
    """Keeps state like an engine would: centimeters, left-handed, yaw in degrees."""

    def __init__(self, convert_yaw_rate=site_yaw_rate_to_unreal, cm_per_m: float = 100.0) -> None:
        self.x_cm = self.y_cm = 0.0
        self.yaw_deg = 0.0
        self.convert_yaw_rate = convert_yaw_rate
        self.cm_per_m = cm_per_m
        self.speed_cmps = 0.0
        self.yaw_rate_degps = 0.0

    def apply(self, action: Action) -> None:
        self.speed_cmps = action.linear_velocity_mps * self.cm_per_m
        self.yaw_rate_degps = math.degrees(self.convert_yaw_rate(action.yaw_rate_radps))

    def step(self, dt: float) -> None:
        self.yaw_deg += self.yaw_rate_degps * dt
        # Unreal: yaw 0 faces +X, and positive yaw turns toward +Y.
        self.x_cm += self.speed_cmps * math.cos(math.radians(self.yaw_deg)) * dt
        self.y_cm += self.speed_cmps * math.sin(math.radians(self.yaw_deg)) * dt

    def contract_pose(self) -> Pose:
        x, y, z = unreal_to_site_position((self.x_cm, self.y_cm, 0.0))
        return Pose(x, y, z, unreal_yaw_degrees_to_site(self.yaw_deg))

    def contract_velocity(self) -> list[float]:
        yaw = unreal_yaw_degrees_to_site(self.yaw_deg)
        speed = self.speed_cmps / 100.0
        return [speed * math.cos(yaw), speed * math.sin(yaw), 0.0]


def run_stand_in(scenario, out: Path, agent_name: str, engine: UnrealStandIn) -> Path:
    """Run the Python agent over a real socket against the stand-in, writing contract logs."""
    remote = RemoteAgent(timeout_s=10.0)
    agent = create_agent(agent_name)
    thread = threading.Thread(target=run_client, args=(agent, remote.port), daemon=True)
    thread.start()
    brief = scenario.brief()
    remote.reset(brief, 1)
    writer = RunWriter(out)
    sequence = 0

    def event(time_s: float, kind: str, data: dict) -> None:
        nonlocal sequence
        writer.event(
            {"schema_version": 0, "seq": sequence, "time_s": time_s, "type": kind, "data": data}
        )
        sequence += 1

    event(0.0, "mission_started", {"scenario": scenario.scenario_id, "seed": 1})
    reached = 0
    every = round(brief.control_period_s / SIM_STEP_S)
    steps, outcome, limit = 0, "time_limit", float(scenario.mission["time_limit_s"])
    while steps * SIM_STEP_S < limit:
        now = steps * SIM_STEP_S
        pose = engine.contract_pose()
        if steps % every == 0:
            observation = Observation(
                time_s=now,
                estimated_pose=pose,
                battery_fraction=1.0,
                estimated_speed_mps=engine.speed_cmps / 100.0,
                targets_reached=reached,
                range_scan=(RangeReading(0.0, None),),
            )
            engine.apply(remote.act(observation))
        engine.step(SIM_STEP_S)
        steps += 1
        now = round(steps * SIM_STEP_S, 6)
        pose = engine.contract_pose()
        writer.telemetry(
            {
                "schema_version": 0,
                "step": steps,
                "time_s": now,
                "pose": pose.to_dict(),
                "linear_velocity_mps": [round(v, 6) for v in engine.contract_velocity()],
                "yaw_rate_radps": round(-math.radians(engine.yaw_rate_degps), 6),
                "slip_fraction": 0.0,
                "distance_m": 0.0,
                "battery_fraction": 1.0,
                "energy_used_wh": 0.0,
                "failed_wheels": [],
                "targets_reached": reached,
            }
        )
        target = scenario.targets[reached]
        if math.hypot(pose.x_m - target.x_m, pose.y_m - target.y_m) <= target.radius_m:
            event(now, "target_reached", {"index": reached})
            reached += 1
            if reached == len(scenario.targets):
                outcome = "success"
                break
    event(
        round(steps * SIM_STEP_S, 6),
        "mission_ended",
        {"outcome": outcome, "targets_reached": reached},
    )
    remote.close()
    thread.join(timeout=5)
    writer.finish(scenario, agent_name, 1, steps, 0.1, backend="unreal-stand-in-test")
    return out


LEFT_TARGET = {
    "objectives": [{"type": "reach_position", "position_m": [10, 15, 0], "radius_m": 1.5}],
    "time_limit_s": 150,
}


def test_stand_in_backend_reaches_a_target_on_the_left(
    make_scenario: MakeScenario, tmp_path
) -> None:
    scenario = make_scenario(mission=LEFT_TARGET)
    run = load_run(run_stand_in(scenario, tmp_path / "r", "waypoint", UnrealStandIn()))
    assert run.events[-1]["data"]["outcome"] == "success"
    assert run.manifest["backend"] == "unreal-stand-in-test"
    x, y, _ = run.telemetry[-1]["pose"]["position_m"]
    assert y > 10 and x > 5  # Toward the target, on the side the contract says.


def test_shared_evaluator_scores_the_stand_in_backend(
    make_scenario: MakeScenario, tmp_path
) -> None:
    scenario = make_scenario(mission=LEFT_TARGET)
    run = load_run(run_stand_in(scenario, tmp_path / "r", "waypoint", UnrealStandIn()))
    metrics = evaluate_run(run)
    assert metrics.success and metrics.score > 0
    assert check_run_contract(tmp_path / "r") == []


def test_a_wrong_yaw_sign_is_caught_by_the_mission(make_scenario: MakeScenario, tmp_path) -> None:
    # Without the sign flip the rover turns the wrong way. It must not be able to pass.
    engine = UnrealStandIn(convert_yaw_rate=lambda rate: rate)
    scenario = make_scenario(mission={**LEFT_TARGET, "time_limit_s": 40})
    run = load_run(run_stand_in(scenario, tmp_path / "r", "waypoint", engine))
    assert run.events[-1]["data"]["outcome"] != "success"


def test_a_centimeter_mistake_is_caught_by_conformance(
    make_scenario: MakeScenario, tmp_path
) -> None:
    # Velocity left in cm/s while position is converted: a hundredfold disagreement.
    class WrongUnits(UnrealStandIn):
        def contract_velocity(self) -> list[float]:
            return [value * 100.0 for value in super().contract_velocity()]

    scenario = make_scenario(mission={**LEFT_TARGET, "time_limit_s": 30})
    run_stand_in(scenario, tmp_path / "r", "waypoint", WrongUnits())
    assert any("units" in problem for problem in check_run_contract(tmp_path / "r"))


def test_a_mirrored_frame_is_caught_by_conformance(make_scenario: MakeScenario, tmp_path) -> None:
    # Pose uses Unreal's Y directly, without the mirror, but yaw is converted.
    class Mirrored(UnrealStandIn):
        def contract_pose(self) -> Pose:
            pose = super().contract_pose()
            return Pose(pose.x_m, -pose.y_m, pose.z_m, pose.yaw_rad)

    scenario = make_scenario(mission={**LEFT_TARGET, "time_limit_s": 30})
    run_stand_in(scenario, tmp_path / "r", "waypoint", Mirrored())
    problems = check_run_contract(tmp_path / "r")
    assert any("frame" in problem for problem in problems), problems


def test_manifest_declares_the_frame(tmp_path: Path) -> None:
    result = run_mission(
        load_scenario("science_sprint"), create_agent("stop"), "s", tmp_path / "r", 1
    )
    assert result.manifest["conventions"] == {
        "frame": FRAME_NAME,
        "quaternion": "xyzw",
        "body": "flu",
    }


# Protocol.
def test_start_message_declares_the_protocol_version(make_scenario: MakeScenario) -> None:
    remote = RemoteAgent(timeout_s=5.0)
    seen = {}

    def client() -> None:
        with socket.create_connection(("127.0.0.1", remote.port), timeout=5) as connection:
            seen["start"] = connection.makefile().readline()

    thread = threading.Thread(target=client)
    thread.start()
    remote.reset(make_scenario().brief(), 1)
    thread.join()
    remote.close()
    message = json.loads(seen["start"])
    assert message["type"] == "start"
    assert message["body"]["protocol_version"] == PROTOCOL_VERSION
    validate("mission_brief", message["body"]["brief"])


def test_client_refuses_a_different_protocol_version(make_scenario: MakeScenario) -> None:
    listener = socket.create_server(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    brief = make_scenario().brief().to_dict()

    def server() -> None:
        connection, _ = listener.accept()
        line = {"type": "start", "body": {"protocol_version": 99, "seed": 1, "brief": brief}}
        connection.sendall((dump_json(line) + "\n").encode())
        connection.close()

    thread = threading.Thread(target=server)
    thread.start()
    with pytest.raises(ContractError, match="protocol 99"):
        run_client(create_agent("stop"), port, timeout_s=5)
    thread.join()
    listener.close()


def test_committed_transcript_matches_the_contract() -> None:
    lines = (repo_root() / "schemas" / "conformance" / "bridge_transcript.jsonl").read_text(
        encoding="utf-8"
    )
    schemas = {"observation": "observation", "action": "action"}
    kinds = []
    for line in lines.splitlines():
        message = json.loads(line)
        kinds.append(message["type"])
        if message["type"] in schemas:
            validate(schemas[message["type"]], message["body"])
        elif message["type"] == "start":
            validate("mission_brief", message["body"]["brief"])
            assert message["body"]["protocol_version"] == PROTOCOL_VERSION
    assert kinds[0] == "start" and kinds[-1] == "end"
    assert {"observation", "action"} <= set(kinds)


# Real-time link safety, as Unreal will need. The game thread reads the latest command.
def connect_link(link: RealtimeCommandLink) -> socket.socket:
    client = socket.create_connection(("127.0.0.1", link.port), timeout=5)
    deadline = time.monotonic() + 5
    while not link.connected and time.monotonic() < deadline:
        time.sleep(0.01)
    assert link.connected
    return client


def send_action(client: socket.socket, speed: float) -> None:
    line = {"type": "action", "body": Action(speed, 0.0).to_dict()}
    client.sendall((dump_json(line) + "\n").encode())


def wait_until(condition, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_latest_command_wins_and_old_ones_are_dropped() -> None:
    with RealtimeCommandLink() as link:
        client = connect_link(link)
        for speed in (0.1, 0.2, 0.3):
            send_action(client, speed)
        assert wait_until(lambda: link.received == 3)
        assert link.take().linear_velocity_mps == 0.3
        assert link.take() is None  # Taken once. The watchdog decides what happens next.
        client.close()


def test_disconnect_is_reported_and_the_watchdog_stops_the_rover() -> None:
    router = CommandRouter(("external",), "external", 1.0, 1.0)
    with RealtimeCommandLink() as link:
        client = connect_link(link)
        send_action(client, 0.5)
        assert wait_until(lambda: link.received == 1)
        router.submit("external", link.take(), 0.0)
        assert router.current(0.5).linear_velocity_mps == 0.5
        client.close()
        assert wait_until(lambda: not link.connected)
        assert link.take() is None
        # No command arrives any more. Simulated time passes, and the rover must stop by itself.
        assert router.current(WATCHDOG_TIMEOUT_S - 0.1).linear_velocity_mps == 0.5
        assert router.current(WATCHDOG_TIMEOUT_S + 0.1) == STOP


@pytest.mark.parametrize(
    "raw",
    [b"not json\n", b'{"type": "observation", "body": {}}\n', b"\xff\xfe\n", b"x" * 1_100_000],
    ids=["text", "wrong-type", "not-utf8", "too-long"],
)
def test_bad_input_drops_the_client_and_is_recorded(raw: bytes) -> None:
    with RealtimeCommandLink() as link:
        client = connect_link(link)
        send_action(client, 0.4)
        assert wait_until(lambda: link.received == 1)
        link.take()
        with contextlib.suppress(OSError):
            client.sendall(raw)
        assert wait_until(lambda: not link.connected)
        assert link.last_error is not None
        assert link.take() is None
        client.close()


def test_a_new_client_can_connect_after_a_disconnect() -> None:
    with RealtimeCommandLink() as link:
        first = connect_link(link)
        first.close()
        assert wait_until(lambda: not link.connected)
        second = connect_link(link)
        send_action(second, 0.2)
        assert wait_until(lambda: link.received == 1)
        assert link.take().linear_velocity_mps == 0.2
        second.close()


def test_link_refuses_non_loopback_addresses() -> None:
    with pytest.raises(ContractError, match="loopback"):
        RealtimeCommandLink(host="0.0.0.0")


def test_rover_geometry_contract_for_backends() -> None:
    from roverloom.rover_builder import load_rover_document

    rover = load_rover_document("pathfinder_6w")
    validate("rover", rover)
    assert rover["geometry"]["frame"] == "body_flu"
    assert {"mass_kg", "max_speed_mps", "max_yaw_rate_radps", "body_radius_m"} <= set(rover)
    fronts = [w for w in rover["geometry"]["wheels"] if w["wheel_id"].startswith("front")]
    assert all(w["position_m"][0] > 0 for w in fronts)
