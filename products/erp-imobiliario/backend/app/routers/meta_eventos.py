"""
GET /api/metas/meta-eventos — read-only lookup of meta_eventos rows.

Primary use case: contextual indicators on source pages
(imoveis, eventos, comissões, contratos) that show "this entity produced
X points for agent Y in the Metas pipeline". RLS on `meta_eventos`
handles scoping — members see their org's rows.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query

from app.dependencies import get_current_user
from app.database import db as db_mod

router = APIRouter(prefix="/api/metas/meta-eventos", tags=["Metas · Meta Eventos"])


@router.get("")
async def listar_por_referencia(
    referencia_tipo: str = Query(..., description="ativo | evento | comissoes_split | contrato"),
    referencia_id: str = Query(...),
    auth = Depends(get_current_user)):
    """Return every meta_evento matching the given (referencia_tipo, referencia_id).

    Usually 0 or 1 row per pair, but some triggers emit multiple (e.g.
    multi-participant visita). Returned oldest-first.
    """
    user, token = auth
    # Use the user client (RLS-enforced) so a non-admin only sees their own
    # org's rows.
    db = db_mod.get_client_for_user(token) if hasattr(db_mod, "get_client_for_user") else db_mod.get_admin_client()
    rows = (
        db.table("meta_eventos")
        .select("*")
        .eq("referencia_tipo", referencia_tipo)
        .eq("referencia_id", referencia_id)
        .order("created_at", desc=False)
        .execute()
    )
    return rows.data or []
