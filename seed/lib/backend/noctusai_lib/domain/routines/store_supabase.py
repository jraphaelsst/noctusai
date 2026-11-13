"""Supabase-backed ``RoutineStore`` (the Real half of Protocol + Fake + Real + factory).

Reads use bare table names on a schema-pinned client; every state change goes through the
SECURITY DEFINER functions emitted by ``ddl.routines_tables_sql`` (row + event, one
transaction). Run-lifecycle events (``run_started`` ...) are a single INSERT -- atomic by
itself. ``KB § PATTERNS/backend/postgrest-schema-targeting.md``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping
from uuid import UUID

from noctusai_lib.domain.routines.types import (
    RUN_EVENT_KINDS,
    SCOPE_ROUTINE,
    EventKind,
    Routine,
    RoutineConflict,
    RoutineEvent,
    RoutineInvalid,
    RoutineNotFound,
    need_reason,
    validate_cron,
    validate_mode,
)
from noctusai_lib.integrations.persistence.paging import iter_paged_rows


def _dt(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _routine(r: Mapping[str, Any]) -> Routine:
    return Routine(
        UUID(str(r["id"])), UUID(str(r["org_id"])), r["name"], r["cron"], r["mode"], bool(r["ativo"]),
        bool(r["killed"]), r.get("config") or {}, _dt(r["created_at"]), _dt(r["updated_at"]),
    )


def _event(r: Mapping[str, Any]) -> RoutineEvent:
    rid = r.get("routine_id")
    return RoutineEvent(
        int(r["id"]), UUID(str(r["org_id"])), None if rid is None else UUID(str(rid)), r["scope"], r["kind"],
        UUID(str(r["actor_id"])), r.get("reason"), r.get("detail") or {}, _dt(r["created_at"]),
    )


def map_db_error(exc: BaseException) -> Exception:
    """Translate a DB error into the typed store error; anything else is returned unchanged."""
    text = str(exc)
    if "routines_not_found" in text:
        return RoutineNotFound(text)
    if "routines_org_name_key" in text or "23505" in text:
        return RoutineConflict(text)
    if "routine_events_reason_ck" in text:
        return RoutineInvalid(text)
    return exc if isinstance(exc, Exception) else RuntimeError(text)


class SupabaseRoutineStore:
    def __init__(self, client: Any, *, schema: str) -> None:
        self._client = client
        self.schema = schema

    def _rpc(self, name: str, params: dict[str, Any]) -> Any:
        try:
            data = self._client.rpc(name, params).execute().data
        except Exception as exc:  # noqa: BLE001 -- re-raised typed below, never swallowed
            raise map_db_error(exc) from exc
        return data[0] if isinstance(data, list) and data else data

    # -- writes ----------------------------------------------------------
    def create_routine(self, *, org_id, name, cron, mode, config, actor_id) -> Routine:
        if not (name or "").strip():
            raise RoutineInvalid("name is required")
        rid = self._rpc("routines_create", {
            "p_org_id": str(org_id), "p_actor_id": str(actor_id), "p_name": name,
            "p_cron": validate_cron(cron), "p_mode": validate_mode(mode), "p_config": dict(config or {}),
        })
        return self.get_routine(org_id, UUID(str(rid)))

    def update_routine(self, *, org_id, routine_id, actor_id, name=None, cron=None, config=None,
                       mode=None, reason=None) -> Routine:
        self._rpc("routines_update", {
            "p_org_id": str(org_id), "p_id": str(routine_id), "p_actor_id": str(actor_id),
            "p_name": name, "p_cron": None if cron is None else validate_cron(cron),
            "p_config": None if config is None else dict(config),
            "p_mode": None if mode is None else validate_mode(mode), "p_reason": reason,
        })
        return self.get_routine(org_id, routine_id)

    def set_enabled(self, *, org_id, routine_id, enabled, actor_id, reason) -> Routine:
        kind = EventKind.ENABLED.value if enabled else EventKind.DISABLED.value
        self._rpc("routines_set_enabled", {
            "p_org_id": str(org_id), "p_id": str(routine_id), "p_actor_id": str(actor_id),
            "p_enabled": enabled, "p_reason": need_reason(kind, reason),
        })
        return self.get_routine(org_id, routine_id)

    def kill(self, *, org_id, routine_id, actor_id, reason) -> Routine:
        self._rpc("routines_kill", {
            "p_org_id": str(org_id), "p_id": str(routine_id), "p_actor_id": str(actor_id),
            "p_reason": need_reason(EventKind.KILLED.value, reason),
        })
        return self.get_routine(org_id, routine_id)

    def set_master(self, *, org_id, enabled, actor_id, reason) -> bool:
        kind = EventKind.ENABLED.value if enabled else EventKind.DISABLED.value
        self._rpc("routines_set_master", {
            "p_org_id": str(org_id), "p_actor_id": str(actor_id), "p_enabled": enabled,
            "p_reason": need_reason(kind, reason),
        })
        return self.master_enabled(org_id)

    def record_event(self, *, org_id, routine_id, kind, actor_id, reason=None, detail=None) -> RoutineEvent:
        if kind not in RUN_EVENT_KINDS:
            raise RoutineInvalid(f"{kind!r} cannot be recorded directly; allowed: {sorted(RUN_EVENT_KINDS)}")
        reason = need_reason(kind, reason)
        self.get_routine(org_id, routine_id)  # org scoping: the routine must be this org's
        try:
            rows = self._client.table("routine_events").insert({
                "org_id": str(org_id), "routine_id": str(routine_id), "scope": SCOPE_ROUTINE, "kind": kind,
                "actor_id": str(actor_id), "reason": reason, "detail": dict(detail or {}),
            }).execute().data
        except Exception as exc:  # noqa: BLE001 -- re-raised typed
            raise map_db_error(exc) from exc
        return _event(rows[0])

    # -- reads -----------------------------------------------------------
    def master_enabled(self, org_id) -> bool:
        rows = (
            self._client.table("routine_master_switches").select("enabled")
            .eq("org_id", str(org_id)).limit(1).execute().data
        )
        return bool(rows[0]["enabled"]) if rows else True

    def get_routine(self, org_id, routine_id) -> Routine:
        rows = (
            self._client.table("routines").select("*")
            .eq("org_id", str(org_id)).eq("id", str(routine_id)).limit(1).execute().data
        )
        if not rows:
            raise RoutineNotFound(f"routine {routine_id} not found")
        return _routine(rows[0])

    def list_routines(self, org_id) -> list[Routine]:
        def page(start: int, end: int) -> list[dict[str, Any]]:
            return (
                self._client.table("routines").select("*").eq("org_id", str(org_id))
                .order("id").range(start, end).execute().data
            )

        return sorted(
            (_routine(r) for r in iter_paged_rows(page, label=f"routines org_id={org_id}")),
            key=lambda r: (r.created_at, r.name),
        )

    def list_events(self, org_id, *, routine_id=None, kinds: Iterable[str] | None = None,
                    since: datetime | None = None, limit: int | None = None) -> list[RoutineEvent]:
        def page(start: int, end: int) -> list[dict[str, Any]]:
            q = self._client.table("routine_events").select("*").eq("org_id", str(org_id))
            if routine_id is not None:
                q = q.eq("routine_id", str(routine_id))
            if kinds is not None:
                q = q.in_("kind", sorted(set(kinds)))
            if since is not None:
                q = q.gte("created_at", since.isoformat())
            return q.order("id").range(start, end).execute().data

        out = [_event(r) for r in iter_paged_rows(page, label=f"routine_events org_id={org_id}")]
        return out if limit is None else out[-limit:]

    def list_runnable(self) -> list[Routine]:
        def page(start: int, end: int) -> list[dict[str, Any]]:
            return (
                self._client.table("routines").select("*").eq("ativo", True).eq("killed", False)
                .order("id").range(start, end).execute().data
            )

        routines = [_routine(r) for r in iter_paged_rows(page, label="routines runnable")]
        off = {
            UUID(str(r["org_id"])) for r in iter_paged_rows(
                lambda a, b: self._client.table("routine_master_switches").select("org_id")
                .eq("enabled", False).order("org_id").range(a, b).execute().data,
                id_key="org_id", label="routine_master_switches off",
            )
        }
        return [r for r in routines if r.org_id not in off]


__all__ = ["SupabaseRoutineStore", "map_db_error"]
