from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..data.store import store
from ..auth_deps import get_current_user

router = APIRouter()


def _invoices_for(did: str, status: str | None = None) -> list[dict[str, Any]]:
    rows = [i for i in store.invoices if i["distributorId"] == did]
    if status:
        rows = [i for i in rows if i["status"] == status]
    rows.sort(key=lambda i: i["issueDate"], reverse=True)
    return rows


@router.get("/invoices")
def list_invoices(
    status: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    did = user.get("distributorId")
    if not did:
        raise HTTPException(401)
    return {"data": _invoices_for(did, status)}


@router.get("/balance")
def get_balance(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    did = user.get("distributorId")
    if not did:
        raise HTTPException(401)
    rows = _invoices_for(did)
    open_amount = sum(i["amount"] for i in rows if i["status"] == "em_aberto")
    overdue = sum(i["amount"] for i in rows if i["status"] == "vencido")
    paid = sum(i["amount"] for i in rows if i["status"] == "pago")
    # Limite de crédito é campo planejado na plataforma — placeholder até vir do ERP.
    credit_limit = 50_000
    return {
        "openAmount": open_amount,
        "overdueAmount": overdue,
        "paidAmount": paid,
        "creditLimit": credit_limit,
        "creditUsed": open_amount + overdue,
    }
