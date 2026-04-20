"""
Equipes Service — business logic for team + membership management.

Teams (DRAGÃO, LEÃO, ÁGUIA + future) are created and managed by the org
owner (admin role). Leaders are agents with papel='lider' inside a team.
Membership is history-enabled: removing a member sets left_at rather than
deleting the row, so historical events stay correctly attributed.

See products/erp-imobiliario/METAS-PLAN.md §5 for design context.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ── Teams ────────────────────────────────────────────────────────────

def listar_equipes(db, *, ativas_apenas: bool = True) -> list[dict]:
    """Return all teams for the current org (RLS scopes to the caller)."""
    query = db.table("equipes").select("*")
    if ativas_apenas:
        query = query.eq("ativo", True)
    result = query.order("nome").execute()
    return result.data or []


def obter_equipe(db, equipe_id: str) -> dict | None:
    result = db.table("equipes").select("*").eq("id", equipe_id).limit(1).execute()
    return (result.data or [None])[0]


def criar_equipe(db, *, org_id: str, nome: str, cor: str | None = None,
                 icone: str | None = None, lider_id: str | None = None) -> dict:
    """Create a team. Uniqueness on (org_id, nome) is enforced by the schema."""
    payload = {
        "org_id": org_id,
        "nome": nome.strip(),
        "cor": cor,
        "icone": icone,
        "lider_id": lider_id,
        "ativo": True,
    }
    payload = {k: v for k, v in payload.items() if v is not None or k in {"cor", "icone", "lider_id"}}
    result = db.table("equipes").insert(payload).execute()
    if not result.data:
        raise RuntimeError("Falha ao criar equipe")
    equipe = result.data[0]
    # If a leader was assigned, create the membership row too
    if lider_id:
        try:
            adicionar_membro(db, equipe_id=equipe["id"], user_id=lider_id, papel="lider")
        except Exception:
            logger.exception("Falha ao inserir lider_id=%s como membro da equipe %s", lider_id, equipe["id"])
    return equipe


def atualizar_equipe(db, equipe_id: str, patch: dict) -> dict:
    """Update mutable team fields. Ignores None values."""
    clean = {k: v for k, v in patch.items() if v is not None}
    if not clean:
        current = obter_equipe(db, equipe_id)
        if current is None:
            raise LookupError("Equipe não encontrada")
        return current
    old_leader = None
    if "lider_id" in clean:
        current = obter_equipe(db, equipe_id)
        old_leader = (current or {}).get("lider_id")
    result = db.table("equipes").update(clean).eq("id", equipe_id).execute()
    if not result.data:
        raise LookupError("Equipe não encontrada")
    equipe = result.data[0]

    # Reconcile leader membership: if leader changed, demote old + add new
    new_leader = equipe.get("lider_id")
    if "lider_id" in clean and old_leader != new_leader:
        if old_leader:
            try:
                _desativar_papel_lider(db, equipe_id=equipe_id, user_id=old_leader)
            except Exception:
                logger.exception("Falha ao remover papel 'lider' anterior (user_id=%s)", old_leader)
        if new_leader:
            try:
                adicionar_membro(db, equipe_id=equipe_id, user_id=new_leader, papel="lider")
            except Exception:
                logger.exception("Falha ao promover novo líder (user_id=%s)", new_leader)
    return equipe


def disband_equipe(db, equipe_id: str) -> dict:
    """Soft-disband: mark inactive + timestamp; set left_at on all active memberships."""
    now_iso = datetime.now(timezone.utc).isoformat()
    result = db.table("equipes").update({
        "ativo": False,
        "disbanded_at": now_iso,
    }).eq("id", equipe_id).execute()
    if not result.data:
        raise LookupError("Equipe não encontrada")
    # Close all active memberships
    db.table("equipe_membros").update({"left_at": now_iso}) \
        .eq("equipe_id", equipe_id).is_("left_at", "null").execute()
    return result.data[0]


# ── Membership ───────────────────────────────────────────────────────

def listar_membros(db, equipe_id: str, *, incluir_historico: bool = False) -> list[dict]:
    query = db.table("equipe_membros").select("*").eq("equipe_id", equipe_id)
    if not incluir_historico:
        query = query.is_("left_at", "null")
    result = query.order("joined_at").execute()
    return result.data or []


def adicionar_membro(db, *, equipe_id: str, user_id: str, papel: str = "corretor") -> dict:
    """Add a user to a team. Re-activates a previously-left membership if present."""
    if papel not in {"lider", "corretor"}:
        raise ValueError(f"papel inválido: {papel}")

    # Is there an active membership? Unique partial index prevents duplicates anyway.
    existing = db.table("equipe_membros").select("*") \
        .eq("equipe_id", equipe_id).eq("user_id", user_id).is_("left_at", "null") \
        .limit(1).execute().data

    if existing:
        # Already a member — update papel if it differs, else no-op
        current = existing[0]
        if current.get("papel") != papel:
            result = db.table("equipe_membros").update({"papel": papel}) \
                .eq("id", current["id"]).execute()
            return (result.data or [current])[0]
        return current

    payload = {"equipe_id": equipe_id, "user_id": user_id, "papel": papel}
    result = db.table("equipe_membros").insert(payload).execute()
    if not result.data:
        raise RuntimeError("Falha ao adicionar membro")
    return result.data[0]


def atualizar_papel_membro(db, *, membro_id: str, papel: str) -> dict:
    if papel not in {"lider", "corretor"}:
        raise ValueError(f"papel inválido: {papel}")
    result = db.table("equipe_membros").update({"papel": papel}).eq("id", membro_id).execute()
    if not result.data:
        raise LookupError("Membro não encontrado")
    return result.data[0]


def remover_membro(db, membro_id: str) -> dict:
    """Soft-remove: set left_at. Preserves history for past events."""
    now_iso = datetime.now(timezone.utc).isoformat()
    result = db.table("equipe_membros").update({"left_at": now_iso}).eq("id", membro_id).execute()
    if not result.data:
        raise LookupError("Membro não encontrado")
    return result.data[0]


def _desativar_papel_lider(db, *, equipe_id: str, user_id: str) -> None:
    """Internal: demote a previous leader's membership to 'corretor' (without removing)."""
    db.table("equipe_membros").update({"papel": "corretor"}) \
        .eq("equipe_id", equipe_id).eq("user_id", user_id).is_("left_at", "null").execute()
