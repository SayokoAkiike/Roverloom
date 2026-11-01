"""Local server for driving or watching a mission in a browser. Loopback only."""

import threading
import time
import webbrowser
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from roverloom.agents import create_agent
from roverloom.api import STOP, Action, MissionBrief, Observation
from roverloom.contract import ContractError, JsonDict, dump_json, parse_json
from roverloom.preview.report import viewer_html, world_payload
from roverloom.runlog import RunWriter
from roverloom.runner import finalize_run
from roverloom.session import MissionSession
from roverloom.world import SIM_STEP_S, Scenario

_HOST = "127.0.0.1"
_MAX_BODY_BYTES = 4096
_INPUT_TIMEOUT_S = 0.6  # A closed tab must not leave the rover driving.


class ManualSource:
    """The keyboard, as a command source using the same path as every agent."""

    def __init__(self) -> None:
        self._action = STOP
        self._updated = 0.0

    def reset(self, brief: MissionBrief, seed: int) -> None:
        self._action = STOP

    def set_action(self, action: Action) -> None:
        self._action, self._updated = action, time.monotonic()

    def act(self, observation: Observation) -> Action:
        if time.monotonic() - self._updated > _INPUT_TIMEOUT_S:
            return STOP
        return self._action


class LiveMission:
    """Owns the session and runs it on a background thread at a real-time multiple."""

    def __init__(
        self, scenario: Scenario, agent: str, seed: int | None, out_dir: Path, speed: float
    ) -> None:
        if not 0.1 <= speed <= 50.0:
            raise ContractError("speed must be between 0.1 and 50")
        self.scenario, self.agent_spec, self.seed = scenario, agent, seed
        self.out_dir, self.speed = out_dir, speed
        self.lock = threading.Lock()
        self.saved_to: str | None = None
        self.metrics: JsonDict | None = None
        self._stopping = threading.Event()
        self._start_session()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _start_session(self) -> None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        self.manual = ManualSource()
        self.events: list[JsonDict] = []
        self.commands = 0
        self.trail: list[list[float]] = []
        self._writer = RunWriter(self.out_dir / stamp)
        self._started = time.perf_counter()
        self._finalized = False
        self.saved_to = None
        self.metrics = None

        def on_event(event: JsonDict) -> None:
            self.events.append(event)
            self._writer.event(event)

        def on_command(command: JsonDict) -> None:
            self.commands += 1
            self._writer.command(command)

        self.session = MissionSession(
            self.scenario,
            {"manual": self.manual, "agent": create_agent(self.agent_spec)},
            "manual",
            seed=self.seed,
            on_telemetry=self._writer.telemetry,
            on_command=on_command,
            on_event=on_event,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5.0)
        with self.lock:
            self.session.abort()
            self._finalize()

    def _finalize(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        result = finalize_run(
            self._writer,
            self.session,
            f"live:{self.agent_spec}",
            time.perf_counter() - self._started,
        )
        self.saved_to = str(result.directory)
        self.metrics = result.metrics.to_dict()

    def _loop(self) -> None:
        next_time = time.monotonic()
        while not self._stopping.is_set():
            with self.lock:
                if self.session.mission.finished:
                    self._finalize()
                else:
                    self.session.step()
                    pose = self.session.sim.state.pose
                    if self.session.step_index % 5 == 0:
                        self.trail.append([round(pose.x_m, 2), round(pose.y_m, 2)])
            next_time += SIM_STEP_S / self.speed
            delay = next_time - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_time = time.monotonic()

    def reset(self) -> None:
        with self.lock:
            self.session.abort()
            self._finalize()
            self._start_session()

    def snapshot(self) -> JsonDict:
        with self.lock:
            session = self.session
            state = session.sim.state
            pose = state.pose
            mission = session.mission
            capacity = session.scenario.rover.battery_capacity_wh
            return {
                "t": round(session.time_s, 2),
                "x": round(pose.x_m, 3),
                "y": round(pose.y_m, 3),
                "yaw": round(pose.yaw_rad, 4),
                "speed": round(state.ground_speed_mps, 3),
                "battery": round(state.battery_wh / capacity, 4),
                "energy": round(state.energy_used_wh, 2),
                "slip": round(state.slip_fraction, 3),
                "targets_reached": mission.targets_reached,
                "failed_wheels": sorted(state.failed_wheels),
                "active_faults": mission.active_faults,
                "source": session.router.active,
                "outcome": mission.outcome.value,
                "events": self.events[-40:],
                "commands": self.commands,
                "trail": self.trail[-1500:],
                "saved_to": self.saved_to,
                "metrics": self.metrics,
            }


class _Handler(BaseHTTPRequestHandler):
    live: LiveMission
    page: str
    allowed_hosts: frozenset[str]

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, document: JsonDict, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(status, dump_json(document).encode("utf-8"), "application/json")

    def _trusted(self) -> bool:
        # Blocks DNS rebinding and other sites posting to this port from a browser.
        if self.headers.get("Host") not in self.allowed_hosts:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin.removeprefix("http://") in self.allowed_hosts

    def do_GET(self) -> None:
        if not self._trusted():
            self._json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
        elif self.path.split("?")[0] == "/":
            self._send(HTTPStatus.OK, self.page.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._json(self.live.snapshot())
        else:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def _read_json(self) -> JsonDict:
        if "application/json" not in self.headers.get("Content-Type", ""):
            raise ContractError("content type must be application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ContractError("invalid content length") from error
        if not 0 < length <= _MAX_BODY_BYTES:
            raise ContractError("invalid request size")
        document = parse_json(self.rfile.read(length).decode("utf-8", errors="strict"))
        if not isinstance(document, dict):
            raise ContractError("expected an object")
        return document

    def do_POST(self) -> None:
        if not self._trusted():
            self._json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
            return
        try:
            if self.path == "/api/command":
                action = Action.from_dict(self._read_json())
                self.live.manual.set_action(action)
            elif self.path == "/api/mode":
                source = self._read_json().get("source")
                if source not in ("manual", "agent"):
                    raise ContractError("source must be manual or agent")
                with self.live.lock:
                    self.live.session.set_active_source(source)
            elif self.path == "/api/reset":
                self._read_json()
                self.live.reset()
            else:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
        except (ContractError, UnicodeDecodeError) as error:
            self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        self._json({"ok": True})


def make_server(live: LiveMission, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((_HOST, port), _Handler)
    actual = server.server_address[1]
    data = {
        "mode": "live",
        "world": world_payload(live.scenario),
        "agent": live.agent_spec,
        "speed": live.speed,
    }
    handler = type(
        "Handler",
        (_Handler,),
        {
            "live": live,
            "page": viewer_html(data),
            "allowed_hosts": frozenset({f"{_HOST}:{actual}", f"localhost:{actual}"}),
        },
    )
    server.RequestHandlerClass = handler
    return server


def serve(
    scenario: Scenario,
    agent: str,
    seed: int | None,
    port: int,
    out_dir: Path,
    open_browser: bool,
    speed: float,
) -> None:
    live = LiveMission(scenario, agent, seed, out_dir, speed)
    server = make_server(live, port)
    url = f"http://{_HOST}:{server.server_address[1]}/"
    live.start()
    print(f"Lightweight preview, not the Unreal renderer: {url}")
    print(f"Simulation speed: {speed}x. Press Ctrl+C here to stop and save the run.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        live.stop()
        print(f"Run saved: {live.saved_to}")
