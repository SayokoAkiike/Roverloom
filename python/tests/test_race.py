"""Race rules: laps, standings, NPCs, ghosts, agents and the leaderboard stay explicit and checked."""

import json
import math
import socket
import threading
import time

import pytest

from roverloom import race_cli
from roverloom.contract import ContractError, dump_json
from roverloom.race import (
    BUILTIN_AGENTS,
    COURSES,
    CapAgent,
    Leaderboard,
    Race,
    RaceAction,
    check_entry,
    ordinal,
    simulate,
    validate_plan,
)
from roverloom.rally import garage

LOOP = COURSES["crater_loop"]


def headless(agent="pursuit", **kw):
    r = Race(garage(), LOOP, controller=f"agent:{agent}", backend="headless", **kw)
    return r, simulate(r, BUILTIN_AGENTS[agent]())


def test_countdown_holds_everyone():
    r = Race(garage(), LOOP)
    s = r.step({"time_s": 0.0, "position_m": [0, 0, 0]})
    assert s["drive_scale"] == 0 and s["race"]["banner"] == "3"
    s = r.step({"time_s": 2.5, "position_m": [0, 0, 0]})
    assert s["race"]["banner"] == "1"
    assert all(o["position_m"][0] < 0 for o in s["race"]["opponents"])  # NPCs still on the grid
    s = r.step({"time_s": 3.2, "position_m": [0, 0, 0]})
    assert s["race"]["banner"] == "GO!" and s["drive_scale"] > 0


def test_checkpoints_must_be_in_order_and_laps_count():
    r = Race(garage(), LOOP, laps=1, npcs=0)
    t = 3.0
    r.step({"time_s": 0.0, "position_m": [0, 0, 0]})
    r.step(
        {"time_s": t + 1, "position_m": [*LOOP.checkpoints[2], 0]}
    )  # skipping ahead counts nothing
    assert r.you.next_cp == 0
    for i, cp in enumerate(LOOP.checkpoints):
        state = r.step({"time_s": t + 2 + i, "position_m": [*cp, 0]})
    assert state["outcome"] == "success" and state["targets_reached"] == 1
    assert r.result()["lap_times_s"] == [pytest.approx(len(LOOP.checkpoints) + 1)]


@pytest.mark.parametrize("agent", ["pursuit", "cap"])
def test_builtin_agents_finish_deterministically(agent):
    _, a = headless(agent, seed=4)
    _, b = headless(agent, seed=4)
    assert a["outcome"] == "success" and len(a["lap_times_s"]) == LOOP.laps
    assert dump_json(a) == dump_json(b)


def test_npcs_race_and_hard_is_faster_than_easy():
    times = {}
    for level in ("easy", "hard"):
        r = Race(garage(), LOOP, npcs=3, difficulty=level, laps=1)
        r.step({"time_s": 0.0, "position_m": [0, 0, 0]})
        t = 0.0
        while all(n.finished_s is None for n in r.racers[1:]) and t < 400:
            t += 0.5
            r.step({"time_s": t, "position_m": [0, 0, 0]})  # the player waits on the line
        times[level] = min(n.finished_s or 1e9 for n in r.racers[1:])
    assert times["hard"] < times["easy"] < 400


def test_standings_put_the_leader_first():
    r = Race(garage(), LOOP, npcs=2)
    for t in range(31):
        s = r.step({"time_s": float(t), "position_m": [0, 0, 0]})
    assert s["race"]["position"] == 3 and s["race"]["standings"][-1]["is_you"]


def test_boost_pad_and_sand():
    r = Race(garage(), LOOP, npcs=0)
    r.step({"time_s": 0.0, "position_m": [0, 0, 0]})
    s = r.step({"time_s": 4.0, "position_m": [5, 0, 0]})
    assert r.you.boosts == 3 and "Boost pad" in s["race"]["message"]
    s = r.step({"time_s": 5.0, "position_m": [12, 4, 0]})
    assert s["race"]["in_sand"] and s["drive_scale"] == pytest.approx(0.55)


def test_rescue_costs_time():
    r = Race(garage(), LOOP)
    r.step({"time_s": 0.0, "position_m": [0, 0, 0]})
    r.step({"time_s": 5.0, "position_m": [0, 0, 0], "resets": 1})
    assert r.you.penalty_s == 30
    with pytest.raises(ContractError):
        r.step({"time_s": 6.0, "position_m": [0, 0, 0], "resets": 0})


def test_bad_telemetry_is_refused():
    r = Race(garage(), LOOP)
    with pytest.raises(ContractError):
        r.step({"time_s": 0.0, "position_m": [0, float("nan"), 0]})


def test_agent_sees_no_hidden_state():
    r = Race(garage(), LOOP)
    r.step({"time_s": 0.0, "position_m": [0, 0, 0]})
    brief, obs = json.dumps(r.brief()), r.observation()
    assert "seed" not in brief and "difficulty" not in brief
    assert set(obs) >= {"next_checkpoints", "charge", "opponents"} and "seed" not in obs
    # A dust warning only in the sensor's window, as on the HUD
    assert isinstance(obs["dust_warning"], bool)


def test_plans_are_data_and_bad_plans_are_refused():
    ok = validate_plan([{"skill": "follow_checkpoints", "args": {"speed_share": 0.8}}])
    assert ok[0]["args"] == {"speed_share": 0.8}
    for bad in (
        "import os",
        [{"skill": "exec", "args": {}}],
        [{"skill": "follow_checkpoints", "args": {"speed_share": 9}}],
        [{"skill": "boost_on_straights", "args": {}}],
        [{"skill": "follow_checkpoints", "code": "x"}],
    ):
        with pytest.raises(ContractError):
            validate_plan(bad)


def test_cap_keeps_last_valid_plan_when_the_source_misbehaves():
    class Flaky:
        calls = 0

        def plan(self, brief, report):
            self.calls += 1
            if self.calls == 1:
                return [{"skill": "follow_checkpoints", "args": {}}]
            return [{"skill": "rm -rf", "args": {}}]

    source = Flaky()
    r = Race(garage(), LOOP, npcs=0, laps=2, backend="headless")
    simulate(r, CapAgent(source))
    assert source.calls >= 2  # asked again after lap 1 and refused the bad plan
    assert r.result()["outcome"] == "success"


def test_action_parsing_clamps_and_refuses():
    a = RaceAction.parse({"linear_velocity_mps": 9, "yaw_rate_radps": -9})
    assert a.linear_velocity_mps == 0.5 and a.yaw_rate_radps == pytest.approx(-0.4918)
    for bad in (
        {},
        {"linear_velocity_mps": True, "yaw_rate_radps": 0},
        {"linear_velocity_mps": 0, "yaw_rate_radps": 0, "boost": 1},
    ):
        with pytest.raises(ContractError):
            RaceAction.parse(bad)


def test_leaderboard_ranks_separately_and_ghosts_replay(tmp_path):
    board = Leaderboard(tmp_path / "b.json")
    _, a = headless("pursuit")
    _, b = headless("cap")
    a["player"], b["player"] = "A", "B"
    _, rank_a = board.add(a)
    _, rank_b = board.add(b)
    assert sorted([rank_a, rank_b]) == [1, 2] or rank_b == 2
    assert len(Leaderboard(tmp_path / "b.json").entries) == 2
    human = dict(a, controller="human", player="H")
    board.add(human)
    assert len(board.boards()) == 2  # humans and agents are separate boards
    ghost = board.ghosts_for("crater_loop", 2, "headless", 1)
    r, _ = headless("pursuit", ghosts=ghost, npcs=0)
    names = [s["name"] for s in r.result()["standings"]]
    assert any("(ghost)" in n for n in names)


def test_shared_entries_are_checked(tmp_path):
    _, a = headless("pursuit")
    for broken in (
        dict(a, ruleset="other"),
        dict(a, total_s=-1),
        dict(a, course="nowhere"),
        dict(a, samples=[[0, 0, 0, "x"]]),
        dict(
            a,
            design={"tires": "rocket", "battery": "standard", "sensor": "basic", "paint": "ivory"},
        ),
    ):
        with pytest.raises(ContractError):
            check_entry(broken)
    assert len(check_entry(dict(a, player="x" * 99))["player"]) == 24


def test_export_and_import_round_trip(tmp_path, capsys):
    src, dst = tmp_path / "a.json", tmp_path / "b.json"
    _, a = headless("pursuit")
    entry, _ = Leaderboard(src).add(a)
    out = tmp_path / "entry.json"
    assert (
        race_cli.main(["export", entry["entry_id"][:6], "--out", str(out), "--board", str(src)])
        == 0
    )
    assert race_cli.main(["import", str(out), "--board", str(dst)]) == 0
    assert Leaderboard(dst).entries[0]["entry_id"] == entry["entry_id"]


def test_lobby_page_embeds_data(tmp_path):
    out = tmp_path / "lobby.html"
    assert race_cli.main(["lobby", "--board", str(tmp_path / "none.json"), "--out", str(out)]) == 0
    html = out.read_text()
    assert "/*RACE_DATA*/null" not in html and "crater_loop" in html


def test_external_agent_over_tcp(tmp_path):
    port = _free_port()
    result = {}

    def agent():
        for _ in range(50):
            try:
                conn = socket.create_connection(("127.0.0.1", port), timeout=5)
                break
            except OSError:
                time.sleep(0.1)
        stream = conn.makefile("rwb")
        for raw in stream:
            msg = json.loads(raw)
            if msg["type"] == "race_brief":
                stream.write(b'{"type":"hello","body":{"name":"tcp-test"}}\n')
            else:
                obs = msg["body"]
                act = BUILTIN_AGENTS["pursuit"]()
                a = act.act(obs)
                body = {
                    "tick": obs["tick"],
                    "linear_velocity_mps": a.linear_velocity_mps,
                    "yaw_rate_radps": a.yaw_rate_radps,
                    "boost": a.boost,
                }
                stream.write((json.dumps({"type": "race_action", "body": body}) + "\n").encode())
            stream.flush()
        conn.close()

    thread = threading.Thread(target=agent, daemon=True)
    thread.start()
    code = race_cli.main(
        [
            "headless",
            "--agent",
            "external",
            "--agent-port",
            str(port),
            "--npcs",
            "1",
            "--laps",
            "1",
            "--board",
            str(tmp_path / "b.json"),
            "--out",
            str(tmp_path),
        ]
    )
    thread.join(5)
    result = json.loads((tmp_path / "race_result.json").read_text())
    assert code == 0 and result["controller"] == "agent:tcp-test"


def test_ordinal():
    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 21)] == [
        "1st",
        "2nd",
        "3rd",
        "4th",
        "11th",
        "12th",
        "21st",
    ]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize("name", ["gale_sprint", "gale_links"])
def test_gale_courses_finish_on_their_path(name):
    course = COURSES[name]
    assert course.ground == "gale" and course.style == "flags"
    path = course.path
    for flag in course.checkpoints:  # every flag is on the routed path
        assert min(math.dist(flag, p) for p in path) < 0.01
    r = Race(garage(), course, npcs=2, backend="headless", controller="agent:pursuit")
    result = simulate(r, BUILTIN_AGENTS["pursuit"]())
    assert result["outcome"] == "success"
    # The rover stayed near the routed path the whole way
    worst = max(_distance_to_path(path, s[1:3]) for s in result["samples"])
    assert worst < 3.0


def test_point_to_point_starts_at_its_start_and_ends_at_the_last_flag():
    course = COURSES["gale_sprint"]
    r = Race(garage(), course, npcs=0)
    assert (r.you.x, r.you.y) == course.start_point
    state = r.step({"time_s": 0.0, "position_m": [0, 0, 0]})
    assert state["race"]["flag"] == 1 and state["race"]["flags"] == 3
    doc = course.document()
    assert doc["start"] == [0.0, 0.0] and doc["line"][-1] == list(course.checkpoints[-1])


def _distance_to_path(path, p):
    best = 1e9
    for a, b in zip(path, path[1:], strict=False):
        ax, ay = a
        dx, dy = b[0] - ax, b[1] - ay
        t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / max(dx * dx + dy * dy, 1e-9)))
        best = min(best, math.dist(p, (ax + dx * t, ay + dy * t)))
    return best


@pytest.mark.parametrize(
    "name", ["noctis_spur", "noctis_sprint", "amazonis_rim", "amazonis_sprint"]
)
def test_new_stage_courses_are_point_to_point_flag_courses(name):
    course = COURSES[name]
    assert course.ground in ("noctis", "amazonis") and course.style == "flags"
    assert course.start_point == course.path[0] and course.path[-1] == course.checkpoints[-1]
    for flag in course.checkpoints:
        assert min(math.dist(flag, p) for p in course.path) < 0.01
    for pad in course.pads:  # pads lie on the path
        assert _distance_to_path(course.path, pad) < 0.5
    r = Race(garage(), course, npcs=2, backend="headless", controller="agent:cap")
    result = simulate(r, BUILTIN_AGENTS["cap"]())
    assert result["outcome"] == "success" and result["racers"] == 3


def test_stage_levels_resolve_from_sites_json():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "play_3d", Path(__file__).parents[2] / "scripts" / "play_3d.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.stage_level("generated") is None
    for site in ("gale", "noctis", "amazonis"):
        level, umap = module.stage_level(site)
        assert level.startswith("/Game/Licensed/") and umap.suffix == ".umap"
    assert {c.ground for c in COURSES.values()} <= {"generated", "gale", "noctis", "amazonis"}


def test_rivals_never_overlap_the_player_or_each_other():
    from roverloom.race import overlap

    r = Race(garage(), LOOP, npcs=5, difficulty="hard", laps=1, backend="headless")
    agent = BUILTIN_AGENTS["pursuit"]()
    agent.reset(r.brief())
    r.step({"time_s": 0.0, "position_m": [r.you.x, r.you.y, 0.0], "yaw_rad": r.you.yaw})
    t, touching = 0.0, []
    while r.outcome == "running" and t < 300:
        act = agent.act(r.observation()) if r.time_s >= 0 else RaceAction(0.0, 0.0)
        r._move(r.you, act, 0.1)
        t = round(t + 0.1, 6)
        r.step(
            {
                "time_s": t,
                "position_m": [r.you.x, r.you.y, 0.0],
                "yaw_rad": r.you.yaw,
                "forward_mps": r.you.speed,
            },
            boost=act.boost,
        )
        solid = [x for x in r.racers if x.kind != "ghost"]
        for i, a in enumerate(solid):
            for b in solid[i + 1 :]:
                if overlap(a, b, gap=-0.05) is not None:
                    touching.append((t, a.name, b.name))
    assert touching == []


def test_contact_follows_the_rover_shapes_not_a_disc():
    """The player's solar deck reaches 1.75 m behind and 1.28 m out: a rival 2.8 m behind or on the
    deck's corner touches it; one 3 m ahead, beyond the sample arm, does not."""
    from roverloom.race import overlap

    r = Race(garage(), LOOP, npcs=1, laps=1)
    you, npc = r.you, r.racers[1]
    you.x, you.y, you.yaw = 0.0, 0.0, 0.0
    npc.yaw = 0.0
    for at, touches in (
        ((-2.8, 0.0), True),
        ((-2.3, 2.0), True),
        ((2.4, 0.0), True),
        ((3.0, 0.0), False),
        ((0.0, 2.6), False),
    ):
        npc.x, npc.y = at
        assert (overlap(you, npc) is not None) is touches, at
    npc.x, npc.y = -2.8, 0.0
    r._separate()
    assert overlap(you, npc, gap=0.0) is None
    assert (you.x, you.y) == (0.0, 0.0)  # the player is never moved


def test_driving_into_a_rival_bumps_and_pushes_it():
    r = Race(garage(), LOOP, npcs=1, laps=1)
    r.step({"time_s": 0.0, "position_m": [0, 0, 0]})
    for t in (3.1, 3.2):
        r.step({"time_s": t, "position_m": [0, 0, 0]})
    npc = r.racers[1]
    # Drive straight onto the rival's spot, moving towards it
    s = r.step(
        {
            "time_s": 3.3,
            "position_m": [npc.x, npc.y, 0],
            "yaw_rad": math.atan2(npc.y, npc.x) + math.pi,
            "forward_mps": 0.5,
        }
    )
    assert math.dist((npc.x, npc.y), (r.you.x, r.you.y)) >= 2.99
    assert "Bump!" in s["race"]["message"] and s["drive_scale"] < 0.7


def test_older_rule_entries_are_kept_but_not_ranked(tmp_path):
    path = tmp_path / "b.json"
    _, a = headless("pursuit")
    old = dict(a, ruleset="race-0.1", player="Old")
    path.write_text(json.dumps({"ruleset": "race-0.1", "entries": [old]}))
    board = Leaderboard(path)
    assert board.entries == [] and len(board.other_rules) == 1
    board.add(a)
    saved = json.loads(path.read_text())
    assert {e["player"] for e in saved["entries"]} == {"Old", a["player"]}


def test_rivals_overtaking_from_behind_go_round_the_solar_deck():
    """Reported on the Mac: rivals passing from behind were drawn through the player's rover. The
    player drives at 70% (gear 2); every rival that passes stays clear of the deck."""
    from roverloom.race import overlap

    r = Race(garage(), COURSES["noctis_sprint"], npcs=5, difficulty="hard", laps=1)
    agent = BUILTIN_AGENTS["pursuit"]()
    agent.reset(r.brief())
    r.step({"time_s": 0.0, "position_m": [r.you.x, r.you.y, 0.0], "yaw_rad": r.you.yaw})
    t, touching, passed = 0.0, 0, set()
    while r.outcome == "running" and t < 240:
        act = agent.act(r.observation()) if r.time_s >= 0 else RaceAction(0.0, 0.0)
        r._move(r.you, RaceAction(act.linear_velocity_mps * 0.7, act.yaw_rate_radps), 0.1)
        t = round(t + 0.1, 6)
        r.step(
            {
                "time_s": t,
                "position_m": [r.you.x, r.you.y, 0.0],
                "yaw_rad": r.you.yaw,
                "forward_mps": r.you.speed,
            },
            boost=False,
        )
        hx, hy = math.cos(r.you.yaw), math.sin(r.you.yaw)
        for o in r.racers[1:]:
            touching += overlap(r.you, o, gap=-0.05) is not None
            if (o.x - r.you.x) * hx + (o.y - r.you.y) * hy > 3.0:
                passed.add(o.id)
    assert len(passed) >= 3
    assert touching == 0


def _fake_unreal(port, ready, log):
    """Stands in for RoverPawn: sends 10 Hz telemetry, moves the rover by the agent's actions, and
    writes RaceDraw lines from the states it receives."""
    with socket.socket() as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen(1)
        ready.set()
        conn, _ = srv.accept()
    course = COURSES["noctis_sprint"]
    x, y = course.start_point
    yaw = math.atan2(course.path[1][1] - y, course.path[1][0] - x)
    v = w = 0.0
    buf = b""
    with conn:
        conn.settimeout(5)
        for tick in range(2000):
            t = tick * 0.1
            body = {"time_s": t, "position_m": [x, y, 0.0], "yaw_rad": yaw, "forward_mps": v}
            try:
                conn.sendall((json.dumps({"type": "telemetry", "body": body}) + "\n").encode())
                state = None
                # The reply is one mission_state line, then an action line when the agent acted
                while state is None or (b"\n" not in buf and _more(conn)):
                    while b"\n" not in buf:
                        chunk = conn.recv(65536)
                        if not chunk:
                            return
                        buf += chunk
                    line, buf = buf.split(b"\n", 1)
                    msg = json.loads(line)
                    if msg["type"] == "mission_state":
                        state = msg["body"]
                    elif msg["type"] == "action":
                        v, w = msg["body"]["linear_velocity_mps"], msg["body"]["yaw_rate_radps"]
                while b"\n" in buf:  # an action that arrived with the state
                    line, buf = buf.split(b"\n", 1)
                    msg = json.loads(line)
                    if msg["type"] == "action":
                        v, w = msg["body"]["linear_velocity_mps"], msg["body"]["yaw_rate_radps"]
            except OSError:
                return
            rivals = " ".join(
                f"{o['id']}@{o['position_m'][0]:.3f},{o['position_m'][1]:.3f},{o['yaw_rad']:.4f}"
                for o in state["race"]["opponents"]
                if math.dist(o["position_m"][:2], (x, y)) < 6
            )
            if rivals:
                log.append(f"RaceDraw t={t:.2f} you={x:.3f},{y:.3f},{yaw:.4f} {rivals}")
            yaw += w * 0.1
            x += v * math.cos(yaw) * 0.1
            y += v * math.sin(yaw) * 0.1


def _more(conn):
    import select

    return bool(select.select([conn], [], [], 0.02)[0])


def test_diagnostic_link_run_reports_contacts(tmp_path):
    """The --diagnose path end to end, with a stand-in for Unreal: a slow agent, rivals overtaking,
    the race stopped unranked, and a report that tells Python's view from the drawn one."""
    from roverloom.race_diagnose import report

    port, ready, log = _free_port(), threading.Event(), []
    thread = threading.Thread(target=_fake_unreal, args=(port, ready, log), daemon=True)
    thread.start()
    ready.wait(5)
    out = tmp_path / "run-x"
    board = tmp_path / "board.json"
    code = race_cli.main(
        ["link", "--out", str(out), "--port", str(port), "--course", "noctis_sprint"]
        + ["--npcs", "4", "--difficulty", "hard", "--agent", "pursuit", "--agent-speed", "0.35"]
        + ["--stop-after", "60", "--wait", "5", "--linger", "0.3", "--board", str(board)]
    )
    thread.join(10)
    assert code == 0
    final = json.loads((out / "final_state.json").read_text())
    assert final["outcome"] == "stopped" and not board.exists()  # not ranked
    assert log, "rivals came close"
    (out / "unreal.log").write_text("Rover model: V2. Body X -175.0..113.5 cm\n" + "\n".join(log))
    text = report(out)
    assert "rovers overlap in 0." in text and "Verdict: no overlap in Python or in Unreal" in text
    # A rival drawn on the solar deck is found, and blamed on the Unreal side
    x, y, yaw = (float(v) for v in log[-1].split("you=")[1].split()[0].split(","))
    bx, by = x - 2.0 * math.cos(yaw), y - 2.0 * math.sin(yaw)
    log.append(f"RaceDraw t=99.00 you={x},{y},{yaw} npc1@{bx:.3f},{by:.3f},{yaw:.4f}")
    (out / "unreal.log").write_text("\n".join(log))
    text = report(out)
    assert "behind (2.0 m back" in text and "Unreal drew them overlapping" in text
