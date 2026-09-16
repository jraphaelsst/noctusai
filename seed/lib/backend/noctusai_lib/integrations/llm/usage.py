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

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

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
    """
    provider: str
    model: str
    operation: str
    org_id: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
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

def estimate_cost_usd(
    *,
    provider: str,
    model: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    image_input_tokens: Optional[int] = None,
    image_output_tokens: Optional[int] = None,
) -> float:
    """Compute a rough cost estimate from the model catalog.

    `image_input_tokens` / `image_output_tokens` price against the model's
    dedicated image rates (`ModelEntry.cost_per_1m_image_input_tokens` /
    `..._output_tokens`) — additive to the text `prompt_tokens` /
    `completion_tokens` legs, never a substitute for them. Omitting them
    (every pre-S2 caller) reproduces the exact prior text-only result.

    Returns 0.0 when any input is missing or the model has no price in the
    catalog (common for stubs + future models). A rate missing for just ONE
    leg (e.g. an `image_edit` model priced on text-in but not yet on
    image-in) zeroes only that leg's contribution, not the whole estimate.
    Never raises — pricing should never break a successful LLM call.
    """
    from .models import models_for

    try:
        entries = [m for m in models_for(provider) if m.id == model]
        if not entries:
            return 0.0
        entry = entries[0]
        in_rate = getattr(entry, "cost_per_1m_input_tokens", None) or 0.0
        out_rate = getattr(entry, "cost_per_1m_output_tokens", None) or 0.0
        img_in_rate = getattr(entry, "cost_per_1m_image_input_tokens", None) or 0.0
        img_out_rate = getattr(entry, "cost_per_1m_image_output_tokens", None) or 0.0
        pt = prompt_tokens or 0
        ct = completion_tokens or 0
        ipt = image_input_tokens or 0
        ipo = image_output_tokens or 0
        return (
            pt * in_rate + ct * out_rate + ipt * img_in_rate + ipo * img_out_rate
        ) / 1_000_000.0
    except Exception as exc:
        logger.debug("estimate_cost_usd failed for %s/%s: %s", provider, model, exc)
        return 0.0


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
    model_version: Optional[str] = None,
    batch: bool = False,
) -> None:
    """Provider-side convenience — builds a `UsageEvent` and dispatches to
    the active sink. Safe to call with `sink=None` (no-op). Never raises.

    `image_input_tokens` / `image_output_tokens` / `model_version` / `batch`
    are additive, keyword-only, defaulted params — every pre-S2 call site
    (which passes none of them) behaves identically to before.

    Imported lazily inside provider methods to avoid a circular import
    (provider → client → usage → ...).
    """
    try:
        from .client import get_llm_config
        config = get_llm_config()
    except Exception as exc:
        logger.debug("llm.usage: get_llm_config() unavailable (%s); usage sink not invoked", exc)
        return
    sink = getattr(config, "usage_sink", None)
    if sink is None:
        return
    cost = estimate_cost_usd(
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        image_input_tokens=image_input_tokens,
        image_output_tokens=image_output_tokens,
    )
    try:
        await sink.record(UsageEvent(
            provider=provider,
            model=model,
            operation=operation,
            org_id=org_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            image_input_tokens=image_input_tokens,
            image_output_tokens=image_output_tokens,
            cost_estimate_usd=cost,
            model_version=model_version,
            batch=batch,
        ))
    except Exception as exc:
        logger.warning("usage_sink.record failed: %s", exc)
