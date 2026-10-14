"""Core team = ``public.org_memberships`` (multi-org S4).

"Who belongs to org X" is the ACTIVE ``org_memberships`` rows of X -- never
``noctus_users.org_id``, which is only the LAST-ACTIVE org of each user (it follows the org
picker, core 081). Reading the profile column would make a member whose last-active org is
elsewhere vanish from the team page, from the seat count and from the notification fan-out.

The three write operations (remove / change role / accept an invitation as an existing user)
are several writes each, and the deferred constraint trigger ``org_memberships_profile_org_active``
refuses a transaction that ends the membership a profile still points at -- so each one is a
single SECURITY DEFINER function (core ``team_membership_ops``) called over RPC, never a
PostgREST call sequence. Refusals arrive as ``team_membership:<code>`` and are mapped here to
strict HTTP statuses.

KB § PATTERNS/backend/tenancy-license-gate.md § Members
"""
from __future__ import annotations

import logging
from typing import Any, Iterator, Optional

from fastapi import HTTPException
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

logger = logging.getLogger(__name__)

#: ``.in_()`` values ride in the URL query string: batch them.
_IN_BATCH = 150

_RPC_PREFIX = "team_membership:"

#: refusal code -> (HTTP status, pt-BR detail)
ERROR_MAP: dict[str, tuple[int, str]] = {
    "not_a_member": (404, "Membro não encontrado"),
    "last_owner": (409, "A organização precisa manter ao menos um proprietário"),
    "invalid_role": (400, "Papel inválido"),
    "invitation_not_found": (404, "Convite não encontrado"),
    "invitation_not_pending": (400, "Este convite não está mais pendente"),
    "invitation_expired": (400, "Este convite expirou"),
    "email_mismatch": (403, "Este convite foi enviado para outro email"),
    "already_member": (409, "Você já pertence a esta organização"),
    "membership_suspended": (403, "Sua participação nesta organização está suspensa"),
    "profile_in_use": (409, "Este usuário possui registros vinculados (convites, chaves, auditoria) e não pode ser removido por completo; transfira ou remova esses vínculos antes"),
}


def _batched(values: list, size: int = _IN_BATCH) -> Iterator[list]:
    for i in range(0, len(values), size):
        yield values[i : i + size]


# ---------------------------------------------------------------------------
# Reads -- members OF an org
# ---------------------------------------------------------------------------

def get_membership(db, org_id: str, user_id: str) -> Optional[dict]:
    """The (user, org) membership row, any status, or ``None``."""
    resp = (
        db.table("org_memberships")
        .select("user_id, org_id, org_role, status")
        .eq("org_id", org_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    return resp.data if resp is not None else None


def list_active_memberships(db, org_id: str) -> list[dict]:
    """Every ACTIVE membership of ``org_id`` (paged -- never the silent 1 000-row cap)."""
    return list(iter_paged_rows(
        lambda start, end: (
            db.table("org_memberships")
            .select("user_id, org_role, created_at")
            .eq("org_id", org_id)
            .eq("status", "active")
            .order("user_id")
            .range(start, end)
            .execute()
            .data
        ),
        id_key="user_id",
        label=f"active memberships of org {org_id}",
    ))


def list_user_active_memberships(db, user_id: str) -> list[dict]:
    """Every ACTIVE membership OF a user, most recently updated first (an ordinary user belongs
    to a handful of orgs; paged anyway so the cap can never hide one)."""
    rows = list(iter_paged_rows(
        lambda start, end: (
            db.table("org_memberships")
            .select("org_id, org_role, updated_at")
            .eq("user_id", user_id)
            .eq("status", "active")
            .order("org_id")
            .range(start, end)
            .execute()
            .data
        ),
        id_key="org_id",
        label=f"active memberships of user {user_id}",
    ))
    rows.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
    return rows


def active_member_user_ids(db, org_id: str) -> list[str]:
    return [str(r["user_id"]) for r in list_active_memberships(db, org_id)]


def count_active_members(db, org_id: str) -> int:
    """Seats in use: ACTIVE memberships (``invited`` is not a seat until accepted)."""
    resp = (
        db.table("org_memberships")
        .select("user_id", count="exact")
        .eq("org_id", org_id)
        .eq("status", "active")
        .execute()
    )
    return resp.count if resp.count is not None else len(resp.data or [])


def profiles_by_id(db, user_ids: list[str], columns: str) -> dict[str, dict]:
    """``noctus_users`` rows for ``user_ids`` keyed by id (``columns`` must include ``id``)."""
    out: dict[str, dict] = {}
    for chunk in _batched(list(user_ids)):
        rows = db.table("noctus_users").select(columns).in_("id", chunk).execute().data or []
        for row in rows:
            out[str(row["id"])] = row
    return out


def list_team(db, org_id: str) -> list[dict]:
    """The team page rows: profile identity + the role IN THIS ORG (the membership role, not the
    profile's last-active-org role)."""
    memberships = list_active_memberships(db, org_id)
    profiles = profiles_by_id(db, [str(m["user_id"]) for m in memberships], "id, nome, email, created_at")
    rows = []
    for m in memberships:
        p = profiles.get(str(m["user_id"]))
        if p is None:
            # An active membership without a profile cannot be named or acted on; say so.
            logger.error("team: active membership without a noctus_users profile org=%s user=%s",
                         org_id, m["user_id"])
            continue
        rows.append({
            "id": p["id"], "nome": p.get("nome"), "email": p.get("email"),
            "org_role": m.get("org_role"), "created_at": p.get("created_at") or m.get("created_at"),
        })
    rows.sort(key=lambda r: str(r.get("created_at") or ""))
    return rows


# ---------------------------------------------------------------------------
# Writes -- one RPC each (atomic)
# ---------------------------------------------------------------------------

def _code_from(exc: Exception) -> Optional[str]:
    text = str(exc)
    if _RPC_PREFIX not in text:
        return None
    tail = text.split(_RPC_PREFIX, 1)[1]
    for code in ERROR_MAP:
        if tail.startswith(code):
            return code
    return None


def _call(db, fn: str, params: dict) -> dict:
    try:
        data = db.rpc(fn, params).execute().data
    except Exception as exc:
        code = _code_from(exc)
        if code is None:
            raise
        status, detail = ERROR_MAP[code]
        raise HTTPException(status_code=status, detail=detail) from exc
    if isinstance(data, list):
        data = data[0] if data else {}
    return data if isinstance(data, dict) else {}


def remove_member(db, org_id: str, user_id: str) -> dict[str, Any]:
    """End the membership; move or delete the profile in the SAME transaction.
    Returns ``{profile_moved_to, profile_deleted, selections_ended, ...}``."""
    return _call(db, "team_member_remove", {"p_org_id": org_id, "p_user_id": user_id})


def set_member_role(db, org_id: str, user_id: str, role: str) -> dict[str, Any]:
    return _call(db, "team_member_set_role", {"p_org_id": org_id, "p_user_id": user_id, "p_role": role})


def accept_invitation_as_member(db, invitation_id: str, user_id: str) -> dict[str, Any]:
    """An EXISTING user joins the inviting org (profile untouched); marks the invitation accepted."""
    return _call(db, "team_invitation_accept", {"p_invitation_id": invitation_id, "p_user_id": user_id})
