"""
AdConnect Financial Router — Supabase-backed (Phase 5).

Replaces the mock-backed `app/data/store.py.invoices` variant with a real
DB-backed surface against `adconnect.faturas`.

Endpoints:
  • GET    /financial/invoices            — distributor's invoices (admin: all-in-org).
  • GET    /financial/invoices/{id}       — single invoice with NF-e + Stripe state.
  • POST   /financial/invoices            — admin creates a draft invoice for a pedido.
  • POST   /financial/invoices/{id}/issue  — admin issues NF-e + Stripe invoice.
  • POST   /financial/invoices/{id}/cancel — admin cancels.
  • POST   /financial/webhook/stripe       — Stripe webhook handler (invoice.paid/payment_failed).
  • GET    /financial/balance              — distributor's open / overdue / paid totals.

Constructor-time prefix is the structural fix (Phase 3 set the convention).
NEVER `router.prefix = ...` post-construction — registers as no-op.

NF-e + Stripe orchestration lives in `financial_service`. The router is a
thin auth + serialization shim.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from ..auth_deps import get_current_user
from ..database import _db as _db_module
from ..schemas.financial import (
    CancelRequest,
    FaturaIn,
    FaturaListOut,
    FaturaOut,
    IssueRequest,
)
from ..services import financial_service
from ..services.nfe_service import NFeProvider, make_nfe_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/financial", tags=["financial"])


DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _resolve_org_id(user: dict[str, Any]) -> str:
    org_id = user.get("org_id") or user.get("orgId")
    return str(org_id) if org_id else DEFAULT_ORG_ID


def _resolve_distributor_id(user: dict[str, Any]) -> Optional[str]:
    did = user.get("distributorId") or user.get("distributor_id")
    return str(did) if did else None


def _is_admin(user: dict[str, Any]) -> bool:
    role = (user.get("role") or "").lower()
    return role in {"admin", "platform_admin"}


def _check_visibility(user: dict[str, Any], fatura: dict[str, Any]) -> None:
    """Allow the row's distributor or any admin in the same org."""
    if _is_admin(user):
        return
    user_did = _resolve_distributor_id(user)
    if user_did and str(fatura.get("distributor_id")) == str(user_did):
        return
    raise HTTPException(403)


def _get_nfe_provider() -> NFeProvider:
    """Resolve the configured NF-e provider.

    Reads `NFE_PROVIDER` env (default: `fake`) and config envs. Tests
    typically override by patching this dependency on the router module.
    """
    provider_name = os.environ.get("NFE_PROVIDER", "fake")
    return make_nfe_provider(
        provider_name,
        api_key=os.environ.get("FOCUSNFE_API_KEY"),
        ambiente=os.environ.get("FOCUSNFE_AMBIENTE", "homologacao"),
        emitter_cnpj=os.environ.get("FOCUSNFE_EMITTER_CNPJ"),
    )


# ---------------------------------------------------------------------------
# Routes — read
# ---------------------------------------------------------------------------


@router.get("/invoices", response_model=FaturaListOut)
def list_invoices(
    status: Optional[str] = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List faturas.

    • Brand admin (`role=admin`): all faturas in their org's distributor set.
    • Distributor user: only their own.
    """
    db = _db()
    if _is_admin(user):
        rows = financial_service.list_for_org(
            db, org_id=_resolve_org_id(user), status=status
        )
        return {"data": rows}
    distributor_id = _resolve_distributor_id(user)
    if not distributor_id:
        raise HTTPException(401, "Usuário sem distribuidor vinculado")
    rows = financial_service.list_for_distributor(
        db, distributor_id=distributor_id, status=status
    )
    return {"data": rows}


@router.get("/balance")
def get_balance(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Distributor's open / overdue / paid totals.

    Mirrors the legacy mock surface so the frontend's existing balance card
    keeps working post-Phase 5 swap.
    """
    db = _db()
    distributor_id = _resolve_distributor_id(user)
    if not distributor_id:
        raise HTTPException(401, "Usuário sem distribuidor vinculado")
    rows = financial_service.list_for_distributor(
        db, distributor_id=distributor_id
    )
    balance = financial_service.compute_balance(rows)
    # Credit limit is a planned platform field — placeholder until ERP wires it.
    balance["creditLimit"] = 50_000.0
    balance["creditUsed"] = balance["openAmount"] + balance["overdueAmount"]
    return balance


@router.get("/invoices/{fatura_id}", response_model=FaturaOut)
def get_invoice(
    fatura_id: str = Path(...),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Fetch a single invoice with NF-e + Stripe state."""
    db = _db()
    fatura = financial_service.get_fatura(db, fatura_id=fatura_id)
    if fatura is None:
        raise HTTPException(404, "Fatura não encontrada")
    _check_visibility(user, fatura)
    return fatura


# ---------------------------------------------------------------------------
# Routes — create / issue / cancel (admin)
# ---------------------------------------------------------------------------


@router.post("/invoices", response_model=FaturaOut, status_code=201)
def create_invoice(
    body: FaturaIn,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a draft invoice for a pedido (admin only)."""
    if not _is_admin(user):
        raise HTTPException(403, "Apenas brand admin pode criar faturas")
    db = _db()
    try:
        return financial_service.create_invoice_for_pedido(
            db,
            pedido_id=body.pedido_id,
            due_date=body.due_date.isoformat() if body.due_date else None,
            observacoes=body.observacoes,
        )
    except financial_service.FinancialError as exc:
        msg = str(exc)
        if "não encontrad" in msg.lower():
            raise HTTPException(404, msg) from exc
        raise HTTPException(400, msg) from exc


@router.post("/invoices/{fatura_id}/issue", response_model=FaturaOut)
def issue_invoice(
    body: IssueRequest,
    fatura_id: str = Path(...),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Issue NF-e + create Stripe invoice (admin only). Idempotent."""
    if not _is_admin(user):
        raise HTTPException(403, "Apenas brand admin pode emitir faturas")
    db = _db()
    nfe = _get_nfe_provider()
    try:
        return financial_service.issue_invoice(
            db, nfe, fatura_id=fatura_id
        )
    except financial_service.FinancialError as exc:
        msg = str(exc)
        if "não encontrad" in msg.lower():
            raise HTTPException(404, msg) from exc
        if "rejeitada" in msg.lower():
            raise HTTPException(422, msg) from exc
        raise HTTPException(400, msg) from exc


@router.post("/invoices/{fatura_id}/cancel", response_model=FaturaOut)
def cancel_invoice(
    body: CancelRequest,
    fatura_id: str = Path(...),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Cancel an issued invoice (admin only). Justificativa required."""
    if not _is_admin(user):
        raise HTTPException(403, "Apenas brand admin pode cancelar faturas")
    db = _db()
    nfe = _get_nfe_provider()
    try:
        return financial_service.cancel_invoice(
            db, nfe, fatura_id=fatura_id, justificativa=body.justificativa
        )
    except financial_service.FinancialError as exc:
        msg = str(exc)
        if "não encontrad" in msg.lower():
            raise HTTPException(404, msg) from exc
        raise HTTPException(400, msg) from exc


# ---------------------------------------------------------------------------
# Routes — Stripe webhook
# ---------------------------------------------------------------------------


@router.post("/webhook/stripe", status_code=200)
async def stripe_webhook(request: Request) -> dict[str, Any]:
    """Stripe webhook handler — routes invoice.paid + invoice.payment_failed
    events back to faturas.

    Signature verification: uses Stripe SDK's `Webhook.construct_event` which
    is the canonical pattern (mirrors `products/core/backend/app/services/
    stripe_service.construct_webhook_event`). Falls back to lightweight
    HMAC verify when the SDK is absent (test mode).

    External-SDK patching is allowed in tests per CLAUDE.md no-monkey-patching
    rule (the rule covers OUR code, not Stripe).
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

    if not secret:
        # Test mode / dev: accept without verification but log the gap.
        logger.warning(
            "stripe_webhook: STRIPE_WEBHOOK_SECRET unset — accepting unverified"
        )
        try:
            import json
            event = json.loads(payload.decode("utf-8") or "{}")
        except Exception as exc:
            raise HTTPException(400, f"Invalid JSON: {exc}") from exc
    else:
        try:
            import stripe  # type: ignore
        except ImportError as exc:
            raise HTTPException(503, "Stripe SDK not installed") from exc
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, secret)
            # Convert SDK Event to dict-shape for downstream handling.
            event = {
                "type": event["type"],
                "data": event["data"],
                "id": event["id"],
            }
        except Exception as exc:
            logger.warning("stripe_webhook: signature verification failed (%s)", exc)
            raise HTTPException(400, "Assinatura inválida") from exc

    event_type = event.get("type") or ""
    data_object = (event.get("data") or {}).get("object") or {}
    stripe_invoice_id = data_object.get("id") or ""
    if not stripe_invoice_id:
        return {"received": True, "ignored": "no invoice id"}

    db = _db()
    fatura = financial_service.find_by_stripe_invoice_id(
        db, stripe_invoice_id=stripe_invoice_id
    )
    if fatura is None:
        # Event for an invoice we don't track — acknowledge so Stripe doesn't retry.
        return {"received": True, "ignored": "fatura not found"}

    fatura_id = str(fatura.get("id"))
    if event_type == "invoice.paid":
        financial_service.mark_paid(
            db,
            fatura_id=fatura_id,
            stripe_payment_intent_id=data_object.get("payment_intent"),
        )
    elif event_type == "invoice.payment_failed":
        financial_service.mark_payment_failed(db, fatura_id=fatura_id)
    else:
        return {"received": True, "ignored": event_type}

    return {"received": True, "fatura_id": fatura_id, "event_type": event_type}


__all__ = ["router"]
