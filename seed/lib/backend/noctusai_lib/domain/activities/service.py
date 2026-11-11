"""Activities service: org-scoped reads + thin callers of the row-locked, event-writing RPCs.

The RPCs are the authority (state change + immutable event in ONE transaction). Python validates shape, resolves ids to
this org (a foreign-org id is a 404) and checks what Postgres cannot see: the assignee is an ACTIVE member of the org
(`ActivitiesContext.is_member`, wired by the host over `domain.org_memberships`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, ClassVar, Mapping, Optional

from noctusai_lib.domain._organ_common import OrganScope, first, now_iso
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from .config import ActivitiesConfig
from .errors import FILTRO_INVALIDO, RESPONSAVEL_INVALIDO, TIPO_DUPLICADO, conflict, from_refusal, invalid, not_found
from .types import (
    ACTIVITY_KINDS,
    INTENT_CANCEL,
    INTENT_COMPLETE,
    INTENT_EDIT,
    INTENT_REASSIGN,
    INTENT_REOPEN,
    INTENT_RESCHEDULE,
)

STATUSES = ("open", "done", "cancelled", "all")


@dataclass(frozen=True)
class Scope(OrganScope):
    """`(db, cfg, org_id)`; stable newest-first order by default."""

    cfg: ActivitiesConfig
    default_order: ClassVar[tuple[tuple[str, bool], ...]] = (("created_at", True), ("id", False))

    def _invalid(self, field: str, message: str, code: str) -> Exception:
        return invalid(field, message, code=code)


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


def present(row: Mapping[str, Any], *, now: Optional[datetime] = None) -> dict:
    """The wire shape: the row + the DERIVED `overdue` (never stored: it would be stale the moment it is written)."""
    out = dict(row)
    due = out.get("due_at")
    overdue = False
    if due and not out.get("done_at") and not out.get("cancelled_at"):
        parsed = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        overdue = parsed < (now or datetime.now(timezone.utc))
    out["overdue"] = overdue
    return out


# ── RPC ────────────────────────────────────────────────────────────────────────────────────────────────────────────


def _rpc(s: Scope, name: str, params: dict) -> dict:
    resp = s.db.rpc(s.cfg.rpc(name), params).execute()
    payload = getattr(resp, "data", None)
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    if not isinstance(payload, dict) or "status" not in payload:
        raise RuntimeError(f"activities RPC {name} answered an unexpected payload: {payload!r}")
    if payload["status"] == "refused":
        raise from_refusal(payload)
    return payload


def _apply(s: Scope, activity_id: Any, intent: str, actor: Optional[str], args: Optional[dict] = None) -> dict:
    payload = _rpc(
        s, "apply", {"p_org": s.org_id, "p_id": str(activity_id), "p_actor": actor, "p_intent": intent, "p_args": args or {}}
    )
    return present(payload["activity"])


# ── types ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def ensure_types(s: Scope) -> None:
    """Lazily seed the org's market types the first time it has none (the org edits them afterwards, so a type it
    deactivated is never resurrected: the seed only runs on an EMPTY table)."""
    head = s.tbl("types").select("slug", count="exact").eq("org_id", s.org_id).limit(1).execute()
    if getattr(head, "count", None) or (head.data or []):
        return
    rows = [{"slug": t.slug, "label": t.label, "kind": t.kind, "position": i} for i, t in enumerate(s.cfg.default_types)]
    _rpc(s, "seed_types", {"p_org": s.org_id, "p_rows": rows})


def list_types(s: Scope, *, active: Optional[bool] = None) -> list[dict]:
    ensure_types(s)
    rows = s.rows("types", eq={"active": active} if active is not None else None, order_col="slug")
    return sorted(rows, key=lambda r: (r.get("position") or 0, r["slug"]))


def create_type(s: Scope, data: Mapping[str, Any]) -> dict:
    ensure_types(s)
    row = {**dict(data), "org_id": s.org_id, "active": True, "created_at": now_iso(), "updated_at": now_iso()}
    try:
        saved = first(s.tbl("types").insert(row).execute())
    except Exception as exc:  # noqa: BLE001 - narrowed below
        if is_unique_violation(exc):
            raise conflict(TIPO_DUPLICADO, "Já existe um tipo de atividade com este código.") from exc
        raise
    return saved or row


def update_type(s: Scope, slug: str, patch: Mapping[str, Any]) -> dict:
    ensure_types(s)
    current = s.find("types", slug, col="slug")
    if current is None:
        raise not_found("Tipo de atividade")
    changes = {k: v for k, v in patch.items() if v is not None}
    if not changes:
        return current
    changes["updated_at"] = now_iso()
    s.tbl("types").update(changes).eq("org_id", s.org_id).eq("slug", slug).execute()
    return {**current, **changes}


# ── activities ─────────────────────────────────────────────────────────────────────────────────────────────────────


def _check_assignee(ctx_is_member: Optional[Callable[[str], bool]], assignee_id: Optional[Any]) -> Optional[str]:
    """`None` (unassigned) is always fine; a user id must be an ACTIVE member of the org (422 otherwise)."""
    if assignee_id is None:
        return None
    assignee = str(assignee_id)
    if ctx_is_member is None or not ctx_is_member(assignee):
        raise invalid("assignee_id", "O responsável precisa ser um membro ativo da organização.", code=RESPONSAVEL_INVALIDO)
    return assignee


def create_activity(
    s: Scope, data: Mapping[str, Any], *, user_id: Optional[str], is_member: Optional[Callable[[str], bool]]
) -> dict:
    ensure_types(s)
    row = {k: v for k, v in dict(data).items() if v is not None}
    for key in ("entity_id", "assignee_id", "org_unit_id"):
        if key in row:
            row[key] = str(row[key])
    if "due_at" in row:
        row["due_at"] = _iso(row["due_at"])
    _check_assignee(is_member, row.get("assignee_id"))
    if user_id:
        row["created_by"] = str(user_id)
    return present(_rpc(s, "create", {"p_org": s.org_id, "p_row": row})["activity"])


def get_activity(s: Scope, activity_id: Any) -> dict:
    return present(s.get("activities", activity_id, what="Atividade"))


def list_events(s: Scope, activity_id: Any) -> list[dict]:
    get_activity(s, activity_id)  # 404 for a foreign / missing id before reading its history
    return s.rows("events", eq={"activity_id": str(activity_id)}, order_col="seq")


def list_activities(
    s: Scope,
    *,
    entity_kind: Optional[str] = None,
    entity_id: Optional[Any] = None,
    assignee_id: Optional[Any] = None,
    status: str = "open",
    type_slug: Optional[str] = None,
    kind: Optional[str] = None,
    overdue: Optional[bool] = None,
    due_from: Optional[datetime] = None,
    due_to: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int, int, int]:
    if status not in STATUSES:
        raise invalid("status", "Situação inválida.", code=FILTRO_INVALIDO)
    if kind is not None and kind not in ACTIVITY_KINDS:
        raise invalid("kind", "Tipo de comportamento inválido.", code=FILTRO_INVALIDO)
    if due_from and due_to and due_from >= due_to:
        raise invalid("due_from", "A data inicial vem depois da final.", code=FILTRO_INVALIDO)
    now = datetime.now(timezone.utc)

    def refine(q: Any) -> Any:
        if entity_kind:
            q = q.eq("entity_kind", entity_kind)
        if entity_id:
            q = q.eq("entity_id", str(entity_id))
        if assignee_id:
            q = q.eq("assignee_id", str(assignee_id))
        if type_slug:
            q = q.eq("type_slug", type_slug)
        if kind:
            q = q.eq("kind", kind)
        if status == "open":
            q = q.is_("done_at", "null").is_("cancelled_at", "null")
        elif status == "done":
            q = q.not_.is_("done_at", "null")
        elif status == "cancelled":
            q = q.not_.is_("cancelled_at", "null")
        if overdue:
            q = q.is_("done_at", "null").is_("cancelled_at", "null").lt("due_at", now.isoformat())
        if due_from:
            q = q.gte("due_at", due_from.isoformat())
        if due_to:
            q = q.lt("due_at", due_to.isoformat())
        return q

    order = (("due_at", False), ("created_at", True), ("id", False)) if status == "open" else None
    rows, total, page, page_size = s.page("activities", page=page, page_size=page_size, refine=refine, order=order)
    return [present(r, now=now) for r in rows], total, page, page_size


def complete(s: Scope, activity_id: Any, outcome: str, *, user_id: Optional[str]) -> dict:
    return _apply(s, activity_id, INTENT_COMPLETE, user_id, {"outcome": outcome})


def reopen(s: Scope, activity_id: Any, *, user_id: Optional[str]) -> dict:
    return _apply(s, activity_id, INTENT_REOPEN, user_id)


def reassign(
    s: Scope, activity_id: Any, assignee_id: Optional[Any], *, user_id: Optional[str], is_member: Optional[Callable[[str], bool]]
) -> dict:
    return _apply(s, activity_id, INTENT_REASSIGN, user_id, {"assignee_id": _check_assignee(is_member, assignee_id)})


def reschedule(s: Scope, activity_id: Any, due_at: Optional[datetime], *, user_id: Optional[str]) -> dict:
    return _apply(s, activity_id, INTENT_RESCHEDULE, user_id, {"due_at": _iso(due_at)})


def edit(s: Scope, activity_id: Any, patch: Mapping[str, Any], *, user_id: Optional[str]) -> dict:
    return _apply(s, activity_id, INTENT_EDIT, user_id, {k: v for k, v in patch.items() if k in ("title", "notes")})


def cancel(s: Scope, activity_id: Any, *, user_id: Optional[str]) -> dict:
    return _apply(s, activity_id, INTENT_CANCEL, user_id)


__all__ = [
    "STATUSES",
    "Scope",
    "cancel",
    "complete",
    "create_activity",
    "create_type",
    "edit",
    "ensure_types",
    "get_activity",
    "list_activities",
    "list_events",
    "list_types",
    "present",
    "reassign",
    "reopen",
    "reschedule",
    "update_type",
]
