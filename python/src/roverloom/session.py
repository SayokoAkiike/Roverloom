"""Advances one mission step by step. Shared by batch runs and the live preview."""

import math
import random
from collections.abc import Callable, Mapping
from typing import Protocol

from roverloom.api import (
    SCHEMA_VERSION,
    STOP,
    Action,
    MissionBrief,
    MissionOutcome,
    MissionState,
    Observation,
)
from roverloom.command import CommandRecord, CommandRouter
from roverloom.contract import ContractError, JsonDict
from roverloom.science import ScienceSystem
from roverloom.sim import CommLink, Effects, Fault, RoverSim, Sensors, build_fault_schedule
from roverloom.world import SIM_STEP_S, Scenario

_DUST_RANGE_LOSS = 0.7
_NOISE_BURST_GAIN = 10.0
_SLIP_BURST = 0.6
_BROWNOUT_LOAD_W = 500.0


class CommandSource(Protocol):
    """Anything that can drive the rover: an agent, a keyboard, or a remote client."""

    def reset(self, brief: MissionBrief, seed: int) -> None: ...

    def act(self, observation: Observation) -> Action: ...


def _telemetry_record(step: int, time_s: float, session: "MissionSession") -> JsonDict:
    state = session.sim.state
    yaw = state.pose.yaw_rad
    science = session.science
    return {
        "schema_version": SCHEMA_VERSION,
        "power_generation_w": round(state.power_generation_w, 3),
        "data_window_open": science.window_open(time_s),
        "science_value": round(science.transmitted_value, 6),
        "stored_value": round(science.stored_value, 6),
        "active_task": science.active_type,
        "active_faults": session.mission.active_faults,
        "source": session.router.active,
        "step": step,
        "time_s": round(time_s, 6),
        "pose": state.pose.to_dict(),
        "linear_velocity_mps": [
            round(state.ground_speed_mps * math.cos(yaw), 6),
            round(state.ground_speed_mps * math.sin(yaw), 6),
            0.0,
        ],
        "yaw_rate_radps": round(state.yaw_rate_radps, 6),
        "slip_fraction": round(state.slip_fraction, 6),
        "distance_m": round(state.distance_m, 6),
        "battery_fraction": round(
            max(0.0, min(1.0, state.battery_wh / session.scenario.rover.battery_capacity_wh)), 6
        ),
        "energy_used_wh": round(state.energy_used_wh, 6),
        "failed_wheels": sorted(state.failed_wheels),
        "targets_reached": session.mission.targets_reached,
    }


class MissionSession:
    """Runs a mission with latency, faults, and noise between truth and the command sources."""

    def __init__(
        self,
        scenario: Scenario,
        sources: Mapping[str, CommandSource],
        active: str,
        seed: int | None = None,
        on_telemetry: Callable[[JsonDict], None] | None = None,
        on_command: Callable[[JsonDict], None] | None = None,
        on_event: Callable[[JsonDict], None] | None = None,
        on_decision: Callable[[JsonDict], None] | None = None,
    ) -> None:
        self.scenario = scenario
        self.seed = scenario.seed if seed is None else seed
        self.step_index = 0
        self.mission = MissionState(targets_total=len(scenario.targets))
        self.sim = RoverSim(scenario, self.seed)
        self.brief = scenario.brief()
        self.faults: list[Fault] = build_fault_schedule(scenario, self.seed)
        self._sources = dict(sources)
        self._on_telemetry = on_telemetry or (lambda _: None)
        self._on_command = on_command or (lambda _: None)
        self._on_event = on_event or (lambda _: None)
        self._on_decision = on_decision or (lambda _: None)
        self._control_every = round(self.brief.control_period_s / SIM_STEP_S)
        self.router = CommandRouter(
            tuple(sources),
            active,
            scenario.rover.max_speed_mps,
            scenario.rover.max_yaw_rate_radps,
        )
        self._sensors = Sensors(scenario, self.seed)
        comms = scenario.document.get("comms", {"latency_s": 0.0, "loss_probability": 0.0})
        self._down: CommLink[Observation] = CommLink(
            comms["latency_s"], comms["loss_probability"], random.Random(f"down:{self.seed}")
        )
        self._up: CommLink[tuple[str, Action]] = CommLink(
            comms["latency_s"], comms["loss_probability"], random.Random(f"up:{self.seed}")
        )
        self._active_faults: list[Fault] = []
        self._pending_faults = list(self.faults)
        self._in_collision = False
        self._watchdog_stopped = False
        self._event_seq = 0
        self._time_limit = float(scenario.mission["time_limit_s"])
        self._energy_limit: float | None = scenario.mission.get("energy_limit_wh")
        rover_doc = scenario.rover.document
        uncertainty = scenario.document.get("uncertainty", {})
        self.science = ScienceSystem(
            scenario.mission.get("science"),
            rover_doc.get("has_sample_tool", True),
            float(rover_doc.get("instrument_power_w", 100.0)),
            self._emit,
            float(uncertainty.get("inspection_noise_sd", 0.0)),
            random.Random(f"inspection:{self.seed}"),
        )
        self._emit("mission_started", {"scenario": scenario.scenario_id, "seed": self.seed})
        for name, source in sources.items():
            try:
                source.reset(self.brief, _source_seed(self.seed, name))
            except Exception as error:  # A failing source must not crash the batch.
                self._agent_failed(name, error)
                break

    @property
    def time_s(self) -> float:
        # An integer step count avoids accumulating floating point error.
        return self.step_index * SIM_STEP_S

    def _emit(self, event_type: str, data: JsonDict) -> None:
        self._on_event(
            {
                "schema_version": SCHEMA_VERSION,
                "seq": self._event_seq,
                "time_s": round(self.time_s, 6),
                "type": event_type,
                "data": data,
            }
        )
        self._event_seq += 1

    def _fault_active(self, fault_type: str) -> bool:
        return any(f.type == fault_type for f in self._active_faults)

    def _severity(self, fault_type: str) -> float:
        return max((f.severity for f in self._active_faults if f.type == fault_type), default=0.0)

    def _agent_failed(self, source: str, error: Exception) -> None:
        message = f"{type(error).__name__}: {error}"[:500]
        self._emit("agent_error", {"source": source, "error": message})
        self._finish(MissionOutcome.AGENT_ERROR)

    def _drain_decisions(self, name: str) -> None:
        drain = getattr(self._sources[name], "drain_decisions", None)
        if drain is None:
            return
        for item in drain():
            kind, text = item if isinstance(item, tuple) else (None, item)
            record: JsonDict = {
                "schema_version": SCHEMA_VERSION,
                "time_s": round(self.time_s, 6),
                "source": name,
                "text": str(text)[:500],
            }
            if kind is not None:
                record["kind"] = kind
            self._on_decision(record)

    def _update_faults(self) -> None:
        now = self.time_s + 1e-9
        while self._pending_faults and self._pending_faults[0].start_time_s <= now:
            fault = self._pending_faults.pop(0)
            if fault.wheel is not None:
                self.sim.fail_wheel(fault.wheel)
            self._active_faults.append(fault)
            self._emit("fault_started", fault.to_dict())
        for fault in list(self._active_faults):
            end = fault.end_time_s
            if end is not None and end <= now:
                self._active_faults.remove(fault)
                self._emit("fault_ended", fault.to_dict())
        self.mission.active_faults = sorted(f.type for f in self._active_faults)

    def _record_command(self, record: CommandRecord) -> None:
        self._on_command(record.to_dict())

    def _exchange(self) -> None:
        """Move sensor data down and commands up, each through its own delayed link."""
        now = self.time_s
        blackout = self._fault_active("comm_blackout")
        if self.step_index % self._control_every == 0:
            observation = self._sensors.observe(
                now,
                self.sim.state,
                self.mission.targets_reached,
                range_available=not self._fault_active("sensor_dropout"),
                range_scale=1.0 - _DUST_RANGE_LOSS * self._severity("dust_storm"),
                noise_scale=1.0 + _NOISE_BURST_GAIN * self._severity("sensor_noise_burst"),
                science=self.science.status(now),
            )
            self._down.send(now, observation, blackout)
        delivered = self._down.receive(now, blackout)
        if delivered:
            active = self.router.active
            try:
                action = self._sources[active].act(delivered[-1])
                if not isinstance(action, Action):
                    raise ContractError(f"source returned {type(action).__name__}, not Action")
            except Exception as error:  # A failing source must not corrupt the mission.
                self._agent_failed(active, error)
                return
            self._drain_decisions(active)
            self._up.send(now, (active, action), blackout)
        for source, action in self._up.receive(now, blackout):
            record = self.router.submit(source, action, now)
            self._record_command(record)
            if record.applied is not None and record.applied.task is not None:
                state = self.sim.state
                self.science.request(
                    record.applied.task, state.pose.x_m, state.pose.y_m, state.wheel_speed_mps, now
                )

    def _update_watchdog(self) -> None:
        expired = self.router.watchdog_expired(self.time_s)
        # A rover that has never received a command is simply idle, not stopped by the watchdog.
        if expired and not self._watchdog_stopped and self.router.has_commanded:
            self._emit("watchdog_stop", {"source": self.router.active})
            self._watchdog_stopped = True
        elif not expired and self._watchdog_stopped:
            self._emit("watchdog_cleared", {"source": self.router.active})
            self._watchdog_stopped = False

    def _update_mission(self) -> None:
        state, mission = self.sim.state, self.mission
        pose = state.pose
        while mission.targets_reached < mission.targets_total:
            target = self.scenario.targets[mission.targets_reached]
            if math.hypot(pose.x_m - target.x_m, pose.y_m - target.y_m) > target.radius_m:
                break
            self._emit("target_reached", {"index": mission.targets_reached})
            mission.targets_reached += 1
        science = self.science
        if science.end_requested:
            self._finish(self._science_outcome())
        elif not science.enabled and mission.targets_reached == mission.targets_total:
            self._finish(MissionOutcome.SUCCESS)
        if mission.finished:
            return
        if state.battery_wh <= 0.0:
            self._finish(MissionOutcome.BATTERY_DEPLETED)
        elif self._energy_limit is not None and state.energy_used_wh >= self._energy_limit:
            self._finish(MissionOutcome.ENERGY_LIMIT)
        elif self.time_s >= self._time_limit:
            self._finish(MissionOutcome.TIME_LIMIT)

    def _at_base(self) -> bool:
        base = self.science.base
        if base is None:
            return False
        pose = self.sim.state.pose
        x, y, _ = base["position_m"]
        return bool(math.hypot(pose.x_m - x, pose.y_m - y) <= base["radius_m"])

    def _science_outcome(self) -> MissionOutcome:
        science, mission = self.science, self.mission
        if not science.enabled:
            return MissionOutcome.ENDED_EARLY
        base_ok = science.base is None or not science.base["required"] or self._at_base()
        value_ok = science.transmitted_value + 1e-9 >= science.success_value
        targets_ok = mission.targets_reached == mission.targets_total
        if base_ok and value_ok and targets_ok:
            return MissionOutcome.SUCCESS
        return MissionOutcome.ENDED_EARLY

    def _finish(self, outcome: MissionOutcome) -> None:
        if not self.mission.finished:
            self.mission.outcome = outcome
            self._emit(
                "mission_ended",
                {
                    "outcome": outcome.value,
                    "targets_reached": self.mission.targets_reached,
                    "science_value": round(self.science.transmitted_value, 6),
                    "at_base": self._at_base(),
                },
            )

    def abort(self) -> None:
        self._finish(MissionOutcome.ABORTED)

    def set_active_source(self, source: str) -> None:
        # Nothing may follow mission_ended, or the log would no longer load.
        if source != self.router.active and not self.mission.finished:
            self.router.set_active(source)
            self._emit("source_changed", {"source": source})

    def step(self) -> None:
        """Advance one fixed step. Does nothing once the mission has finished."""
        if self.mission.finished:
            return
        self._update_faults()
        self._exchange()
        if self.mission.finished:
            return
        self.science.update(self.time_s, not self._fault_active("comm_blackout"))
        self._update_watchdog()
        # The rover holds still while a task runs, whatever it is commanded.
        command = STOP if self.science.busy else self.router.current(self.time_s)
        effects = Effects(
            extra_slip=_SLIP_BURST * self._severity("slip_burst"),
            immobilized=self._fault_active("immobilized"),
            solar_scale=1.0 - self._severity("dust_storm"),
            extra_load_w=_BROWNOUT_LOAD_W * self._severity("power_brownout"),
            task_power_w=self.science.task_power_w,
        )
        hit = self.sim.step(command, SIM_STEP_S, effects)
        if hit and not self._in_collision:
            pose = self.sim.state.pose
            self._emit("collision", {"x_m": round(pose.x_m, 3), "y_m": round(pose.y_m, 3)})
        self._in_collision = hit
        self.step_index += 1
        self._update_mission()
        self._on_telemetry(_telemetry_record(self.step_index, self.time_s, self))


def _source_seed(seed: int, name: str) -> int:
    return random.Random(f"source:{seed}:{name}").getrandbits(32)
