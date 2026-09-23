"""``AuditSink`` — seed IO module for the request-history audit trail.

Ships Protocol + Fake + Real + factory (no half-ship —
``KB § PATTERNS/backend/seed-fake-real-adapter.md``). Mirrors
``noctusai_lib.api.auth.session.audit.ApiTokenAuditWriter``'s shape
(best-effort, never raises into the request it's auditing) with one
addition: the Real adapter batches through a bounded in-process queue
instead of one INSERT per request, because this sink is expected to
fire on every mutating request across every product, not once per
resolved product-token call.

**Target table.** ``public.audit_logs`` — the table core already ships
(``products/core/backend/migrations/001_noctusai_core.sql``,
``action``/``resource_type``/``resource_id``/``details``/``user_id``/
``org_id``/``created_at``). This sink writes THROUGH that existing
shape (``action=method``, ``resource_type=product``, ``details={...}``)
rather than requiring new columns, so it needs no migration of its own
to start recording — ``settings.audit_trail_enabled`` staying ``False``
until "core migration S1 is live" per the owner brief refers to an
*additive* follow-up (dedicated ``route_template``/``path_params``/
``status``/``correlation_id`` columns + indexes for
``noctusai_lib.domain.card_hub.gatherers.gather_audit``'s query shape)
— not a hard blocker for this module's own correctness. Until that
migration lands, every field the dedicated columns will eventually
carry still round-trips inside ``details`` (see ``_to_row``).

**Overflow / failure never swallows.** Both a full queue and a failed
flush go through :func:`log_overflow_or_failure` — ERROR level, a
named process-wide counter, and a stdout JSON fallback line so the row
is recoverable from log aggregation even when the DB write itself is
what failed. ``noctusai_lib.domain.action_log.log_action`` reuses this
same helper (see that module) instead of its own silent
``except Exception as e: logger.warning(...)``.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sys
from dataclasses import asdict
from typing import Any, Callable, Optional, Protocol

from .types import AuditActor, AuditEntry

logger = logging.getLogger(__name__)

_TABLE = "audit_logs"
_SCHEMA = "public"

#: Process-wide, best-effort visibility counter — not a metrics
#: pipeline, just enough for `logger.error` to report a running total
#: instead of "it happened once" every time. Reset only by process
#: restart; a monotonically-growing number in a log line is the point.
_overflow_or_failure_count = 0


def log_overflow_or_failure(
    *,
    kind: str,
    entry: Any,
    exc: Optional[BaseException] = None,
) -> None:
    """The ONE place an audit write's failure or overflow becomes
    visible. Never called from inside a `try/except: pass` — every
    caller passes through here instead. Logs at ERROR (with traceback
    when `exc` is given) AND emits a single-line JSON row to stdout, so
    the entry survives even when the log sink and the DB are both
    unreachable at once.
    """
    global _overflow_or_failure_count
    _overflow_or_failure_count += 1
    logger.error(
        "audit_%s total=%d entry=%r",
        kind,
        _overflow_or_failure_count,
        entry,
        exc_info=exc is not None,
    )
    try:
        fallback = {"audit_fallback": kind, "entry": _jsonable(entry)}
        print(json.dumps(fallback, default=str), file=sys.stdout, flush=True)
    except Exception:  # noqa: BLE001 — the fallback itself must never raise
        logger.exception("audit_fallback_stdout_write_failed kind=%s", kind)


def overflow_or_failure_count() -> int:
    """Test/introspection accessor for the module-level counter."""
    return _overflow_or_failure_count


def _jsonable(entry: Any) -> Any:
    if isinstance(entry, AuditEntry):
        d = asdict(entry)
        d["occurred_at"] = entry.occurred_at.isoformat()
        return d
    if isinstance(entry, dict):
        return entry
    return {"repr": repr(entry)}


class AuditSink(Protocol):
    """Records one :class:`AuditEntry`. Never raises — a concrete impl
    swallows its own IO failures via :func:`log_overflow_or_failure`
    (never a bare ``except: pass``)."""

    async def record(self, entry: AuditEntry) -> None: ...

    async def drain(self) -> None:
        """Flush any buffered entries and stop background work. Called
        once, from the product's `lifespan` shutdown hook
        (`noctusai_seed.app.create_product_app`)."""
        ...


class FakeAuditSink:
    """In-memory recorder — tests assert on ``.entries``."""

    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def record(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

    async def drain(self) -> None:  # pragma: no cover — nothing to flush
        return None


def _to_row(entry: AuditEntry) -> dict[str, Any]:
    """Map an :class:`AuditEntry` onto ``public.audit_logs``'s existing
    columns — see the module docstring's "Target table" section."""
    actor: AuditActor = entry.actor
    return {
        "user_id": actor.user_id,
        "org_id": actor.org_id,
        "action": entry.method,
        "resource_type": entry.product,
        "resource_id": None,
        "user_agent": entry.client_hint,
        "details": {
            "route_template": entry.route_template,
            "path_params": dict(entry.path_params),
            "status": entry.status,
            "correlation_id": entry.correlation_id,
            "duration_ms": entry.duration_ms,
            "actor_kind": entry.actor_kind,
            "role": actor.role,
        },
    }


class RealAuditSink:
    """Bounded-queue, batched writer into ``public.audit_logs``.

    Args:
        get_admin_client: Zero-arg callable returning a service-role
            Supabase client. Called fresh on every flush (never
            cached) — ``.schema(SCHEMA)`` mutates the underlying
            client's shared session in place, so re-deriving it per
            call is what keeps a concurrent cross-schema caller from
            poisoning this sink's writes. See
            ``KB § PATTERNS/backend/admin-client-schema-pinning.md``.
        max_queue: Bound on buffered entries. A burst beyond this drops
            the newest entry (never blocks the request it's auditing)
            and reports through :func:`log_overflow_or_failure`.
        flush_interval_s: Background loop wakes at most this often.
        batch_size: Also flushes as soon as this many entries are
            queued, without waiting for the timer — "every 2s or 50
            rows," whichever comes first.
    """

    def __init__(
        self,
        get_admin_client: Callable[[], Any],
        *,
        schema: str = _SCHEMA,
        table: str = _TABLE,
        max_queue: int = 2000,
        flush_interval_s: float = 2.0,
        batch_size: int = 50,
    ) -> None:
        self._get_admin_client = get_admin_client
        self._schema = schema
        self._table = table
        self._queue: asyncio.Queue[AuditEntry] = asyncio.Queue(maxsize=max_queue)
        self._flush_interval_s = flush_interval_s
        self._batch_size = batch_size
        self._task: Optional[asyncio.Task] = None

    async def record(self, entry: AuditEntry) -> None:
        self._ensure_started()
        try:
            self._queue.put_nowait(entry)
        except asyncio.QueueFull:
            log_overflow_or_failure(kind="queue_full", entry=entry)

    def _ensure_started(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._flush_loop())

    async def _flush_loop(self) -> None:
        while True:
            batch = await self._collect_batch()
            if batch:
                await self._write_batch(batch)

    async def _collect_batch(self) -> list[AuditEntry]:
        batch: list[AuditEntry] = []
        try:
            first = await asyncio.wait_for(self._queue.get(), timeout=self._flush_interval_s)
            batch.append(first)
        except asyncio.TimeoutError:
            return batch
        while len(batch) < self._batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return batch

    async def _write_batch(self, batch: list[AuditEntry]) -> None:
        rows = [_to_row(e) for e in batch]
        try:
            admin = self._get_admin_client()
            admin.schema(self._schema).table(self._table).insert(rows).execute()
        except Exception as exc:  # noqa: BLE001 — best-effort per module contract
            for entry in batch:
                log_overflow_or_failure(kind="write_failed", entry=entry, exc=exc)

    async def drain(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        remaining: list[AuditEntry] = []
        while True:
            try:
                remaining.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if remaining:
            await self._write_batch(remaining)


def make_audit_sink(
    get_admin_client: Optional[Callable[[], Any]] = None,
    *,
    schema: str = _SCHEMA,
    table: str = _TABLE,
) -> AuditSink:
    """Return the appropriate sink for the environment.

    ``get_admin_client=None`` (no DB wired — dev/test) returns the
    in-memory Fake; otherwise the batched Real adapter.
    """
    if get_admin_client is not None:
        return RealAuditSink(get_admin_client, schema=schema, table=table)
    return FakeAuditSink()


__all__ = [
    "AuditSink",
    "FakeAuditSink",
    "RealAuditSink",
    "log_overflow_or_failure",
    "make_audit_sink",
    "overflow_or_failure_count",
]
