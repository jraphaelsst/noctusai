"""AI credits — platform admin (`noctus_users.role == 'admin'`).

GET  /api/admin/credits/wallets                   every wallet (org name, mode, balance credits + R$)
GET  /api/admin/credits/{org_id}                  one org: wallet + recent entries + purchases
GET  /api/admin/credits/{org_id}/grant            the org's grant history
POST /api/admin/credits/{org_id}/grant            grant credits (in credits OR US$) — same ledger path
                                                  as a paid purchase (kind=grant, source=admin_grant)
POST /api/admin/credits/{org_id}/adjustments      signed correction
PUT  /api/admin/credits/{org_id}/wallet           mode prepaid | postpaid_trusted | byok, overdraft, alerts
GET  /api/admin/credits/pricing                   pricing versions (+ implied gross margin)
POST /api/admin/credits/pricing                   new pricing version (effective now; never edits a past one)
GET  /api/admin/credits/margin                    revenue (credits charged, R$) vs provider cost per org/product

An unknown org is 404 (never a silently created wallet).
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from noctusai_lib.api.auth.session.types import AuthContext

from app.routers.credits import pricing_or_503, window
from app.schemas.credits import (
    CreditAdjustmentRequest,
    CreditGrantRequest,
    CreditPricingCreate,
    CreditWalletSettingsRequest,
)
from app.services.billing_context import BillingContext, get_billing_context
from app.services.credits import purchases, reports, wallets
from app.services.credits.pricing import PRICING_TABLE, list_pricing
from app.services.trusted_auth import require_platform_admin_dep

router = APIRouter(prefix="/api/admin/credits", tags=["Admin · Credits"])


def _org_or_404(ctx: BillingContext, org_id: str) -> dict[str, Any]:
    rows = ctx.db.table("organizations").select("id, nome, slug").eq("id", org_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Organização não encontrada")
    return rows[0]


def _refused(exc: wallets.CreditsError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/wallets")
def list_wallets(
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    pricing = pricing_or_503(ctx)
    rows = ctx.db.table(wallets.WALLETS).select("*").order("updated_at", desc=True).limit(1000).execute().data or []
    ids = [str(r["org_id"]) for r in rows]
    names: dict[str, dict[str, Any]] = {}
    if ids:
        for o in ctx.db.table("organizations").select("id, nome, slug").in_("id", ids).execute().data or []:
            names[str(o["id"])] = o
    return {"data": [
        {"org_id": str(r["org_id"]), "org_nome": names.get(str(r["org_id"]), {}).get("nome"),
         "org_slug": names.get(str(r["org_id"]), {}).get("slug"), **wallets.wallet_view(r, pricing)}
        for r in rows
    ]}


@router.get("/pricing")
def get_pricing(
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    return {"data": list_pricing(ctx.db)}


@router.post("/pricing")
def create_pricing(
    body: CreditPricingCreate,
    auth: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    latest = ctx.db.table(PRICING_TABLE).select("version").order("version", desc=True).limit(1).execute().data or []
    version = (int(latest[0]["version"]) if latest else 0) + 1
    row = body.model_dump(mode="json")  # Decimal -> exact string
    ctx.db.table(PRICING_TABLE).insert({
        **row, "version": version, "effective_from": ctx.clock().isoformat(), "created_by": str(auth.user_id),
    }).execute()
    return {"data": list_pricing(ctx.db)}


@router.get("/margin")
def margin(
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    org_id: Optional[str] = Query(None),
):
    start, end = window(from_, to)
    return {"data": reports.margin_report(ctx.db, start=start, end=end, org_id=org_id)}


@router.get("/{org_id}")
def org_detail(
    org_id: str,
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    org = _org_or_404(ctx, org_id)
    pricing = pricing_or_503(ctx)
    return {"data": {
        "org": org,
        "wallet": wallets.wallet_view(wallets.get_wallet(ctx.db, org_id), pricing),
        "entries": reports.recent_entries(ctx.db, org_id),
        "purchases": purchases.list_purchases(ctx.db, org_id),
    }}


@router.get("/{org_id}/grant")
def grant_history(
    org_id: str,
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    _org_or_404(ctx, org_id)
    rows = (
        ctx.db.table("credit_entries")
        .select("id,created_at,credits,brl_amount,usd_amount,fx_rate,reason,created_by,balance_after")
        .eq("org_id", org_id).eq("kind", "grant").order("created_at", desc=True).limit(200).execute().data or []
    )
    return {"data": rows}


@router.post("/{org_id}/grant")
def grant_credits(
    org_id: str,
    body: CreditGrantRequest,
    auth: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    _org_or_404(ctx, org_id)
    try:
        result = wallets.grant(ctx, org_id, credits=body.credits, usd=body.usd, reason=body.reason,
                               actor=str(auth.user_id))
    except wallets.CreditsError as exc:
        raise _refused(exc) from exc
    return {"data": result}


@router.post("/{org_id}/adjustments")
def adjust_credits(
    org_id: str,
    body: CreditAdjustmentRequest,
    auth: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    _org_or_404(ctx, org_id)
    try:
        result = wallets.adjust(ctx, org_id, credits=body.credits, reason=body.reason, actor=str(auth.user_id))
    except wallets.CreditsError as exc:
        raise _refused(exc) from exc
    return {"data": result}


@router.put("/{org_id}/wallet")
def set_wallet(
    org_id: str,
    body: CreditWalletSettingsRequest,
    auth: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    _org_or_404(ctx, org_id)
    pricing = pricing_or_503(ctx)
    try:
        wallet = wallets.update_settings(
            ctx, org_id, mode=body.mode, overdraft_limit_credits=body.overdraft_limit_credits,
            alert_thresholds=body.alert_thresholds, actor=str(auth.user_id),
        )
    except wallets.CreditsError as exc:
        raise _refused(exc) from exc
    return {"data": wallets.wallet_view(wallet, pricing)}
