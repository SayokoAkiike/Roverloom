"""Loopback JSON Lines protocol between a simulator and an agent in another process.

The planned Unreal bridge will speak this protocol. Today it is exercised only against the
lightweight backend. See docs/unreal-integration.md.
"""

import contextlib
import ipaddress
import socket
import sys
import threading
import time
from typing import Protocol

from roverloom.api import Action, MissionBrief, Observation
from roverloom.contract import ContractError, JsonDict, dump_json, parse_json

MAX_LINE_BYTES = 1024 * 1024
DEFAULT_TIMEOUT_S = 30.0
PROTOCOL_VERSION = 1


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

    def receive(self, deadline: float | None = None) -> tuple[str, JsonDict]:
        """Read one message. A deadline limits the whole message, not each piece of it."""
        while b"\n" not in self._buffer:
            if len(self._buffer) > MAX_LINE_BYTES:
                raise ContractError("bridge message is too long")
            if deadline is not None:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise ContractError("bridge reply took too long")
                self._socket.settimeout(left)
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
    Each reply has a time limit, and a budget limits the agent's total thinking time.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        total_budget_s: float | None = None,
    ) -> None:
        _require_loopback(host)
        self._timeout = timeout_s
        self._budget = total_budget_s
        self.thinking_s = 0.0
        self._listener = socket.create_server((host, port))
        self._listener.settimeout(timeout_s)
        self.port: int = self._listener.getsockname()[1]
        self._channel: _LineChannel | None = None

    def reset(self, brief: MissionBrief, seed: int) -> None:
        connection, _ = self._listener.accept()
        connection.settimeout(self._timeout)
        self._channel = _LineChannel(connection)
        self._channel.send(
            "start",
            {"protocol_version": PROTOCOL_VERSION, "seed": seed, "brief": brief.to_dict()},
        )

    def act(self, observation: Observation) -> Action:
        if self._channel is None:
            raise ContractError("no bridge client is connected")
        self._channel.send("observation", observation.to_dict())
        started = time.monotonic()
        limit = self._timeout
        if self._budget is not None:
            left = self._budget - self.thinking_s
            if left <= 0:
                raise ContractError("agent used all of its thinking time")
            limit = min(limit, left)
        try:
            message_type, body = self._channel.receive(started + limit)
        finally:
            self.thinking_s += time.monotonic() - started
        if message_type != "action":
            raise ContractError(f"expected an action, received {message_type}")
        return Action.from_dict(body)

    def close(self) -> None:
        if self._channel is not None:
            with contextlib.suppress(OSError):
                self._channel.send("end", {})
            self._channel.close()
        self._listener.close()


class RealtimeCommandLink:
    """Real-time command input, as a game-thread engine needs it. A reference for Unreal.

    A background thread reads the socket, and the simulation takes the newest command when it is
    ready. Older commands are dropped. Bad input or a lost connection drops the client and never
    raises into the simulation. Stopping is the job of the watchdog in CommandRouter, which
    expires on its own when commands stop arriving, whatever the reason.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        _require_loopback(host)
        self._listener = socket.create_server((host, port))
        self.port: int = self._listener.getsockname()[1]
        self._lock = threading.Lock()
        self._latest: Action | None = None
        self.connected = False
        self.received = 0
        self.last_error: str | None = None
        self._closing = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def __enter__(self) -> "RealtimeCommandLink":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def take(self) -> Action | None:
        """Return the newest command not yet taken, or None if there is none."""
        with self._lock:
            action, self._latest = self._latest, None
            return action

    def _serve(self) -> None:
        while not self._closing:
            try:
                connection, _ = self._listener.accept()
            except OSError:
                return
            channel = _LineChannel(connection)
            self.connected = True
            try:
                while True:
                    message_type, body = channel.receive()
                    if message_type != "action":
                        raise ContractError(f"expected an action, received {message_type}")
                    action = Action.from_dict(body)
                    with self._lock:
                        self._latest = action
                        self.received += 1
            except (ContractError, OSError) as error:
                self.last_error = str(error)[:200]
            finally:
                # Commands that arrived before a bad message must not outlive the client.
                with self._lock:
                    self._latest = None
                self.connected = False
                channel.close()

    def close(self) -> None:
        self._closing = True
        self._listener.close()
        self._thread.join(timeout=2.0)


def main() -> int:
    """Run one agent as a separate process: python -m roverloom.bridge FILE:CLASS PORT."""
    from roverloom.agents import create_agent

    spec, port = sys.argv[1], int(sys.argv[2])
    if len(sys.argv) > 3 and sys.argv[3] == "--guarded":
        from roverloom.guard import install_guard

        install_guard(port)
    run_client(create_agent(spec), port)
    return 0


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
        version = body.get("protocol_version", PROTOCOL_VERSION)
        if version != PROTOCOL_VERSION:
            raise ContractError(f"bridge protocol {version} is not {PROTOCOL_VERSION}")
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


if __name__ == "__main__":
    sys.exit(main())
