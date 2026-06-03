"""
Tasks service — tasks CRUD, status transition, and routines management.

Routines spawn tasks: when run_due_routines() is called (intended as
a scheduled or on-demand trigger), each active routine whose next_run
<= today is spawned into a tasks row and next_run is advanced by the
cadence.

No silent errors: every except logs at the right level and re-raises.
No mock-data fallbacks: callers receive explicit empty states.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

# Cadence → advance next_run by this many days
_CADENCE_DAYS: dict[str, int] = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
}


def _advance_date(current: str, cadence: str) -> str:
    """Advance an ISO date string by the cadence offset.

    Monthly uses +30 days as an approximation; exact calendar-month
    semantics can be layered on top if required.
    """
    d = date.fromisoformat(current)
    delta = _CADENCE_DAYS.get(cadence, 7)
    return (d + timedelta(days=delta)).isoformat()


class TasksService:
    def __init__(self, db: Any, org_id: UUID) -> None:
        self._db = db
        self._org_id = str(org_id)

    def _t(self, table: str):
        # The Supabase client is already schema-scoped to "orbity" by
        # create_database_module(settings, schema="orbity").
        return self._db.table(table)

    # ------------------------------------------------------------------
    # Tasks CRUD
    # ------------------------------------------------------------------

    def list_tasks(
        self,
        *,
        status: str | None = None,
        priority: str | None = None,
        assignee_user_id: str | None = None,
        client_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        try:
            query = (
                self._t("tasks")
                .select("*")
                .eq("org_id", self._org_id)
                .order("created_at", desc=True)
            )
            if status:
                query = query.eq("status", status)
            if priority:
                query = query.eq("priority", priority)
            if assignee_user_id:
                query = query.eq("assignee_user_id", assignee_user_id)
            if client_id:
                query = query.eq("client_id", client_id)
            offset = (page - 1) * page_size
            query = query.range(offset, offset + page_size - 1)
            result = query.execute()
        except Exception:
            logger.exception("tasks.list_tasks failed org=%s", self._org_id)
            raise
        rows = result.data or []
        return {"items": rows, "page": page, "page_size": page_size, "count": len(rows)}

    def create_task(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert a task row, stamping org_id. Returns the inserted row."""
        payload = {**data, "org_id": self._org_id}
        # Prevent caller from overriding id; generate explicitly so we can
        # return it even when the mock doesn't echo back the insert.
        payload.setdefault("id", str(uuid4()))
        try:
            result = self._t("tasks").insert(payload).execute()
        except Exception:
            logger.exception("tasks.create_task failed org=%s", self._org_id)
            raise
        rows = result.data or []
        if not rows:
            raise RuntimeError(f"tasks.create_task: insert returned no data org={self._org_id}")
        return rows[0]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        try:
            result = (
                self._t("tasks")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", task_id)
                .execute()
            )
        except Exception:
            logger.exception("tasks.get_task failed org=%s id=%s", self._org_id, task_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def update_task(self, task_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        # Strip fields that must not be caller-overridden
        safe = {k: v for k, v in data.items() if k not in ("id", "org_id", "created_at")}
        try:
            result = (
                self._t("tasks")
                .update(safe)
                .eq("org_id", self._org_id)
                .eq("id", task_id)
                .execute()
            )
        except Exception:
            logger.exception("tasks.update_task failed org=%s id=%s", self._org_id, task_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def delete_task(self, task_id: str) -> bool:
        try:
            result = (
                self._t("tasks")
                .delete()
                .eq("org_id", self._org_id)
                .eq("id", task_id)
                .execute()
            )
        except Exception:
            logger.exception("tasks.delete_task failed org=%s id=%s", self._org_id, task_id)
            raise
        return bool(result.data)

    # ------------------------------------------------------------------
    # Routines CRUD + spawn
    # ------------------------------------------------------------------

    def list_routines(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        try:
            query = (
                self._t("routines")
                .select("*")
                .eq("org_id", self._org_id)
                .order("next_run", desc=False)
            )
            if active_only:
                query = query.eq("active", True)
            result = query.execute()
        except Exception:
            logger.exception("tasks.list_routines failed org=%s", self._org_id)
            raise
        return result.data or []

    def create_routine(self, data: dict[str, Any]) -> dict[str, Any]:
        payload = {**data, "org_id": self._org_id}
        payload.setdefault("id", str(uuid4()))
        try:
            result = self._t("routines").insert(payload).execute()
        except Exception:
            logger.exception("tasks.create_routine failed org=%s", self._org_id)
            raise
        rows = result.data or []
        if not rows:
            raise RuntimeError(f"tasks.create_routine: insert returned no data org={self._org_id}")
        return rows[0]

    def get_routine(self, routine_id: str) -> dict[str, Any] | None:
        try:
            result = (
                self._t("routines")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", routine_id)
                .execute()
            )
        except Exception:
            logger.exception("tasks.get_routine failed org=%s id=%s", self._org_id, routine_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def update_routine(self, routine_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        safe = {k: v for k, v in data.items() if k not in ("id", "org_id", "created_at")}
        try:
            result = (
                self._t("routines")
                .update(safe)
                .eq("org_id", self._org_id)
                .eq("id", routine_id)
                .execute()
            )
        except Exception:
            logger.exception("tasks.update_routine failed org=%s id=%s", self._org_id, routine_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def delete_routine(self, routine_id: str) -> bool:
        try:
            result = (
                self._t("routines")
                .delete()
                .eq("org_id", self._org_id)
                .eq("id", routine_id)
                .execute()
            )
        except Exception:
            logger.exception("tasks.delete_routine failed org=%s id=%s", self._org_id, routine_id)
            raise
        return bool(result.data)

    def run_due_routines(self, *, as_of: str | None = None) -> list[dict[str, Any]]:
        """Spawn tasks from active routines due on or before `as_of` date.

        Returns a list of spawned task rows. Advances each routine's
        next_run by its cadence after spawning.

        `as_of` defaults to today (ISO string). Intended for a scheduled
        trigger or manual on-demand endpoint — NOT called automatically
        per-request.
        """
        today = as_of or date.today().isoformat()
        spawned: list[dict[str, Any]] = []
        try:
            result = (
                self._t("routines")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("active", True)
                .lte("next_run", today)
                .execute()
            )
        except Exception:
            logger.exception("tasks.run_due_routines fetch failed org=%s", self._org_id)
            raise

        for routine in result.data or []:
            task_data = {
                "title": routine["title"],
                "description": routine.get("description"),
                "status": "todo",
                "priority": "med",
            }
            try:
                task = self.create_task(task_data)
                spawned.append(task)
            except Exception:
                logger.error(
                    "tasks.run_due_routines failed to spawn task for routine=%s org=%s",
                    routine.get("id"),
                    self._org_id,
                )
                raise

            # Advance next_run for the routine
            new_next_run = _advance_date(routine["next_run"], routine["cadence"])
            try:
                self._t("routines").update({"next_run": new_next_run}).eq(
                    "id", routine["id"]
                ).execute()
            except Exception:
                logger.error(
                    "tasks.run_due_routines failed to advance next_run for routine=%s org=%s",
                    routine.get("id"),
                    self._org_id,
                )
                raise

        return spawned
