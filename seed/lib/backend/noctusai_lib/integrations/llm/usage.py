"""Token-usage accounting for the shared LLM client.

Every provider can optionally report a `UsageEvent` to an active `UsageSink`
after a successful call. The high-level entry points (`chat_completion`,
`generate_embedding`, etc.) remain unchanged — providers emit usage
themselves, keeping the public contract string/list-shaped.

Cost estimation is derived from `noctusai_lib.llm.models` — each `ModelEntry`
carries optional `cost_per_1m_input_tokens` / `cost_per_1m_output_tokens`
fields (USD). Unknown models record zero cost.

LGPD: `UsageEvent` intentionally never stores the prompt or response text,
only counts + model/provider identifiers + `org_id`. Clinical prompt content
never reaches the sink. Per-org aggregation is still a useful billing
signal without leaking patient data.
"""
from __future__ import annotations

import contextlib
import contextvars
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator, Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class UsageEvent:
    """A single LLM-call usage observation.

    - `operation`: "chat" | "embedding" | "audio" | "vision"
    - `prompt_tokens` / `completion_tokens`: reported by the provider;
      may be `None` if the provider doesn't expose them (e.g. some audio
      APIs don't return token counts).
    - `cost_estimate_usd`: computed locally from `prompt_tokens *
      cost_per_1m_input / 1e6 + completion_tokens * cost_per_1m_output / 1e6`
      (plus the image-token legs below, when present). Not a billing source
      of truth — treat as an approximation.
    - `model_version`: the provider-reported dated snapshot actually served
      (e.g. "gpt-4o-2026-08-06"), distinct from `model` (the requested
      alias, which can roll to a new snapshot server-side without the
      caller changing anything). Recording both is what lets model
      comparisons stay trustworthy over time — `model` alone silently
      conflates two different served models under one label.
    - `batch`: True when this event was recorded from the provider's async
      Batch API (discounted rate) rather than a real-time call. NOT the
      same concept as a `generate_embeddings_batch`-shaped synchronous
      multi-input call — see `models.ModelEntry.supports_batch` docstring.
    - `cache_creation_input_tokens` / `cache_read_input_tokens`: Anthropic
      prompt-caching counts (`providers.anthropic_provider` is the only
      populator today — OpenAI/Gemini callers leave both `None`). Additive
      to (never a re-use of) `prompt_tokens`, which on Anthropic's response
      is the *uncached* input-token count only. `cost_estimate_usd` already
      folds these in at Anthropic's published multipliers (1.25x input for
      a cache write, 0.1x for a cache read) via `estimate_cost_usd` — the
      raw counts here are additionally kept for analytics/debugging, same
      as `image_input_tokens`/`image_output_tokens` below. Like those two,
      no shipped `<schema>.llm_usage` table has columns for them yet, so
      `SupabaseUsageSink.record()` does not persist the raw counts — only
      the already-priced `cost_estimate_usd` reaches the DB (see that
      class's docstring for the `supports_image_columns` precedent this
      would extend if a consumer ever needs the raw per-call breakdown).
    """
    provider: str
    model: str
    operation: str
    org_id: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cache_creation_input_tokens: Optional[int] = None
    cache_read_input_tokens: Optional[int] = None
    # Image-token counts — populated by `image_edit` / multi-image vision
    # calls. Additive to (never a re-use of) `prompt_tokens`/
    # `completion_tokens` above, because `ModelEntry` prices image tokens at
    # a separate published rate from text tokens.
    image_input_tokens: Optional[int] = None
    image_output_tokens: Optional[int] = None
    cost_estimate_usd: float = 0.0
    at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    model_version: Optional[str] = None
    batch: bool = False
    # Hook for callers that want to attach a correlation id without mutating
    # the rest of the event. Opaque to the sink.
    extra: dict[str, Any] = field(default_factory=dict)
    # ── D25 central-ledger dimensions (stamped by `record_usage` from
    # `attribution.current_attribution()`; see `attribution.py`). ──
    product: Optional[str] = None
    feature: Optional[str] = None
    purpose: Optional[str] = None
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    agent_key: Optional[str] = None
    request_id: Optional[str] = None
    #: "ok" | "partial" (a stream cut short — counts may be estimated, see
    #: `extra["tokens_estimated"]`) | "error" (the provider call raised).
    status: str = "ok"
    #: Which rate card priced `cost_estimate_usd`: "catalog:<rates-hash>",
    #: "override:v<N>" (an operator `llm_model_overrides` version) or
    #: "unpriced" (no catalog row — cost 0, flagged, never silently billed).
    price_version: Optional[str] = None


class UsageSink(Protocol):
    """Where usage events get persisted. Production uses a Supabase-backed
    sink; tests use `InMemoryUsageSink`; `None` disables tracking."""

    async def record(self, event: UsageEvent) -> None: ...


class InMemoryUsageSink:
    """Dev/test sink — keeps events in a list in memory. Not thread-safe.

    Exposes `events` for assertions and `aggregate()` for a quick summary.
    Not suitable for long-lived processes or multi-worker production.
    """

    def __init__(self) -> None:
        self.events: list[UsageEvent] = []

    async def record(self, event: UsageEvent) -> None:
        self.events.append(event)

    def aggregate(self) -> dict[tuple[str, str, str], dict[str, Any]]:  # noqa: F811
        """Delegates to the module-level `aggregate` so both sinks share shape."""
        return _aggregate_events(self.events)


class SupabaseUsageSink:
    """Production sink — inserts one row per `UsageEvent` into
    `<schema>.<table>` (default `llm_usage`) on the given Supabase client.

    The client is expected to be a **service-role** client (bypasses RLS)
    since usage writes must succeed regardless of the caller's permissions.
    Reads are RLS-scoped through the `/api/llm/usage` endpoint using a
    user-scoped client.

    LGPD: this sink writes counts + provider/model identifiers + `org_id`
    only — never prompt content. See `UsageEvent` docstring.

    `supports_image_columns` — was `NOC-REMEDIATE[llm-usage-image-columns]`
    (resolved 2026-09, edicao-fotos Wave 1 W1 migrations slice):
    `image_input_tokens` / `image_output_tokens` / `model_version` / `batch`
    are computed on every `UsageEvent` (S2) but were withheld from `row`
    because most `<schema>.llm_usage` tables don't carry those columns —
    `erp-imobiliario/020_llm_usage.sql` and `therapy-platform/006_llm_usage.
    sql` are pre-existing APPLIED migrations on the narrower shape, and
    inserting unknown keys against them would fail (or, if PostgREST
    silently ignored extras, would look like it worked while dropping the
    very fields this flag exists to preserve). The canonical WIDE shape now
    ships as `noctusai_lib/integrations/llm/migrations/llm_usage.sql.
    template` (first instantiated by social-wiring's `122_llm_usage.sql`).
    Pass `supports_image_columns=True` ONLY when the product's own
    `llm_usage` table was created from that template (or an `ALTER TABLE
    ... ADD COLUMN IF NOT EXISTS` follow-up that added the same four
    columns) — default `False` keeps every existing consumer's insert shape
    byte-identical.
    """

    def __init__(
        self,
        db_client: Any,
        schema: str,
        table: str = "llm_usage",
        *,
        supports_image_columns: bool = False,
    ) -> None:
        self._db = db_client
        self._schema = schema
        self._table = table
        self._supports_image_columns = supports_image_columns

    async def record(self, event: UsageEvent) -> None:
        row = {
            "org_id": event.org_id,
            "provider": event.provider,
            "model": event.model,
            "operation": event.operation,
            "prompt_tokens": event.prompt_tokens,
            "completion_tokens": event.completion_tokens,
            "total_tokens": event.total_tokens,
            "cost_estimate_usd": event.cost_estimate_usd,
            "at": event.at.isoformat(),
        }
        if self._supports_image_columns:
            row.update({
                "image_input_tokens": event.image_input_tokens,
                "image_output_tokens": event.image_output_tokens,
                "model_version": event.model_version,
                "batch": event.batch,
            })
        try:
            # supabase-py is sync under the hood; dispatching to a thread
            # keeps the caller's event loop responsive under load.
            import asyncio

            def _insert() -> None:
                self._db.schema(self._schema).table(self._table).insert(row).execute()

            await asyncio.to_thread(_insert)
        except Exception as exc:
            logger.warning(
                "SupabaseUsageSink.record failed provider=%s model=%s op=%s org=%s: %s",
                event.provider, event.model, event.operation, event.org_id, exc,
            )


def _aggregate_events(events: list[UsageEvent]) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Group events by `(org_id, provider, model)` — shared by both sinks
    and by the `/api/llm/usage` endpoint when in-memory aggregation is
    requested instead of a DB-side `group by`."""
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for ev in events:
        key = (ev.org_id or "", ev.provider, ev.model)
        bucket = buckets.setdefault(key, {
            "org_id": ev.org_id,
            "provider": ev.provider,
            "model": ev.model,
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_estimate_usd": 0.0,
        })
        bucket["calls"] += 1
        bucket["prompt_tokens"] += ev.prompt_tokens or 0
        bucket["completion_tokens"] += ev.completion_tokens or 0
        bucket["total_tokens"] += ev.total_tokens or 0
        bucket["cost_estimate_usd"] += ev.cost_estimate_usd
    return buckets


# ── Cost calc helper ───────────────────────────────────────────────

#: Anthropic's published prompt-cache multipliers on the base per-1M INPUT
#: rate (`ModelEntry.cost_per_1m_input_tokens`) — there is no separate
#: per-model "cache rate" column in the catalog because Anthropic prices
#: caching as a multiplier of whatever the model's normal input rate is,
#: not an independently-published number. These are the 5-minute-TTL
#: (the default `CacheControlEphemeralParam` — `chat.build_cached_messages`
#: never sets `ttl`, so it always gets this tier) rates: a cache WRITE
#: costs 1.25x a normal input token, a cache READ costs 0.1x. The 1-hour
#: TTL tier (2x write / 0.1x read) is not modelled — nothing in this
#: codebase requests it yet.
_ANTHROPIC_CACHE_WRITE_MULTIPLIER = 1.25
_ANTHROPIC_CACHE_READ_MULTIPLIER = 0.1


def estimate_cost_usd(
    *,
    provider: str,
    model: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    image_input_tokens: Optional[int] = None,
    image_output_tokens: Optional[int] = None,
    cache_creation_input_tokens: Optional[int] = None,
    cache_read_input_tokens: Optional[int] = None,
) -> float:
    """Compute a cost estimate (USD) from the model catalog.

    `image_input_tokens` / `image_output_tokens` price against the model's
    dedicated image rates (`ModelEntry.cost_per_1m_image_input_tokens` /
    `..._output_tokens`) — additive to the text `prompt_tokens` /
    `completion_tokens` legs, never a substitute for them.

    `cache_creation_input_tokens` / `cache_read_input_tokens` price against
    the model's own `cost_per_1m_input_tokens` rate at Anthropic's published
    multipliers (see `_ANTHROPIC_CACHE_WRITE_MULTIPLIER` /
    `_ANTHROPIC_CACHE_READ_MULTIPLIER`) — additive to `prompt_tokens`, which
    on an Anthropic response is only the *uncached* portion of the input.
    Gated on `provider == "anthropic"`.

    Returns 0.0 when the model has no price in the catalog. A rate missing
    for just ONE leg zeroes only that leg. Never raises. `price_usage` is the
    same computation plus the rate-card version the ledger records.
    """
    return price_usage(
        provider=provider, model=model, prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens, image_input_tokens=image_input_tokens,
        image_output_tokens=image_output_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
    )[0]


_UNPRICED = "unpriced"


def _price_version_of(entry: Any) -> str:
    """Stable id of the rate card that priced `entry` — an operator override
    reports its own version; a static catalog row reports a hash of its
    rates, so a price change in `models.py` changes the recorded version."""
    import hashlib

    from .catalog_overrides import get_model_override

    override = get_model_override(entry.provider, entry.kind, entry.id)
    if override is not None and override.version:
        return f"override:v{override.version}"
    rates = (
        entry.cost_per_1m_input_tokens, entry.cost_per_1m_output_tokens,
        entry.cost_per_1m_image_input_tokens, entry.cost_per_1m_image_output_tokens,
    )
    return "catalog:" + hashlib.sha256(repr(rates).encode()).hexdigest()[:10]


def price_usage(
    *,
    provider: str,
    model: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    image_input_tokens: Optional[int] = None,
    image_output_tokens: Optional[int] = None,
    cache_creation_input_tokens: Optional[int] = None,
    cache_read_input_tokens: Optional[int] = None,
) -> tuple[float, str]:
    """``(cost_usd, price_version)`` at WRITE time from the effective catalog
    (static rows + operator overlay). ``price_version == "unpriced"`` when the
    model has no catalog row. Never raises."""
    from .models import models_for

    try:
        entry = next((m for m in models_for(provider) if m.id == model), None)
        if entry is None:
            return 0.0, _UNPRICED
        in_rate = entry.cost_per_1m_input_tokens or 0.0
        out_rate = entry.cost_per_1m_output_tokens or 0.0
        img_in_rate = entry.cost_per_1m_image_input_tokens or 0.0
        img_out_rate = entry.cost_per_1m_image_output_tokens or 0.0
        cost = (
            (prompt_tokens or 0) * in_rate
            + (completion_tokens or 0) * out_rate
            + (image_input_tokens or 0) * img_in_rate
            + (image_output_tokens or 0) * img_out_rate
        ) / 1_000_000.0
        if provider == "anthropic":
            cost += (
                (cache_creation_input_tokens or 0) * in_rate * _ANTHROPIC_CACHE_WRITE_MULTIPLIER
                + (cache_read_input_tokens or 0) * in_rate * _ANTHROPIC_CACHE_READ_MULTIPLIER
            ) / 1_000_000.0
        return cost, _price_version_of(entry)
    except Exception as exc:
        logger.warning("price_usage failed for %s/%s: %s", provider, model, exc)
        return 0.0, _UNPRICED


# ── Entry-point helper used by providers ──────────────────────────

async def record_usage(
    *,
    provider: str,
    model: str,
    operation: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    total_tokens: Optional[int],
    org_id: Optional[str] = None,
    image_input_tokens: Optional[int] = None,
    image_output_tokens: Optional[int] = None,
    cache_creation_input_tokens: Optional[int] = None,
    cache_read_input_tokens: Optional[int] = None,
    model_version: Optional[str] = None,
    batch: bool = False,
    status: str = "ok",
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """Provider-side convenience — builds a `UsageEvent`, prices it at write
    time (`price_usage`), stamps the attribution in force
    (`attribution.current_attribution()`) and dispatches to the active sink.
    Safe to call with `sink=None` (no-op). Never raises.

    `org_id` passed here wins over the attribution's org (the provider knows
    which org's key it billed). `status` is "ok" | "partial" | "error" — the
    failure paths come from `record_failed_call` / `metered_stream`.

    Imported lazily inside provider methods to avoid a circular import
    (provider → client → usage → ...).
    """
    from .attribution import current_attribution

    cost, price_version = price_usage(
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        image_input_tokens=image_input_tokens,
        image_output_tokens=image_output_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
    )
    try:
        attr = current_attribution()
    except Exception as exc:  # attribution must never cost a billable row
        logger.warning("llm.usage: attribution unavailable (%s); recording unattributed", exc)
        from .attribution import UsageAttribution

        attr = UsageAttribution()
    event = UsageEvent(
        provider=provider,
        model=model,
        operation=operation,
        org_id=org_id or attr.org_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        image_input_tokens=image_input_tokens,
        image_output_tokens=image_output_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
        cost_estimate_usd=cost,
        model_version=model_version,
        batch=batch,
        extra=dict(extra or {}),
        product=attr.product,
        feature=attr.feature,
        purpose=attr.purpose,
        user_id=attr.user_id,
        conversation_id=attr.conversation_id,
        agent_key=attr.agent_key,
        request_id=attr.request_id,
        status=status,
        price_version=price_version,
    )
    # Every active `coletar_uso()` scope sees the event too — independent of
    # whether a sink is configured (a harness or an extractor attributing
    # cost to ONE read needs the numbers even where billing is off).
    for coletor in _COLETORES.get():
        coletor.append(event)
    try:
        from .client import get_llm_config
        config = get_llm_config()
    except Exception as exc:
        logger.debug("llm.usage: get_llm_config() unavailable (%s); usage sink not invoked", exc)
        return
    sink = getattr(config, "usage_sink", None)
    if sink is None:
        return
    try:
        await sink.record(event)
    except Exception as exc:
        logger.warning("usage_sink.record failed: %s", exc)


# ── Failure / partial emission (D25: a failed or cut call is still a row) ──


async def record_failed_call(
    *, provider: str, model: str, operation: str, org_id: Optional[str], exc: BaseException
) -> None:
    """One ``status="error"`` row for a provider call that raised before it
    reported usage. Token counts stay NULL (unknown, not zero); the error
    class rides in ``extra``. Never raises."""
    try:
        await record_usage(
            provider=provider, model=model, operation=operation,
            prompt_tokens=None, completion_tokens=None, total_tokens=None,
            org_id=org_id, status="error",
            extra={"error": type(exc).__name__, "cancelled": isinstance(exc, _cancelled_types())},
        )
    except BaseException as rec_exc:  # noqa: BLE001 — must not mask the original failure
        logger.warning("llm.usage: could not record failed %s call: %s", operation, rec_exc)


def _cancelled_types() -> tuple[type[BaseException], ...]:
    import asyncio

    return (asyncio.CancelledError,)


async def metered_call(
    call: Any, *, provider: str, model: str, operation: str, org_id: Optional[str]
) -> Any:
    """Await ``call()`` (a zero-arg coroutine factory) so that a provider call
    that raises WITHOUT having recorded usage still leaves a ``status="error"``
    row. A provider that recorded before raising is not double-counted."""
    with coletar_uso() as eventos:
        try:
            return await call()
        except BaseException as exc:
            if not eventos and not _is_local_refusal(exc):
                await record_failed_call(
                    provider=provider, model=model, operation=operation, org_id=org_id, exc=exc,
                )
            raise


def _is_local_refusal(exc: BaseException) -> bool:
    """Failures raised before any request left the process (no key, a stub
    provider, an unimplemented capability, a budget refusal) are not calls —
    they never produce a ledger row."""
    from .exceptions import LLMBudgetExceeded, LLMBudgetNotConfigured, LLMNotConfigured, ProviderNotImplemented

    return isinstance(
        exc,
        (LLMNotConfigured, ProviderNotImplemented, NotImplementedError, LLMBudgetExceeded, LLMBudgetNotConfigured),
    )


def _approx_tokens(chars: int) -> int:
    """~4 chars per token — the same heuristic `chat.build_cached_messages`
    uses. Only ever applied to a cut-short stream, and always flagged."""
    return max(0, (chars + 3) // 4)


async def metered_stream(
    stream: Any,
    *,
    provider: str,
    model: str,
    org_id: Optional[str],
    prompt_chars: int,
) -> Any:
    """Wrap a provider stream (async iterator of text deltas). A stream that
    runs to completion is left alone (the provider records the reported
    counts). A stream that is cut short — consumer abort, cancellation, a
    provider error mid-stream — records ONE row: ``status="partial"`` when any
    text was delivered (output tokens estimated from the delivered chars,
    input tokens from the prompt chars, ``extra.tokens_estimated=True``), else
    ``status="error"``."""
    delivered = 0
    completed = False
    failure: Optional[BaseException] = None
    try:
        async for chunk in stream:
            delivered += len(chunk or "")
            yield chunk
        completed = True
    except BaseException as exc:
        failure = exc
        raise
    finally:
        aclose = getattr(stream, "aclose", None)
        if not completed and aclose is not None:
            try:
                await aclose()
            except BaseException as close_exc:  # noqa: BLE001
                logger.debug("llm.usage: closing a cut stream raised %s", close_exc)
        if not completed:
            reason = (
                type(failure).__name__
                if failure is not None and not isinstance(failure, GeneratorExit)
                else "consumer_closed"
            )
            try:
                if delivered:
                    pt = _approx_tokens(prompt_chars)
                    ct = _approx_tokens(delivered)
                    await record_usage(
                        provider=provider, model=model, operation="chat",
                        prompt_tokens=pt, completion_tokens=ct, total_tokens=pt + ct,
                        org_id=org_id, status="partial",
                        extra={"tokens_estimated": True, "cut_reason": reason,
                               "delivered_chars": delivered},
                    )
                else:
                    await record_usage(
                        provider=provider, model=model, operation="chat",
                        prompt_tokens=None, completion_tokens=None, total_tokens=None,
                        org_id=org_id, status="error", extra={"error": reason},
                    )
            except BaseException as rec_exc:  # noqa: BLE001
                logger.warning("llm.usage: could not record cut stream: %s", rec_exc)


def prompt_chars_of(messages: Any) -> int:
    """Total text length of an OpenAI-shaped message list (for estimates)."""
    total = 0
    for m in messages or ():
        content = m.get("content") if isinstance(m, dict) else None
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    total += len(block["text"])
    return total


# ── Scoped collection (per-read cost attribution) ─────────────────

#: The open `coletar_uso()` scopes of the CURRENT task context. A tuple of
#: lists so nesting works (an outer per-document scope and an inner per-read
#: scope both see the same event) and a copy-on-enter keeps sibling tasks
#: from seeing each other's scopes.
_COLETORES: contextvars.ContextVar[tuple[list[UsageEvent], ...]] = contextvars.ContextVar(
    "noctusai_llm_usage_coletores", default=()
)


@contextlib.contextmanager
def coletar_uso() -> Iterator[list[UsageEvent]]:
    """Collect every `UsageEvent` recorded inside this scope (this task and
    the tasks it spawns) — the per-read cost attribution an extractor needs
    to say "this read cost US$ X with model Y" without a second accounting
    path: the SAME events the configured sink receives.

        with coletar_uso() as eventos:
            await ladder.to_text(...)
        usd = sum(e.cost_estimate_usd for e in eventos)
    """
    eventos: list[UsageEvent] = []
    token = _COLETORES.set((*_COLETORES.get(), eventos))
    try:
        yield eventos
    finally:
        _COLETORES.reset(token)
