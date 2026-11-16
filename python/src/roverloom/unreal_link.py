"""G3 mission link: the Mission Core judges a mission while Unreal drives the rover.

Unreal listens on loopback (reached from the Air through the night key's tunnel) and sends one
`telemetry` line per 0.1 s with the rover's site-frame position. This client runs an ordinary
MissionSession for the scenario, replaces only its rover position with Unreal's, and lets the
session's own rules decide targets, success, and limits. After each telemetry line it sends a
`mission_state` line back, which Unreal shows on its HUD and never re-judges. Framing is the bridge
protocol's: UTF-8 JSON Lines of {"type": ..., "body": ...}, 1 MiB per line.

    python -m roverloom.unreal_link --scenario g3_reach_target --port 18100 --out runs/g3

With `--agent NAME`, the named agent also drives: it sees Unreal's position through the session's
ordinary sensors and comms model, and each command the session accepts goes back to Unreal as an
`action` line (bridge v1 body, contract units). Unreal's router clamps it, a held key takes the
rover back, and a lost link returns control to the keyboard. This is real time, not lockstep: such
runs do not reproduce and must not be ranked.

Unreal's physics are its own: this run is not comparable with lightweight-backend runs, and it is
not scored here. The session's battery and energy still come from the Mission Core's model.
"""

import argparse
import json
import socket
import sys
import time
from pathlib import Path

from roverloom.agents import create_agent
from roverloom.api import Action, Pose
from roverloom.bridge import MAX_LINE_BYTES, _require_loopback
from roverloom.contract import JsonDict, dump_json
from roverloom.session import MissionSession
from roverloom.world import SIM_STEP_S, load_scenario


class UnrealPoseSim:
    """Wraps the session's RoverSim: its power model runs, its position is Unreal's."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.position_m: tuple[float, float, float] | None = None

    @property
    def state(self):  # type: ignore[no-untyped-def]
        return self._inner.state  # type: ignore[attr-defined]

    def step(self, action, dt, effects=None) -> bool:  # type: ignore[no-untyped-def]
        args = (action, dt) if effects is None else (action, dt, effects)
        self._inner.step(*args)  # type: ignore[attr-defined]
        if self.position_m is not None:
            pose = self._inner.state.pose  # type: ignore[attr-defined]
            x, y, z = self.position_m
            self._inner.state.pose = Pose(x, y, z, pose.yaw_rad)  # type: ignore[attr-defined]
        return False  # Collisions are Unreal's; the Mission Core's rocks do not exist there


def mission_state(session: MissionSession) -> JsonDict:
    mission = session.mission
    return {
        "scenario": session.scenario.scenario_id,
        "time_s": round(session.time_s, 1),
        "targets_reached": mission.targets_reached,
        "targets_total": mission.targets_total,
        "outcome": str(mission.outcome),
    }


def connect(host: str, port: int, wait_s: float) -> socket.socket:
    _require_loopback(host)
    deadline = time.monotonic() + wait_s
    while True:
        try:
            return socket.create_connection((host, port), timeout=5.0)
        except OSError:
            if time.monotonic() > deadline:
                raise
            time.sleep(1.0)


def run(
    scenario_name: str,
    host: str,
    port: int,
    out: Path,
    wait_s: float,
    linger_s: float,
    agent: str | None = None,
) -> JsonDict:
    out.mkdir(parents=True, exist_ok=True)
    events_file = (out / "events.jsonl").open("w", encoding="utf-8")
    states_file = (out / "states.jsonl").open("w", encoding="utf-8")
    scenario = load_scenario(scenario_name)

    def write_event(event: JsonDict) -> None:
        events_file.write(dump_json(event) + "\n")

    session = MissionSession(
        scenario,
        # Without an agent, Unreal's driver moves the rover and this source only exists.
        {"agent": create_agent(agent or "stop")},
        "agent",
        on_event=write_event,
    )
    sim = UnrealPoseSim(session.sim)
    session.sim = sim  # type: ignore[assignment]
    deadline = time.monotonic() + wait_s
    conn = connect(host, port, wait_s)
    conn.settimeout(10.0)
    buffer, ended_at, heard = b"", None, False
    try:
        while True:
            if ended_at is not None and time.monotonic() - ended_at > linger_s:
                break
            try:
                chunk = conn.recv(65536)
            except TimeoutError:
                break
            if not chunk and not heard and time.monotonic() < deadline:
                # A tunnel accepts before Unreal listens, then closes: retry until Unreal answers.
                conn.close()
                time.sleep(1.0)
                conn = connect(host, port, max(0.0, deadline - time.monotonic()))
                conn.settimeout(10.0)
                continue
            if not chunk:
                break
            heard = True
            buffer += chunk
            if len(buffer) > MAX_LINE_BYTES:
                raise ValueError("line longer than 1 MiB")
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                message = json.loads(line.decode("utf-8"))
                if message.get("type") != "telemetry":
                    continue
                body = message["body"]
                sim.position_m = tuple(float(v) for v in body["position_m"])  # type: ignore[assignment]
                # The session's fixed step catches up with Unreal's clock.
                while not session.mission.finished and session.time_s + SIM_STEP_S <= float(
                    body["time_s"]
                ):
                    session.step()
                if agent is not None and not session.mission.finished:
                    command = session.router.current(session.time_s)
                    action = Action(command.linear_velocity_mps, command.yaw_rate_radps)
                    conn.sendall(
                        (dump_json({"type": "action", "body": action.to_dict()}) + "\n").encode(
                            "utf-8"
                        )
                    )
                state = mission_state(session)
                states_file.write(dump_json(state) + "\n")
                conn.sendall(
                    (dump_json({"type": "mission_state", "body": state}) + "\n").encode("utf-8")
                )
                if session.mission.finished and ended_at is None:
                    ended_at = (
                        time.monotonic()
                    )  # Keep answering briefly, so the HUD shows the result
    finally:
        conn.close()
        events_file.close()
        states_file.close()
    final = mission_state(session)
    (out / "final_state.json").write_text(dump_json(final) + "\n", encoding="utf-8")
    return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18100)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--wait", type=float, default=180.0, help="seconds to keep trying to connect"
    )
    parser.add_argument(
        "--linger", type=float, default=5.0, help="seconds to keep answering after the end"
    )
    parser.add_argument("--agent", help="agent that drives the rover through the link (real time)")
    args = parser.parse_args(argv)
    final = run(args.scenario, args.host, args.port, args.out, args.wait, args.linger, args.agent)
    print(json.dumps(final))
    return 0


if __name__ == "__main__":
    sys.exit(main())
