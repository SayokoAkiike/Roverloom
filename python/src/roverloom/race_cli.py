"""Race commands: the Unreal link, headless agent races, the leaderboard and the lobby page.

Run from the repository root, for example:

    uv run --project python python -m roverloom.race_cli headless --agent pursuit
    uv run --project python python -m roverloom.race_cli board
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from pathlib import Path

from roverloom.bridge import MAX_LINE_BYTES
from roverloom.contract import ContractError, JsonDict, dump_json, load_json_file, parse_json
from roverloom.race import (
    AGENT_PROTOCOL,
    BUILTIN_AGENTS,
    COURSES,
    DIFFICULTIES,
    NPC_ROSTER,
    RULESET,
    STOP,
    TICK_S,
    Leaderboard,
    Race,
    RaceAction,
    RaceAgent,
    board_key,
    check_entry,
    fmt_time,
    simulate,
    summary,
)
from roverloom.rally import load_garage
from roverloom.unreal_link import connect

AGENT_PORT = 8101
DEFAULT_BOARD = Path("runs") / "race" / "leaderboard.json"


class ExternalAgent:
    """Your own agent, in any language, as a separate process on this machine.

    It connects to 127.0.0.1:8101, receives `race_brief` once and `race_observation` every tick,
    and answers each observation with a `race_action`. See docs/race.md. Nothing it sends is run.
    """

    def __init__(self, port: int = AGENT_PORT, wait_s: float = 60.0, lockstep: bool = True):
        self.name = "external"
        self.lockstep = lockstep  # headless waits for each answer; real time does not
        self.server = socket.create_server(("127.0.0.1", port))
        self.server.settimeout(wait_s)
        print(f"Waiting for your agent on 127.0.0.1:{port} ...", flush=True)
        self.conn, _ = self.server.accept()
        self.conn.settimeout(1.0 if lockstep else 0.0)
        self.buffer = b""
        self.tick = 0
        self.last = STOP
        self.last_tick = -1
        self.late = 0

    def _send(self, kind: str, body: JsonDict) -> None:
        self.conn.sendall((dump_json({"type": kind, "body": body}) + "\n").encode())

    def reset(self, brief: JsonDict) -> None:
        self._send("race_brief", brief)
        hello = self._read(timeout=10.0)
        if hello is not None and isinstance(hello.get("name"), str):
            self.name = hello["name"][:32]

    def _read(self, timeout: float | None = None) -> JsonDict | None:
        if timeout is not None:
            self.conn.settimeout(timeout)
        try:
            while b"\n" not in self.buffer:
                chunk = self.conn.recv(65536)
                if not chunk:
                    raise ConnectionError("agent disconnected")
                self.buffer += chunk
                if len(self.buffer) > MAX_LINE_BYTES:
                    raise ContractError("agent line too large")
        except (TimeoutError, BlockingIOError):
            return None
        finally:
            self.conn.settimeout(1.0 if self.lockstep else 0.0)
        line, self.buffer = self.buffer.split(b"\n", 1)
        message = parse_json(line.decode())
        if not isinstance(message, dict) or not isinstance(message.get("body"), dict):
            raise ContractError("agent messages are {type, body} objects")
        body: JsonDict = message["body"]
        return body

    def act(self, observation: JsonDict) -> RaceAction:
        self.tick += 1
        self._send("race_observation", {"tick": self.tick, **observation})
        while True:
            body = self._read()
            if body is None:
                break
            try:
                self.last = RaceAction.parse(body)
                self.last_tick = int(body.get("tick", self.tick))
            except ContractError:
                self.last = STOP
            if not self.lockstep or self.last_tick >= self.tick:
                break
        if self.tick - self.last_tick > 10:  # one second without an answer: stop the rover
            self.late += 1
            return STOP
        return self.last

    def close(self) -> None:
        self.conn.close()
        self.server.close()


def make_agent(kind: str, port: int, lockstep: bool) -> RaceAgent:
    if kind == "external":
        return ExternalAgent(port, lockstep=lockstep)
    if kind not in BUILTIN_AGENTS:
        raise ContractError(f"unknown agent {kind}; use {', '.join(BUILTIN_AGENTS)} or external")
    return BUILTIN_AGENTS[kind]()


def build_race(args: argparse.Namespace, backend: str, controller: str) -> Race:
    course = COURSES[args.course]
    if getattr(args, "offset", None):
        dx, dy = (float(v) for v in args.offset.split(","))
        course = course.shifted(dx, dy)
    board = Leaderboard(Path(args.board))
    laps = args.laps or course.laps
    ghosts = board.ghosts_for(args.course, laps, backend, args.ghosts) if args.ghosts else []
    return Race(
        load_garage(Path(args.garage) if args.garage else None),
        course,
        player=args.name,
        laps=laps,
        npcs=args.npcs,
        difficulty=args.difficulty,
        seed=args.seed,
        ghosts=ghosts,
        controller=controller,
        backend=backend,
    )


def finish(race: Race, out: Path | None, board_path: Path, agent_name: str | None) -> JsonDict:
    result = race.result()
    if agent_name:
        result["controller"] = f"agent:{agent_name}"
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "race_result.json").write_text(dump_json(result) + "\n", encoding="utf-8")
    rank = None
    if result["outcome"] == "success":
        _, rank = Leaderboard(board_path).add(result)
    print_result(result, rank)
    return result


def print_result(result: JsonDict, rank: int | None) -> None:
    print()
    print(f"  {result['player']}  |  {result['course']}  |  {result['controller']}")
    if result["outcome"] == "success":
        laps = "  ".join(fmt_time(t) for t in result["lap_times_s"])
        print(
            f"  FINISHED {result['position']} of {result['racers']}"
            f"  in {fmt_time(result['total_s'])}"
        )
        print(f"  laps: {laps}   penalty: {result['penalty_s']:.0f} s")
        if rank:
            print(f"  leaderboard rank: {rank}  ({board_key(result)})")
    else:
        print(f"  not finished: {result['outcome']}")
    print()
    for row in result["standings"]:
        total = fmt_time(row["total_s"]) if row["total_s"] else "--"
        print(f"   {row['pos']}. {row['name']:<24} {row['kind']:<6} {total}")
    print()


# ---------------------------------------------------------------------------- Unreal link


def link(args: argparse.Namespace) -> int:
    """Same-Mac real-time link: Unreal moves the rover; Python judges and drives the rivals."""
    if not 0.1 <= args.agent_speed <= 1.0:
        raise ValueError("--agent-speed must be between 0.1 and 1")
    controller = "human" if args.agent == "none" else f"agent:{args.agent}"
    race = build_race(args, "unreal", controller)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    course_file = out / "course.json"
    course_file.write_text(dump_json(race.course.document()) + "\n", encoding="utf-8")
    agent = None if args.agent == "none" else make_agent(args.agent, args.agent_port, False)
    conn = connect("127.0.0.1", args.port, args.wait)
    conn.settimeout(10)
    buffer = b""
    ended: float | None = None
    next_action = 0.0
    if agent:
        agent.reset(race.brief())
    try:
        with (out / "states.jsonl").open("w", encoding="utf-8") as states:
            while ended is None or time.monotonic() - ended < args.linger:
                try:
                    chunk = conn.recv(65536)
                except TimeoutError:
                    break
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if len(line) > MAX_LINE_BYTES:
                        raise ValueError("race line too large")
                    message = parse_json(line.decode())
                    if message.get("type") != "telemetry":
                        continue
                    action = None
                    if agent and race.time_s >= 0 and race.outcome == "running":
                        now = time.monotonic()
                        if now >= next_action:
                            next_action = now + TICK_S
                            action = agent.act(race.observation())
                            if args.agent_speed < 1.0:
                                action = RaceAction(
                                    action.linear_velocity_mps * args.agent_speed,
                                    action.yaw_rate_radps,
                                    False,
                                )
                    state = race.step(message["body"], boost=action.boost if action else None)
                    if (
                        args.stop_after
                        and race.outcome == "running"
                        and race.time_s >= args.stop_after
                    ):
                        race.outcome = "stopped"  # a diagnostic run: ends unranked
                        state = race.state()
                    states.write(dump_json(state) + "\n")
                    reply = dump_json({"type": "mission_state", "body": state}) + "\n"
                    if action:
                        reply += (
                            dump_json(
                                {
                                    "type": "action",
                                    "body": {
                                        "linear_velocity_mps": action.linear_velocity_mps,
                                        "yaw_rate_radps": action.yaw_rate_radps,
                                    },
                                }
                            )
                            + "\n"
                        )
                    conn.sendall(reply.encode())
                    if race.outcome != "running" and ended is None:
                        ended = time.monotonic()
                if len(buffer) > MAX_LINE_BYTES:
                    raise ValueError("race line too large")
    finally:
        conn.close()
        if isinstance(agent, ExternalAgent):
            agent.close()
    (out / "final_state.json").write_text(dump_json(race.state()) + "\n", encoding="utf-8")
    finish(race, out, Path(args.board), getattr(agent, "name", None) if agent else None)
    return 0


# ---------------------------------------------------------------------------- headless


def headless(args: argparse.Namespace) -> int:
    agent = make_agent(args.agent, args.agent_port, True)
    race = build_race(args, "headless", f"agent:{args.agent}")
    try:
        simulate(race, agent)
    finally:
        if isinstance(agent, ExternalAgent):
            agent.close()
    out = Path(args.out) if args.out else None
    result = finish(race, out, Path(args.board), agent.name)
    return 0 if result["outcome"] == "success" else 1


# ---------------------------------------------------------------------------- board


def board(args: argparse.Namespace) -> int:
    boards = Leaderboard(Path(args.board)).boards()
    if not boards:
        print("No finished races yet.")
    for key, entries in boards.items():
        print(f"\n  {key}")
        for row in summary(entries, args.top):
            d = row["design"]
            parts = f"{d['tires']}/{d['battery']}/{d['sensor']}"
            print(
                f"   {row['rank']:>2}. {row['player']:<20} {row['total']:>7}  "
                f"{row['controller']:<18} {parts:<26} id {row['entry_id'][:8]}"
            )
    print()
    return 0


def export(args: argparse.Namespace) -> int:
    entries = Leaderboard(Path(args.board)).entries
    match = [e for e in entries if e["entry_id"].startswith(args.entry)]
    if len(match) != 1:
        raise ContractError("give a unique entry id prefix; see the id column of `board`")
    Path(args.out).write_text(dump_json(match[0]) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}. Send it to another player; they run `import` on it.")
    return 0


def import_entry(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if path.stat().st_size > 2_000_000:
        raise ContractError("entry file too large")
    entry, rank = Leaderboard(Path(args.board)).add(check_entry(load_json_file(path)))
    print(
        f"Imported {entry['player']} {fmt_time(entry['total_s'])}:"
        f" rank {rank} on {board_key(entry)}"
    )
    return 0


def lobby(args: argparse.Namespace) -> int:
    page = Path(__file__).parent / "preview" / "lobby.html"
    entries = Leaderboard(Path(args.board)).boards()
    data = {
        "ruleset": RULESET,
        "courses": {k: c.document() for k, c in COURSES.items()},
        "npcs": [p.name for p in NPC_ROSTER],
        "difficulties": list(DIFFICULTIES),
        "boards": {k: summary(v) for k, v in entries.items()},
        "agents": [*BUILTIN_AGENTS, "external"],
        "protocol": AGENT_PROTOCOL,
    }
    html = page.read_text(encoding="utf-8").replace(
        "/*RACE_DATA*/null", json.dumps(data).replace("</", "<\\/")
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Open {out} in a browser")
    return 0


def diagnose(args: argparse.Namespace) -> int:
    from roverloom.race_diagnose import newest_run, report

    run = Path(args.run) if args.run else newest_run(Path("runs") / "first-3d")
    print(report(run))
    return 0


def add_race_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--course", choices=tuple(COURSES), default="crater_loop")
    p.add_argument("--laps", type=int)
    p.add_argument("--npcs", type=int, default=3)
    p.add_argument("--ghosts", type=int, default=0, help="race your best saved runs")
    p.add_argument("--difficulty", choices=tuple(DIFFICULTIES), default="standard")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--garage", help="garage.json from the lobby or `roverloom.rally`")
    p.add_argument("--name", default="You")
    p.add_argument("--board", default=str(DEFAULT_BOARD))
    p.add_argument("--agent-port", type=int, default=AGENT_PORT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("link", help="run with Unreal (started by scripts/play_3d.py --race)")
    add_race_options(p)
    p.add_argument("--agent", default="none", help="none (you drive), pursuit, cap or external")
    p.add_argument("--out", required=True)
    p.add_argument("--port", type=int, default=8100)
    p.add_argument("--offset", help="shift the course to x,y metres (for other start points)")
    p.add_argument("--wait", type=float, default=180)
    p.add_argument("--linger", type=float, default=10)
    p.add_argument(
        "--agent-speed",
        type=float,
        default=1.0,
        help="scale the agent's speed, 0.1 to 1 (slow driving lets rivals overtake)",
    )
    p.add_argument("--stop-after", type=float, help="end the race unranked after this many seconds")
    p.set_defaults(run=link)
    p = sub.add_parser("diagnose", help="check a run for rovers that overlap")
    p.add_argument("run", nargs="?", help="run directory (default: the newest under runs/first-3d)")
    p.set_defaults(run=diagnose)
    p = sub.add_parser("headless", help="race an agent without Unreal, on the race model")
    add_race_options(p)
    p.add_argument("--agent", default="pursuit", help="pursuit, cap or external")
    p.add_argument("--out")
    p.set_defaults(run=headless)
    p = sub.add_parser("board", help="show the local leaderboards")
    p.add_argument("--board", default=str(DEFAULT_BOARD))
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(run=board)
    p = sub.add_parser("export", help="write one entry to share")
    p.add_argument("entry", help="entry id prefix")
    p.add_argument("--out", default="race-entry.json")
    p.add_argument("--board", default=str(DEFAULT_BOARD))
    p.set_defaults(run=export)
    p = sub.add_parser("import", help="add another player's entry")
    p.add_argument("file")
    p.add_argument("--board", default=str(DEFAULT_BOARD))
    p.set_defaults(run=import_entry)
    p = sub.add_parser("lobby", help="write the lobby page with your leaderboard")
    p.add_argument("--board", default=str(DEFAULT_BOARD))
    p.add_argument("--out", default=str(Path("runs") / "race" / "lobby.html"))
    p.set_defaults(run=lobby)
    args = parser.parse_args(argv)
    try:
        code: int = args.run(args)
        return code
    except (ContractError, OSError, ValueError) as error:
        print(f"race: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
