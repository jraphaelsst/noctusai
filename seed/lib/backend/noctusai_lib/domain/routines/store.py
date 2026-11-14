"""``RoutineStore`` Protocol + ``FakeRoutineStore`` + ``make_routine_store`` factory.

Every mutation writes its event in the SAME unit of work as the change (the Supabase
store does it inside one SECURITY DEFINER function, the Fake under one method), so a
routine can never change state without leaving its who / when / why.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Protocol
from uuid import UUID, uuid4

from noctusai_lib.domain.routines.types import (
    RUN_EVENT_KINDS,
    SCOPE_MASTER,
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


class RoutineStore(Protocol):
    def create_routine(
        self, *, org_id: UUID, name: str, cron: str, mode: str, config: Mapping[str, Any], actor_id: UUID,
    ) -> Routine: ...

    def update_routine(
        self, *, org_id: UUID, routine_id: UUID, actor_id: UUID, name: str | None = None,
        cron: str | None = None, config: Mapping[str, Any] | None = None, mode: str | None = None,
        reason: str | None = None,
    ) -> Routine: ...

    def set_enabled(
        self, *, org_id: UUID, routine_id: UUID, enabled: bool, actor_id: UUID, reason: str,
    ) -> Routine: ...

    def kill(self, *, org_id: UUID, routine_id: UUID, actor_id: UUID, reason: str) -> Routine: ...

    def set_master(self, *, org_id: UUID, enabled: bool, actor_id: UUID, reason: str) -> bool: ...

    def master_enabled(self, org_id: UUID) -> bool: ...

    def record_event(
        self, *, org_id: UUID, routine_id: UUID, kind: str, actor_id: UUID,
        reason: str | None = None, detail: Mapping[str, Any] | None = None,
    ) -> RoutineEvent: ...

    def get_routine(self, org_id: UUID, routine_id: UUID) -> Routine: ...

    def list_routines(self, org_id: UUID) -> list[Routine]: ...

    def list_events(
        self, org_id: UUID, *, routine_id: UUID | None = None, kinds: Iterable[str] | None = None,
        since: datetime | None = None, limit: int | None = None,
    ) -> list[RoutineEvent]: ...

    def list_runnable(self) -> list[Routine]:
        """Every routine (ALL orgs of this product) the dispatcher may schedule:
        ``ativo`` and not ``killed`` and its org's master switch on."""
        ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FakeRoutineStore:
    def __init__(self, *, now: Callable[[], datetime] = _now) -> None:
        self._now = now
        self._routines: dict[UUID, Routine] = {}
        self._events: list[RoutineEvent] = []
        self._master: dict[UUID, bool] = {}

    # -- internals -------------------------------------------------------
    def _get(self, org_id: UUID, routine_id: UUID) -> Routine:
        r = self._routines.get(routine_id)
        if r is None or r.org_id != org_id:
            raise RoutineNotFound(f"routine {routine_id} not found")
        return r

    def _append(self, org_id, routine_id, scope, kind, actor_id, reason, detail) -> RoutineEvent:
        e = RoutineEvent(
            len(self._events) + 1, org_id, routine_id, scope, kind, actor_id,
            (reason or "").strip() or None, copy.deepcopy(dict(detail or {})), self._now(),
        )
        self._events.append(e)
        return e

    def _out(self, r: Routine) -> Routine:
        return replace(r, config=copy.deepcopy(dict(r.config)))

    # -- writes ----------------------------------------------------------
    def create_routine(self, *, org_id, name, cron, mode, config, actor_id) -> Routine:
        name = (name or "").strip()
        if not name:
            raise RoutineInvalid("name is required")
        cron, mode = validate_cron(cron), validate_mode(mode)
        if any(r.org_id == org_id and r.name == name for r in self._routines.values()):
            raise RoutineConflict(f"routine {name!r} already exists for this org")
        now = self._now()
        r = Routine(uuid4(), org_id, name, cron, mode, False, False, copy.deepcopy(dict(config or {})), now, now)
        self._routines[r.id] = r
        self._append(org_id, r.id, SCOPE_ROUTINE, EventKind.CREATED.value, actor_id, None,
                     {"name": name, "cron": cron, "mode": mode})
        return self._out(r)

    def update_routine(self, *, org_id, routine_id, actor_id, name=None, cron=None, config=None,
                       mode=None, reason=None) -> Routine:
        r = self._get(org_id, routine_id)
        new_name = r.name if name is None else (name or "").strip()
        if not new_name:
            raise RoutineInvalid("name cannot be empty")
        new_cron = r.cron if cron is None else validate_cron(cron)
        new_mode = r.mode if mode is None else validate_mode(mode)
        new_config = r.config if config is None else copy.deepcopy(dict(config))
        if new_name != r.name and any(
            x.org_id == org_id and x.name == new_name for x in self._routines.values()
        ):
            raise RoutineConflict(f"routine {new_name!r} already exists for this org")
        changed = [f for f, a, b in (("name", r.name, new_name), ("cron", r.cron, new_cron),
                                      ("config", dict(r.config), dict(new_config))) if a != b]
        now = self._now()
        out = r
        if changed:
            out = replace(out, name=new_name, cron=new_cron, config=new_config, updated_at=now)
            self._append(org_id, r.id, SCOPE_ROUTINE, EventKind.EDITED.value, actor_id, reason,
                         {"changed": changed})
        if new_mode != r.mode:
            out = replace(out, mode=new_mode, updated_at=now)
            self._append(org_id, r.id, SCOPE_ROUTINE, EventKind.MODE_CHANGED.value, actor_id, reason,
                         {"from": r.mode, "to": new_mode})
        self._routines[r.id] = out
        return self._out(out)

    def set_enabled(self, *, org_id, routine_id, enabled, actor_id, reason) -> Routine:
        kind = EventKind.ENABLED.value if enabled else EventKind.DISABLED.value
        reason = need_reason(kind, reason)
        r = self._get(org_id, routine_id)
        if r.ativo == enabled and not (enabled and r.killed):
            return self._out(r)
        r = replace(r, ativo=enabled, killed=False if enabled else r.killed, updated_at=self._now())
        self._routines[r.id] = r
        self._append(org_id, r.id, SCOPE_ROUTINE, kind, actor_id, reason, {})
        return self._out(r)

    def kill(self, *, org_id, routine_id, actor_id, reason) -> Routine:
        reason = need_reason(EventKind.KILLED.value, reason)
        r = self._get(org_id, routine_id)
        if r.killed:
            return self._out(r)
        r = replace(r, ativo=False, killed=True, updated_at=self._now())
        self._routines[r.id] = r
        self._append(org_id, r.id, SCOPE_ROUTINE, EventKind.KILLED.value, actor_id, reason, {})
        return self._out(r)

    def set_master(self, *, org_id, enabled, actor_id, reason) -> bool:
        kind = EventKind.ENABLED.value if enabled else EventKind.DISABLED.value
        reason = need_reason(kind, reason)
        if self.master_enabled(org_id) == enabled and org_id in self._master:
            return enabled
        self._master[org_id] = enabled
        self._append(org_id, None, SCOPE_MASTER, kind, actor_id, reason, {})
        return enabled

    def record_event(self, *, org_id, routine_id, kind, actor_id, reason=None, detail=None) -> RoutineEvent:
        if kind not in RUN_EVENT_KINDS:
            raise RoutineInvalid(f"{kind!r} cannot be recorded directly; allowed: {sorted(RUN_EVENT_KINDS)}")
        reason = need_reason(kind, reason)
        self._get(org_id, routine_id)
        return self._append(org_id, routine_id, SCOPE_ROUTINE, kind, actor_id, reason, detail)

    # -- reads -----------------------------------------------------------
    def master_enabled(self, org_id) -> bool:
        return self._master.get(org_id, True)

    def get_routine(self, org_id, routine_id) -> Routine:
        return self._out(self._get(org_id, routine_id))

    def list_routines(self, org_id) -> list[Routine]:
        return [self._out(r) for r in sorted(self._routines.values(), key=lambda r: (r.created_at, r.name))
                if r.org_id == org_id]

    def list_events(self, org_id, *, routine_id=None, kinds=None, since=None, limit=None) -> list[RoutineEvent]:
        ks = None if kinds is None else set(kinds)
        out = [
            e for e in self._events
            if e.org_id == org_id and (routine_id is None or e.routine_id == routine_id)
            and (ks is None or e.kind in ks) and (since is None or e.created_at >= since)
        ]
        return out if limit is None else out[-limit:]

    def list_runnable(self) -> list[Routine]:
        return [self._out(r) for r in self._routines.values()
                if r.ativo and not r.killed and self.master_enabled(r.org_id)]


def make_routine_store(schema: str, *, use_fake: bool = False, client: Any | None = None) -> RoutineStore:
    """``use_fake=True`` -> ``FakeRoutineStore``. Otherwise a Supabase client scoped to
    ``schema`` is REQUIRED -- a missing client raises, it never degrades to the Fake."""
    if use_fake:
        return FakeRoutineStore()
    if client is None:
        raise RuntimeError("make_routine_store: client is required when use_fake=False")
    from noctusai_lib.domain.routines.store_supabase import SupabaseRoutineStore

    return SupabaseRoutineStore(client, schema=schema)


__all__ = ["FakeRoutineStore", "RoutineStore", "make_routine_store"]
