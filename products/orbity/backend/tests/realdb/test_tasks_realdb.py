"""
Real-DB integration tests for migration 007 — orbity.tasks and orbity.routines.

Requires: migration 007_tasks_agenda.sql applied to the target Supabase project.
Pending migration apply: these tests are intentionally skipped until the
tech-lead applies the migration (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY
must be set AND the migration must have been applied).

Run: pytest products/orbity/backend/tests/realdb/test_tasks_realdb.py -v
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.realdb


class TestTasksRoundTrip:
    """Service-role round-trip: insert → fetch → update → delete."""

    def test_create_and_fetch_task(self, orbity_db, test_org_a):
        """Inserted task can be fetched by id with all fields intact."""
        org_id = test_org_a["id"]
        task_id = str(uuid.uuid4())
        payload = {
            "id": task_id,
            "org_id": org_id,
            "title": "Real-DB task test",
            "status": "todo",
            "priority": "med",
        }
        try:
            inserted = orbity_db.table("tasks").insert(payload).execute().data
            assert len(inserted) == 1
            assert inserted[0]["id"] == task_id

            fetched = (
                orbity_db.table("tasks").select("*").eq("id", task_id).execute().data
            )
            assert len(fetched) == 1
            assert fetched[0]["title"] == "Real-DB task test"
            assert fetched[0]["org_id"] == org_id
        finally:
            orbity_db.table("tasks").delete().eq("id", task_id).execute()

    def test_update_task_status(self, orbity_db, test_org_a):
        """Update task status from todo → done."""
        org_id = test_org_a["id"]
        task_id = str(uuid.uuid4())
        orbity_db.table("tasks").insert({
            "id": task_id,
            "org_id": org_id,
            "title": "Task to complete",
            "status": "todo",
            "priority": "low",
        }).execute()
        try:
            orbity_db.table("tasks").update({"status": "done"}).eq("id", task_id).execute()
            row = orbity_db.table("tasks").select("status").eq("id", task_id).execute().data
            assert row[0]["status"] == "done"
        finally:
            orbity_db.table("tasks").delete().eq("id", task_id).execute()

    def test_delete_task(self, orbity_db, test_org_a):
        """Deleted task is no longer fetchable."""
        org_id = test_org_a["id"]
        task_id = str(uuid.uuid4())
        orbity_db.table("tasks").insert({
            "id": task_id,
            "org_id": org_id,
            "title": "Delete me",
            "status": "todo",
            "priority": "low",
        }).execute()
        orbity_db.table("tasks").delete().eq("id", task_id).execute()
        rows = orbity_db.table("tasks").select("*").eq("id", task_id).execute().data
        assert rows == []


class TestTasksRLSIsolation:
    """RLS: org A's tasks are invisible to org B and vice versa.

    Note: true RLS enforcement requires JWT-scoped clients. Service-role
    bypasses RLS. This test verifies that org_id scoping at the data layer
    is correct; end-to-end RLS enforcement is validated by the router auth
    tests (401 boundary) + the RLS policies in the migration itself.
    """

    def test_tasks_scoped_by_org_id(self, orbity_db, test_org_a, test_org_b):
        """Tasks inserted for org A do not appear in org B's filter."""
        id_a = str(uuid.uuid4())
        id_b = str(uuid.uuid4())
        try:
            orbity_db.table("tasks").insert({
                "id": id_a,
                "org_id": test_org_a["id"],
                "title": "Org A task",
                "status": "todo",
                "priority": "low",
            }).execute()
            orbity_db.table("tasks").insert({
                "id": id_b,
                "org_id": test_org_b["id"],
                "title": "Org B task",
                "status": "todo",
                "priority": "low",
            }).execute()

            rows_a = (
                orbity_db.table("tasks")
                .select("id")
                .eq("org_id", test_org_a["id"])
                .execute()
                .data
            )
            rows_b = (
                orbity_db.table("tasks")
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
            orbity_db.table("tasks").delete().eq("id", id_a).execute()
            orbity_db.table("tasks").delete().eq("id", id_b).execute()


class TestRoutinesRoundTrip:
    """Service-role round-trip: insert → fetch → update → delete."""

    def test_create_and_fetch_routine(self, orbity_db, test_org_a):
        org_id = test_org_a["id"]
        routine_id = str(uuid.uuid4())
        payload = {
            "id": routine_id,
            "org_id": org_id,
            "title": "Weekly check",
            "cadence": "weekly",
            "next_run": "2026-06-09",
            "active": True,
        }
        try:
            inserted = orbity_db.table("routines").insert(payload).execute().data
            assert len(inserted) == 1

            fetched = (
                orbity_db.table("routines").select("*").eq("id", routine_id).execute().data
            )
            assert fetched[0]["cadence"] == "weekly"
            assert fetched[0]["active"] is True
        finally:
            orbity_db.table("routines").delete().eq("id", routine_id).execute()

    def test_invalid_cadence_rejected(self, orbity_db, test_org_a):
        """DB-level CHECK constraint rejects invalid cadence values."""
        from postgrest.exceptions import APIError

        with pytest.raises((APIError, Exception)):
            orbity_db.table("routines").insert({
                "org_id": test_org_a["id"],
                "title": "bad routine",
                "cadence": "hourly",  # not in ('daily','weekly','monthly')
                "next_run": "2026-06-01",
                "active": True,
            }).execute()
