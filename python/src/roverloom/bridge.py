"""Loopback JSON Lines protocol between a simulator and an agent in another process.

The planned Unreal bridge will speak this protocol. Today it is exercised only against the
lightweight backend. See docs/unreal-integration.md.
"""

import contextlib
import ipaddress
import socket
from typing import Protocol

from roverloom.api import Action, MissionBrief, Observation
from roverloom.contract import ContractError, JsonDict, dump_json, parse_json

MAX_LINE_BYTES = 1024 * 1024
DEFAULT_TIMEOUT_S = 30.0


class _Agent(Protocol):
    def reset(self, brief: MissionBrief, seed: int) -> None: ...

    def act(self, observation: Observation) -> Action: ...


class _LineChannel:
    def __init__(self, connection: socket.socket) -> None:
        self._socket = connection
        self._buffer = b""

    def send(self, message_type: str, body: JsonDict) -> None:
        line = dump_json({"type": message_type, "body": body}) + "\n"
        self._socket.sendall(line.encode("utf-8"))

    def receive(self) -> tuple[str, JsonDict]:
        while b"\n" not in self._buffer:
            if len(self._buffer) > MAX_LINE_BYTES:
                raise ContractError("bridge message is too long")
            chunk = self._socket.recv(65536)
            if not chunk:
                raise ContractError("bridge connection closed")
            self._buffer += chunk
        line, _, self._buffer = self._buffer.partition(b"\n")
        if len(line) > MAX_LINE_BYTES:
            raise ContractError("bridge message is too long")
        try:
            message = parse_json(line.decode("utf-8"))
        except UnicodeDecodeError as error:
            raise ContractError(f"bridge message is not UTF-8: {error}") from error
        if (
            not isinstance(message, dict)
            or set(message) != {"type", "body"}
            or not isinstance(message["type"], str)
            or not isinstance(message["body"], dict)
        ):
            raise ContractError("bridge message must be an object with type and body")
        return message["type"], message["body"]

    def close(self) -> None:
        self._socket.close()


def _require_loopback(host: str) -> None:
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        raise ContractError(f"the bridge has no authentication; only loopback is allowed: {host}")


class RemoteAgent:
    """Simulator side. Acts as an agent by forwarding each observation to a connected client.

    It waits for the reply, so the simulation stays in lockstep and is reproducible.
    """

    def __init__(
        self, host: str = "127.0.0.1", port: int = 0, timeout_s: float = DEFAULT_TIMEOUT_S
    ) -> None:
        _require_loopback(host)
        self._timeout = timeout_s
        self._listener = socket.create_server((host, port))
        self._listener.settimeout(timeout_s)
        self.port: int = self._listener.getsockname()[1]
        self._channel: _LineChannel | None = None

    def reset(self, brief: MissionBrief, seed: int) -> None:
        connection, _ = self._listener.accept()
        connection.settimeout(self._timeout)
        self._channel = _LineChannel(connection)
        self._channel.send("start", {"seed": seed, "brief": brief.to_dict()})

    def act(self, observation: Observation) -> Action:
        if self._channel is None:
            raise ContractError("no bridge client is connected")
        self._channel.send("observation", observation.to_dict())
        message_type, body = self._channel.receive()
        if message_type != "action":
            raise ContractError(f"expected an action, received {message_type}")
        return Action.from_dict(body)

    def close(self) -> None:
        if self._channel is not None:
            with contextlib.suppress(OSError):
                self._channel.send("end", {})
            self._channel.close()
        self._listener.close()


def run_client(
    agent: _Agent, port: int, host: str = "127.0.0.1", timeout_s: float = DEFAULT_TIMEOUT_S
) -> int:
    """Agent side. Connects, drives the agent until the mission ends, and counts its actions."""
    _require_loopback(host)
    channel = _LineChannel(socket.create_connection((host, port), timeout=timeout_s))
    actions = 0
    try:
        message_type, body = channel.receive()
        if message_type != "start" or not isinstance(body.get("seed"), int):
            raise ContractError("expected a start message with a seed")
        agent.reset(MissionBrief.from_dict(body.get("brief")), body["seed"])
        while True:
            message_type, body = channel.receive()
            if message_type == "end":
                return actions
            if message_type != "observation":
                raise ContractError(f"unexpected bridge message: {message_type}")
            channel.send("action", agent.act(Observation.from_dict(body)).to_dict())
            actions += 1
    finally:
        channel.close()
