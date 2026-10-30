"""The central AI-usage ledger — ``public.ai_usage`` (roadmap D25, core migration 090).

ONE append-only table for every LLM call of every product: attributed (org →
product → feature → user / conversation / agent), priced at WRITE time from
the effective model catalog (`usage.price_usage`, `price_version` recorded),
and converted to BRL at the latest stored BCB PTAX (`public.fx_rates`, written
by core's `core_ptax_daily` job). It is the foundation per-org → per-product
billing reads; the prepaid credit wallet (next slice) fills the reserved
``charged_credits`` column — the migration's trigger allows exactly that one
NULL → value write and refuses every other UPDATE / DELETE.

Wiring is by construction: ``noctusai_seed.app.create_product_app`` installs
`CentralUsageSink` for every product (core included), so no product registers
a schema anywhere — the hand-kept ``_PRODUCT_SCHEMAS`` maps this replaces are
gone.

Seam shape (KB § PATTERNS/backend/seed-fake-real-adapter.md): the sink
protocol is `usage.UsageSink`; Fake = `usage.InMemoryUsageSink`; Real =
`CentralUsageSink`; factory = `make_central_usage_sink` (refuses Real under
pytest unless ``force_real=True`` — the `make_audit_sink` precedent).

LGPD: counts, identifiers and prices only — never prompt / response text.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
import uuid
from typing import Any, Callable, Optional

import anyio.to_thread

from .usage import UsageEvent

logger = logging.getLogger(__name__)

__all__ = [
    "AI_USAGE_TABLE",
    "CentralUsageSink",
    "FanOutUsageSink",
    "FxQuote",
    "build_ai_usage_row",
    "make_central_usage_sink",
]

AI_USAGE_TABLE = "ai_usage"
FX_TABLE = "fx_rates"
FX_PAIR = "USD/BRL"
UNATTRIBUTED_PRODUCT = "unattributed"
_DEFAULT_ENV_USD_TO_BRL = 5.0
_TEXT_CAP = 200


class FxQuote:
    """The USD→BRL rate a row was converted at, and where it came from."""

    __slots__ = ("rate", "source", "quote_date")

    def __init__(self, rate: float, source: str, quote_date: Optional[str] = None) -> None:
        self.rate = rate
        self.source = source  # "ptax" | "env_fallback"
        self.quote_date = quote_date


def _uuid_or_none(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


def _cap(value: Optional[str]) -> Optional[str]:
    return value[:_TEXT_CAP] if isinstance(value, str) else value


def build_ai_usage_row(event: UsageEvent, fx: FxQuote) -> dict[str, Any]:
    """`UsageEvent` → one ``public.ai_usage`` row (pure; unit-tested).

    A non-uuid ``org_id`` / ``user_id`` (a legacy caller passing a slug) is
    kept in ``extra`` instead of failing the insert — the row is the billing
    record and must land.
    """
    extra: dict[str, Any] = dict(event.extra or {})
    org_id = _uuid_or_none(event.org_id)
    if event.org_id and org_id is None:
        extra["org_ref"] = str(event.org_id)[:_TEXT_CAP]
    user_id = _uuid_or_none(event.user_id)
    if event.user_id and user_id is None:
        extra["user_ref"] = str(event.user_id)[:_TEXT_CAP]
    if fx.source != "ptax":
        extra["fx_source"] = fx.source
        extra["fx_warning"] = "no stored PTAX bulletin readable; converted at LLM_USD_TO_BRL"
    elif fx.quote_date:
        extra["fx_quote_date"] = fx.quote_date
    if event.price_version == "unpriced":
        extra["unpriced"] = True
    cost_usd = round(float(event.cost_estimate_usd or 0.0), 8)
    return {
        "created_at": event.at.isoformat(),
        "org_id": org_id,
        "product": _cap(event.product) or UNATTRIBUTED_PRODUCT,
        "feature": _cap(event.feature),
        "purpose": _cap(event.purpose),
        "user_id": user_id,
        "conversation_id": _cap(event.conversation_id),
        "agent_key": _cap(event.agent_key),
        "provider": event.provider,
        "model": event.model,
        "model_version": event.model_version,
        "operation": event.operation,
        "batch": bool(event.batch),
        "input_tokens": event.prompt_tokens,
        "output_tokens": event.completion_tokens,
        "cache_read_tokens": event.cache_read_input_tokens,
        "cache_write_tokens": event.cache_creation_input_tokens,
        "image_input_tokens": event.image_input_tokens,
        "image_output_tokens": event.image_output_tokens,
        "cost_usd": cost_usd,
        "fx_rate": fx.rate,
        "cost_brl": round(cost_usd * fx.rate, 8),
        "price_version": event.price_version or "unpriced",
        "status": event.status if event.status in ("ok", "partial", "error") else "error",
        "request_id": _cap(event.request_id),
        "extra": extra,
    }


def _env_usd_to_brl() -> float:
    raw = os.environ.get("LLM_USD_TO_BRL")
    try:
        return float(raw) if raw else _DEFAULT_ENV_USD_TO_BRL
    except ValueError:
        logger.warning("llm.ledger: LLM_USD_TO_BRL=%r is not a float; using %s", raw, _DEFAULT_ENV_USD_TO_BRL)
        return _DEFAULT_ENV_USD_TO_BRL


class CentralUsageSink:
    """Real `UsageSink` — inserts one ``public.ai_usage`` row per event.

    ``core_client_factory`` returns a SERVICE-ROLE client targeting the
    ``public`` schema (``DatabaseModule.get_core_client``) — resolved per call
    (late binding), so a test patch or a client rebuild is always honoured.
    The latest PTAX is cached for ``fx_ttl_seconds`` (a bulletin lands twice a
    weekday; one read per process-hour is plenty).
    """

    def __init__(
        self,
        core_client_factory: Callable[[], Any],
        *,
        fx_ttl_seconds: float = 3600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client_factory = core_client_factory
        self._fx_ttl = fx_ttl_seconds
        self._clock = clock
        self._fx: Optional[FxQuote] = None
        self._fx_at = 0.0
        self._fx_lock = threading.Lock()

    def _read_ptax(self, db: Any) -> Optional[FxQuote]:
        rows = (
            db.table(FX_TABLE)
            .select("rate,quote_date")
            .eq("pair", FX_PAIR)
            .order("quote_date", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not rows or rows[0].get("rate") in (None, ""):
            return None
        return FxQuote(float(rows[0]["rate"]), "ptax", str(rows[0].get("quote_date") or "") or None)

    def _fx_quote(self, db: Any) -> FxQuote:
        with self._fx_lock:
            if self._fx is not None and self._clock() - self._fx_at < self._fx_ttl:
                return self._fx
        try:
            quote = self._read_ptax(db)
        except Exception as exc:
            logger.warning("llm.ledger: reading public.fx_rates failed (%s); env fallback", exc)
            quote = None
        if quote is None:
            # Not cached: the next event retries the stored bulletin.
            return FxQuote(_env_usd_to_brl(), "env_fallback")
        with self._fx_lock:
            self._fx, self._fx_at = quote, self._clock()
        return quote

    def _insert(self, event: UsageEvent) -> None:
        db = self._client_factory()
        row = build_ai_usage_row(event, self._fx_quote(db))
        db.table(AI_USAGE_TABLE).insert(row).execute()

    async def record(self, event: UsageEvent) -> None:
        try:
            await anyio.to_thread.run_sync(self._insert, event)
        except Exception as exc:
            # A lost row is lost revenue: ERROR, not WARNING. The LLM call
            # itself already succeeded and is never failed by bookkeeping.
            # NOC-REMEDIATE[ai-usage-durable-outbox]: spool + replay failed inserts — 2026-10-29
            logger.error(
                "llm.ledger: ai_usage insert failed provider=%s model=%s product=%s org=%s status=%s: %s",
                event.provider, event.model, event.product, event.org_id, event.status, exc,
            )


class FanOutUsageSink:
    """Deliver every event to several sinks (the central ledger plus, during
    the transition, a product's legacy ``<schema>.llm_usage`` sink). One
    sink failing never starves the others."""

    def __init__(self, sinks: list[Any]) -> None:
        self.sinks = [s for s in sinks if s is not None]

    async def record(self, event: UsageEvent) -> None:
        for sink in self.sinks:
            try:
                await sink.record(event)
            except Exception as exc:
                logger.error("llm.ledger: %s.record failed: %s", type(sink).__name__, exc)


def make_central_usage_sink(
    core_client_factory: Optional[Callable[[], Any]], *, force_real: bool = False
) -> Optional[CentralUsageSink]:
    """The Real sink, or ``None`` when no client factory is available or the
    process is a pytest run (a product's ``app.main`` builds its app at test
    collection time — it must never write the production ledger). Tests that
    exercise the Real sink pass ``force_real=True`` with a mock client."""
    if core_client_factory is None:
        return None
    if "pytest" in sys.modules and not force_real:
        return None
    return CentralUsageSink(core_client_factory)
