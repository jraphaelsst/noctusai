from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..data.store import store
from ..auth_deps import require_role

router = APIRouter()


@router.get("/dashboard")
def dashboard(_: dict[str, Any] = Depends(require_role("admin"))) -> dict[str, Any]:
    paid = sum(i["amount"] for i in store.invoices if i["status"] == "pago")
    return {
        "distributorsCount": len(store.distributors),
        "activeDistributors": sum(
            1 for d in store.distributors if d["status"] == "active"
        ),
        "pendingDistributors": sum(
            1 for d in store.distributors if d["status"] == "pending"
        ),
        "ordersCount": len(store.orders),
        "totalRevenue": paid,
        "pendingSellout": sum(
            1 for r in store.sellout_reports if r["status"] == "Pendente"
        ),
    }


class RewardRuleInput(BaseModel):
    sku: str
    product: str
    category: str
    minQty: int
    active: bool
    tiers: dict[str, dict[str, float]]


@router.get("/reward-rules")
def list_rules(_: dict[str, Any] = Depends(require_role("admin"))) -> dict[str, Any]:
    return {"data": store.reward_rules}


@router.put("/reward-rules/{id}")
def upsert_rule(
    id: str,
    body: RewardRuleInput,
    _: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    rule = {**body.model_dump(), "id": id}
    idx = next((i for i, r in enumerate(store.reward_rules) if r["id"] == id), -1)
    if idx >= 0:
        store.reward_rules[idx] = rule
    else:
        store.reward_rules.append(rule)
    return rule


@router.delete("/reward-rules/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    id: str, _: dict[str, Any] = Depends(require_role("admin"))
) -> None:
    idx = next((i for i, r in enumerate(store.reward_rules) if r["id"] == id), -1)
    if idx < 0:
        raise HTTPException(404)
    store.reward_rules.pop(idx)


class PromoInput(BaseModel):
    sku: str
    product: str
    type: str
    label: str
    cashbackPct: float
    mktBudgetPct: float
    validFrom: str
    validTo: str
    active: bool


@router.get("/promos")
def list_promos(_: dict[str, Any] = Depends(require_role("admin"))) -> dict[str, Any]:
    return {"data": store.promos}


@router.put("/promos/{id}")
def upsert_promo(
    id: str,
    body: PromoInput,
    _: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    promo = {**body.model_dump(), "id": id}
    idx = next((i for i, p in enumerate(store.promos) if p["id"] == id), -1)
    if idx >= 0:
        store.promos[idx] = promo
    else:
        store.promos.append(promo)
    return promo


@router.delete("/promos/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_promo(
    id: str, _: dict[str, Any] = Depends(require_role("admin"))
) -> None:
    idx = next((i for i, p in enumerate(store.promos) if p["id"] == id), -1)
    if idx < 0:
        raise HTTPException(404)
    store.promos.pop(idx)


@router.get("/sellout/reports")
def admin_sellout_reports(
    _: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    rows = sorted(store.sellout_reports, key=lambda r: r["uploadDate"], reverse=True)
    return {"data": rows}


class StatusInput(BaseModel):
    status: str


@router.patch("/sellout/reports/{id}/status")
def admin_set_status(
    id: str,
    body: StatusInput,
    _: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    r = next((x for x in store.sellout_reports if x["id"] == id), None)
    if not r:
        raise HTTPException(404, "Relatório não encontrado")
    if body.status not in ("Aprovado", "Pendente", "Rejeitado"):
        raise HTTPException(400, "Status inválido")
    r["status"] = body.status
    return r
