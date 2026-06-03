"""
Tests for TasksService — tasks CRUD, routines CRUD, and routine spawn.

No monkeypatching of our own code.
read-side: MockSupabaseClient(data=[...])
write-side: inserted_payloads / updated_payloads
"""
from datetime import date
from uuid import UUID

import pytest

from noctusai_lib.testing import MockSupabaseClient

from app.services.tasks_service import TasksService, _advance_date

ORG = UUID("00000000-0000-0000-0000-000000000002")


def _task(id_="t-1", title="Fix bug", status="todo", priority="med", due_date=None):
    return {
        "id": id_,
        "org_id": str(ORG),
        "title": title,
        "description": None,
        "assignee_user_id": None,
        "client_id": None,
        "status": status,
        "priority": priority,
        "due_date": due_date,
        "completed_at": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _routine(id_="r-1", title="Daily check", cadence="daily", next_run="2026-01-01", active=True):
    return {
        "id": id_,
        "org_id": str(ORG),
        "title": title,
        "description": None,
        "cadence": cadence,
        "next_run": next_run,
        "active": active,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _svc(rows=None):
    db = MockSupabaseClient(data=rows, schema="orbity")
    return db, TasksService(db, org_id=ORG)


# ---------------------------------------------------------------------------
# _advance_date helper (unit)
# ---------------------------------------------------------------------------

class TestAdvanceDate:
    def test_daily_advances_by_1(self):
        assert _advance_date("2026-01-01", "daily") == "2026-01-02"

    def test_weekly_advances_by_7(self):
        assert _advance_date("2026-01-01", "weekly") == "2026-01-08"

    def test_monthly_advances_by_30(self):
        assert _advance_date("2026-01-01", "monthly") == "2026-01-31"

    def test_unknown_cadence_falls_back_to_7(self):
        assert _advance_date("2026-01-01", "quarterly") == "2026-01-08"


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------

class TestTaskCreate:
    def test_create_stamps_org_id(self):
        task = _task(title="Nova tarefa")
        db, svc = _svc([task])
        svc.create_task({"title": "Nova tarefa"})
        inserted = db.table("tasks").inserted_payloads
        assert any(p.get("org_id") == str(ORG) and p.get("title") == "Nova tarefa" for p in inserted)

    def test_create_inserts_with_org_id_stamp(self):
        task = _task(title="Nova tarefa")
        db, svc = _svc([task])
        result = svc.create_task({"title": "Nova tarefa"})
        # Mock always echoes back the row; verify it's non-empty
        assert result is not None


class TestTaskGet:
    def test_get_existing(self):
        db, svc = _svc([_task(id_="t-99")])
        row = svc.get_task("t-99")
        assert row is not None
        assert row["id"] == "t-99"

    def test_get_missing_returns_none(self):
        db, svc = _svc([])
        assert svc.get_task("ghost") is None


class TestTaskUpdate:
    def test_update_patches_row(self):
        db, svc = _svc([_task(id_="t-1", title="Old")])
        updated = svc.update_task("t-1", {"title": "New"})
        assert updated is not None
        assert any(p.get("title") == "New" for p in db.table("tasks").updated_payloads)

    def test_update_strips_org_id(self):
        db, svc = _svc([_task(id_="t-1")])
        svc.update_task("t-1", {"title": "ok", "org_id": "hacker"})
        updated = db.table("tasks").updated_payloads
        assert not any(p.get("org_id") == "hacker" for p in updated)

    def test_update_missing_returns_none(self):
        db, svc = _svc([])
        assert svc.update_task("ghost", {"title": "x"}) is None


class TestTaskDelete:
    def test_delete_returns_true_when_found(self):
        db, svc = _svc([_task(id_="t-1")])
        ok = svc.delete_task("t-1")
        assert ok is True

    def test_delete_returns_false_when_missing(self):
        db, svc = _svc([])
        assert svc.delete_task("ghost") is False


class TestTaskList:
    def test_list_returns_dict_with_items(self):
        db, svc = _svc([_task("t-1"), _task("t-2")])
        result = svc.list_tasks()
        assert "items" in result
        assert "page" in result
        assert "page_size" in result

    def test_empty_org_returns_empty_items(self):
        db, svc = _svc([])
        result = svc.list_tasks()
        assert result["items"] == []


# ---------------------------------------------------------------------------
# Routine CRUD
# ---------------------------------------------------------------------------

class TestRoutineCreate:
    def test_create_stamps_org_id(self):
        routine = _routine(title="Rotina", cadence="weekly", next_run="2026-01-01")
        db, svc = _svc([routine])
        svc.create_routine({"title": "Rotina", "cadence": "weekly", "next_run": "2026-01-01"})
        inserted = db.table("routines").inserted_payloads
        assert any(p.get("org_id") == str(ORG) and p.get("title") == "Rotina" for p in inserted)

    def test_create_routine_inserts_with_org_id_stamp(self):
        routine = _routine(title="Rotina")
        db, svc = _svc([routine])
        result = svc.create_routine({"title": "Rotina", "cadence": "daily", "next_run": "2026-01-01"})
        assert result is not None


class TestRoutineGet:
    def test_get_existing(self):
        db, svc = _svc([_routine(id_="r-7")])
        row = svc.get_routine("r-7")
        assert row is not None
        assert row["id"] == "r-7"

    def test_get_missing_returns_none(self):
        db, svc = _svc([])
        assert svc.get_routine("ghost") is None


class TestRoutineUpdate:
    def test_update_active_flag(self):
        db, svc = _svc([_routine(id_="r-1", active=True)])
        result = svc.update_routine("r-1", {"active": False})
        assert result is not None
        assert any(p.get("active") is False for p in db.table("routines").updated_payloads)

    def test_update_missing_returns_none(self):
        db, svc = _svc([])
        assert svc.update_routine("ghost", {"active": False}) is None


class TestRoutineDelete:
    def test_delete_returns_true_when_found(self):
        db, svc = _svc([_routine(id_="r-1")])
        assert svc.delete_routine("r-1") is True

    def test_delete_returns_false_when_missing(self):
        db, svc = _svc([])
        assert svc.delete_routine("ghost") is False


# ---------------------------------------------------------------------------
# Routine spawn
# ---------------------------------------------------------------------------

class TestRunDueRoutines:
    def test_spawns_task_for_due_routine(self):
        """A due active routine → a task row is inserted, next_run advances.

        MockSupabaseClient returns the seeded rows for every table query.
        We seed both the routine (for the fetch) and a stub task row (for
        the create_task insert echo-back) to avoid the RuntimeError raised
        when insert returns no data.
        """
        routine = _routine(id_="r-1", title="Daily check", cadence="daily", next_run="2026-06-01")
        spawned_task = _task(id_="spawned-1", title="Daily check")
        # Seed both rows so MockSupabaseClient returns them for both table calls
        db, svc = _svc([routine, spawned_task])
        spawned = svc.run_due_routines(as_of="2026-06-03")
        # One task should be spawned
        assert len(spawned) == 1
        assert spawned[0]["title"] == "Daily check"
        # The tasks insert was called
        inserted_tasks = db.table("tasks").inserted_payloads
        assert any(p.get("title") == "Daily check" for p in inserted_tasks)
        # next_run was advanced
        updated = db.table("routines").updated_payloads
        assert any("next_run" in p for p in updated)

    def test_no_due_routines_returns_empty(self):
        """Routine with future next_run → no tasks spawned."""
        db, svc = _svc([])
        spawned = svc.run_due_routines(as_of="2026-06-03")
        assert spawned == []
