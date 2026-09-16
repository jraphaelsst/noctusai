"""Billing admin — platform admin only.

GET    /api/admin/billing/summary                       MRR/ARR + counts + switches
GET    /api/admin/billing/plans                         plans (incl. inactive) + prices
POST   /api/admin/billing/plans                         create plan
PATCH  /api/admin/billing/plans/{plan_id}               update plan
POST   /api/admin/billing/plans/{plan_id}/prices        new price (retires the current one)
PATCH  /api/admin/billing/prices/{price_id}             Stripe price ids / active flag
GET    /api/admin/billing/settings                      mode, switches, secret status, webhook URLs
PUT    /api/admin/billing/settings                      mode / switches / storage price
PUT    /api/admin/billing/settings/secrets              save or clear one gateway secret
POST   /api/admin/billing/settings/test-connection      read-only gateway call
GET    /api/admin/billing/subscriptions                 all subscriptions (paged)
POST   /api/admin/billing/subscriptions/manual          manual onboarding
POST   /api/admin/billing/subscriptions/{id}/renew      record a manual payment
POST   /api/admin/billing/subscriptions/{id}/cancel     cancel (now or at period end)
GET    /api/admin/billing/payments                      charges with fees (paged)

Secrets are write-only: no response ever carries one.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from noctusai_lib.api.auth.session.types import AuthContext
from noctusai_lib.integrations.payments import PaymentGatewayError
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

from app.schemas.billing_admin import (
    BillingPlanCreate,
    BillingPlanUpdate,
    BillingSettingsUpdate,
    GatewaySecretUpdate,
    GatewayTestRequest,
    ManualOnboardRequest,
    ManualRenewRequest,
    PlanPriceCreate,
    PlanPriceUpdate,
    SubscriptionCancelRequest,
)
from app.services import billing_metrics, billing_subscriptions as subs
from app.services.trusted_auth import require_platform_admin_dep
from app.services.billing_config import (
    SECRET_FIELDS,
    EncryptionNotConfigured,
    GatewayNotConfigured,
    InvalidSecret,
)
from app.services.billing_context import BillingContext, get_billing_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/billing", tags=["Admin · Billing"])

_STATUSES = ("incomplete", "trial", "active", "past_due", "grace", "canceled", "expired")


def _billing_error(exc: subs.BillingError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _one(ctx: BillingContext, table: str, row_id: str) -> dict[str, Any]:
    rows = ctx.db.table(table).select("*").eq("id", row_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    return rows[0]


# ── summary ─────────────────────────────────────────────────────────────


@router.get("/summary")
async def billing_summary(
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    subscriptions = billing_metrics.load_billing_subscriptions(ctx.db)
    mrr = billing_metrics.compute_mrr(subscriptions, billing_metrics.load_plan_prices(ctx.db))
    counts = {status: 0 for status in _STATUSES}
    for row in subscriptions:
        counts[row.get("status")] = counts.get(row.get("status"), 0) + 1
    return {
        "data": {
            **mrr.as_dict(),
            "counts": counts,
            "mode": ctx.config.mode(),
            "automations_enabled": ctx.config.automations_enabled(),
        }
    }


# ── plans + prices ──────────────────────────────────────────────────────


@router.get("/plans")
async def list_plans(
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    plans = list(iter_paged_rows(
        lambda start, end: ctx.db.table("plans").select("*").order("id").range(start, end).execute().data,
        label="plans",
    ))
    prices = list(iter_paged_rows(
        lambda start, end: ctx.db.table("plan_prices").select("*").order("id").range(start, end).execute().data,
        label="plan_prices",
    ))
    plans.sort(key=lambda p: str(p.get("created_at") or ""))
    prices.sort(key=lambda p: str(p.get("created_at") or ""), reverse=True)
    by_plan: dict[str, list] = {}
    for price in prices:
        by_plan.setdefault(str(price["plan_id"]), []).append(price)
    return {"data": [{**plan, "prices": by_plan.get(str(plan["id"]), [])} for plan in plans]}


@router.post("/plans", status_code=201)
async def create_plan(
    body: BillingPlanCreate,
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    if ctx.db.table("plans").select("id").eq("slug", body.slug).limit(1).execute().data:
        raise HTTPException(status_code=409, detail="Já existe um plano com este slug")
    if body.product_id:
        _one(ctx, "products", body.product_id)
    payload = body.model_dump(exclude_none=True)
    payload["ativo"] = True
    created = ctx.db.table("plans").insert(payload).execute().data or []
    if not created:
        raise HTTPException(status_code=500, detail="Erro ao criar plano")
    return {"data": {**created[0], "prices": []}}


@router.patch("/plans/{plan_id}")
async def update_plan(
    plan_id: str,
    body: BillingPlanUpdate,
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    _one(ctx, "plans", plan_id)
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    if payload.get("product_id"):
        _one(ctx, "products", payload["product_id"])
    payload["updated_at"] = ctx.clock().isoformat()
    updated = ctx.db.table("plans").update(payload).eq("id", plan_id).execute().data or []
    return {"data": updated[0] if updated else _one(ctx, "plans", plan_id)}


@router.post("/plans/{plan_id}/prices", status_code=201)
async def create_price(
    plan_id: str,
    body: PlanPriceCreate,
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    """A price is immutable once sold; a new amount is a new row.

    The currently active price for the same cycle + currency is retired
    first (subscriptions keep pointing at the price they were sold at).
    """
    _one(ctx, "plans", plan_id)
    now = ctx.clock().isoformat()
    ctx.db.table("plan_prices").update({"ativo": False, "updated_at": now}).eq("plan_id", plan_id).eq(
        "billing_cycle", body.billing_cycle
    ).eq("currency", body.currency).eq("ativo", True).execute()
    created = (
        ctx.db.table("plan_prices")
        .insert({**body.model_dump(exclude_none=True), "plan_id": plan_id, "ativo": True})
        .execute()
        .data
        or []
    )
    if not created:
        raise HTTPException(status_code=500, detail="Erro ao criar preço")
    return {"data": created[0]}


@router.patch("/prices/{price_id}")
async def update_price(
    price_id: str,
    body: PlanPriceUpdate,
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    _one(ctx, "plan_prices", price_id)
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    for key in ("stripe_price_id_test", "stripe_price_id_live"):
        if key in payload and payload[key] == "":
            payload[key] = None
    payload["updated_at"] = ctx.clock().isoformat()
    updated = ctx.db.table("plan_prices").update(payload).eq("id", price_id).execute().data or []
    return {"data": updated[0] if updated else _one(ctx, "plan_prices", price_id)}


# ── gateway settings ────────────────────────────────────────────────────


@router.get("/settings")
async def get_settings(
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    return {"data": ctx.config.view(webhook_base_url=ctx.webhook_base_url())}


@router.put("/settings")
async def update_settings(
    body: BillingSettingsUpdate,
    auth: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    mode = body.mode
    if mode == "live":
        requested = {"stripe": body.stripe_enabled, "asaas": body.asaas_enabled}
        enabled = {
            g: (flag if flag is not None else ctx.config.gateway_enabled(g))
            for g, flag in requested.items()
        }
        missing = [g for g, on in enabled.items() if on and not ctx.config.gateway_ready(g, "live")]
        if missing:
            raise HTTPException(
                status_code=409,
                detail=f"Modo live sem credenciais completas para: {', '.join(missing)}",
            )
    ctx.config.update_flags(
        user_id=str(auth.user_id),
        mode=mode,
        automations_enabled=body.automations_enabled,
        stripe_enabled=body.stripe_enabled,
        asaas_enabled=body.asaas_enabled,
        storage_price_usd_per_gb_month=body.storage_price_usd_per_gb_month,
    )
    logger.info(
        "billing_admin: settings changed by %s: %s",
        auth.user_id, body.model_dump(exclude_none=True),
    )
    return {"data": ctx.config.view(webhook_base_url=ctx.webhook_base_url())}


@router.put("/settings/secrets")
async def update_secret(
    body: GatewaySecretUpdate,
    auth: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    if body.field not in SECRET_FIELDS[body.gateway]:
        raise HTTPException(status_code=422, detail=f"Campo {body.field} não pertence a {body.gateway}")
    try:
        ctx.config.set_secret(body.gateway, body.field, body.mode, body.value)
    except EncryptionNotConfigured as exc:
        logger.error("billing_admin: cannot store secret — %s", exc)
        raise HTTPException(
            status_code=503, detail="ENCRYPTION_KEY não configurada no Core; nada foi salvo."
        ) from exc
    except InvalidSecret as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    action = "cleared" if not body.value.strip() else "saved"
    logger.info(
        "billing_admin: secret %s.%s.%s %s by %s", body.gateway, body.field, body.mode, action, auth.user_id
    )
    return {"data": ctx.config.view(webhook_base_url=ctx.webhook_base_url())}


@router.post("/settings/test-connection")
async def test_connection(
    body: GatewayTestRequest,
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    try:
        ctx.gateway(body.gateway, body.mode).verify_credentials()
    except GatewayNotConfigured as exc:
        return {"data": {"ok": False, "message": str(exc)}}
    except PaymentGatewayError as exc:
        logger.info("billing_admin: %s/%s test failed: %s", body.gateway, body.mode, exc)
        return {"data": {"ok": False, "message": f"Falha ({exc.status or 'rede'}): {exc.message}"}}
    webhook_field = "webhook_secret" if body.gateway == "stripe" else "webhook_token"
    webhook_ready = bool(ctx.config.get_secret(body.gateway, webhook_field, body.mode))
    message = "Conexão OK." if webhook_ready else "Conexão OK — falta o segredo do webhook."
    return {"data": {"ok": True, "webhook_configured": webhook_ready, "message": message}}


# ── subscriptions + payments ───────────────────────────────────────────


@router.get("/subscriptions")
async def list_subscriptions(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    if status is not None and status not in _STATUSES:
        raise HTTPException(status_code=422, detail="status inválido")
    start = (page - 1) * page_size
    query = ctx.db.table("subscriptions").select(
        "*, organizations(id, nome, slug, org_type), plans(id, nome, slug)", count="exact"
    )
    if status:
        query = query.eq("status", status)
    result = query.order("created_at", desc=True).range(start, start + page_size - 1).execute()
    return {"data": result.data or [], "total": result.count, "page": page, "page_size": page_size}


@router.post("/subscriptions/manual", status_code=201)
async def onboard_manual(
    body: ManualOnboardRequest,
    auth: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    try:
        row = subs.onboard_manual(
            ctx,
            org_id=body.org_id,
            plan_price_id=body.plan_price_id,
            current_period_end=body.current_period_end,
            trial_days=body.trial_days,
            note=body.note,
            actor_user_id=str(auth.user_id),
        )
    except subs.BillingError as exc:
        raise _billing_error(exc) from exc
    return {"data": row}


@router.post("/subscriptions/{subscription_id}/renew")
async def renew_manual(
    subscription_id: str,
    body: ManualRenewRequest,
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    row = _one(ctx, "subscriptions", subscription_id)
    if not row.get("automation_managed"):
        raise HTTPException(status_code=409, detail="Assinatura anterior ao faturamento automático")
    try:
        return {"data": subs.renew_manual(ctx, row, period_end=body.current_period_end)}
    except subs.BillingError as exc:
        raise _billing_error(exc) from exc


@router.post("/subscriptions/{subscription_id}/cancel")
async def cancel_subscription(
    subscription_id: str,
    body: SubscriptionCancelRequest,
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    row = _one(ctx, "subscriptions", subscription_id)
    if not row.get("automation_managed"):
        raise HTTPException(
            status_code=409,
            detail="Assinatura anterior ao faturamento automático — use o fluxo legado.",
        )
    try:
        return {"data": subs.cancel(ctx, row, at_period_end=body.at_period_end)}
    except (PaymentGatewayError, GatewayNotConfigured) as exc:
        logger.error("billing_admin: cancel %s failed at the gateway: %s", subscription_id, exc)
        raise HTTPException(status_code=502, detail=f"O gateway recusou o cancelamento: {exc}") from exc


@router.get("/payments")
async def list_payments(
    org_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: AuthContext = Depends(require_platform_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    start = (page - 1) * page_size
    query = ctx.db.table("billing_payments").select("*, organizations(id, nome)", count="exact")
    if org_id:
        query = query.eq("org_id", org_id)
    result = query.order("created_at", desc=True).range(start, start + page_size - 1).execute()
    rows = result.data or []
    totals = {"gross_cents": 0, "fee_cents": 0, "net_cents": 0}
    for row in rows:
        if row.get("status") == "paid" and row.get("currency") == "BRL":
            for key in totals:
                totals[key] += int(row.get(key) or 0)
    return {"data": rows, "page_totals_brl": totals, "total": result.count, "page": page, "page_size": page_size}
