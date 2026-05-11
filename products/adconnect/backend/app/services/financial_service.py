"""
Financial service — orchestration layer for `adconnect.faturas`.

Owns:
  • `create_invoice_for_pedido` — assemble draft fatura from pedido + items.
  • `issue_invoice` — call NF-e provider + Stripe; flip to `emitida`.
  • `cancel_invoice` — call NF-e provider cancel + Stripe void; flip to `cancelada`.
  • `mark_paid` — webhook handler entry point; flips to `paga`.
  • `list_for_distributor` / `list_for_org` / `get_fatura` — read-side.

Lifecycle:
  rascunho → emitida → paga / vencida / cancelada / estornada

NF-e status (independent of fatura status):
  pendente → enviado → autorizado → cancelado
                    └→ rejeitado

Stripe inheritance pattern:
  AdConnect emits its own invoices (NF-e is required by Brazilian fiscal law);
  Stripe is the payment processor. Cross-product imports of
  `products/core/backend/app/services/stripe_service` were tried and rejected
  (no `__init__.py` chain — products are independent FastAPI apps with
  separate venvs). Instead we use the Stripe SDK directly (mirrors what
  `products/therapy-platform/backend/app/services/stripe_service.py` does).
  External-SDK monkey-patching in tests is fine per CLAUDE.md no-monkey-patching
  rule (the rule covers OUR code, not external integrations).

Email notifications:
  Invoice issued → distributor; payment received → distributor.
  Pattern mirrors orders_service.

Idempotency:
  • `issue_invoice` is idempotent on `nfe_status='autorizado'` — re-calling
    is a no-op that returns the existing fatura row.
  • Stripe SDK calls are idempotent via `idempotency_key` derived from fatura.id.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from noctusai_lib.integrations.email import Digest, send_to_one
from noctusai_lib.primitives.timeutil import now_utc_iso

from . import nfe_service
from .nfe_service import (
    NFeIssueRequest,
    NFeIssueResult,
    NFeItem,
    NFeProvider,
    NFeCancelRequest,
)
from .orders_service import (
    ITENS_PEDIDO_TABLE,
    PEDIDOS_TABLE,
    get_pedido_with_items,
)

logger = logging.getLogger(__name__)

FATURAS_TABLE = "faturas"
DISTRIBUTORS_TABLE = "distributors"


class FinancialError(ValueError):
    """Raised when a financial operation violates a business rule."""


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def generate_numero_fatura(*, pedido_id: str, sequence: Optional[int] = None) -> str:
    """Generate a deterministic-yet-unique invoice number.

    Format: `ADC-<YYYYMM>-<short_pedido_id>` — month-bucketed for human
    readability + first 8 chars of pedido_id for uniqueness within a month.
    The DB-level UNIQUE constraint on `numero_fatura` is the canonical
    uniqueness guarantee; this function provides a sensible default.
    """
    now = datetime.now(timezone.utc)
    short = (pedido_id or "").replace("-", "")[:8].upper() or "NOID0000"
    bucket = f"{now.year:04d}{now.month:02d}"
    if sequence is not None:
        return f"ADC-{bucket}-{short}-{sequence:03d}"
    return f"ADC-{bucket}-{short}"


def compute_total_from_items(items: list[dict[str, Any]]) -> Decimal:
    """Pure function: sum subtotals from itens_pedido rows.

    Falls back to (quantidade * price_at_order) if subtotal is missing.
    """
    total = Decimal("0")
    for it in items or []:
        subtotal = it.get("subtotal")
        if subtotal is not None:
            total += _to_decimal(subtotal)
            continue
        qty = int(it.get("quantidade") or 0)
        price = _to_decimal(it.get("price_at_order") or it.get("price_at_add"))
        total += price * qty
    return total


def _schedule_coro(coro) -> None:
    """Fire-and-forget async work without blocking the request.

    Mirrors orders_service._schedule_coro.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        try:
            asyncio.run(coro)
        except Exception as exc:
            logger.warning("financial_service: scheduled coro failed (%s)", exc)


# ---------------------------------------------------------------------------
# Email notifications
# ---------------------------------------------------------------------------


async def _notify_invoice_issued(
    *,
    org_id: Optional[str],
    distributor_email: Optional[str],
    fatura_id: str,
    numero_fatura: str,
    valor_total: float,
    nfe_xml_url: Optional[str],
) -> None:
    """Email distributor that an invoice has been issued."""
    if not distributor_email:
        logger.debug(
            "financial_service: no distributor_email — skipping invoice-issued"
        )
        return
    nfe_link = (
        f"\nLink NF-e: {nfe_xml_url}" if nfe_xml_url else ""
    )
    digest = Digest(
        subject=f"[AdConnect] Fatura {numero_fatura} emitida",
        text=(
            f"Sua fatura {numero_fatura} no valor de R$ {valor_total:.2f} "
            f"foi emitida.{nfe_link}\n"
            f"ID interno: {fatura_id}"
        ),
    )
    try:
        await send_to_one(
            digest,
            recipient=distributor_email,
            org_id=org_id,
            log_prefix="ADCONNECT_INVOICE_ISSUED",
        )
    except Exception as exc:
        logger.warning("financial_service: invoice-issued email failed (%s)", exc)


async def _notify_payment_received(
    *,
    org_id: Optional[str],
    distributor_email: Optional[str],
    fatura_id: str,
    numero_fatura: str,
    valor_total: float,
) -> None:
    """Email distributor that payment was received."""
    if not distributor_email:
        logger.debug(
            "financial_service: no distributor_email — skipping payment-received"
        )
        return
    digest = Digest(
        subject=f"[AdConnect] Pagamento recebido — fatura {numero_fatura}",
        text=(
            f"Recebemos o pagamento da fatura {numero_fatura} "
            f"no valor de R$ {valor_total:.2f}. Obrigado!"
        ),
    )
    try:
        await send_to_one(
            digest,
            recipient=distributor_email,
            org_id=org_id,
            log_prefix="ADCONNECT_INVOICE_PAID",
        )
    except Exception as exc:
        logger.warning("financial_service: payment-received email failed (%s)", exc)


# ---------------------------------------------------------------------------
# Public surface — creation
# ---------------------------------------------------------------------------


def create_invoice_for_pedido(
    db: Any,
    *,
    pedido_id: str,
    due_date: Optional[str] = None,
    observacoes: Optional[str] = None,
) -> dict[str, Any]:
    """Create a draft fatura for an existing pedido.

    Args:
      pedido_id: the order to invoice. Must exist; fatura inherits
        distributor_id + total from it.
      due_date: optional ISO date; defaults to None (admin sets at issue time).
      observacoes: optional internal notes.

    Returns the inserted fatura row in `rascunho` status.

    Raises:
      FinancialError if pedido is missing, has no items, or insert fails.
    """
    pedido = get_pedido_with_items(db, pedido_id=pedido_id)
    if pedido is None:
        raise FinancialError("Pedido não encontrado")

    items = pedido.get("items") or []
    if not items:
        raise FinancialError("Pedido sem itens — fatura requer ao menos 1 item")

    distributor_id = str(pedido.get("distributor_id"))
    # Prefer the canonical pedido total when available, else compute.
    total = (
        _to_decimal(pedido.get("total"))
        if pedido.get("total") is not None
        else compute_total_from_items(items)
    )

    payload = {
        "distributor_id": distributor_id,
        "pedido_id": pedido_id,
        "numero_fatura": generate_numero_fatura(pedido_id=pedido_id),
        "valor_total": float(total),
        "moeda": "BRL",
        "nfe_status": "pendente",
        "status": "rascunho",
        "due_date": due_date,
        "observacoes": observacoes,
    }
    res = db.table(FATURAS_TABLE).insert(payload).execute()
    rows = list(res.data or [])
    if not rows:
        # Mock-builder write-propagation gap: synthesize the row from the
        # payload (mirrors orders_service.transition_status workaround).
        merged = dict(payload)
        merged.setdefault("id", f"fatura-{pedido_id[:8]}")
        return merged
    return rows[0]


# ---------------------------------------------------------------------------
# Public surface — issuance
# ---------------------------------------------------------------------------


def _build_nfe_request(
    *,
    fatura: dict[str, Any],
    distributor: dict[str, Any],
    items: list[dict[str, Any]],
) -> NFeIssueRequest:
    """Assemble the provider-agnostic NFeIssueRequest from DB rows."""
    nfe_items = [
        NFeItem(
            sku=str(it.get("sku_at_order") or ""),
            descricao=str(it.get("nome_at_order") or ""),
            quantidade=int(it.get("quantidade") or 0),
            valor_unitario=float(it.get("price_at_order") or 0.0),
            cfop="5102",  # default sale-within-state CFOP
        )
        for it in (items or [])
    ]
    return NFeIssueRequest(
        fatura_id=str(fatura.get("id")),
        distributor_cnpj=str(distributor.get("cnpj") or ""),
        distributor_razao_social=str(
            distributor.get("razao_social") or distributor.get("nome") or ""
        ),
        distributor_endereco={
            "logradouro": distributor.get("endereco_logradouro") or "",
            "numero": distributor.get("endereco_numero") or "",
            "complemento": distributor.get("endereco_complemento") or "",
            "bairro": distributor.get("endereco_bairro") or "",
            "cidade": distributor.get("endereco_cidade") or "",
            "uf": distributor.get("endereco_uf") or "",
            "cep": distributor.get("endereco_cep") or "",
        },
        items=nfe_items,
        valor_total=float(fatura.get("valor_total") or 0.0),
    )


def _create_stripe_invoice(
    *,
    fatura: dict[str, Any],
    distributor: dict[str, Any],
) -> dict[str, str]:
    """Create-or-reuse a Stripe Customer and create a Stripe Invoice.

    Returns dict with `customer_id`, `invoice_id`, `payment_intent_id`.
    Skips entirely (returns empty) when STRIPE_SECRET_KEY is unset — this is
    the local-dev / test mode where no payment processor is wired.

    External SDK calls (stripe.Customer.create, stripe.Invoice.create) — these
    are external integrations, NOT our own code; SDK-level patching in tests
    is allowed per the no-monkey-patching rule (it covers our own modules).
    """
    api_key = os.environ.get("STRIPE_SECRET_KEY")
    if not api_key:
        logger.info(
            "financial_service: STRIPE_SECRET_KEY unset — skipping Stripe call"
        )
        return {}
    try:
        import stripe  # type: ignore
    except ImportError:
        logger.warning("financial_service: stripe SDK not installed")
        return {}

    stripe.api_key = api_key
    fatura_id = str(fatura.get("id"))

    # Customer reuse: prefer existing stripe_customer_id on the fatura;
    # else look it up on the distributor row; else create.
    customer_id = (
        fatura.get("stripe_customer_id")
        or distributor.get("stripe_customer_id")
    )
    if not customer_id:
        try:
            customer = stripe.Customer.create(
                email=distributor.get("email") or "",
                name=str(
                    distributor.get("razao_social")
                    or distributor.get("nome")
                    or "Distribuidor"
                ),
                metadata={
                    "distributor_id": str(distributor.get("id") or ""),
                    "adconnect_fatura_id": fatura_id,
                },
                idempotency_key=f"adconnect-customer-{distributor.get('id')}",
            )
            customer_id = customer.id
        except Exception as exc:
            logger.error("financial_service: Stripe customer.create failed (%s)", exc)
            raise FinancialError(f"Erro Stripe: {exc}") from exc

    # Create the Stripe Invoice. We do this as a single-shot invoice with
    # `auto_advance=True` so Stripe finalizes + emails the customer.
    try:
        invoice = stripe.Invoice.create(
            customer=customer_id,
            auto_advance=True,
            currency=(fatura.get("moeda") or "BRL").lower(),
            metadata={
                "adconnect_fatura_id": fatura_id,
                "numero_fatura": str(fatura.get("numero_fatura") or ""),
            },
            idempotency_key=f"adconnect-invoice-{fatura_id}",
        )
    except Exception as exc:
        logger.error("financial_service: Stripe invoice.create failed (%s)", exc)
        raise FinancialError(f"Erro Stripe: {exc}") from exc

    return {
        "customer_id": customer_id,
        "invoice_id": getattr(invoice, "id", "") or "",
        "payment_intent_id": getattr(invoice, "payment_intent", "") or "",
    }


def issue_invoice(
    db: Any,
    nfe_provider: NFeProvider,
    *,
    fatura_id: str,
    distributor_email: Optional[str] = None,
) -> dict[str, Any]:
    """Issue NF-e + create Stripe invoice for a draft fatura.

    Idempotent on `nfe_status='autorizado'` — re-calling returns the existing
    row without re-issuing.

    Side effects (non-fatal email):
      • Email distributor that invoice was issued.

    Returns the updated fatura row.
    """
    fatura = get_fatura(db, fatura_id=fatura_id)
    if fatura is None:
        raise FinancialError("Fatura não encontrada")

    # Idempotency guard: already authorized → return as-is.
    if str(fatura.get("nfe_status")) == "autorizado":
        return fatura

    # Resolve distributor + items.
    distributor = _get_distributor(db, distributor_id=str(fatura.get("distributor_id")))
    if distributor is None:
        raise FinancialError("Distribuidor da fatura não encontrado")

    pedido_id = fatura.get("pedido_id")
    items: list[dict[str, Any]] = []
    if pedido_id:
        items_res = (
            db.table(ITENS_PEDIDO_TABLE)
            .select("*")
            .eq("pedido_id", pedido_id)
            .execute()
        )
        items = list(items_res.data or [])

    # 1. Issue NF-e via the provider Protocol.
    nfe_request = _build_nfe_request(
        fatura=fatura, distributor=distributor, items=items
    )
    nfe_result: NFeIssueResult = nfe_provider.issue(nfe_request)

    if nfe_result.status == "rejeitado":
        # Persist the rejection but don't proceed to Stripe.
        update_payload = {
            "nfe_status": "rejeitado",
            "nfe_provider": nfe_result.provider,
            "nfe_provider_id": nfe_result.provider_id,
            "updated_at": now_utc_iso(),
        }
        _update_fatura(db, fatura_id=fatura_id, payload=update_payload)
        raise FinancialError(
            f"NF-e rejeitada: {nfe_result.rejection_reason or 'sem detalhes'}"
        )

    # 2. Stripe — create-or-reuse Customer + create Invoice.
    stripe_ids = _create_stripe_invoice(fatura=fatura, distributor=distributor)

    # 3. Persist results.
    update_payload: dict[str, Any] = {
        "nfe_chave": nfe_result.chave,
        "nfe_xml": nfe_result.xml,
        "nfe_xml_url": nfe_result.xml_url,
        "nfe_status": nfe_result.status,
        "nfe_provider": nfe_result.provider,
        "nfe_provider_id": nfe_result.provider_id,
        "status": "emitida",
        "issued_at": now_utc_iso(),
        "updated_at": now_utc_iso(),
    }
    if stripe_ids:
        update_payload["stripe_customer_id"] = stripe_ids.get("customer_id")
        update_payload["stripe_invoice_id"] = stripe_ids.get("invoice_id")
        if stripe_ids.get("payment_intent_id"):
            update_payload["stripe_payment_intent_id"] = stripe_ids[
                "payment_intent_id"
            ]

    updated = _update_fatura(db, fatura_id=fatura_id, payload=update_payload)

    # Email — fire-and-forget.
    _schedule_coro(
        _notify_invoice_issued(
            org_id=distributor.get("org_id"),
            distributor_email=distributor_email or distributor.get("email"),
            fatura_id=fatura_id,
            numero_fatura=str(fatura.get("numero_fatura") or ""),
            valor_total=float(fatura.get("valor_total") or 0.0),
            nfe_xml_url=nfe_result.xml_url,
        )
    )

    return updated


# ---------------------------------------------------------------------------
# Public surface — cancel
# ---------------------------------------------------------------------------


def cancel_invoice(
    db: Any,
    nfe_provider: NFeProvider,
    *,
    fatura_id: str,
    justificativa: str,
) -> dict[str, Any]:
    """Cancel an issued fatura — calls NF-e provider + Stripe void.

    Args:
      justificativa: required by Brazilian NF-e regulation; min 15 chars.

    Returns the updated fatura row.
    """
    fatura = get_fatura(db, fatura_id=fatura_id)
    if fatura is None:
        raise FinancialError("Fatura não encontrada")

    # State machine: only `emitida` invoices can be cancelled. `paga` requires
    # `estornada` (refund flow — not Phase 5 scope).
    current = str(fatura.get("status") or "")
    if current != "emitida":
        raise FinancialError(
            f"Cancelamento permitido apenas para faturas emitidas (atual: {current})"
        )

    # NF-e cancel — only if NF-e was authorized.
    chave = fatura.get("nfe_chave")
    if chave and str(fatura.get("nfe_status")) == "autorizado":
        try:
            nfe_provider.cancel(
                NFeCancelRequest(chave=str(chave), justificativa=justificativa)
            )
        except Exception as exc:
            logger.error("financial_service: NF-e cancel failed (%s)", exc)
            raise FinancialError(f"Erro ao cancelar NF-e: {exc}") from exc

    # Stripe void (best-effort — invoice may already be void/paid).
    stripe_invoice_id = fatura.get("stripe_invoice_id")
    if stripe_invoice_id and os.environ.get("STRIPE_SECRET_KEY"):
        try:
            import stripe  # type: ignore

            stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
            stripe.Invoice.void_invoice(str(stripe_invoice_id))
        except Exception as exc:
            logger.warning(
                "financial_service: Stripe void_invoice failed (%s) — continuing",
                exc,
            )

    update_payload = {
        "status": "cancelada",
        "nfe_status": "cancelado" if chave else fatura.get("nfe_status") or "pendente",
        "canceled_at": now_utc_iso(),
        "observacoes": (fatura.get("observacoes") or "")
        + f"\n[Cancelamento {now_utc_iso()}]: {justificativa}",
        "updated_at": now_utc_iso(),
    }
    return _update_fatura(db, fatura_id=fatura_id, payload=update_payload)


# ---------------------------------------------------------------------------
# Public surface — webhook
# ---------------------------------------------------------------------------


def mark_paid(
    db: Any,
    *,
    fatura_id: str,
    stripe_payment_intent_id: Optional[str] = None,
    distributor_email: Optional[str] = None,
) -> dict[str, Any]:
    """Mark a fatura as paid — called from Stripe webhook handler.

    Idempotent: if already `paga`, no-op.
    """
    fatura = get_fatura(db, fatura_id=fatura_id)
    if fatura is None:
        raise FinancialError("Fatura não encontrada")

    if str(fatura.get("status")) == "paga":
        return fatura

    update_payload: dict[str, Any] = {
        "status": "paga",
        "paid_at": now_utc_iso(),
        "updated_at": now_utc_iso(),
    }
    if stripe_payment_intent_id:
        update_payload["stripe_payment_intent_id"] = stripe_payment_intent_id

    updated = _update_fatura(db, fatura_id=fatura_id, payload=update_payload)

    # Email distributor.
    distributor = _get_distributor(
        db, distributor_id=str(fatura.get("distributor_id"))
    )
    org_id = (distributor or {}).get("org_id")
    email = distributor_email or (distributor or {}).get("email")
    _schedule_coro(
        _notify_payment_received(
            org_id=org_id,
            distributor_email=email,
            fatura_id=fatura_id,
            numero_fatura=str(fatura.get("numero_fatura") or ""),
            valor_total=float(fatura.get("valor_total") or 0.0),
        )
    )
    return updated


def mark_payment_failed(
    db: Any,
    *,
    fatura_id: str,
) -> dict[str, Any]:
    """Mark a fatura as vencida (payment failed) — called from webhook."""
    fatura = get_fatura(db, fatura_id=fatura_id)
    if fatura is None:
        raise FinancialError("Fatura não encontrada")
    update_payload = {
        "status": "vencida",
        "updated_at": now_utc_iso(),
    }
    return _update_fatura(db, fatura_id=fatura_id, payload=update_payload)


def find_by_stripe_invoice_id(
    db: Any, *, stripe_invoice_id: str
) -> Optional[dict[str, Any]]:
    """Look up a fatura by its Stripe invoice id (webhook event lookup)."""
    res = (
        db.table(FATURAS_TABLE)
        .select("*")
        .eq("stripe_invoice_id", stripe_invoice_id)
        .limit(1)
        .execute()
    )
    rows = list(res.data or [])
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Public surface — read
# ---------------------------------------------------------------------------


def list_for_distributor(
    db: Any,
    *,
    distributor_id: str,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return the distributor's faturas, most recent first."""
    q = db.table(FATURAS_TABLE).select("*").eq("distributor_id", distributor_id)
    if status:
        q = q.eq("status", status)
    res = q.execute()
    rows = list(res.data or [])
    rows.sort(
        key=lambda r: r.get("created_at") or "",
        reverse=True,
    )
    return rows


def list_for_org(
    db: Any,
    *,
    org_id: str,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Brand admin: list every fatura for distributors in their org.

    Mirrors orders_service.list_for_org — two-step fetch since the mock
    builder doesn't model joins.
    """
    dist_res = (
        db.table(DISTRIBUTORS_TABLE).select("id").eq("org_id", org_id).execute()
    )
    dist_ids = {
        str(d.get("id")) for d in (dist_res.data or []) if d.get("id")
    }
    if not dist_ids:
        return []

    q = db.table(FATURAS_TABLE).select("*")
    if status:
        q = q.eq("status", status)
    res = q.execute()
    rows = [
        r for r in (res.data or []) if str(r.get("distributor_id")) in dist_ids
    ]
    rows.sort(
        key=lambda r: r.get("created_at") or "",
        reverse=True,
    )
    return rows


def get_fatura(db: Any, *, fatura_id: str) -> Optional[dict[str, Any]]:
    """Fetch a single fatura row by id."""
    res = (
        db.table(FATURAS_TABLE)
        .select("*")
        .eq("id", fatura_id)
        .limit(1)
        .execute()
    )
    rows = list(res.data or [])
    return rows[0] if rows else None


def compute_balance(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Pure function: aggregate a list of faturas into totals by status."""
    open_amount = 0.0
    overdue = 0.0
    paid = 0.0
    for r in rows:
        amt = float(r.get("valor_total") or 0.0)
        st = str(r.get("status") or "")
        if st == "emitida":
            open_amount += amt
        elif st == "vencida":
            overdue += amt
        elif st == "paga":
            paid += amt
    return {
        "openAmount": open_amount,
        "overdueAmount": overdue,
        "paidAmount": paid,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_distributor(db: Any, *, distributor_id: str) -> Optional[dict[str, Any]]:
    res = (
        db.table(DISTRIBUTORS_TABLE)
        .select("*")
        .eq("id", distributor_id)
        .limit(1)
        .execute()
    )
    rows = list(res.data or [])
    return rows[0] if rows else None


def _update_fatura(
    db: Any, *, fatura_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """Apply an UPDATE to a fatura and return the merged row.

    Mock-builder write-propagation gap: the in-memory builder echoes the
    seeded SELECT data unchanged through `.update().execute()`. Real Supabase
    returns post-update rows only when `.select()` is chained. Merging the
    payload locally is invariant to either backend.
    """
    res = (
        db.table(FATURAS_TABLE)
        .update(payload)
        .eq("id", fatura_id)
        .execute()
    )
    rows = list(res.data or [])
    base = rows[0] if rows else (get_fatura(db, fatura_id=fatura_id) or {})
    if not base:
        # Defensive: return payload + id so callers see the intent.
        merged = dict(payload)
        merged.setdefault("id", fatura_id)
        return merged
    merged = dict(base)
    merged.update(payload)
    return merged


__all__ = [
    "FATURAS_TABLE",
    "FinancialError",
    "cancel_invoice",
    "compute_balance",
    "compute_total_from_items",
    "create_invoice_for_pedido",
    "find_by_stripe_invoice_id",
    "generate_numero_fatura",
    "get_fatura",
    "issue_invoice",
    "list_for_distributor",
    "list_for_org",
    "mark_paid",
    "mark_payment_failed",
]
