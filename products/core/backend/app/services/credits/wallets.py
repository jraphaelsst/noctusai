"""Credit wallets — settings, the one apply path (+ 50/80/100% alerts), admin grants.

Every movement goes through `apply()` → `ctx.credits().apply(...)` (the
``credit_apply_entry`` RPC). A crossed alert threshold comes back from that
same transaction and is turned into an in-app notification for the org's
owners/admins AND the platform admins (seed `write_in_app`). A notification
failure never undoes the money movement; it is logged at ERROR.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from noctusai_lib.domain.notifications import write_in_app

from app.services import fx_service
from app.services.billing_context import BillingContext
from app.services.credits.ledger import ApplyResult, CreditEntryInput
from app.services.credits.pricing import Pricing, brl_for_credits, credits_for_usd_grant, load_pricing

logger = logging.getLogger(__name__)

WALLETS = "credit_wallets"
MODES = ("prepaid", "postpaid_trusted", "byok")
ALERT_KIND = "creditos_alerta"
_ORG_ALERT_ROLES = ("owner", "admin")


class CreditsError(RuntimeError):
    """A refused credit operation (status_code is the HTTP answer)."""

    def __init__(self, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


def get_wallet(db: Any, org_id: str) -> Optional[dict[str, Any]]:
    rows = db.table(WALLETS).select("*").eq("org_id", org_id).limit(1).execute().data or []
    return rows[0] if rows else None


def _num(value: Any) -> float:
    return float(value) if value is not None else 0.0


def wallet_view(wallet: Optional[dict[str, Any]], pricing: Pricing) -> dict[str, Any]:
    """What the org / admin screens show (credits AND R$; never the margin)."""
    unit = float(pricing.credit_unit_brl)
    if wallet is None:
        return {
            "exists": False, "mode": None, "balance_credits": 0.0, "balance_brl": 0.0,
            "overdraft_limit_credits": 0.0, "alert_thresholds": [0.5, 0.8, 1.0], "consumed_pct": 0.0,
            "credit_unit_brl": unit, "blocked": False,
        }
    balance = _num(wallet.get("balance_credits"))
    base = _num(wallet.get("alert_base_credits"))
    overdraft = _num(wallet.get("overdraft_limit_credits"))
    consumed = 0.0 if base <= 0 else max(0.0, min(1.0, (base - balance) / base))
    return {
        "exists": True,
        "mode": wallet.get("mode"),
        "balance_credits": balance,
        "balance_brl": round(balance * unit, 2),
        "overdraft_limit_credits": overdraft,
        "alert_thresholds": [float(t) for t in (wallet.get("alert_thresholds") or [])],
        "alert_base_credits": base,
        "consumed_pct": round(consumed, 4),
        "credit_unit_brl": unit,
        "blocked": wallet.get("mode") == "prepaid" and balance <= -overdraft,
        "charge_from": wallet.get("charge_from"),
        "updated_at": wallet.get("updated_at"),
    }


def ensure_wallet(
    db: Any, org_id: str, *, actor: Optional[str] = None, now: Optional[datetime] = None,
) -> dict[str, Any]:
    """The org's wallet, created empty (prepaid, balance 0) when missing."""
    existing = get_wallet(db, org_id)
    if existing:
        return existing
    db.table(WALLETS).insert({
        "org_id": org_id, "updated_by": actor,
        # usage BEFORE the wallet existed is never billed retroactively
        "charge_from": (now or datetime.now(timezone.utc)).isoformat(),
    }).execute()
    created = get_wallet(db, org_id)
    if created is None:
        raise RuntimeError(f"credits: wallet insert for org {org_id} returned no row")
    return created


def update_settings(
    ctx: BillingContext,
    org_id: str,
    *,
    mode: Optional[str] = None,
    overdraft_limit_credits: Optional[Decimal] = None,
    alert_thresholds: Optional[list[float]] = None,
    actor: Optional[str] = None,
) -> dict[str, Any]:
    if mode is not None and mode not in MODES:
        raise CreditsError(f"Modo inválido: {mode}")
    if overdraft_limit_credits is not None and overdraft_limit_credits < 0:
        raise CreditsError("O limite de saldo negativo não pode ser negativo.")
    if alert_thresholds is not None and any(not (0 < t <= 1) for t in alert_thresholds):
        raise CreditsError("Alertas devem estar entre 0 e 1 (ex.: 0.5, 0.8, 1.0).")
    ensure_wallet(ctx.db, org_id, actor=actor, now=ctx.clock())
    patch: dict[str, Any] = {"updated_by": actor, "updated_at": ctx.clock().isoformat()}
    if mode is not None:
        patch["mode"] = mode
    if overdraft_limit_credits is not None:
        patch["overdraft_limit_credits"] = str(overdraft_limit_credits)
    if alert_thresholds is not None:
        patch["alert_thresholds"] = sorted(set(alert_thresholds))
    ctx.db.table(WALLETS).update(patch).eq("org_id", org_id).execute()
    wallet = get_wallet(ctx.db, org_id)
    if wallet is None:
        raise RuntimeError(f"credits: wallet for org {org_id} vanished after update")
    return wallet


# ── alerts ──────────────────────────────────────────────────────────────


def _org_admin_ids(db: Any, org_id: str) -> list[str]:
    rows = (
        db.table("org_memberships").select("user_id, org_role")
        .eq("org_id", org_id).eq("status", "active").execute().data or []
    )
    return [str(r["user_id"]) for r in rows if r.get("org_role") in _ORG_ALERT_ROLES]


def _platform_admin_ids(db: Any) -> list[str]:
    rows = db.table("noctus_users").select("id").eq("role", "admin").execute().data or []
    return [str(r["id"]) for r in rows]


def notify_threshold(db: Any, org_id: str, threshold: Decimal, balance: Optional[Decimal]) -> int:
    """In-app alert: org owners/admins (their org) + platform admins (no org scope)."""
    pct = int(round(float(threshold) * 100))
    title = f"Créditos de IA: {pct}% consumidos"
    message = (
        "O saldo de créditos de IA da organização acabou — chamadas de IA estão bloqueadas até uma recarga."
        if pct >= 100 else
        f"A organização já consumiu {pct}% dos créditos de IA da última recarga."
    )
    meta = {"link": "/creditos", "threshold": float(threshold),
            "balance_credits": None if balance is None else float(balance), "org_id": org_id}
    sent = write_in_app(db, user_ids=_org_admin_ids(db, org_id), kind=ALERT_KIND, title=title,
                        message=message, metadata=meta, org_id=org_id)
    sent += write_in_app(db, user_ids=_platform_admin_ids(db), kind=ALERT_KIND,
                         title=f"[org {org_id[:8]}] {title}", message=message,
                         metadata={**meta, "link": "/admin/creditos"})
    return sent


def apply(ctx: BillingContext, entry: CreditEntryInput) -> ApplyResult:
    """The one way credits move. Alerts ride on the result of the same txn."""
    result = ctx.credits().apply(entry)
    if result.status == "applied" and result.alert_threshold is not None:
        try:
            notify_threshold(ctx.db, entry.org_id, result.alert_threshold, result.balance_credits)
        except Exception as exc:  # noqa: BLE001 — the movement is committed; the alert is best-effort but loud
            logger.error(
                "credits: %s%% alert for org %s could not be delivered: %s",
                int(float(result.alert_threshold) * 100), entry.org_id, exc,
            )
    return result


# ── admin movements ─────────────────────────────────────────────────────


def grant(
    ctx: BillingContext,
    org_id: str,
    *,
    reason: str,
    actor: str,
    credits: Optional[Decimal] = None,
    usd: Optional[Decimal] = None,
) -> dict[str, Any]:
    """Owner grants an org credits (stated in credits OR USD). Same ledger path as a
    paid purchase — `kind='grant'`, `source='admin_grant'` — so the wallet, the debit
    and the alerts behave exactly as if the org had paid."""
    if (credits is None) == (usd is None):
        raise CreditsError("Informe o valor em créditos OU em US$ (um dos dois).")
    if not reason or not reason.strip():
        raise CreditsError("Informe o motivo da concessão.")
    pricing = load_pricing(ctx.db, at=ctx.clock())
    fx_rate: Optional[Decimal] = None
    if usd is not None:
        if usd <= 0:
            raise CreditsError("O valor em US$ deve ser positivo.")
        conversion = fx_service.conversion_for(ctx.db, ctx.fx, "USD", ctx.clock().date())
        if conversion.pending or conversion.fx_rate is None:
            raise CreditsError("Sem cotação PTAX disponível agora — conceda em créditos.", status_code=409)
        fx_rate = conversion.fx_rate
        credits = credits_for_usd_grant(usd, fx_rate, pricing)
    assert credits is not None
    if credits <= 0:
        raise CreditsError("A quantidade de créditos deve ser positiva.")
    ensure_wallet(ctx.db, org_id, actor=actor, now=ctx.clock())
    result = apply(ctx, CreditEntryInput(
        org_id=org_id, kind="grant", credits=credits, source="admin_grant",
        brl_amount=brl_for_credits(credits, pricing), usd_amount=usd, fx_rate=fx_rate,
        pricing_version=pricing.version, reason=reason.strip(), created_by=actor,
        detail={"granted_in": "usd" if usd is not None else "credits"},
    ))
    return {"status": result.status, "entry_id": result.entry_id, "credits": float(credits),
            "balance_credits": None if result.balance_credits is None else float(result.balance_credits)}


def adjust(ctx: BillingContext, org_id: str, *, credits: Decimal, reason: str, actor: str) -> dict[str, Any]:
    """A signed correction (credits ≠ 0). Does not open a new alert cycle."""
    if credits == 0:
        raise CreditsError("O ajuste não pode ser zero.")
    if not reason or not reason.strip():
        raise CreditsError("Informe o motivo do ajuste.")
    pricing = load_pricing(ctx.db, at=ctx.clock())
    ensure_wallet(ctx.db, org_id, actor=actor, now=ctx.clock())
    result = apply(ctx, CreditEntryInput(
        org_id=org_id, kind="adjustment", credits=credits, source="admin_adjustment",
        brl_amount=brl_for_credits(credits, pricing), pricing_version=pricing.version,
        reason=reason.strip(), created_by=actor,
    ))
    return {"status": result.status, "entry_id": result.entry_id,
            "balance_credits": None if result.balance_credits is None else float(result.balance_credits)}


__all__ = [
    "ALERT_KIND",
    "CreditsError",
    "MODES",
    "adjust",
    "apply",
    "ensure_wallet",
    "get_wallet",
    "grant",
    "notify_threshold",
    "update_settings",
    "wallet_view",
]
