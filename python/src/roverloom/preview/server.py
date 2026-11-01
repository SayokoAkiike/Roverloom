"""Local server for driving or watching a mission in a browser. Loopback only."""

import threading
import time
import webbrowser
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from roverloom.agents import BUILTIN_AGENTS, create_agent
from roverloom.api import STOP, Action, MissionBrief, Observation, TaskRequest
from roverloom.contract import ContractError, JsonDict, dump_json, parse_json
from roverloom.preview.report import report_html, viewer_html, world_payload
from roverloom.rover_builder import list_designs
from roverloom.runlog import RunWriter, load_run
from roverloom.runner import finalize_run
from roverloom.session import MissionSession
from roverloom.world import SIM_STEP_S, Scenario, list_practice_scenarios, load_scenario

_HOST = "127.0.0.1"
_MAX_BODY_BYTES = 4096
_DRAIN_LIMIT_BYTES = 1024 * 1024
_TASKS = ("inspect", "collect", "transmit", "end_mission")
_INPUT_TIMEOUT_S = 0.6  # A closed tab must not leave the rover driving.


class ManualSource:
    """The keyboard, as a command source using the same path as every agent."""

    def __init__(self) -> None:
        self._action = STOP
        self._updated = 0.0
        self._task: TaskRequest | None = None

    def reset(self, brief: MissionBrief, seed: int) -> None:
        self._action = STOP
        self._task = None

    def set_action(self, action: Action) -> None:
        self._action, self._updated = action, time.monotonic()

    def request_task(self, task: TaskRequest) -> None:
        self._task = task

    def act(self, observation: Observation) -> Action:
        task, self._task = self._task, None
        if task is not None:
            return Action(0.0, 0.0, task)
        if time.monotonic() - self._updated > _INPUT_TIMEOUT_S:
            return STOP
        return self._action


class LiveMission:
    """Owns the session and runs it on a background thread at a real-time multiple."""

    def __init__(
        self,
        scenario: Scenario,
        agent: str,
        seed: int | None,
        out_dir: Path,
        speed: float,
        scenario_name: str | None = None,
        rover_name: str | None = None,
    ) -> None:
        self.speed = _check_speed(speed)
        self.scenario, self.agent_spec, self.seed = scenario, agent, seed
        self.scenario_name = scenario_name or scenario.scenario_id
        self.rover_name = rover_name
        self.out_dir = out_dir
        self.lock = threading.Lock()
        self.saved_to: str | None = None
        self.metrics: JsonDict | None = None
        self._stopping = threading.Event()
        self._start_session()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _start_session(self) -> None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        self.manual = ManualSource()
        self.agent = create_agent(self.agent_spec)
        self.events: list[JsonDict] = []
        self.decisions: list[JsonDict] = []
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

        def on_decision(decision: JsonDict) -> None:
            self.decisions.append(decision)
            self._writer.decision(decision)

        self.session = MissionSession(
            self.scenario,
            {"manual": self.manual, "agent": self.agent},
            "manual",
            seed=self.seed,
            on_telemetry=self._writer.telemetry,
            on_command=on_command,
            on_event=on_event,
            on_decision=on_decision,
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

    def end_mission(self) -> None:
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

    def configure(self, scenario: str, rover: str, agent: str, speed: float) -> None:
        """Start a new mission with another setup. Choices come only from the published lists."""
        if scenario not in list_practice_scenarios():
            raise ContractError(f"unknown scenario: {scenario}")
        if rover not in rover_choices():
            raise ContractError(f"unknown rover: {rover}")
        if agent not in agent_choices(self.agent_spec):
            raise ContractError(f"unknown agent: {agent}")
        loaded = load_scenario(scenario, rover=rover)
        speed = _check_speed(speed)
        with self.lock:
            self.session.abort()
            self._finalize()
            self.scenario, self.scenario_name, self.rover_name = loaded, scenario, rover
            self.agent_spec, self.speed = agent, speed
            self._start_session()

    def replay_page(self) -> str | None:
        with self.lock:
            saved = self.saved_to
        if saved is None:
            return None
        run = load_run(Path(saved))
        manifest = run.manifest
        key = (manifest["scenario_id"], manifest["agent"], manifest["seed"])
        return report_html([], [(key, run)])

    def control_state(self) -> JsonDict:
        """The display contract, shared with any future Unreal HUD. Caller holds the lock."""
        session = self.session
        state, mission, science = session.sim.state, session.mission, session.science
        pose = state.pose
        status = science.status(session.time_s)
        capacity = session.scenario.rover.battery_capacity_wh
        comms = session.scenario.document.get("comms", {})
        pending = getattr(self.agent, "pending", None)
        return {
            "schema_version": 0,
            "time_s": round(session.time_s, 2),
            "rover": {
                "rover_id": session.scenario.rover.rover_id,
                "x_m": round(pose.x_m, 3),
                "y_m": round(pose.y_m, 3),
                "yaw_rad": round(pose.yaw_rad, 4),
                "speed_mps": round(state.ground_speed_mps, 3),
                "slip_fraction": round(state.slip_fraction, 3),
                "battery_fraction": round(max(0.0, state.battery_wh / capacity), 4),
                "energy_used_wh": round(state.energy_used_wh, 2),
                "power_generation_w": round(state.power_generation_w, 1),
                "failed_wheels": sorted(state.failed_wheels),
                "active_task": science.active_type,
                "task_progress": status.task_progress if status else 0.0,
            },
            "comms": {
                "command_link_up": "comm_blackout" not in mission.active_faults,
                "data_window_open": science.window_open(session.time_s),
                "latency_s": comms.get("latency_s", 0.0),
                "commands_received": self.commands,
            },
            "mission": {
                "scenario_id": session.scenario.scenario_id,
                "outcome": mission.outcome.value,
                "targets_reached": mission.targets_reached,
                "targets_total": mission.targets_total,
                "science_value": round(science.transmitted_value, 3),
                "stored_value": round(science.stored_value, 3),
                "success_value": science.success_value if science.enabled else None,
                "time_limit_s": session.scenario.mission["time_limit_s"],
                "inspected": dict(status.inspected) if status else {},
                "collected": list(status.collected) if status else [],
            },
            "driver": session.router.active,
            "agent": self.agent_spec,
            "active_faults": list(mission.active_faults),
            "events": self.events[-60:],
            "decisions": self.decisions[-30:],
            "trail": self.trail[-1500:],
            "pending_approval": pending.skill if pending is not None else None,
            "metrics": self.metrics,
            "saved_to": self.saved_to,
        }

    def snapshot(self) -> JsonDict:
        with self.lock:
            control = self.control_state()
            rover, mission = control["rover"], control["mission"]
            # The flat keys are the original API, kept for compatibility.
            return {
                "t": control["time_s"],
                "x": rover["x_m"],
                "y": rover["y_m"],
                "yaw": rover["yaw_rad"],
                "speed": rover["speed_mps"],
                "battery": rover["battery_fraction"],
                "energy": rover["energy_used_wh"],
                "slip": rover["slip_fraction"],
                "targets_reached": mission["targets_reached"],
                "failed_wheels": rover["failed_wheels"],
                "active_faults": control["active_faults"],
                "source": control["driver"],
                "outcome": mission["outcome"],
                "events": control["events"],
                "commands": control["comms"]["commands_received"],
                "trail": control["trail"],
                "saved_to": control["saved_to"],
                "metrics": control["metrics"],
                "control": control,
            }

    def options(self) -> JsonDict:
        with self.lock:
            rover = self.rover_name or self.scenario.rover.rover_id
            return {
                "scenarios": list_practice_scenarios(),
                "rovers": rover_choices(),
                "agents": agent_choices(self.agent_spec),
                "current": {
                    "scenario": self.scenario_name,
                    "rover": rover,
                    "agent": self.agent_spec,
                    "speed": self.speed,
                },
            }

    def world(self) -> JsonDict:
        with self.lock:
            return world_payload(self.scenario)


def _check_speed(speed: float) -> float:
    if not isinstance(speed, int | float) or not 0.1 <= speed <= 50.0:
        raise ContractError("speed must be between 0.1 and 50")
    return float(speed)


def rover_choices() -> list[str]:
    return ["standard_6w", *list_designs()]


def agent_choices(current: str) -> list[str]:
    # A custom agent given on the command line stays available. The browser cannot add others.
    names = [name for name in BUILTIN_AGENTS if name != "skill-plan"]
    return names if current in names else [*names, current]


class _Handler(BaseHTTPRequestHandler):
    live: LiveMission
    page: str
    allowed_hosts: frozenset[str]
    _length_ok: bool = False

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
        elif self.path == "/api/world":
            self._json(self.live.world())
        elif self.path == "/api/options":
            self._json(self.live.options())
        elif self.path == "/replay":
            page = self.live.replay_page()
            if page is None:
                self._json({"error": "no finished run yet"}, HTTPStatus.NOT_FOUND)
            else:
                self._send(HTTPStatus.OK, page.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def _read_body(self) -> bytes:
        """Read the whole request first. Replying without it can reset the client's connection."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 <= length <= _DRAIN_LIMIT_BYTES:
            self.close_connection = True
            return b""
        self._length_ok = 0 < length <= _MAX_BODY_BYTES
        return self.rfile.read(length)

    def _read_json(self, body: bytes) -> JsonDict:
        if "application/json" not in self.headers.get("Content-Type", ""):
            raise ContractError("content type must be application/json")
        if not body or not self._length_ok:
            raise ContractError("invalid request size")
        document = parse_json(body.decode("utf-8", errors="strict"))
        if not isinstance(document, dict):
            raise ContractError("expected an object")
        return document

    def do_POST(self) -> None:
        self._length_ok = False
        body = self._read_body()
        if not self._trusted():
            self._json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
            return
        try:
            if self.path == "/api/command":
                action = Action.from_dict(self._read_json(body))
                self.live.manual.set_action(action)
            elif self.path == "/api/mode":
                source = self._read_json(body).get("source")
                if source not in ("manual", "agent"):
                    raise ContractError("source must be manual or agent")
                with self.live.lock:
                    self.live.session.set_active_source(source)
            elif self.path == "/api/reset":
                self._read_json(body)
                self.live.reset()
            elif self.path == "/api/stop":
                self._read_json(body)
                self.live.end_mission()
            elif self.path == "/api/task":
                data = self._read_json(body)
                if data.get("type") not in _TASKS:
                    raise ContractError("unknown task")
                target = data.get("target_id")
                if target is not None and not isinstance(target, str):
                    raise ContractError("target_id must be text")
                self.live.manual.request_task(TaskRequest(data["type"], target))
            elif self.path == "/api/approve":
                approved = self._read_json(body).get("approved")
                answer = getattr(self.live.agent, "answer", None)
                if not isinstance(approved, bool) or answer is None:
                    raise ContractError("nothing to approve")
                with self.live.lock:
                    answer(approved)
            elif self.path == "/api/configure":
                data = self._read_json(body)
                self.live.configure(
                    str(data.get("scenario")),
                    str(data.get("rover")),
                    str(data.get("agent")),
                    data.get("speed", self.live.speed),
                )
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
    scenario_name: str | None = None,
    rover_name: str | None = None,
) -> None:
    live = LiveMission(scenario, agent, seed, out_dir, speed, scenario_name, rover_name)
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
