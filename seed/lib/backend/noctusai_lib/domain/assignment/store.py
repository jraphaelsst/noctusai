"""The assignment store: org-scoped row access (`OrgTableStore`) + the atomic `AssignmentLedger` (Protocol + Fake + Supabase).

Rows (teams, members, rules, settings, cursors, events reads) go through the shared `OrgTableStore` -- every call names the
org, so a foreign id is indistinguishable from a missing one. The two writes that must be atomic -- assign / release (capacity
check, assignment row, cursor, event, the card's owner column) -- are the `AssignmentLedger`: the Supabase one calls the
`asg_assign` / `asg_release` RPCs (one transaction, a per-member advisory lock); the Fake mirrors them over the Fake tables so
the same suite runs against both.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, Protocol, runtime_checkable

from noctusai_lib.domain._organ_common import OrgTableStore, TableSpec, UniqueKey, make_org_table_store

from .config import AssignmentConfig
from .errors import CapacityFull, SubjectNotFound
from .sql import ERR_CAPACITY_FULL, ERR_SUBJECT_NOT_FOUND
from .types import EVENT_ASSIGNED, EVENT_CLOSED, EVENT_REASSIGNED, EVENT_UNASSIGNED

T_SETTINGS, T_TEAMS, T_MEMBERS, T_RULES, T_CURSORS, T_ASSIGNMENTS, T_EVENTS = (
    "settings", "teams", "members", "rules", "cursors", "assignments", "events",
)

#: `(subject_id, user_id | None) -> None` -- the Fake's stand-in for the in-transaction card write (a host test asserts on it).
CardWriter = Callable[[str, Optional[str]], None]


def table_specs(cfg: AssignmentConfig) -> dict[str, TableSpec]:
    """The logical tables, with the UNIQUE guards the DDL carries (so the Fake refuses what the database refuses)."""
    p = cfg.table_prefix
    return {
        T_SETTINGS: TableSpec(cfg.table(T_SETTINGS), unique=(UniqueKey(f"uq_{p}settings_org", ("org_id",)),),
                              defaults={"strategy": "round_robin", "default_team_id": None, "keep_last": True}),
        T_TEAMS: TableSpec(cfg.table(T_TEAMS), unique=(UniqueKey(f"uq_{p}teams_name", ("org_id", "name")),),
                           defaults={"auto": True, "org_unit_id": None}),
        T_MEMBERS: TableSpec(cfg.table(T_MEMBERS), unique=(UniqueKey(f"uq_{p}members_team_user", ("team_id", "user_id")),),
                             defaults={"active": True, "position": 0, "capacity": None, "ooo_from": None, "ooo_until": None}),
        T_RULES: TableSpec(cfg.table(T_RULES), unique=(UniqueKey(f"uq_{p}rules_match", ("org_id", "kind", "match_value")),)),
        T_CURSORS: TableSpec(cfg.table(T_CURSORS), unique=(UniqueKey(f"uq_{p}cursors_team", ("team_id",)),),
                             defaults={"last_user_id": None}),
        T_ASSIGNMENTS: TableSpec(cfg.table(T_ASSIGNMENTS),
                                 unique=(UniqueKey(f"uq_{p}assignments_subject", ("org_id", "subject_kind", "subject_id")),),
                                 defaults={"team_id": None, "org_unit_id": None, "closed_at": None}),
        T_EVENTS: TableSpec(cfg.table(T_EVENTS), timestamps=("created_at",),
                            defaults={"from_user_id": None, "to_user_id": None, "team_id": None, "org_unit_id": None,
                                      "strategy": None, "criterion": None, "actor_id": None, "note": None}),
    }


@runtime_checkable
class AssignmentLedger(Protocol):
    """The two atomic writes. Both return `{"changed": bool, "event": str | None, ...}` (RPC shape)."""

    def commit(self, org_id: str, row: Mapping[str, Any]) -> dict: ...

    def release(self, org_id: str, row: Mapping[str, Any]) -> dict: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FakeAssignmentLedger:
    """In-memory ledger over the Fake tables: same refusals (capacity), same event rows, same idempotence as the RPCs."""

    def __init__(self, tables: OrgTableStore, cfg: AssignmentConfig, *, card_writer: Optional[CardWriter] = None) -> None:
        self._t, self._cfg, self._card_writer = tables, cfg, card_writer

    def _current(self, org_id: str, kind: str, subject: str) -> Optional[dict]:
        rows = self._t.select(T_ASSIGNMENTS, org_id, eq={"subject_kind": kind, "subject_id": subject})
        return rows[0] if rows else None

    def _event(self, org_id: str, row: Mapping[str, Any], event: str, **cols: Any) -> None:
        self._t.insert(T_EVENTS, org_id, [{
            "subject_kind": row["subject_kind"], "subject_id": row["subject_id"], "event": event,
            "actor_id": row.get("actor_id"), "note": row.get("note"), **cols,
        }])

    def commit(self, org_id: str, row: Mapping[str, Any]) -> dict:
        kind, subject, user = row["subject_kind"], str(row["subject_id"]), str(row["user_id"])
        team = row.get("team_id") or None
        prev = self._current(org_id, kind, subject)
        had = prev is not None and prev.get("closed_at") is None
        if had and str(prev["user_id"]) == user:
            return {"changed": False, "event": None, "assignment": prev}
        if row.get("enforce_capacity") and team:
            seat = next(iter(self._t.select(T_MEMBERS, org_id, eq={"team_id": team, "user_id": user})), None)
            capacity = (seat or {}).get("capacity")
            if capacity is not None:
                open_now = [a for a in self._t.select(T_ASSIGNMENTS, org_id, eq={"user_id": user}, is_null=["closed_at"])
                            if not (a["subject_kind"] == kind and str(a["subject_id"]) == subject)]
                if len(open_now) >= capacity:
                    raise CapacityFull(ERR_CAPACITY_FULL)
        body = {"user_id": user, "team_id": team, "org_unit_id": row.get("org_unit_id") or None, "strategy": row["strategy"],
                "criterion": row["criterion"], "assigned_at": _now(), "closed_at": None}
        if prev is not None:
            saved = self._t.update(T_ASSIGNMENTS, org_id, prev["id"], body)
        else:
            saved = self._t.insert(T_ASSIGNMENTS, org_id, [{"subject_kind": kind, "subject_id": subject, **body}])[0]
        if row.get("advance_cursor") and team:
            cursor = next(iter(self._t.select(T_CURSORS, org_id, eq={"team_id": team})), None)
            if cursor:
                self._t.update(T_CURSORS, org_id, cursor["id"], {"last_user_id": user, "moved_at": _now()})
            else:
                self._t.insert(T_CURSORS, org_id, [{"team_id": team, "last_user_id": user, "moved_at": _now()}])
        event = EVENT_REASSIGNED if had else EVENT_ASSIGNED
        self._event(org_id, row, event, from_user_id=prev["user_id"] if had else None, to_user_id=user, team_id=team,
                    org_unit_id=row.get("org_unit_id") or None, strategy=row["strategy"], criterion=row["criterion"])
        if self._card_writer and self._cfg.card_table and kind == self._cfg.subject_kind:
            self._card_writer(subject, user)
        return {"changed": True, "event": event, "assignment": saved}

    def release(self, org_id: str, row: Mapping[str, Any]) -> dict:
        kind, subject, event = row["subject_kind"], str(row["subject_id"]), row["event"]
        if event not in (EVENT_UNASSIGNED, EVENT_CLOSED):
            raise ValueError("release event must be unassigned or closed")
        prev = self._current(org_id, kind, subject)
        if prev is None or prev.get("closed_at") is not None:
            return {"changed": False, "event": None}
        if event == EVENT_CLOSED:
            self._t.update(T_ASSIGNMENTS, org_id, prev["id"], {"closed_at": _now()})
        else:
            self._t.delete(T_ASSIGNMENTS, org_id, prev["id"])
        self._event(org_id, row, event, from_user_id=prev["user_id"], to_user_id=None, team_id=prev.get("team_id"),
                    org_unit_id=prev.get("org_unit_id"), strategy=prev.get("strategy"), criterion=prev.get("criterion"))
        if event == EVENT_UNASSIGNED and self._card_writer and self._cfg.card_table and kind == self._cfg.subject_kind:
            self._card_writer(subject, None)
        return {"changed": True, "event": event}


class SupabaseAssignmentLedger:
    """The Real ledger: `asg_assign` / `asg_release` RPCs over a SERVICE-ROLE client (schema-pinned, like the other organs)."""

    def __init__(self, client: Any, cfg: AssignmentConfig) -> None:
        self._client, self._cfg = client, cfg

    def _call(self, name: str, org_id: str, row: Mapping[str, Any]) -> dict:
        try:
            data = self._client.rpc(self._cfg.table(name), {"p_org": str(org_id), "p_row": dict(row)}).execute().data
        except Exception as exc:  # noqa: BLE001 - narrowed below: only the RPCs' own refusals are translated, the rest re-raises
            text = str(exc)
            if ERR_CAPACITY_FULL in text:
                raise CapacityFull(ERR_CAPACITY_FULL) from exc
            if ERR_SUBJECT_NOT_FOUND in text:
                raise SubjectNotFound(ERR_SUBJECT_NOT_FOUND) from exc
            raise
        if isinstance(data, list):
            data = data[0] if data else {}
        return dict(data or {})

    def commit(self, org_id: str, row: Mapping[str, Any]) -> dict:
        return self._call("assign", org_id, row)

    def release(self, org_id: str, row: Mapping[str, Any]) -> dict:
        return self._call("release", org_id, row)


@dataclass(frozen=True)
class AssignmentStore:
    tables: OrgTableStore
    ledger: AssignmentLedger


def build_assignment_store(
    cfg: AssignmentConfig, *, use_fake: bool = False, supabase_client: Any = None, card_writer: Optional[CardWriter] = None
) -> AssignmentStore:
    """The Fake store (`use_fake=True`) or the Supabase one. A missing client is a loud error, never a silent Fake."""
    specs = table_specs(cfg)
    tables = make_org_table_store(specs, use_fake=use_fake, supabase_client=supabase_client)
    if use_fake:
        return AssignmentStore(tables, FakeAssignmentLedger(tables, cfg, card_writer=card_writer))
    return AssignmentStore(tables, SupabaseAssignmentLedger(supabase_client, cfg))


__all__ = [
    "AssignmentLedger", "AssignmentStore", "CardWriter", "FakeAssignmentLedger", "SupabaseAssignmentLedger", "T_ASSIGNMENTS",
    "T_CURSORS", "T_EVENTS", "T_MEMBERS", "T_RULES", "T_SETTINGS", "T_TEAMS", "build_assignment_store", "table_specs",
]
