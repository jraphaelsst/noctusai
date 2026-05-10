"""
Rewards router — DB-backed (replaces the mock-backed JSON variant).

Endpoints:
  - GET   /api/rewards/ledger             — distributor's accrual ledger
  - GET   /api/rewards/rules              — active reward rules in the org
  - POST  /api/rewards/redeem             — request redemption (status=pendente)
  - PATCH /api/rewards/redeem/{id}/process — brand admin approves/rejects/marks paid

Auth uses the existing custom-JWT shim in `app.auth_deps`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from ..auth_deps import get_current_user, require_role
from ..database import _db as _db_module
from ..schemas.rewards import (
    RedemptionOut,
    RedemptionProcessIn,
    RedemptionRequestIn,
    RewardLedgerOut,
    RewardRulesListOut,
)
from ..services.rewards_service import (
    LEDGER_TABLE,
    REGRAS_TABLE,
    RESGATES_TABLE,
    summarize_ledger,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rewards", tags=["rewards"])

DEFAULT_ORG_ID = "adconnect-default"


def _db() -> Any:
    """Lazy access via `_db` so test patches of `_db.get_client` are honored."""
    try:
        client = _db_module.get_client()
    except Exception:
        client = None
    if client is None:
        try:
            client = _db_module.get_admin_client()
        except Exception:
            client = None
    if client is None:
        raise HTTPException(503, "Supabase client unavailable")
    return client


def _user_distributor(user: dict[str, Any]) -> Optional[str]:
    return user.get("distributorId") or user.get("distributor_id")


def _user_org(user: dict[str, Any]) -> str:
    return user.get("orgId") or user.get("org_id") or DEFAULT_ORG_ID


@router.get("/ledger", response_model=RewardLedgerOut)
def get_ledger(
    user: dict[str, Any] = Depends(get_current_user),
    distributor_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    db = _db()
    role = user.get("role")
    target_did = distributor_id or _user_distributor(user)
    if not target_did and role != "admin":
        raise HTTPException(403, "Sem distribuidor associado")
    builder = db.table(LEDGER_TABLE).select("*")
    if role == "admin":
        builder = builder.eq("org_id", _user_org(user))
        if target_did:
            builder = builder.eq("distributor_id", target_did)
    else:
        builder = builder.eq("distributor_id", target_did)
    res = builder.execute()
    rows = list(res.data or [])
    return {"data": rows, "summary": summarize_ledger(rows)}


@router.get("/rules", response_model=RewardRulesListOut)
def get_rules(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    db = _db()
    res = (
        db.table(REGRAS_TABLE)
        .select("*")
        .eq("org_id", _user_org(user))
        .eq("ativo", True)
        .execute()
    )
    return {"data": list(res.data or [])}


@router.post(
    "/redeem", response_model=RedemptionOut, status_code=status.HTTP_201_CREATED
)
def request_redemption(
    body: RedemptionRequestIn,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    distributor_id = body.distributor_id or _user_distributor(user)
    if not distributor_id:
        raise HTTPException(400, "distributor_id obrigatório")
    if body.valor <= 0:
        raise HTTPException(400, "Valor precisa ser positivo")
    db = _db()
    payload = {
        "org_id": _user_org(user),
        "distributor_id": distributor_id,
        "requested_by": user.get("sub"),
        "tipo": body.tipo,
        "valor": body.valor,
        "pedido_ref": body.pedido_ref,
        "status": "pendente",
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    res = db.table(RESGATES_TABLE).insert(payload).execute()
    if not res.data:
        raise HTTPException(500, "Falha ao criar resgate")
    return res.data[0]


@router.patch("/redeem/{redemption_id}/process", response_model=RedemptionOut)
def process_redemption(
    body: RedemptionProcessIn,
    redemption_id: str = Path(...),
    user: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    if body.status not in {"aprovado", "rejeitado", "pago"}:
        raise HTTPException(400, "status inválido")
    db = _db()
    payload: dict[str, Any] = {
        "status": body.status,
        "review_notes": body.review_notes,
        "reviewed_by": user.get("sub"),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    if body.status == "pago":
        payload["paid_at"] = datetime.now(timezone.utc).isoformat()
    res = (
        db.table(RESGATES_TABLE)
        .update(payload)
        .eq("id", redemption_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "Resgate não encontrado")
    return res.data[0]


__all__ = ["router"]
