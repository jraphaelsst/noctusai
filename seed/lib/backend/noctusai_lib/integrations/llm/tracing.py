"""Per-call AI tracing on the house ledger — one trace per conversation turn / request, one span per LLM call and
per tool call, plus a guardrail-verdict hook point.

WHY NOT OpenTelemetry / Langfuse. The house runs no trace backend (Sentry is wired for ERRORS only, no performance
tracing, and it carries no token/cost/prompt-version dimensions). The central ledger `public.ai_usage` (core 091)
already holds, per LLM call, everything a span needs — model, tokens, cache-read tokens, cost, org / product /
agent / conversation. So the minimal REAL option is to extend it: core migration 115 adds
``trace_id / span_id / parent_span_id / latency_ms / prompt_version`` to ``ai_usage`` (an LLM call row IS its span)
and a ``public.ai_trace_spans`` table for the NON-LLM spans (tool calls, guardrail verdicts, internal steps). The
view ``public.ai_trace_timeline`` unions both: ``select * from ai_trace_timeline where trace_id = :t order by
started_at``. `read_trace` is the same query for Python callers.

HOW IT IS WIRED (by construction, no product plumbing)
  - LLM calls: `usage.record_usage` stamps every event with `usage_stamp()` — the trace/span ids in force (the open
    `span(...)`, else the request correlation id as the trace, else a fresh id) and the call latency measured by
    `usage.metered_call`. The existing `CentralUsageSink` writes them. Streams carry ids but no latency.
  - Tool calls / turns / guardrails: `async with span("agents.turn", kind="internal")`, `async with span(tool_name,
    kind="tool")`, `await record_guardrail_verdict("leak_filter", "pass")` — written through the configured
    `SpanSink` (Real installed by `create_product_app`, like `CentralUsageSink`).

Seam shape (KB § PATTERNS/backend/seed-fake-real-adapter.md): Protocol = `SpanSink`; Fake = `InMemorySpanSink`; Real
= `SupabaseSpanSink`; factory = `make_span_sink` (refuses Real under pytest unless ``force_real=True``).

LGPD: ids, names, timings, counts and verdict labels only — never prompt / response / tool-argument text. Span
attributes are filtered to short scalars.
"""
from __future__ import annotations

import contextlib
import contextvars
import logging
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Iterator, Literal, Optional, Protocol

import anyio.to_thread

logger = logging.getLogger(__name__)

__all__ = [
    "InMemorySpanSink",
    "Span",
    "SpanRecord",
    "SpanSink",
    "SupabaseSpanSink",
    "configure_span_sink",
    "current_trace_ids",
    "llm_call_scope",
    "make_span_sink",
    "read_trace",
    "record_guardrail_verdict",
    "span",
    "usage_stamp",
]

SPAN_TABLE = "ai_trace_spans"
TIMELINE_VIEW = "ai_trace_timeline"
SpanKind = Literal["tool", "guardrail", "internal"]
_ATTR_KEYS_MAX = 20
_ATTR_TEXT_MAX = 200
_ID_MAX = 64


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def _new_trace_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class _Ref:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    started: float = 0.0  # monotonic, for the latency of an LLM-call scope
    llm: bool = False  # True for the scope of ONE provider call (`llm_call_scope`)


_CURRENT: contextvars.ContextVar[Optional[_Ref]] = contextvars.ContextVar("noctusai_ai_trace_current", default=None)


@dataclass
class SpanRecord:
    """One non-LLM span, as persisted to ``public.ai_trace_spans``."""

    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    kind: str
    name: str
    started_at: datetime
    latency_ms: Optional[int] = None
    status: str = "ok"  # "ok" | "error" | "blocked"
    guardrail_verdict: Optional[str] = None
    org_id: Optional[str] = None
    product: Optional[str] = None
    agent_key: Optional[str] = None
    conversation_id: Optional[str] = None
    prompt_version: Optional[str] = None
    attributes: dict[str, Any] = field(default_factory=dict)


class SpanSink(Protocol):
    async def record(self, span: SpanRecord) -> None: ...


class InMemorySpanSink:
    """Fake — keeps spans in a list for assertions."""

    def __init__(self) -> None:
        self.spans: list[SpanRecord] = []

    async def record(self, span: SpanRecord) -> None:
        self.spans.append(span)


def _clean_attributes(attributes: Optional[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in list((attributes or {}).items())[:_ATTR_KEYS_MAX]:
        if isinstance(value, (bool, int, float)) or value is None:
            out[str(key)[:80]] = value
        elif isinstance(value, str):
            out[str(key)[:80]] = value[:_ATTR_TEXT_MAX]
    return out


def _uuid_or_none(value: Optional[str]) -> Optional[str]:
    try:
        return str(uuid.UUID(str(value))) if value else None
    except (ValueError, AttributeError, TypeError):
        return None


class SupabaseSpanSink:
    """Real — inserts one ``public.ai_trace_spans`` row per span through a SERVICE-ROLE ``public`` client
    (``DatabaseModule.get_core_client``), resolved per call. A lost span is logged at ERROR; tracing never fails
    the traced work."""

    def __init__(self, core_client_factory: Callable[[], Any]) -> None:
        self._client_factory = core_client_factory

    def _insert(self, span: SpanRecord) -> None:
        row = {
            "trace_id": span.trace_id[:_ID_MAX],
            "span_id": span.span_id[:_ID_MAX],
            "parent_span_id": span.parent_span_id[:_ID_MAX] if span.parent_span_id else None,
            "kind": span.kind,
            "name": span.name[:200],
            "started_at": span.started_at.isoformat(),
            "latency_ms": span.latency_ms,
            "status": span.status if span.status in ("ok", "error", "blocked") else "error",
            "guardrail_verdict": span.guardrail_verdict[:80] if span.guardrail_verdict else None,
            "org_id": _uuid_or_none(span.org_id),
            "product": span.product[:200] if span.product else None,
            "agent_key": span.agent_key[:200] if span.agent_key else None,
            "conversation_id": span.conversation_id[:200] if span.conversation_id else None,
            "prompt_version": span.prompt_version[:200] if span.prompt_version else None,
            "attributes": _clean_attributes(span.attributes),
        }
        self._client_factory().table(SPAN_TABLE).insert(row).execute()

    async def record(self, span: SpanRecord) -> None:
        try:
            await anyio.to_thread.run_sync(self._insert, span)
        except Exception as exc:  # noqa: BLE001 — tracing never fails the traced work; the loss is loud
            logger.error(
                "llm.tracing: ai_trace_spans insert failed kind=%s name=%s trace=%s: %s",
                span.kind, span.name, span.trace_id, exc,
            )


def make_span_sink(core_client_factory: Optional[Callable[[], Any]], *, force_real: bool = False) -> Optional[SpanSink]:
    """The Real sink, or ``None`` with no client factory or under pytest (an app built at test collection must
    never write production). Tests of the Real sink pass ``force_real=True`` with a mock client."""
    if core_client_factory is None:
        return None
    if "pytest" in sys.modules and not force_real:
        return None
    return SupabaseSpanSink(core_client_factory)


_sink: Optional[SpanSink] = None


def configure_span_sink(sink: Optional[SpanSink]) -> None:
    """Install the process-wide span sink (``None`` = spans are not persisted; LLM rows still carry ids)."""
    global _sink
    _sink = sink


# ── context ──────────────────────────────────────────────────────────────────────────────────────────────────


def current_trace_ids() -> Optional[tuple[str, str]]:
    """``(trace_id, span_id)`` of the open span in this context, or ``None``."""
    ref = _CURRENT.get()
    return (ref.trace_id, ref.span_id) if ref else None


class Span:
    """The handle `span(...)` yields: set the outcome / verdict / attributes before the block ends."""

    def __init__(self, ref: _Ref, record: SpanRecord) -> None:
        self.trace_id = ref.trace_id
        self.span_id = ref.span_id
        self._record = record

    def set(
        self, *, status: Optional[str] = None, guardrail_verdict: Optional[str] = None,
        prompt_version: Optional[str] = None, **attributes: Any,
    ) -> None:
        if status is not None:
            self._record.status = status
        if guardrail_verdict is not None:
            self._record.guardrail_verdict = guardrail_verdict
        if prompt_version is not None:
            self._record.prompt_version = prompt_version
        self._record.attributes.update(attributes)


@contextlib.asynccontextmanager
async def span(
    name: str, *, kind: SpanKind = "internal", trace_id: Optional[str] = None,
    prompt_version: Optional[str] = None, **attributes: Any,
) -> AsyncIterator[Span]:
    """Open a span (a child of the current one; a root — new trace — when none is open and no ``trace_id`` is
    passed). On exit its latency is measured and the record is written through the configured `SpanSink`; an
    exception marks it ``status="error"`` and propagates. Nested LLM calls and spans inherit the trace."""
    from .attribution import current_attribution

    parent = _CURRENT.get()
    ref = _Ref(
        trace_id=(trace_id or (parent.trace_id if parent else None) or _correlation_trace_id() or _new_trace_id())[:_ID_MAX],
        span_id=_new_id(),
        parent_span_id=parent.span_id if parent and (trace_id is None or trace_id == parent.trace_id) else None,
        started=time.monotonic(),
    )
    record = SpanRecord(
        trace_id=ref.trace_id, span_id=ref.span_id, parent_span_id=ref.parent_span_id, kind=kind, name=name,
        started_at=datetime.now(timezone.utc), prompt_version=prompt_version, attributes=dict(attributes),
    )
    token = _CURRENT.set(ref)
    handle = Span(ref, record)
    try:
        yield handle
    except BaseException as exc:
        record.status = "error"
        record.attributes.setdefault("error", type(exc).__name__)
        raise
    finally:
        _CURRENT.reset(token)
        record.latency_ms = int((time.monotonic() - ref.started) * 1000)
        try:
            attr = current_attribution()
            record.org_id, record.product = attr.org_id, attr.product
            record.agent_key, record.conversation_id = attr.agent_key, attr.conversation_id
            record.prompt_version = record.prompt_version or attr.prompt_version
        except Exception as exc:  # noqa: BLE001 — attribution must never cost a span
            logger.debug("llm.tracing: attribution unavailable (%s)", exc)
        if _sink is not None:
            await _sink.record(record)


async def record_guardrail_verdict(
    name: str, verdict: str, *, blocked: bool = False, **attributes: Any,
) -> None:
    """The hook point for guardrails: one ``kind="guardrail"`` span, child of the open span, carrying the verdict
    label (``"pass"`` / ``"redacted"`` / ``"blocked"`` ...). ``blocked=True`` marks ``status="blocked"``."""
    async with span(name, kind="guardrail", **attributes) as s:
        s.set(guardrail_verdict=verdict, status="blocked" if blocked else "ok")


def _correlation_trace_id() -> Optional[str]:
    try:
        from noctusai_lib.primitives._correlation import get_correlation_id

        rid = get_correlation_id()
        return rid if rid and rid != "-" else None
    except Exception as exc:  # noqa: BLE001 — the correlation id is a convenience, never required
        logger.debug("llm.tracing: correlation id unavailable (%s)", exc)
        return None


# ── LLM-call spans (the ai_usage row IS the span) ────────────────────────────────────────────────────────────


@contextlib.contextmanager
def llm_call_scope() -> Iterator[_Ref]:
    """Wrap ONE provider call (`usage.metered_call` does): the usage event recorded inside gets this span id and
    its latency. A child of the open span when there is one."""
    parent = _CURRENT.get()
    ref = _Ref(
        trace_id=(parent.trace_id if parent else None) or _correlation_trace_id() or _new_trace_id(),
        span_id=_new_id(),
        parent_span_id=parent.span_id if parent else None,
        started=time.monotonic(),
        llm=True,
    )
    token = _CURRENT.set(ref)
    try:
        yield ref
    finally:
        _CURRENT.reset(token)


@dataclass(frozen=True)
class UsageStamp:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    latency_ms: Optional[int]


def usage_stamp() -> UsageStamp:
    """The ids (and latency, inside `llm_call_scope`) for the usage event being recorded right now. Outside any
    scope (embeddings / audio providers, a stream) the event still gets a span id under the open trace — or a
    one-span trace — with no latency."""
    ref = _CURRENT.get()
    if ref is None:
        return UsageStamp(_correlation_trace_id() or _new_trace_id(), _new_id(), None, None)
    if ref.llm:
        return UsageStamp(ref.trace_id, ref.span_id, ref.parent_span_id, int((time.monotonic() - ref.started) * 1000))
    return UsageStamp(ref.trace_id, _new_id(), ref.span_id, None)


# ── read ─────────────────────────────────────────────────────────────────────────────────────────────────────


def read_trace(core_client_factory: Callable[[], Any], trace_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
    """Every span of one trace (LLM calls from ``ai_usage`` + tool / guardrail / internal spans), oldest first —
    the ``ai_trace_timeline`` view through a SERVICE-ROLE ``public`` client. Raises on a read failure (a trace
    that cannot be read is not an empty trace)."""
    rows = (
        core_client_factory().table(TIMELINE_VIEW).select("*").eq("trace_id", trace_id)
        .order("started_at").limit(limit).execute().data
    )
    return list(rows or [])
