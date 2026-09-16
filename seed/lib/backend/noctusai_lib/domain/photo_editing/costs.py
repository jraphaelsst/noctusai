"""Cost recording — provider usage × catalog price → ``llm_usage`` + ``cost_ledger``.

Per AI call:

1. Price the usage from the model catalog (``integrations.llm.models``)
   AT CALL TIME, and persist the dollar amount — the row is the price
   snapshot, so a later catalog change never re-prices history.
2. Write one ``llm_usage`` row (tokens incl. image tokens, model version).
3. Write one ``cost_ledger`` row: native USD, plus the PTAX venda rate of
   the latest bulletin ≤ the São Paulo call date (``integrations.fx``) and
   the BRL amount. When no bulletin is available (weekend walk-back
   exhausted, BCB unreachable) the row is ``fx_pending`` — the
   ``LLM_USD_TO_BRL`` estimate is NEVER used here — and ``fotos.fx_backfill``
   resolves it later.

A model missing from the catalog, or priced on none of the legs its usage
consumed, raises ``UnpricedModelError`` instead of recording a silent $0.

Econômico (``batch=True``): the catalog price × ``BATCH_API_DISCOUNT`` — the
provider's async Batch API bills half the real-time rate (plan §1/§3). The
discount is applied HERE, once, and the ``llm_usage`` row carries
``batch=True`` so the discounted amount is always explainable.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from noctusai_lib.domain.photo_editing.ports import PhotoEditingPorts, TokenUsage
from noctusai_lib.domain.photo_editing.types import CostLedgerRow, LlmUsageRow
from noctusai_lib.integrations.fx import FxError
from noctusai_lib.integrations.llm.models import ModelEntry, ModelKind, models_for
from noctusai_lib.integrations.llm.usage import estimate_cost_usd

logger = logging.getLogger(__name__)

CURRENCY_USD = "USD"
CURRENCY_BRL = "BRL"

CATEGORY_OPENAI_EDIT = "openai_edit"
CATEGORY_OPENAI_VISION = "openai_vision"
CATEGORY_OPENAI_TEXT = "openai_text"

#: Multiplier on the catalog price for a Batch-API call (50% off).
BATCH_API_DISCOUNT = Decimal("0.5")

_MONEY_Q = Decimal("0.000001")  # NUMERIC(14, 6)
_RATE_Q = Decimal("0.00001")  # NUMERIC(12, 5)


class UnpricedModelError(LookupError):
    """The catalog cannot price this call — a configuration error (fatal)."""

    code = "modelo_sem_preco"


def catalog_entry(provider: str, model: str, kind: ModelKind) -> ModelEntry:
    for entry in models_for(provider, kind):
        if entry.id == model:
            return entry
    raise UnpricedModelError(f"{provider}/{model} is not a {kind!r} model in the catalog")


def _require_priced(entry: ModelEntry, usage: TokenUsage) -> None:
    legs = (
        (usage.prompt_tokens, entry.cost_per_1m_input_tokens, "input"),
        (usage.completion_tokens, entry.cost_per_1m_output_tokens, "output"),
        (usage.image_input_tokens, entry.cost_per_1m_image_input_tokens, "image input"),
        (usage.image_output_tokens, entry.cost_per_1m_image_output_tokens, "image output"),
    )
    missing = [name for tokens, rate, name in legs if tokens and rate is None]
    if missing:
        raise UnpricedModelError(
            f"{entry.provider}/{entry.id} has no catalog rate for: {', '.join(missing)}"
        )


def price_usage_usd(entry: ModelEntry, usage: TokenUsage, *, batch: bool = False) -> Decimal:
    """Catalog price of ``usage`` in USD, quantized to the ledger's scale.
    ``batch=True`` applies ``BATCH_API_DISCOUNT``."""
    _require_priced(entry, usage)
    amount = estimate_cost_usd(
        provider=entry.provider,
        model=entry.id,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        image_input_tokens=usage.image_input_tokens,
        image_output_tokens=usage.image_output_tokens,
    )
    price = Decimal(repr(amount))
    if batch:
        price = price * BATCH_API_DISCOUNT
    return price.quantize(_MONEY_Q, rounding=ROUND_HALF_UP)


def build_cost_row(
    *,
    org_id: str,
    category: str,
    step: str | None,
    reference_type: str | None,
    reference_id: str | None,
    amount_native: Decimal,
    currency: str,
    fx_rate: Decimal | None = None,
    fx_quote_date: date | None = None,
) -> CostLedgerRow:
    """The ONLY constructor for a ledger row — yields exactly one of the
    three shapes the table CHECK allows (BRL native · foreign pending ·
    foreign converted)."""
    amount_native = amount_native.quantize(_MONEY_Q, rounding=ROUND_HALF_UP)
    common = dict(
        org_id=org_id,
        category=category,
        step=step,
        reference_type=reference_type,
        reference_id=reference_id,
        amount_native=amount_native,
        currency=currency,
    )
    if currency == CURRENCY_BRL:
        return CostLedgerRow(**common, fx_pending=False, amount_brl=amount_native)
    if fx_rate is None or fx_quote_date is None:
        return CostLedgerRow(**common, fx_pending=True)
    rate = fx_rate.quantize(_RATE_Q, rounding=ROUND_HALF_UP)
    return CostLedgerRow(
        **common,
        fx_pending=False,
        fx_rate=rate,
        fx_quote_date=fx_quote_date,
        amount_brl=(amount_native * rate).quantize(_MONEY_Q, rounding=ROUND_HALF_UP),
    )


def local_call_date(at: datetime, tz_name: str) -> date:
    if at.tzinfo is None:
        raise ValueError("call timestamp must be timezone-aware")
    return at.astimezone(ZoneInfo(tz_name)).date()


async def _ptax(ports: PhotoEditingPorts, day: date):
    """PTAX lookup off the event loop (the BCB adapter is sync HTTP).
    Returns ``None`` on any ``FxError`` — the caller marks the row pending."""
    try:
        return await asyncio.to_thread(ports.fx.get_ptax, day)
    except FxError as exc:
        logger.warning("photo_editing.costs.fx_pending day=%s reason=%s", day, exc)
        return None


@dataclass(frozen=True)
class RecordedCost:
    llm_usage_id: int
    cost_ledger_id: int
    amount_usd: Decimal
    fx_pending: bool


async def record_ai_cost(
    ports: PhotoEditingPorts,
    *,
    org_id: str,
    step: str,
    category: str,
    operation: str,
    kind: ModelKind,
    model: str,
    usage: TokenUsage,
    model_version: str | None = None,
    batch: bool = False,
) -> RecordedCost:
    provider = (
        ports.config.image_edit_provider if kind == "image_edit" else ports.config.llm_provider
    )
    entry = catalog_entry(provider, model, kind)
    amount = price_usage_usd(entry, usage, batch=batch)
    now = ports.clock()
    usage_id = await ports.repo.add_llm_usage(
        LlmUsageRow(
            provider=provider,
            model=model,
            operation=operation,
            cost_estimate_usd=amount,
            org_id=org_id,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            image_input_tokens=usage.image_input_tokens,
            image_output_tokens=usage.image_output_tokens,
            model_version=model_version,
            batch=batch,
            at=now,
        )
    )
    ptax = await _ptax(ports, local_call_date(now, ports.config.fx_timezone))
    row = build_cost_row(
        org_id=org_id,
        category=category,
        step=step,
        reference_type="llm_usage",
        reference_id=str(usage_id),
        amount_native=amount,
        currency=CURRENCY_USD,
        fx_rate=ptax.rate if ptax else None,
        fx_quote_date=ptax.quote_date if ptax else None,
    )
    cost_id = await ports.repo.add_cost(row)
    return RecordedCost(
        llm_usage_id=usage_id,
        cost_ledger_id=cost_id,
        amount_usd=amount,
        fx_pending=row.fx_pending,
    )


@dataclass(frozen=True)
class BackfillReport:
    resolved: int
    still_pending: int


async def backfill_fx(ports: PhotoEditingPorts, *, limit: int = 200) -> BackfillReport:
    """Resolve ``fx_pending`` ledger rows using the bulletin for each row's
    own São Paulo creation date. Idempotent."""
    resolved = 0
    pending = 0
    for row in await ports.repo.list_fx_pending(limit=limit):
        if row.id is None or row.created_at is None:
            raise ValueError("fx_pending ledger row without id/created_at")
        ptax = await _ptax(ports, local_call_date(row.created_at, ports.config.fx_timezone))
        if ptax is None:
            pending += 1
            continue
        converted = build_cost_row(
            org_id=row.org_id,
            category=row.category,
            step=row.step,
            reference_type=row.reference_type,
            reference_id=row.reference_id,
            amount_native=row.amount_native,
            currency=row.currency,
            fx_rate=ptax.rate,
            fx_quote_date=ptax.quote_date,
        )
        await ports.repo.resolve_fx(
            row.id,
            fx_rate=converted.fx_rate,
            fx_quote_date=converted.fx_quote_date,
            amount_brl=converted.amount_brl,
        )
        resolved += 1
    return BackfillReport(resolved=resolved, still_pending=pending)


__all__ = [
    "BATCH_API_DISCOUNT",
    "BackfillReport",
    "CATEGORY_OPENAI_EDIT",
    "CATEGORY_OPENAI_TEXT",
    "CATEGORY_OPENAI_VISION",
    "CURRENCY_BRL",
    "CURRENCY_USD",
    "RecordedCost",
    "UnpricedModelError",
    "backfill_fx",
    "build_cost_row",
    "catalog_entry",
    "local_call_date",
    "price_usage_usd",
    "record_ai_cost",
]
