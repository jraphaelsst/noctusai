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

S4b (owner decisions 2026-10-14, core ``member_access_rules``): the writes carry the ACTOR (D2:
only the NoctusAI owner may override the last-owner rule -- decided in SQL from the actor, never
from a caller-supplied flag); removing a sole-org member keeps the profile in a personal org (D4,
:func:`remove_member_keeping_profile`); moving a user between orgs (D3, :func:`move_member`); and
per-member product blocks (D5, :func:`set_product_access` / :func:`member_product_access`).

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
    "invalid_mode": (400, "Modo inválido: use 'transfer' ou 'add'"),
    "invalid_request": (400, "Requisição inválida"),
    "same_org": (400, "Origem e destino precisam ser organizações diferentes"),
    "org_not_found": (404, "Organização não encontrada"),
    "forbidden": (403, "Você não tem permissão para gerenciar esta organização"),
    "role_above_actor": (403, "Não é possível conceder um papel acima do seu nesta organização"),
    "personal_org_required": (409, "A situação do membro mudou durante a remoção; tente novamente"),
    "personal_org_invalid": (409, "A organização pessoal do membro não pôde ser usada; tente novamente"),
    "product_not_found": (404, "Produto não encontrado"),
    "not_licensed": (409, "A organização não tem licença ativa deste produto"),
    # Raised only by core 082's (superseded) remove; kept so a deploy whose DB still runs 082 maps it.
    "profile_in_use": (409, "Este usuário possui registros vinculados e não pôde ser removido; tente novamente"),
}

#: Org roles that manage an org (team, moves, product blocks) -- D3/D5. Mirror of the SQL
#: ``public.org_manager_role``.
MANAGER_ORG_ROLES = ("owner", "admin")


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


def remove_member(
    db, org_id: str, user_id: str, *, actor_id: str, personal_org_id: Optional[str] = None,
) -> dict[str, Any]:
    """End the membership; move the profile in the SAME transaction (to the most recent other
    ACTIVE membership, else to ``personal_org_id``). Returns ``{profile_moved_to,
    personal_org_id, selections_ended, ...}``. Prefer :func:`remove_member_keeping_profile`."""
    return _call(db, "team_member_remove", {
        "p_org_id": org_id, "p_user_id": user_id, "p_actor_id": actor_id,
        "p_personal_org_id": personal_org_id,
    })


def remove_member_keeping_profile(db, org_id: str, user_id: str, *, actor_id: str) -> dict[str, Any]:
    """D4: remove ``user_id`` from ``org_id`` without ever deleting their profile.

    When ``org_id`` is their ONLY active membership a personal org is created first through the
    signup org path (``org_provisioning``) and handed to the transactional RPC, which validates it
    and moves the profile there. If the RPC fails -- or another membership took the profile after
    all (a concurrent invite) -- the unused org is discarded, never left behind silently."""
    from app.services import org_provisioning

    personal_org_id: Optional[str] = None
    active = list_user_active_memberships(db, user_id)
    if [str(m.get("org_id")) for m in active] == [str(org_id)]:
        profile = profiles_by_id(db, [user_id], "id, nome, email").get(str(user_id)) or {}
        nome = (profile.get("nome") or (profile.get("email") or "").split("@", 1)[0] or "Pessoal").strip()
        personal_org_id = str(org_provisioning.create_personal_org(db, owner_id=user_id, nome=nome)["id"])
    try:
        outcome = remove_member(db, org_id, user_id, actor_id=actor_id, personal_org_id=personal_org_id)
    except Exception:
        if personal_org_id:
            org_provisioning.discard_unused_org(db, personal_org_id)
        raise
    if personal_org_id and str(outcome.get("personal_org_id") or "") != personal_org_id:
        org_provisioning.discard_unused_org(db, personal_org_id)
    return outcome


def set_member_role(db, org_id: str, user_id: str, role: str, *, actor_id: str) -> dict[str, Any]:
    return _call(db, "team_member_set_role", {
        "p_org_id": org_id, "p_user_id": user_id, "p_role": role, "p_actor_id": actor_id,
    })


def move_member(
    db, *, actor_id: str, user_id: str, source_org_id: str, target_org_id: str, role: str, mode: str,
) -> dict[str, Any]:
    """D3: move ``user_id`` from ``source_org_id`` to ``target_org_id`` (``mode`` transfer = end the
    source membership, add = keep it). Authority, role cap and last-owner rule live in SQL."""
    return _call(db, "team_member_move", {
        "p_actor_id": actor_id, "p_user_id": user_id, "p_source_org_id": source_org_id,
        "p_target_org_id": target_org_id, "p_role": role, "p_mode": mode,
    })


def accept_invitation(db, invitation_id: str, user_id: str, nome: Optional[str]) -> dict[str, Any]:
    """Accept an invitation in ONE transaction: an EXISTING user joins the inviting org (profile
    untouched); a FIRST-TIME invitee gets their profile there. Either way the membership carries
    ``invited_by``/``invitation_id`` (D4) and the invitation is marked accepted."""
    return _call(db, "team_invitation_accept", {
        "p_invitation_id": invitation_id, "p_user_id": user_id, "p_nome": nome,
    })


# ---------------------------------------------------------------------------
# D2/D3/D5 -- who manages an org; per-member product blocks
# ---------------------------------------------------------------------------

def manager_role(db, actor_id: str, org_id: str) -> Optional[str]:
    """The role ``actor_id`` manages ``org_id`` with: ``owner`` for platform staff (any org, D2),
    else their ACTIVE owner/admin membership role there, else ``None``. Mirror of SQL
    ``public.org_manager_role`` (the RPCs re-decide; this only lets reads answer 403 early)."""
    from noctusai_lib.api.auth.effective_org import platform_staff_role

    if platform_staff_role(db, actor_id) is not None:
        return "owner"
    m = get_membership(db, org_id, actor_id)
    if m and m.get("status") == "active" and m.get("org_role") in MANAGER_ORG_ROLES:
        return m.get("org_role")
    return None


def set_product_access(
    db, *, actor_id: str, org_id: str, user_id: str, product_slug: str, blocked: bool,
) -> dict[str, Any]:
    """D5: block (``blocked=True``) or unblock a member's access to a product inside an org."""
    return _call(db, "org_member_product_access_set", {
        "p_actor_id": actor_id, "p_org_id": org_id, "p_user_id": user_id,
        "p_product_slug": product_slug, "p_blocked": blocked,
    })


def blocked_org_ids(db, user_id: str, product_id: str) -> set[str]:
    """Orgs where ``user_id`` is BLOCKED from ``product_id`` (live D5 rows)."""
    rows = list(iter_paged_rows(
        lambda start, end: (
            db.table("org_member_product_access")
            .select("id, org_id")
            .eq("user_id", user_id)
            .eq("product_id", product_id)
            .is_("unblocked_at", "null")
            .order("id")
            .range(start, end)
            .execute()
            .data
        ),
        label=f"product blocks of user {user_id}",
    ))
    return {str(r["org_id"]) for r in rows}


def blocked_product_ids(db, user_id: str, org_id: str) -> set[str]:
    """Products ``user_id`` is BLOCKED from inside ``org_id`` (live D5 rows)."""
    rows = list(iter_paged_rows(
        lambda start, end: (
            db.table("org_member_product_access")
            .select("id, product_id")
            .eq("user_id", user_id)
            .eq("org_id", org_id)
            .is_("unblocked_at", "null")
            .order("id")
            .range(start, end)
            .execute()
            .data
        ),
        label=f"product blocks of user {user_id} in org {org_id}",
    ))
    return {str(r["product_id"]) for r in rows}


def member_product_access(db, org_id: str, user_id: str) -> list[dict]:
    """The member's access to every product the org is licensed for:
    ``[{product_id, slug, nome, blocked, blocked_at, blocked_by}]`` by name."""
    from app.dependencies import get_licensed_product_ids

    licensed = sorted(str(p) for p in get_licensed_product_ids(db, org_id))
    blocks: dict[str, dict] = {}
    for r in iter_paged_rows(
        lambda start, end: (
            db.table("org_member_product_access")
            .select("id, product_id, blocked_at, blocked_by")
            .eq("user_id", user_id)
            .eq("org_id", org_id)
            .is_("unblocked_at", "null")
            .order("id")
            .range(start, end)
            .execute()
            .data
        ),
        label=f"product blocks of user {user_id} in org {org_id}",
    ):
        blocks[str(r["product_id"])] = r
    products: dict[str, dict] = {}
    for chunk in _batched(licensed):
        for p in db.table("products").select("id, slug, nome").in_("id", chunk).execute().data or []:
            products[str(p["id"])] = p
    out = []
    for pid in licensed:
        p = products.get(pid)
        if p is None:
            continue
        b = blocks.get(pid)
        out.append({
            "product_id": pid, "slug": p.get("slug"), "nome": p.get("nome"),
            "blocked": b is not None,
            "blocked_at": b.get("blocked_at") if b else None,
            "blocked_by": b.get("blocked_by") if b else None,
        })
    out.sort(key=lambda r: (r.get("nome") or r.get("slug") or "").lower())
    return out
