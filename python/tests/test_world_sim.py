"""Scenario checks and the behavior of the lightweight models. Tests behavior, not realism."""

import math
import random

import pytest
from conftest import MakeScenario

from roverloom.api import Action, Pose
from roverloom.contract import ContractError
from roverloom.sim import CommLink, RoverSim, Sensors, build_fault_schedule
from roverloom.world import load_scenario

DT = 0.1
GO = Action(0.5, 0.0)


def drive(sim: RoverSim, action: Action, seconds: float) -> None:
    for _ in range(round(seconds / DT)):
        sim.step(action, DT)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"mission": {"objectives": [{"type": "reach_position", "position_m": [999, 0, 0], "radius_m": 2}]}}, "outside"),
        ({"mission": {"start_pose": {"position_m": [999, 0, 0], "orientation_xyzw": [0, 0, 0, 1]}}}, "start is outside"),
        ({"mission": {"start_pose": {"position_m": [0, 0, 0], "orientation_xyzw": [0, 0, 0, 3]}}}, "unit quaternion"),
        ({"mission": {"terrain_id": "other"}}, "terrain does not match"),
        ({"mission": {"time_limit_s": -1}}, "time_limit_s"),
        ({"scenario": {"seed": -1}}, "seed"),
        ({"scenario": {"comms": {"latency_s": 0.1, "loss_probability": 2}}}, "loss_probability"),
        ({"scenario": {"faults": [{"type": "comm_blackout", "start_time_s": 1}]}}, "faults"),
        ({"rover": {"mass_kg": 0}}, "mass_kg"),
        ({"rover": {"rover_id": "other"}}, "rover does not match"),
        ({"terrain": {"extent_m": {"min_xy": [5, 5], "max_xy": [0, 0]}}}, "extent"),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)  # fmt: skip
def test_invalid_configuration_is_rejected(
    make_scenario: MakeScenario, changes: dict, message: str
) -> None:
    with pytest.raises(ContractError, match=message):
        make_scenario(**changes)


def test_target_inside_rock_is_rejected(make_scenario: MakeScenario) -> None:
    rocks = {"explicit": [{"center_xy": [20, 0], "radius_m": 3}]}
    with pytest.raises(ContractError, match="inside a rock"):
        make_scenario(terrain={"rocks": rocks})


def test_unknown_scenario_is_rejected() -> None:
    with pytest.raises(ContractError, match="not found"):
        load_scenario("no_such_scenario")


def test_terrain_generation_is_deterministic() -> None:
    first, second = load_scenario("demo_traverse").terrain, load_scenario("demo_traverse").terrain
    assert first.heights == second.heights
    assert first.rocks == second.rocks


def test_rover_drives_forward_and_accelerates(make_scenario: MakeScenario) -> None:
    sim = RoverSim(make_scenario(), 1)
    sim.step(GO, DT)
    assert sim.state.wheel_speed_mps == pytest.approx(0.25 * DT)
    drive(sim, GO, 10)
    assert sim.state.wheel_speed_mps == pytest.approx(0.5)
    assert sim.state.pose.x_m > 3
    assert abs(sim.state.pose.y_m) < 1e-9


def test_yaw_rate_sign_is_counterclockwise(make_scenario: MakeScenario) -> None:
    sim = RoverSim(make_scenario(), 1)
    drive(sim, Action(0.0, 0.5), 2)
    assert sim.state.pose.yaw_rad > 0


def test_speed_never_exceeds_limit_even_if_commanded(make_scenario: MakeScenario) -> None:
    sim = RoverSim(make_scenario(), 1)
    drive(sim, Action(100.0, 0.0), 20)
    assert sim.state.wheel_speed_mps <= 0.5 + 1e-9


def test_rock_stops_rover_without_penetration(make_scenario: MakeScenario) -> None:
    rocks = {"explicit": [{"center_xy": [6, 0], "radius_m": 2}]}
    scenario = make_scenario(terrain={"rocks": rocks})
    sim = RoverSim(scenario, 1)
    hits = [sim.step(GO, DT) for _ in range(400)]
    assert any(hits)
    assert sim.state.wheel_speed_mps < 0.05
    assert math.hypot(sim.state.pose.x_m - 6, sim.state.pose.y_m) >= 2 + 1.2


def test_boundary_stops_rover(make_scenario: MakeScenario) -> None:
    terrain = {"extent_m": {"min_xy": [-10, -10], "max_xy": [30, 10]}}
    sim = RoverSim(make_scenario(terrain=terrain), 1)
    drive(sim, GO, 200)
    assert sim.state.pose.x_m <= 30 - 1.2


def test_failed_wheels_reduce_speed_and_pull_toward_their_side(make_scenario: MakeScenario) -> None:
    sim = RoverSim(make_scenario(), 1)
    sim.fail_wheel("middle_left")
    drive(sim, GO, 20)
    assert sim.state.wheel_speed_mps == pytest.approx(0.5 * 5 / 6)
    assert sim.state.pose.y_m > 0.1  # Left drive failure yields positive yaw in this model.


def test_soft_soil_increases_slip_and_shortens_distance(make_scenario: MakeScenario) -> None:
    firm = RoverSim(make_scenario(), 1)
    soft_terrain = {"soft_soil": [{"center_xy": [0, 0], "radius_m": 50, "slip_fraction": 0.5}]}
    soft = RoverSim(make_scenario(terrain=soft_terrain), 1)
    drive(firm, GO, 20)
    drive(soft, GO, 20)
    assert soft.state.slip_fraction > firm.state.slip_fraction
    assert soft.state.pose.x_m < firm.state.pose.x_m * 0.7


def test_energy_is_used_when_idle_and_more_when_driving(make_scenario: MakeScenario) -> None:
    idle, moving = RoverSim(make_scenario(), 1), RoverSim(make_scenario(), 1)
    drive(idle, Action(0, 0), 10)
    drive(moving, GO, 10)
    assert idle.state.energy_used_wh == pytest.approx(300 * 10 / 3600)
    assert moving.state.energy_used_wh > idle.state.energy_used_wh


def test_steep_slope_stalls_rover() -> None:
    scenario = load_scenario("demo_traverse")
    sim = RoverSim(scenario, 1)
    # A direct check of the rule: at the climb limit, the reachable speed is zero.
    sim._terrain.slope_along = lambda *_: 0.6  # type: ignore[method-assign]
    drive(sim, GO, 5)
    assert sim.state.wheel_speed_mps == 0


def test_battery_never_goes_negative(make_scenario: MakeScenario) -> None:
    sim = RoverSim(make_scenario(rover={"battery_capacity_wh": 0.01}), 1)
    drive(sim, GO, 30)
    assert sim.state.battery_wh == 0.0


def test_comm_link_delays_messages(make_scenario: MakeScenario) -> None:
    link: CommLink[str] = CommLink(1.0, 0.0, random.Random(1))
    assert link.send(0.0, "a", False)
    assert link.receive(0.9, False) == []
    assert link.receive(1.0, False) == ["a"]


def test_comm_link_drops_during_blackout() -> None:
    link: CommLink[str] = CommLink(1.0, 0.0, random.Random(1))
    assert not link.send(0.0, "lost at sending", True)
    assert link.send(0.0, "lost in flight", False)
    assert link.receive(1.0, True) == []
    assert link.receive(2.0, False) == []


def test_comm_link_loss_probability_is_roughly_honored() -> None:
    link: CommLink[int] = CommLink(0.0, 0.25, random.Random(3))
    sent = sum(link.send(0.0, i, False) for i in range(4000))
    assert 2850 < sent < 3150


def test_sensor_noise_is_applied_and_seeded(make_scenario: MakeScenario) -> None:
    noisy = {
        "pose_noise_m": 0.5,
        "yaw_noise_rad": 0.1,
        "speed_noise_mps": 0.1,
        "range_noise_m": 0.1,
    }
    scenario = make_scenario(scenario={"sensors": noisy})
    state = RoverSim(scenario, 1).state
    first = Sensors(scenario, 9).observe(0.0, state, 0, True)
    second = Sensors(scenario, 9).observe(0.0, state, 0, True)
    third = Sensors(scenario, 10).observe(0.0, state, 0, True)
    assert first == second
    assert first.estimated_pose != third.estimated_pose
    assert first.estimated_pose != state.pose


def test_scan_sees_rock_only_in_range_and_not_during_dropout(make_scenario: MakeScenario) -> None:
    rocks = {
        "explicit": [{"center_xy": [8, 0], "radius_m": 2}, {"center_xy": [40, 0], "radius_m": 2}]
    }
    scenario = make_scenario(terrain={"rocks": rocks})
    state = RoverSim(scenario, 1).state
    sensors = Sensors(scenario, 1)
    ahead = [r for r in sensors.observe(0, state, 0, True).range_scan if abs(r.bearing_rad) < 0.2]
    assert all(r.range_m == pytest.approx(6.2, abs=0.2) for r in ahead)
    assert all(r.range_m is None for r in sensors.observe(0, state, 0, False).range_scan)


def test_ray_ignores_rock_behind(make_scenario: MakeScenario) -> None:
    rocks = {"explicit": [{"center_xy": [-8, 0], "radius_m": 2}]}
    terrain = make_scenario(terrain={"rocks": rocks}).terrain
    assert terrain.cast_ray(0, 0, 0, 12) is None


def test_random_faults_depend_only_on_seed_and_stay_in_time(make_scenario: MakeScenario) -> None:
    generators = [{"type": "wheel_drive_failure", "rate_per_hour": 120}]
    scenario = make_scenario(scenario={"fault_generators": generators})
    first = build_fault_schedule(scenario, 1)
    assert first == build_fault_schedule(scenario, 1)
    assert first != build_fault_schedule(scenario, 2)
    assert first
    assert all(0 <= f.start_time_s < 120 and f.wheel for f in first)


def test_fault_generator_respects_max_count(make_scenario: MakeScenario) -> None:
    generators = [{"type": "comm_blackout", "rate_per_hour": 3600, "max_count": 2, "duration_s": 1}]
    scenario = make_scenario(scenario={"fault_generators": generators})
    assert len(build_fault_schedule(scenario, 1)) == 2


def test_pose_helpers(make_scenario: MakeScenario) -> None:
    assert make_scenario().start_pose == Pose(0, 0, 0, 0)
