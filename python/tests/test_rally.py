"""Rally rules must remain explicit, replayable, and separate from benchmark scoring."""

import json
import math

import pytest

from roverloom.contract import ContractError
from roverloom.rally import Ghost, Rally, design_hash, garage, load_garage, stats


def tick(rally, t, x, y, speed=0, **extras):
    return rally.step({"time_s": t, "position_m": [x, y, 0.7], "forward_mps": speed, **extras})


def finish(r):
    tick(r, 1, 5, -3)
    for t in (1.5, 2, 2.5, 3):
        tick(r, t, 14, 0)
    for t in (3.5, 4):
        tick(r, t, 22, 0)
    return tick(r, 5, 0, 0)


def test_ordered_stops_and_finish():
    r = Rally(garage())
    assert tick(r, 0.5, 22, 0)["targets_reached"] == 0
    final = finish(r)
    assert final["outcome"] == "success" and final["targets_reached"] == 4
    assert final["drive_scale"] == 0
    assert tick(r, 6, 5, 7)["result_time_s"] == final["result_time_s"]
    assert len(r.samples) == 9


def test_safe_detour_also_counts():
    r = Rally(garage())
    tick(r, 1, 5, 7)
    assert r.reached == 1


def test_moving_through_supply_does_not_refuel():
    r = Rally(garage())
    tick(r, 1, 5, -3)
    tick(r, 2, 14, 0, 0.5)
    tick(r, 3, 14, 0, 0.5)
    assert r.reached == 1 and r.charge < 100


def test_boost_is_edge_triggered_limited_and_charged():
    r = Rally(garage())
    a = tick(r, 1, 0, 0, boost_requested=True)
    assert r.boosts == 1 and a["drive_scale"] == 1.5 and r.charge < 93
    tick(r, 2, 0, 0, boost_requested=True)
    tick(r, 4, 0, 0, boost_requested=True)
    assert r.boosts == 1
    tick(r, 5, 0, 0)
    tick(r, 6, 0, 0, boost_requested=True)
    assert r.boosts == 0
    tick(r, 10, 0, 0)
    tick(r, 11, 0, 0, boost_requested=True)
    assert r.boosts == 0


def test_supply_restores_charge_once():
    r = Rally(garage())
    r.charge = 50
    tick(r, 1, 5, 7)
    for t in (1.5, 2, 2.5, 3):
        tick(r, t, 14, 0)
    charge = r.charge
    tick(r, 4, 14, 0)
    assert r.reached == 2 and r.charge < charge and charge > 70


def test_loadouts_have_real_game_tradeoffs():
    plain = Rally(garage())
    sand = Rally(garage(tires="sand"))
    assert tick(plain, 1, 5, -3)["drive_scale"] < tick(sand, 1, 5, -3)["drive_scale"]
    assert stats(garage(battery="endurance"))["capacity"] > stats(garage())["capacity"]
    assert stats(garage(battery="endurance"))["cruise_scale"] < stats(garage())["cruise_scale"]


def test_weather_is_seeded_and_does_not_depend_on_other_draws():
    a = Rally(garage(), "hard", 2)
    b = Rally(garage(), "hard", 2)
    expected = [a.weather(t) for t in range(240)]
    for t in reversed(range(240)):
        b.weather(t)
    assert expected == [b.weather(t) for t in range(240)]
    assert any(expected) and not any(Rally(garage()).weather(t) for t in range(240))


@pytest.mark.parametrize(
    "body",
    [
        {"time_s": math.nan, "position_m": [0, 0, 0]},
        {"time_s": 1, "position_m": [0, math.inf, 0]},
        {"time_s": -1, "position_m": [0, 0, 0]},
    ],
)
def test_invalid_telemetry_cannot_finish(body):
    with pytest.raises(ContractError):
        Rally(garage()).step(body)


def test_timeout_and_rescue_penalty():
    r = Rally(garage())
    assert tick(r, 1, 0, 0, resets=1)["result_time_s"] == 61
    assert tick(r, 240, 0, 0, resets=1)["outcome"] == "time_limit"


def test_garage_roundtrip_and_reject_forged_stats(tmp_path):
    p = tmp_path / "garage.json"
    d = garage("sand", "endurance", "scout", "cyan")
    p.write_text(json.dumps(d))
    assert load_garage(p) == d and design_hash(load_garage(p)) == design_hash(d)
    p.write_text(json.dumps({**d, "capacity": 999}))
    with pytest.raises(ContractError):
        load_garage(p)


def test_ghost_interpolation_and_mismatch(tmp_path):
    r = Rally(garage())
    tick(r, 1, 0, 0)
    tick(r, 2, 2, 0)
    p = tmp_path / "ghost.json"
    p.write_text(json.dumps(r.ghost_document()))
    g = Ghost(p, "easy", 1)
    assert g.at(0) is None and g.at(1.5) == [1, 0, 0.7] and g.at(3) is None
    with pytest.raises(ContractError):
        Ghost(p, "hard", 1)


def test_ghost_rejects_nonmonotonic_samples(tmp_path):
    r = Rally(garage())
    tick(r, 1, 0, 0)
    tick(r, 2, 2, 0)
    doc = r.ghost_document()
    doc["samples"].reverse()
    p = tmp_path / "ghost.json"
    p.write_text(json.dumps(doc))
    with pytest.raises(ContractError):
        Ghost(p, "easy", 1)
