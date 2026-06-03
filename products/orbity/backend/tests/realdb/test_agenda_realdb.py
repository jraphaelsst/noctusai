"""
Real-DB integration tests for migration 007 — orbity.agenda_events.

Requires: migration 007_tasks_agenda.sql applied to the target Supabase project.
Pending migration apply: these tests are intentionally skipped until the
tech-lead applies the migration (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY
must be set AND the migration must have been applied).

Run: pytest products/orbity/backend/tests/realdb/test_agenda_realdb.py -v
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.realdb


class TestAgendaEventsRoundTrip:
    """Service-role round-trip: insert → fetch → update → delete."""

    def test_create_and_fetch_event(self, orbity_db, test_org_a):
        org_id = test_org_a["id"]
        event_id = str(uuid.uuid4())
        payload = {
            "id": event_id,
            "org_id": org_id,
            "title": "Kickoff meeting",
            "event_type": "meeting",
            "starts_at": "2026-06-10T09:00:00+00:00",
            "ends_at": "2026-06-10T10:00:00+00:00",
        }
        try:
            inserted = orbity_db.table("agenda_events").insert(payload).execute().data
            assert len(inserted) == 1

            fetched = (
                orbity_db.table("agenda_events").select("*").eq("id", event_id).execute().data
            )
            assert len(fetched) == 1
            assert fetched[0]["title"] == "Kickoff meeting"
            assert fetched[0]["gcal_event_id"] is None  # Not synced yet
        finally:
            orbity_db.table("agenda_events").delete().eq("id", event_id).execute()

    def test_update_gcal_event_id(self, orbity_db, test_org_a):
        """gcal_event_id can be set (simulates GCal sync seam write)."""
        org_id = test_org_a["id"]
        event_id = str(uuid.uuid4())
        orbity_db.table("agenda_events").insert({
            "id": event_id,
            "org_id": org_id,
            "title": "Sync test event",
            "event_type": "call",
            "starts_at": "2026-06-11T14:00:00+00:00",
            "ends_at": "2026-06-11T15:00:00+00:00",
        }).execute()
        try:
            fake_gcal_id = f"fake_gcal_{uuid.uuid4().hex[:8]}"
            orbity_db.table("agenda_events").update(
                {"gcal_event_id": fake_gcal_id}
            ).eq("id", event_id).execute()

            row = (
                orbity_db.table("agenda_events")
                .select("gcal_event_id")
                .eq("id", event_id)
                .execute()
                .data
            )
            assert row[0]["gcal_event_id"] == fake_gcal_id
        finally:
            orbity_db.table("agenda_events").delete().eq("id", event_id).execute()

    def test_time_order_constraint_rejected(self, orbity_db, test_org_a):
        """ends_at must be after starts_at — DB CHECK constraint rejects inversion."""
        from postgrest.exceptions import APIError

        with pytest.raises((APIError, Exception)):
            orbity_db.table("agenda_events").insert({
                "org_id": test_org_a["id"],
                "title": "Bad event",
                "event_type": "other",
                "starts_at": "2026-06-10T10:00:00+00:00",
                "ends_at": "2026-06-10T09:00:00+00:00",  # BEFORE starts_at
            }).execute()

    def test_invalid_event_type_rejected(self, orbity_db, test_org_a):
        """DB-level CHECK constraint rejects unknown event_type values."""
        from postgrest.exceptions import APIError

        with pytest.raises((APIError, Exception)):
            orbity_db.table("agenda_events").insert({
                "org_id": test_org_a["id"],
                "title": "bad type event",
                "event_type": "webinar",  # not in ('meeting','call','visit','other')
                "starts_at": "2026-06-10T09:00:00+00:00",
                "ends_at": "2026-06-10T10:00:00+00:00",
            }).execute()


class TestAgendaEventsRLSIsolation:
    """Verify org_id scoping at the data layer (service-role client)."""

    def test_events_scoped_by_org_id(self, orbity_db, test_org_a, test_org_b):
        id_a = str(uuid.uuid4())
        id_b = str(uuid.uuid4())
        try:
            orbity_db.table("agenda_events").insert({
                "id": id_a,
                "org_id": test_org_a["id"],
                "title": "Org A event",
                "event_type": "meeting",
                "starts_at": "2026-06-10T09:00:00+00:00",
                "ends_at": "2026-06-10T10:00:00+00:00",
            }).execute()
            orbity_db.table("agenda_events").insert({
                "id": id_b,
                "org_id": test_org_b["id"],
                "title": "Org B event",
                "event_type": "call",
                "starts_at": "2026-06-10T11:00:00+00:00",
                "ends_at": "2026-06-10T12:00:00+00:00",
            }).execute()

            rows_a = (
                orbity_db.table("agenda_events")
                .select("id")
                .eq("org_id", test_org_a["id"])
                .execute()
                .data
            )
            rows_b = (
                orbity_db.table("agenda_events")
                .select("id")
                .eq("org_id", test_org_b["id"])
                .execute()
                .data
            )
            ids_a = {r["id"] for r in rows_a}
            ids_b = {r["id"] for r in rows_b}
            assert id_a in ids_a
            assert id_a not in ids_b
            assert id_b in ids_b
            assert id_b not in ids_a
        finally:
            orbity_db.table("agenda_events").delete().eq("id", id_a).execute()
            orbity_db.table("agenda_events").delete().eq("id", id_b).execute()
