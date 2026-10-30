"""AI credits — the org's own wallet (owner / admin / manager of the selected org).

GET  /api/credits/wallet    balance (credits + R$), mode, alert state, recent top-ups,
                            purchases, the gateways a purchase may use
GET  /api/credits/usage     org → product → feature: calls, tokens, credits, R$ (retail)
                            + a daily credits series per product; ?from&to&product
POST /api/credits/purchase  open a prepaid PIX / boleto / card charge on the existing
                            billing gateway; the paid webhook credits the wallet

The org is ALWAYS the caller's selected org (`AuthContext.org_id`) — there is no
org parameter to tamper with. Provider cost and margin never appear here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from noctusai_lib.api.auth.session.types import AuthContext
from noctusai_lib.integrations.llm.ledger_read import AiUsageWindowTooLarge
from noctusai_lib.primitives.parsing import parse_iso_or_400 as _parse_iso

from app.routers.billing import _safe_return_url
from app.schemas.credits import CreditPurchaseRequest
from app.services.billing_context import BillingContext, get_billing_context
from app.services.credits import purchases, reports, wallets
from app.services.credits.pricing import PricingNotConfigured, load_pricing
from app.services.trusted_auth import get_trusted_db, require_org_admin_dep

router = APIRouter(prefix="/api/credits", tags=["Credits"])

MAX_WINDOW_DAYS = 400


def window(from_: Optional[str], to: Optional[str], *, default_days: int = 30) -> tuple[datetime, datetime]:
    now = datetime.now(tz=timezone.utc)
    start = _parse_iso(from_) or (now - timedelta(days=default_days))
    end = _parse_iso(to) or now
    if end < start:
        raise HTTPException(status_code=400, detail="'to' precede 'from'")
    if end - start > timedelta(days=MAX_WINDOW_DAYS):
        raise HTTPException(status_code=400, detail=f"Janela maior que {MAX_WINDOW_DAYS} dias")
    return start, end


def pricing_or_503(ctx: BillingContext):
    try:
        return load_pricing(ctx.db, at=ctx.clock())
    except PricingNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/wallet")
def my_wallet(
    auth: AuthContext = Depends(require_org_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    org_id = str(auth.org_id)
    pricing = pricing_or_503(ctx)
    gateways = [g for g in ("asaas", "stripe") if ctx.config.gateway_enabled(g)]
    return {"data": {
        "wallet": wallets.wallet_view(wallets.get_wallet(ctx.db, org_id), pricing),
        "entries": reports.recent_entries(ctx.db, org_id),
        "purchases": purchases.list_purchases(ctx.db, org_id),
        "gateways": gateways,
    }}


@router.get("/usage")
def my_usage(
    auth: AuthContext = Depends(require_org_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    product: Optional[str] = Query(None, max_length=200),
):
    start, end = window(from_, to)
    pricing = pricing_or_503(ctx)
    try:
        data = reports.org_usage(ctx.db, str(auth.org_id), start=start, end=end, pricing=pricing, product=product)
    except AiUsageWindowTooLarge as exc:
        raise HTTPException(status_code=400, detail="Janela grande demais; reduza o período") from exc
    return {"data": data}


@router.post("/purchase")
def buy_credits(
    body: CreditPurchaseRequest,
    auth: AuthContext = Depends(require_org_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
    db: Any = Depends(get_trusted_db),
):
    users = db.table("noctus_users").select("email").eq("id", str(auth.user_id)).limit(1).execute().data or []
    payer_email = (users[0].get("email") if users else None) or ""
    try:
        result = purchases.start_purchase(
            ctx,
            org_id=str(auth.org_id),
            amount_brl=body.amount_brl,
            gateway=body.gateway,
            billing_method=body.billing_method,
            payer_email=payer_email,
            tax_id=body.tax_id,
            actor=str(auth.user_id),
            success_url=_safe_return_url(ctx.settings.app_base_url, body.success_url, "/creditos?compra=ok"),
            cancel_url=_safe_return_url(ctx.settings.app_base_url, body.cancel_url, "/creditos"),
        )
    except wallets.CreditsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except PricingNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"data": result}
