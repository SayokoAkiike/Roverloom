"""One command path for manual drivers, agents, and future remote clients."""

import math
from dataclasses import dataclass

from roverloom.api import SCHEMA_VERSION, STOP, Action
from roverloom.contract import ContractError, JsonDict

WATCHDOG_TIMEOUT_S = 2.0


@dataclass(frozen=True, slots=True)
class CommandRecord:
    time_s: float
    source: str
    requested: Action
    applied: Action | None
    clamped: bool
    rejected_reason: str | None

    def to_dict(self) -> JsonDict:
        return {
            "schema_version": SCHEMA_VERSION,
            "time_s": round(self.time_s, 6),
            "source": self.source,
            "requested": self.requested.to_dict(),
            "applied": None if self.applied is None else self.applied.to_dict(),
            "clamped": self.clamped,
            "rejected_reason": self.rejected_reason,
        }


class CommandRouter:
    """Selects one active source, clamps commands, and stops a rover that loses contact."""

    def __init__(
        self,
        sources: tuple[str, ...],
        active: str,
        max_speed_mps: float,
        max_yaw_rate_radps: float,
        watchdog_timeout_s: float = WATCHDOG_TIMEOUT_S,
    ) -> None:
        if active not in sources:
            raise ContractError(f"active source is not registered: {active}")
        self._sources = sources
        self.active = active
        self._max_speed = max_speed_mps
        self._max_yaw = max_yaw_rate_radps
        self._timeout = watchdog_timeout_s
        self._current = STOP
        self._last_accept_s: float | None = None

    def set_active(self, source: str) -> None:
        if source not in self._sources:
            raise ContractError(f"unknown command source: {source}")
        # Handover starts from a stop, so a stale command cannot carry over.
        if source != self.active:
            self.active = source
            self._current = STOP
            self._last_accept_s = None

    def submit(self, source: str, action: Action, time_s: float) -> CommandRecord:
        if source not in self._sources:
            return CommandRecord(time_s, source, action, None, False, "unknown_source")
        if source != self.active:
            return CommandRecord(time_s, source, action, None, False, "inactive_source")
        speed = max(-self._max_speed, min(self._max_speed, action.linear_velocity_mps))
        yaw = max(-self._max_yaw, min(self._max_yaw, action.yaw_rate_radps))
        applied = Action(speed, yaw)
        clamped = not (
            math.isclose(speed, action.linear_velocity_mps)
            and math.isclose(yaw, action.yaw_rate_radps)
        )
        self._current = applied
        self._last_accept_s = time_s
        return CommandRecord(time_s, source, action, applied, clamped, None)

    @property
    def has_commanded(self) -> bool:
        return self._last_accept_s is not None

    def watchdog_expired(self, time_s: float) -> bool:
        return self._last_accept_s is None or time_s - self._last_accept_s > self._timeout

    def current(self, time_s: float) -> Action:
        return STOP if self.watchdog_expired(time_s) else self._current
