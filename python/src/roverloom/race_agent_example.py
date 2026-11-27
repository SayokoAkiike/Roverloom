"""A minimal race agent that runs as its own process. Copy it and make it yours.

It uses only the Python standard library, so it shows the whole protocol. Any language that can
open a TCP socket and read and write JSON Lines can do the same. Start the race first, then:

    python -m roverloom.race_agent_example --name "My Agent"

Protocol race-agent-1, on 127.0.0.1:8101, one JSON object per line:

    race -> agent   {"type": "race_brief", "body": {course, laps, garage, stats, limits, ...}}
    agent -> race   {"type": "hello", "body": {"name": "My Agent"}}
    race -> agent   {"type": "race_observation", "body": {"tick": 12, "position_m": [x, y], ...}}
    agent -> race   {"type": "race_action", "body": {"tick": 12, "linear_velocity_mps": 0.5,
                                                    "yaw_rate_radps": 0.1, "boost": false}}

An LLM agent fits the same loop: ask your model for a plan once per lap (for example which
corner to cut or when to boost), check the answer as data, and keep this loop as the driver.
Never run model output as code.
"""

from __future__ import annotations

import argparse
import json
import math
import socket
from typing import Any


def drive(obs: dict[str, Any], limits: dict[str, float], aggression: float) -> dict[str, Any]:
    x, y = obs["position_m"]
    tx, ty = obs["path_ahead"][0]  # the drivable path; next_checkpoints holds the flags
    error = math.atan2(ty - y, tx - x) - obs["yaw_rad"]
    error = (error + math.pi) % (2 * math.pi) - math.pi
    w = max(-limits["max_yaw_rate_radps"], min(limits["max_yaw_rate_radps"], 1.6 * error))
    v = limits["max_speed_mps"] * aggression * max(0.15, math.cos(error))
    straight = abs(error) < 0.08 and math.dist((x, y), (tx, ty)) > 4.5
    return {"linear_velocity_mps": v, "yaw_rate_radps": w, "boost": straight and obs["charge"] > 30}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--name", default="Example Agent")
    parser.add_argument("--port", type=int, default=8101)
    parser.add_argument("--aggression", type=float, default=1.0)
    args = parser.parse_args()
    with socket.create_connection(("127.0.0.1", args.port), timeout=30) as conn:
        stream = conn.makefile("rwb")

        def send(kind: str, body: dict[str, Any]) -> None:
            stream.write((json.dumps({"type": kind, "body": body}) + "\n").encode())
            stream.flush()

        limits: dict[str, float] = {}
        for raw in stream:
            message = json.loads(raw)
            body = message["body"]
            if message["type"] == "race_brief":
                limits = body["limits"]
                print(f"{body['course']['name']}, {body['laps']} laps, garage {body['garage']}")
                send("hello", {"name": args.name})
            elif message["type"] == "race_observation":
                if body["finished"]:
                    continue
                action = drive(body, limits, args.aggression)
                send("race_action", {"tick": body["tick"], **action})
    print("Race over.")


if __name__ == "__main__":
    main()
