"""The router gives manual drivers and agents one identical path."""

import pytest

from roverloom.api import STOP, Action
from roverloom.command import CommandRouter
from roverloom.contract import ContractError, validate


def router(active: str = "agent") -> CommandRouter:
    return CommandRouter(("manual", "agent"), active, 0.5, 0.5, watchdog_timeout_s=2.0)


def test_starts_stopped() -> None:
    assert router().current(0.0) == STOP


def test_accepts_active_source() -> None:
    r = router()
    record = r.submit("agent", Action(0.2, 0.1), 1.0)
    assert record.applied == Action(0.2, 0.1)
    assert not record.clamped
    assert r.current(1.0) == Action(0.2, 0.1)


def test_rejects_inactive_source_without_changing_command() -> None:
    r = router()
    r.submit("agent", Action(0.2, 0.0), 1.0)
    record = r.submit("manual", Action(-0.4, 0.0), 1.1)
    assert record.applied is None
    assert record.rejected_reason == "inactive_source"
    assert r.current(1.1) == Action(0.2, 0.0)


def test_rejects_unknown_source() -> None:
    assert router().submit("intruder", Action(1, 0), 0.0).rejected_reason == "unknown_source"


def test_clamps_and_reports_it() -> None:
    record = router().submit("agent", Action(9.0, -9.0), 0.0)
    assert record.applied == Action(0.5, -0.5)
    assert record.clamped


def test_watchdog_boundary() -> None:
    r = router()
    r.submit("agent", Action(0.2, 0.0), 10.0)
    assert r.current(12.0) == Action(0.2, 0.0)  # Exactly at the timeout it still holds.
    assert r.current(12.1) == STOP
    r.submit("agent", Action(0.3, 0.0), 13.0)
    assert r.current(13.0) == Action(0.3, 0.0)


def test_switching_source_stops_until_the_new_source_commands() -> None:
    r = router("manual")
    r.submit("manual", Action(0.4, 0.0), 1.0)
    r.set_active("agent")
    assert r.current(1.0) == STOP
    r.submit("agent", Action(0.1, 0.0), 1.1)
    assert r.current(1.1) == Action(0.1, 0.0)


def test_unknown_sources_cannot_be_activated() -> None:
    with pytest.raises(ContractError):
        router().set_active("intruder")
    with pytest.raises(ContractError):
        CommandRouter(("agent",), "manual", 1, 1)


def test_records_match_schema() -> None:
    r = router()
    validate("command_record", r.submit("agent", Action(9, 0), 0.0).to_dict())
    validate("command_record", r.submit("manual", Action(0, 0), 0.0).to_dict())
