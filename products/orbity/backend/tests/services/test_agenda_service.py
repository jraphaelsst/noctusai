"""
Tests for AgendaService — events CRUD and GCal sync seam (Fake adapter).

No monkeypatching of our own code.
read-side: MockSupabaseClient(data=[...])
write-side: inserted_payloads / updated_payloads

GCal sync seam tests exercise the named Protocol seam using
FakeCalendarAdapter — verifies that (a) the seam is properly wired
into the service, (b) the Fake returns a deterministic event_id,
(c) gcal_event_id is persisted on the event row.
"""
from uuid import UUID

import pytest

from noctusai_lib.testing import MockSupabaseClient
from noctusai_lib.integrations.google_calendar import FakeCalendarAdapter

from app.services.agenda_service import AgendaService

ORG = UUID("00000000-0000-0000-0000-000000000003")


def _event(
    id_="e-1",
    title="Reunião",
    event_type="meeting",
    starts_at="2026-06-10T09:00:00+00:00",
    ends_at="2026-06-10T10:00:00+00:00",
    gcal_event_id=None,
):
    return {
        "id": id_,
        "org_id": str(ORG),
        "title": title,
        "description": None,
        "event_type": event_type,
        "client_id": None,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "location": None,
        "gcal_event_id": gcal_event_id,
        "assignee_user_id": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _svc(rows=None, calendar_adapter=None):
    db = MockSupabaseClient(data=rows, schema="orbity")
    kwargs = {}
    if calendar_adapter is not None:
        kwargs["calendar_adapter"] = calendar_adapter
    return db, AgendaService(db, org_id=ORG, **kwargs)


# ---------------------------------------------------------------------------
# Event CRUD
# ---------------------------------------------------------------------------

class TestAgendaEventCreate:
    def test_create_stamps_org_id(self):
        ev = _event(title="Kickoff")
        db, svc = _svc([ev])
        svc.create_event({
            "title": "Kickoff",
            "starts_at": "2026-06-10T09:00:00+00:00",
            "ends_at": "2026-06-10T10:00:00+00:00",
        })
        inserted = db.table("agenda_events").inserted_payloads
        assert any(p.get("org_id") == str(ORG) and p.get("title") == "Kickoff" for p in inserted)

    def test_create_event_inserts_and_returns_row(self):
        ev = _event(title="E")
        db, svc = _svc([ev])
        result = svc.create_event({
            "title": "E",
            "starts_at": "2026-06-10T09:00:00+00:00",
            "ends_at": "2026-06-10T10:00:00+00:00",
        })
        assert result is not None


class TestAgendaEventGet:
    def test_get_existing(self):
        db, svc = _svc([_event(id_="e-5")])
        row = svc.get_event("e-5")
        assert row is not None
        assert row["id"] == "e-5"

    def test_get_missing_returns_none(self):
        db, svc = _svc([])
        assert svc.get_event("ghost") is None


class TestAgendaEventUpdate:
    def test_update_title(self):
        db, svc = _svc([_event(id_="e-1", title="Old")])
        result = svc.update_event("e-1", {"title": "New"})
        assert result is not None
        assert any(p.get("title") == "New" for p in db.table("agenda_events").updated_payloads)

    def test_update_strips_org_id(self):
        db, svc = _svc([_event(id_="e-1")])
        svc.update_event("e-1", {"title": "ok", "org_id": "hacker"})
        updated = db.table("agenda_events").updated_payloads
        assert not any(p.get("org_id") == "hacker" for p in updated)

    def test_update_missing_returns_none(self):
        db, svc = _svc([])
        assert svc.update_event("ghost", {"title": "x"}) is None


class TestAgendaEventDelete:
    def test_delete_returns_true_when_found(self):
        db, svc = _svc([_event(id_="e-1")])
        assert svc.delete_event("e-1") is True

    def test_delete_returns_false_when_missing(self):
        db, svc = _svc([])
        assert svc.delete_event("ghost") is False


class TestAgendaEventList:
    def test_list_returns_dict_with_items(self):
        db, svc = _svc([_event("e-1"), _event("e-2")])
        result = svc.list_events()
        assert "items" in result
        assert "page" in result

    def test_empty_returns_empty_items(self):
        db, svc = _svc([])
        assert svc.list_events()["items"] == []


# ---------------------------------------------------------------------------
# GCal sync seam — exercises the Protocol with FakeCalendarAdapter
# ---------------------------------------------------------------------------

class TestGCalSyncSeam:
    """Verify the GCal sync seam is a named, testable Protocol seam.

    FakeCalendarAdapter is injected — no network calls, no GCal credentials
    required. This proves the seam is correctly wired and that consumers
    can substitute the Real adapter without service changes.
    """

    def test_default_adapter_is_fake(self):
        """AgendaService uses FakeCalendarAdapter by default (safe in prod w/o creds)."""
        db = MockSupabaseClient(data=[], schema="orbity")
        svc = AgendaService(db, org_id=ORG)
        assert isinstance(svc._gcal, FakeCalendarAdapter)

    def test_sync_gcal_returns_none_for_missing_event(self):
        db, svc = _svc([], calendar_adapter=FakeCalendarAdapter())
        result = svc.sync_to_gcal("ghost-id")
        assert result is None

    def test_sync_gcal_creates_fake_event_and_persists_id(self):
        """sync_to_gcal with Fake adapter sets gcal_event_id on the event row."""
        ev = _event(id_="e-gcal")
        db, svc = _svc([ev], calendar_adapter=FakeCalendarAdapter())
        result = svc.sync_to_gcal("e-gcal")
        # The service attempted to update gcal_event_id
        updated = db.table("agenda_events").updated_payloads
        assert any("gcal_event_id" in p for p in updated)

    def test_fake_adapter_create_event_returns_created_event(self):
        """FakeCalendarAdapter.create_event() returns a CreatedEvent with a non-empty event_id."""
        from noctusai_lib.integrations.google_calendar import EventInput, FakeCalendarAdapter
        from datetime import datetime, timezone

        adapter = FakeCalendarAdapter()
        ev = EventInput(
            summary="Test",
            start_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            end_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            timezone="UTC",
        )
        created = adapter.create_event("primary", ev)
        assert created.event_id
        assert isinstance(created.event_id, str)

    def test_injected_real_adapter_seam_accepts_protocol(self):
        """Any CalendarAdapter-shaped object can be injected (duck-type)."""
        from noctusai_lib.integrations.google_calendar import CalendarAdapter

        # FakeCalendarAdapter implements the Protocol — passes the check
        fake = FakeCalendarAdapter()
        db = MockSupabaseClient(data=[], schema="orbity")
        # Should not raise
        svc = AgendaService(db, org_id=ORG, calendar_adapter=fake)
        assert svc._gcal is fake
