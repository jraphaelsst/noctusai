"""Financial router -- the Orbity layer over the seed finance + contracts organs.

The organs own the money model and are mounted by ``app/main.py``:
  /api/finance/*     entries (receivable / payable), settlements, categories, DRE, cash flow, aging, reconciliation
  /api/contracts/*   contracts: create / activate / suspend / resume / terminate / amend / readjust / billing preview

This router holds only what the organs do not know (the client behind a receivable, its gateway charge):

  GET    /api/financial/gateway                         is a payment gateway configured for this org?
  GET    /api/financial/cash-flow/{month}               month summary (kept-after-inactivation rule)
  GET    /api/financial/charges                         receivables + gateway state (queued/generating/retrying/generated/failed)
  POST   /api/financial/charges                         an extra (one-off) receivable for a client        [admin]
  POST   /api/financial/charges/{entry_id}/generate     (re)queue a skipped/failed charge for the gateway  [admin]

Auth: every route -> strict 401; the writes need an ORG ADMIN of the SELECTED org (``make_organ_auth``).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from noctusai_seed.organ_auth import make_organ_auth

from app import billing
from app.dependencies import coerce_org_uuid, get_admin_client, get_core_client, get_current_user_org
from app.schemas.financial import ChargeListOut, ChargeOut, ExtraChargeCreate, MonthlyCashFlowOut
from app.services import billing_charges as bc
from app.services.financial_service import FinancialService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/financial", tags=["Financial"])

_organ_auth = make_organ_auth(get_current_user_org, get_core_client, context="Financeiro")
admin_dependency = _organ_auth.admin


def _org(auth: tuple) -> str:
    return str(coerce_org_uuid(auth[2]))


def _http(exc: bc.BillingError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.message)


@router.get("/gateway", status_code=status.HTTP_200_OK)
async def gateway_status(auth: tuple = Depends(get_current_user_org)) -> dict:
    org_id = _org(auth)
    return {"gateway": billing.GATEWAY_NAME, "configured": billing.gateway_is_configured(org_id)}


@router.get("/cash-flow/{month}", response_model=MonthlyCashFlowOut, status_code=status.HTTP_200_OK)
async def monthly_cash_flow(month: str, auth: tuple = Depends(get_current_user_org)) -> MonthlyCashFlowOut:
    """``month`` is ``YYYY-MM-DD`` (first of the month; any day is accepted and normalised)."""
    org_id = _org(auth)
    try:
        summary = await asyncio.to_thread(lambda: FinancialService(get_admin_client(), org_id).monthly_cash_flow(month))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("financial.cash_flow failed org=%s month=%s", org_id, month)
        raise HTTPException(status_code=502, detail="Falha ao calcular fluxo de caixa")
    return MonthlyCashFlowOut(**summary)


@router.get("/charges", response_model=ChargeListOut, status_code=status.HTTP_200_OK)
async def list_charges(
    client_id: Optional[str] = Query(default=None),
    generation_status: Optional[str] = Query(default=None, pattern="^(queued|generating|retrying|generated|failed|skipped)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> ChargeListOut:
    org_id = _org(auth)
    try:
        data = await asyncio.to_thread(lambda: FinancialService(get_admin_client(), org_id).list_charges(
            client_id=client_id, generation_status=generation_status, page=page, page_size=page_size))
    except Exception:
        logger.exception("financial.list_charges failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar cobranças")
    return ChargeListOut(**data)


@router.post("/charges", response_model=ChargeOut, status_code=status.HTTP_201_CREATED)
async def create_extra_charge(payload: ExtraChargeCreate, auth: tuple = Depends(admin_dependency)) -> ChargeOut:
    org_id = _org(auth)
    try:
        created = await asyncio.to_thread(lambda: bc.create_extra_charge(
            get_admin_client(), org_id, client_id=payload.client_id, description=payload.description,
            amount_cents=payload.amount_cents, due_date=payload.due_date, gateway=billing.get_gateway()))
        rows = await asyncio.to_thread(lambda: FinancialService(get_admin_client(), org_id).present_charges([created]))
    except bc.BillingError as exc:
        raise _http(exc)
    except Exception:
        logger.exception("financial.create_extra_charge failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar a cobrança")
    return ChargeOut(**rows[0])


@router.post("/charges/{entry_id}/generate", response_model=ChargeOut, status_code=status.HTTP_200_OK)
async def generate_charge(entry_id: str, auth: tuple = Depends(admin_dependency)) -> ChargeOut:
    org_id = _org(auth)
    try:
        charge = await asyncio.to_thread(lambda: bc.requeue_charge(get_admin_client(), org_id, entry_id, billing.get_gateway()))
        rows = await asyncio.to_thread(lambda: FinancialService(get_admin_client(), org_id).present_charges([charge]))
    except bc.BillingError as exc:
        raise _http(exc)
    except Exception:
        logger.exception("financial.generate_charge failed org=%s entry=%s", org_id, entry_id)
        raise HTTPException(status_code=502, detail="Falha ao enfileirar a cobrança")
    return ChargeOut(**rows[0])
