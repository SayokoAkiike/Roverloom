"""Science campaign rules: inspecting, collecting, storing, and transmitting.

Values are game points for comparing strategies. They do not represent real science return.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass

from roverloom.api import ScienceStatus, TaskRequest, TaskResult
from roverloom.contract import JsonDict

INSPECT_SHARE = 0.3
COLLECT_SHARE = 0.7
_TASK_POWER_FACTOR = {"inspect": 1.0, "collect": 3.0, "transmit": 1.5}
_STOPPED_MPS = 0.05


@dataclass(slots=True)
class _ActiveTask:
    type: str
    target_id: str | None
    started_s: float
    duration_s: float


class ScienceSystem:
    """Runs tasks on the rover. Truth stays here; agents get only ScienceStatus."""

    def __init__(
        self,
        spec: JsonDict | None,
        has_tool: bool,
        power_w: float,
        emit: Callable[[str, JsonDict], None],
        inspection_noise_sd: float = 0.0,
        rng: random.Random | None = None,
    ) -> None:
        self.enabled = spec is not None
        spec = spec or {"targets": [], "transmit_s_per_item": 1.0, "success_value": 0.0}
        self._targets = {t["id"]: t for t in spec["targets"]}
        self._windows: JsonDict | None = spec.get("data_windows")
        self._transmit_s: float = spec["transmit_s_per_item"]
        self.success_value: float = spec["success_value"]
        self.base: JsonDict | None = spec.get("base")
        # A survey mission counts readings only, so that sampling hardware earns nothing.
        self._survey = bool(spec.get("survey"))
        self._has_tool = has_tool and not self._survey
        self._power = power_w
        self._emit = emit
        self._inspection_noise = inspection_noise_sd
        self._rng = rng or random.Random(0)
        self.inspected: dict[str, float] = {}
        self.collected: list[str] = []
        self._stored: list[tuple[str, str, float]] = []
        self.transmitted_value = 0.0
        self.end_requested = False
        self._active: _ActiveTask | None = None
        self._last_result: TaskResult | None = None
        self._window_was_open: bool | None = None

    @property
    def total_value(self) -> float:
        return float(sum(t["true_value"] for t in self._targets.values()))

    @property
    def busy(self) -> bool:
        return self._active is not None

    @property
    def active_type(self) -> str | None:
        return self._active.type if self._active else None

    @property
    def stored_value(self) -> float:
        return sum(value for _, _, value in self._stored)

    @property
    def task_power_w(self) -> float:
        if self._active is None:
            return 0.0
        return self._power * _TASK_POWER_FACTOR.get(self._active.type, 0.0)

    def window_open(self, time_s: float) -> bool:
        if self._windows is None:
            return True
        phase = (time_s - self._windows["offset_s"]) % self._windows["period_s"]
        return bool(time_s >= self._windows["offset_s"] and phase < self._windows["open_s"])

    def _result(
        self, task: str, target: str | None, status: str, reason: str | None, now: float
    ) -> None:
        self._last_result = TaskResult(task, target, status, reason, round(now, 6))
        event = {"completed": "task_completed", "rejected": "task_rejected"}.get(
            status, "task_failed"
        )
        self._emit(event, {"task": task, "target_id": target, "reason": reason})

    def _rejection(
        self, task: TaskRequest, x: float, y: float, speed: float, now: float
    ) -> str | None:
        kind, target_id = task.type, task.target_id
        if self._active is not None:
            return "busy"
        if kind == "end_mission":
            return None
        if not self.enabled:
            return "no_science_mission"
        if abs(speed) > _STOPPED_MPS:
            return "rover_moving"
        if kind == "transmit":
            if not self._stored:
                return "no_data"
            return None if self.window_open(now) else "window_closed"
        target = self._targets.get(target_id or "")
        if target is None:
            return "unknown_target"
        tx, ty, _ = target["position_m"]
        if (x - tx) ** 2 + (y - ty) ** 2 > target["radius_m"] ** 2:
            return "out_of_range"
        # With noisy readings, measuring again is a real choice. It adds no more data.
        if kind == "inspect" and target_id in self.inspected and not self._inspection_noise:
            return "already_done"
        if kind == "collect":
            if not self._has_tool:
                return "no_sample_tool"
            if target_id not in self.inspected:
                return "needs_inspection"
            if target_id in self.collected:
                return "already_done"
        return None

    def request(self, task: TaskRequest, x: float, y: float, speed: float, now: float) -> None:
        # A lost-reply retry of the running task is not an error.
        if (
            self._active is not None
            and self._active.type == task.type
            and self._active.target_id == task.target_id
        ):
            return
        reason = self._rejection(task, x, y, speed, now)
        if reason is not None:
            self._result(task.type, task.target_id, "rejected", reason, now)
            return
        if task.type == "end_mission":
            self.end_requested = True
            self._result(task.type, None, "completed", None, now)
            return
        if task.type == "transmit":
            duration = self._transmit_s * len(self._stored)
        else:
            target = self._targets[task.target_id or ""]
            duration = target["inspect_s"] if task.type == "inspect" else target["collect_s"]
        self._active = _ActiveTask(task.type, task.target_id, now, float(duration))
        self._emit("task_started", {"task": task.type, "target_id": task.target_id})

    def update(self, now: float, link_up: bool) -> None:
        window = self.window_open(now)
        if self._windows is not None and self.enabled and window != self._window_was_open:
            if self._window_was_open is not None or window:
                self._emit("data_window_opened" if window else "data_window_closed", {})
            self._window_was_open = window
        active = self._active
        if active is None:
            return
        if active.type == "transmit" and not (window and link_up):
            # Data sent before the interruption stays delivered, item by item.
            self._active = None
            reason = "window_closed" if not window else "link_lost"
            self._result(active.type, None, "failed", reason, now)
            return
        if active.type == "transmit":
            while self._stored and now - active.started_s >= self._transmit_s:
                _, _, value = self._stored.pop(0)
                self.transmitted_value += value
                active.started_s += self._transmit_s
            if not self._stored:
                self._active = None
                self._result("transmit", None, "completed", None, now)
            return
        if now - active.started_s + 1e-9 < active.duration_s:
            return
        self._active = None
        target_id = active.target_id or ""
        value = float(self._targets[target_id]["true_value"])
        if active.type == "inspect":
            first = target_id not in self.inspected
            reading = value
            if self._inspection_noise:
                reading = round(max(0.0, self._rng.gauss(value, self._inspection_noise)), 3)
            self.inspected[target_id] = reading
            if first:
                share = 1.0 if self._survey else INSPECT_SHARE
                self._stored.append((target_id, "inspect", value * share))
        else:
            self.collected.append(target_id)
            self._stored.append((target_id, "collect", value * COLLECT_SHARE))
        self._result(active.type, target_id, "completed", None, now)

    def status(self, now: float) -> ScienceStatus | None:
        if not self.enabled:
            return None
        active = self._active
        progress = 0.0
        if active is not None:
            if active.type == "transmit":
                progress = 0.0 if self._stored else 1.0
            else:
                progress = min(1.0, (now - active.started_s) / active.duration_s)
        return ScienceStatus(
            active_task=active.type if active else None,
            task_progress=round(progress, 4),
            inspected=tuple(sorted(self.inspected.items())),
            collected=tuple(self.collected),
            stored_items=len(self._stored),
            stored_value=round(self.stored_value, 6),
            transmitted_value=round(self.transmitted_value, 6),
            data_window_open=self.window_open(now),
            last_result=self._last_result,
        )
