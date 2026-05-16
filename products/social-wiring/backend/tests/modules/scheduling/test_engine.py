"""Tests for the absorbed scheduling engine wiring (Wave 2.3).

These exercise the real-estate scheduling domain — rules construction,
the seed ``SchedulingEngine`` integration, and the
propose→confirm→cancel→reschedule lifecycle — against a schema-
validation-off ``MockSupabaseClient`` (the ``sched_*`` tables land in
``001_social-wiring.sql`` via the architect's W2.3 splice, so the
migration-derived schema cache is intentionally bypassed here).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from noctusai_lib.testing import MockSupabaseClient
from app.modules.scheduling.engine import (
    DEFAULT_RULE_CONFIG,
    SchedulingRuleDefaults,
    SchedulingService,
    build_engine,
    build_rules,
)

_ORG = UUID("00000000-0000-4000-8000-000000000001")


def test_build_rules_default_windows_and_lunch_gap():
    rules = build_rules(DEFAULT_RULE_CONFIG)
    names = sorted(w.name for w in rules.working_windows)
    assert names == ["afternoon", "morning"]
    assert rules.transition_buffer_minutes == 10
    assert rules.default_duration_minutes == 90
    # The lunch block is the implicit gap 12:00 → 13:30 — no window covers it.
    morning = next(w for w in rules.working_windows if w.name == "morning")
    afternoon = next(w for w in rules.working_windows if w.name == "afternoon")
    assert morning.end.hour == 12
    assert afternoon.start.hour == 13 and afternoon.start.minute == 30


def test_build_rules_accepts_custom_config():
    cfg = SchedulingRuleDefaults(
        timezone="UTC",
        morning_start="08:00",
        morning_end="11:00",
        afternoon_start="14:00",
        afternoon_end="18:00",
        travel_buffer_minutes=5,
        slot_grid_minutes=15,
    )
    rules = build_rules(cfg)
    assert rules.transition_buffer_minutes == 5
    assert rules.slot_grid_minutes == 15
    assert str(rules.timezone) == "UTC"


def test_build_engine_default_conflicts_and_scorer():
    engine = build_engine(build_rules())
    assert len(engine.conflicts) == 1  # DefaultConflict only by default


def _client_with(rows: list[dict]) -> MockSupabaseClient:
    # validate_schema=False — the sched_* tables are spliced into 001 by
    # the architect (W2.3 marker); the schema cache isn't aware of them
    # during this scoped engineer run.
    return MockSupabaseClient(rows, validate_schema=False)


def test_lookup_property_not_found_returns_found_false():
    svc = SchedulingService(
        _client_with([]),
        org_id=_ORG,
        rules=build_rules(),
    )
    result = svc.lookup_property("AP-404")
    assert result.found is False
    assert result.code == "AP-404"


def test_lookup_property_found_resolves_condominium():
    prop_id = str(uuid4())
    condo_id = str(uuid4())
    rows = [
        {
            "id": prop_id,
            "code": "AP-2034",
            "condominium_id": condo_id,
            "active": True,
            "org_id": str(_ORG),
            "name": "Residencial Aurora",
        }
    ]
    svc = SchedulingService(_client_with(rows), org_id=_ORG, rules=build_rules())
    result = svc.lookup_property("AP-2034")
    assert result.found is True
    assert result.property_id == prop_id
    assert result.condominium_id == condo_id


def test_propose_appointment_unknown_property_raises_value_error():
    svc = SchedulingService(_client_with([]), org_id=_ORG, rules=build_rules())
    with pytest.raises(ValueError, match="Property code not found"):
        svc.propose_appointment(
            property_code="NOPE",
            requested_date=date.today() + timedelta(days=3),
            time_window="any",
        )


def test_propose_appointment_returns_engine_slots():
    prop_id = str(uuid4())
    condo_id = str(uuid4())
    # Single row reused for properties + condominium + (empty) appointments.
    rows = [
        {
            "id": prop_id,
            "code": "AP-1",
            "condominium_id": condo_id,
            "active": True,
            "org_id": str(_ORG),
            "name": "Cond X",
        }
    ]
    svc = SchedulingService(_client_with(rows), org_id=_ORG, rules=build_rules())
    target = date.today() + timedelta(days=5)
    slots = svc.propose_appointment(
        property_code="AP-1",
        requested_date=target,
        time_window="morning",
        limit=3,
    )
    assert isinstance(slots, list)
    # Morning window 09:00–12:00 with 90-min default duration → at least
    # one candidate slot exists with no existing bookings.
    assert len(slots) >= 1
    for s in slots:
        assert s.duration_minutes == 90
        assert s.start_at.endswith("+00:00") or "T" in s.start_at


def test_confirm_appointment_rejects_end_before_start():
    svc = SchedulingService(_client_with([]), org_id=_ORG, rules=build_rules())
    now = datetime(2030, 6, 1, 10, 0, tzinfo=timezone.utc)
    result = svc.confirm_appointment(
        property_code="AP-1",
        start_at=now,
        end_at=now,  # equal → not strictly after
    )
    assert result.created is False
    assert "strictly after" in (result.reason or "")


def test_cancel_appointment_not_found():
    svc = SchedulingService(_client_with([]), org_id=_ORG, rules=build_rules())
    result = svc.cancel_appointment(appointment_id=str(uuid4()))
    assert result.cancelled is False
    assert "not found" in (result.reason or "")


def test_reschedule_rejects_non_chronological_window():
    svc = SchedulingService(_client_with([]), org_id=_ORG, rules=build_rules())
    start = datetime(2030, 6, 1, 10, 0, tzinfo=timezone.utc)
    result = svc.reschedule_appointment(
        appointment_id=str(uuid4()),
        new_start_at=start,
        new_end_at=start - timedelta(hours=1),
    )
    assert result.rescheduled is False
    assert "strictly after" in (result.reason or "")
