"""
Financial router — contracts, expenses, revenues, and monthly cash-flow summary.

Auth boundary:
  All /api/financial/* → Depends(get_current_user_org) → strict 401.

Endpoints:
  GET    /api/financial/contracts                   list (paginated, filterable)
  POST   /api/financial/contracts                   create → 201
  GET    /api/financial/contracts/{id}              get by id
  PATCH  /api/financial/contracts/{id}              update
  DELETE /api/financial/contracts/{id}              delete

  GET    /api/financial/expenses                    list (paginated, filterable)
  POST   /api/financial/expenses                    create → 201
  GET    /api/financial/expenses/{id}               get by id
  PATCH  /api/financial/expenses/{id}               update
  DELETE /api/financial/expenses/{id}               delete

  GET    /api/financial/revenues                    list (paginated, filterable)
  POST   /api/financial/revenues                    create → 201
  GET    /api/financial/revenues/{id}               get by id
  PATCH  /api/financial/revenues/{id}               update
  DELETE /api/financial/revenues/{id}               delete

  GET    /api/financial/cash-flow/{month}           monthly cash-flow summary
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import (
    coerce_org_uuid,
    get_current_user_org,
    get_user_client,
)
from app.schemas.financial import (
    ContractCreate,
    ContractOut,
    ContractUpdate,
    ExpenseCreate,
    ExpenseOut,
    ExpenseUpdate,
    MonthlyCashFlowOut,
    RevenueCreate,
    RevenueOut,
    RevenueUpdate,
)
from app.services.financial_service import FinancialService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Financial"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _fin(token: str, org_id: UUID) -> FinancialService:
    return FinancialService(get_user_client(token), org_id=org_id)


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

@router.get("/api/financial/contracts", status_code=status.HTTP_200_OK)
async def list_contracts(
    status_filter: str | None = Query(default=None, alias="status"),
    client_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _fin(token, org_id).list_contracts(
            status=status_filter,
            client_id=client_id,
            page=page,
            page_size=page_size,
        )
    except Exception:
        logger.exception("financial.list_contracts failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar contratos")


@router.post(
    "/api/financial/contracts",
    response_model=ContractOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_contract(
    payload: ContractCreate,
    auth: tuple = Depends(get_current_user_org),
) -> ContractOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _fin(token, org_id).create_contract(payload.model_dump(exclude_none=True))
    except Exception:
        logger.exception("financial.create_contract failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar contrato")
    return ContractOut(**row)


@router.get(
    "/api/financial/contracts/{contract_id}",
    response_model=ContractOut,
    status_code=status.HTTP_200_OK,
)
async def get_contract(
    contract_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> ContractOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _fin(token, org_id).get_contract(contract_id)
    except Exception:
        logger.exception("financial.get_contract failed org=%s id=%s", org_id, contract_id)
        raise HTTPException(status_code=502, detail="Falha ao buscar contrato")
    if not row:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    return ContractOut(**row)


@router.patch(
    "/api/financial/contracts/{contract_id}",
    response_model=ContractOut,
    status_code=status.HTTP_200_OK,
)
async def update_contract(
    contract_id: str,
    payload: ContractUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> ContractOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = _fin(token, org_id).update_contract(contract_id, data)
    except Exception:
        logger.exception("financial.update_contract failed org=%s id=%s", org_id, contract_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar contrato")
    if not row:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    return ContractOut(**row)


@router.delete("/api/financial/contracts/{contract_id}", status_code=status.HTTP_200_OK)
async def delete_contract(
    contract_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _fin(token, org_id).delete_contract(contract_id)
    except Exception:
        logger.exception("financial.delete_contract failed org=%s id=%s", org_id, contract_id)
        raise HTTPException(status_code=502, detail="Falha ao deletar contrato")
    if not ok:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    return {"ok": True, "id": contract_id}


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

@router.get("/api/financial/expenses", status_code=status.HTTP_200_OK)
async def list_expenses(
    paid: bool | None = Query(default=None),
    recurrence: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _fin(token, org_id).list_expenses(
            paid=paid,
            recurrence=recurrence,
            page=page,
            page_size=page_size,
        )
    except Exception:
        logger.exception("financial.list_expenses failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar despesas")


@router.post(
    "/api/financial/expenses",
    response_model=ExpenseOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_expense(
    payload: ExpenseCreate,
    auth: tuple = Depends(get_current_user_org),
) -> ExpenseOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _fin(token, org_id).create_expense(payload.model_dump(exclude_none=True))
    except Exception:
        logger.exception("financial.create_expense failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar despesa")
    return ExpenseOut(**row)


@router.get(
    "/api/financial/expenses/{expense_id}",
    response_model=ExpenseOut,
    status_code=status.HTTP_200_OK,
)
async def get_expense(
    expense_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> ExpenseOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _fin(token, org_id).get_expense(expense_id)
    except Exception:
        logger.exception("financial.get_expense failed org=%s id=%s", org_id, expense_id)
        raise HTTPException(status_code=502, detail="Falha ao buscar despesa")
    if not row:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    return ExpenseOut(**row)


@router.patch(
    "/api/financial/expenses/{expense_id}",
    response_model=ExpenseOut,
    status_code=status.HTTP_200_OK,
)
async def update_expense(
    expense_id: str,
    payload: ExpenseUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> ExpenseOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = _fin(token, org_id).update_expense(expense_id, data)
    except Exception:
        logger.exception("financial.update_expense failed org=%s id=%s", org_id, expense_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar despesa")
    if not row:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    return ExpenseOut(**row)


@router.delete("/api/financial/expenses/{expense_id}", status_code=status.HTTP_200_OK)
async def delete_expense(
    expense_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _fin(token, org_id).delete_expense(expense_id)
    except Exception:
        logger.exception("financial.delete_expense failed org=%s id=%s", org_id, expense_id)
        raise HTTPException(status_code=502, detail="Falha ao deletar despesa")
    if not ok:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    return {"ok": True, "id": expense_id}


# ---------------------------------------------------------------------------
# Revenues
# ---------------------------------------------------------------------------

@router.get("/api/financial/revenues", status_code=status.HTTP_200_OK)
async def list_revenues(
    status_filter: str | None = Query(default=None, alias="status"),
    client_id: str | None = Query(default=None),
    reference_month: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _fin(token, org_id).list_revenues(
            status=status_filter,
            client_id=client_id,
            reference_month=reference_month,
            page=page,
            page_size=page_size,
        )
    except Exception:
        logger.exception("financial.list_revenues failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar receitas")


@router.post(
    "/api/financial/revenues",
    response_model=RevenueOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_revenue(
    payload: RevenueCreate,
    auth: tuple = Depends(get_current_user_org),
) -> RevenueOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _fin(token, org_id).create_revenue(payload.model_dump(exclude_none=True))
    except Exception:
        logger.exception("financial.create_revenue failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar receita")
    return RevenueOut(**row)


@router.get(
    "/api/financial/revenues/{revenue_id}",
    response_model=RevenueOut,
    status_code=status.HTTP_200_OK,
)
async def get_revenue(
    revenue_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> RevenueOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _fin(token, org_id).get_revenue(revenue_id)
    except Exception:
        logger.exception("financial.get_revenue failed org=%s id=%s", org_id, revenue_id)
        raise HTTPException(status_code=502, detail="Falha ao buscar receita")
    if not row:
        raise HTTPException(status_code=404, detail="Receita não encontrada")
    return RevenueOut(**row)


@router.patch(
    "/api/financial/revenues/{revenue_id}",
    response_model=RevenueOut,
    status_code=status.HTTP_200_OK,
)
async def update_revenue(
    revenue_id: str,
    payload: RevenueUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> RevenueOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = _fin(token, org_id).update_revenue(revenue_id, data)
    except Exception:
        logger.exception("financial.update_revenue failed org=%s id=%s", org_id, revenue_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar receita")
    if not row:
        raise HTTPException(status_code=404, detail="Receita não encontrada")
    return RevenueOut(**row)


@router.delete("/api/financial/revenues/{revenue_id}", status_code=status.HTTP_200_OK)
async def delete_revenue(
    revenue_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _fin(token, org_id).delete_revenue(revenue_id)
    except Exception:
        logger.exception("financial.delete_revenue failed org=%s id=%s", org_id, revenue_id)
        raise HTTPException(status_code=502, detail="Falha ao deletar receita")
    if not ok:
        raise HTTPException(status_code=404, detail="Receita não encontrada")
    return {"ok": True, "id": revenue_id}


# ---------------------------------------------------------------------------
# Cash-flow summary
# ---------------------------------------------------------------------------

@router.get(
    "/api/financial/cash-flow/{month}",
    response_model=MonthlyCashFlowOut,
    status_code=status.HTTP_200_OK,
)
async def monthly_cash_flow(
    month: str,
    auth: tuple = Depends(get_current_user_org),
) -> MonthlyCashFlowOut:
    """Monthly cash-flow summary.

    ``month`` must be a date string in YYYY-MM-DD format (first day of month).
    Returns paid revenues, paid expenses, net, and AR aging buckets.
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        summary = _fin(token, org_id).monthly_cash_flow(month)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("financial.cash_flow failed org=%s month=%s", org_id, month)
        raise HTTPException(status_code=502, detail="Falha ao calcular fluxo de caixa")
    return MonthlyCashFlowOut(**summary)
