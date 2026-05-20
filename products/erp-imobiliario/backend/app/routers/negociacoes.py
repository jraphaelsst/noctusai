"""
Negociações Router — replaces frontend supabase.from('negociacoes') bypass.

Created 2026-05-20 (Phase 4 — Pattern D resolution). Replaces the
`useNegociacoes.ts` direct supabase.from() read; backend role-aware filter
moves out of the frontend (security: prevents tampered client predicates).
RLS on `erp.negociacoes` is the primary boundary; the role-aware OR-filter
mirrors the previous client-side shape for admin-vs-corretor visibility.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user, get_user_client, get_erp_user_role
from app.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/negociacoes", tags=["Negociacoes"])


@router.get("")
async def listar_negociacoes(
    status_etapa: Optional[str] = Query(default=None, description="Filter by status_etapa; omit/'todas' for all"),
    auth=Depends(get_current_user),
):
    """List negociações the caller can see.

    Admins see all rows; non-admins see only rows where they appear as
    `cliente_proprietario_id` or `cliente_ofertante_id` (mirrors the
    pre-existing FE-side filter that lived in useNegociacoes.ts).
    Backend enforcement supersedes the client predicate (security).
    """
    user, token = auth
    db = get_user_client(token)
    role = get_erp_user_role(user)
    is_admin = role in ("admin", "platform_admin", "owner")

    query = db.table("negociacoes").select("*").order("created_at", desc=True)

    if not is_admin:
        # Same OR-shape as the prior FE filter
        query = query.or_(
            f"cliente_proprietario_id.eq.{user.id},cliente_ofertante_id.eq.{user.id}"
        )

    if status_etapa and status_etapa != "todas":
        query = query.eq("status_etapa", status_etapa)

    result = query.execute()
    rows = result.data or []
    return success_response(rows, total=len(rows))
