"""``AuditSink`` — seed IO module for the request-history audit trail.

Ships Protocol + Fake + Real + factory (no half-ship —
``KB § PATTERNS/backend/seed-fake-real-adapter.md``). Mirrors
``noctusai_lib.api.auth.session.audit.ApiTokenAuditWriter``'s shape
(best-effort, never raises into the request it's auditing) with one
addition: the Real adapter batches through a bounded in-process queue
instead of one INSERT per request, because this sink is expected to
fire on every mutating request across every product, not once per
resolved product-token call.

**Target table.** ``public.audit_logs``, widened by
``products/core/backend/migrations/053_audit_trail_expansion.sql``
(S1, landed 2026-09-23) with dedicated columns for every field this
sink captures: ``product_slug``, ``method``, ``route_template``,
``path_params`` (JSONB), ``status_code``, ``correlation_id``,
``role``, ``actor_kind`` (DB CHECK-enforced ``user``/``agent``/
``service``), ``client_hint``, ``duration_ms``. ``_to_row`` writes
these directly — ``details`` stays for genuine extras only (empty
today; this sink has nothing left to fold into it). The ORIGINAL
columns (``action``/``resource_type``/``resource_id``/``user_id``/
``org_id``/``created_at``, 001/002) are also populated:
``action=method``, and ``resource_type``/``resource_id`` are derived
from the route (see ``_derive_resource``) — together with
``product_slug`` they back the migration's
``idx_audit_logs_product_resource`` index, the one
``noctusai_lib.domain.card_hub.gatherers.gather_audit`` queries
against.

``audit_logs`` is append-only (053's ``guard_audit_logs_append_only``
trigger) — this sink only ever ``INSERT``s, never ``UPDATE``/``DELETE``,
matching the guard by construction.

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
from typing import Any, Callable, Mapping, Optional, Protocol

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


def _derive_resource(
    route_template: str, path_params: Mapping[str, Any]
) -> tuple[Optional[str], Optional[str]]:
    """``("leads", "<uuid>")`` from ``"/api/leads/{lead_id}/notas/{nota_id}"``
    + ``{"lead_id": "<uuid>", "nota_id": "..."}`` — the path SEGMENT
    immediately before the FIRST ``{param}`` (URL-template order), and
    that parameter's resolved value.

    FIRST, not last: ``noctusai_lib.domain.card_hub.router``'s
    ``entity_path()`` convention (and RESTful nesting generally) always
    puts the card/entity's own id as the OUTERMOST path parameter —
    ``/{id_param}/notas/{nota_id}``, ``/{id_param}/checklists/{checklist_id}``
    — so the first param is consistently "which entity did this mutate,"
    while a LAST-param convention would instead resolve every nested
    sub-resource route (notes, checklists, documents, ...) to ITS OWN
    id, missing them all in a per-entity query. Matches
    ``CardHubConfig.entity_table`` by the module's own docstring
    convention (``entity_table: "clientes"`` next to
    ``prefix: "/api/clientes"`` — same string).

    ``(None, None)`` for a route with no path parameter at all (a bare
    collection route, e.g. ``POST /api/leads``).
    """
    segments = [s for s in route_template.split("/") if s]
    for i, seg in enumerate(segments):
        if seg.startswith("{") and seg.endswith("}"):
            param_name = seg[1:-1].split(":", 1)[0]
            resource_type = segments[i - 1] if i > 0 else None
            raw_value = path_params.get(param_name)
            resource_id = str(raw_value) if raw_value is not None else None
            return resource_type, resource_id
    return None, None


def _to_row(entry: AuditEntry) -> dict[str, Any]:
    """Map an :class:`AuditEntry` onto ``public.audit_logs`` — dedicated
    columns (053) written directly, original columns (001/002) derived
    — see the module docstring's "Target table" section."""
    actor: AuditActor = entry.actor
    resource_type, resource_id = _derive_resource(entry.route_template, entry.path_params)
    return {
        # Original columns (001/002) — `action`/`resource_type` are
        # NOT NULL; `resource_type` falls back to `product_slug` when
        # the route has no path parameter at all (still a meaningful
        # grouping, never a NULL that would violate the constraint).
        "user_id": actor.user_id,
        "org_id": actor.org_id,
        "action": entry.method,
        "resource_type": resource_type or entry.product_slug,
        "resource_id": resource_id,
        # Dedicated columns (053).
        "product_slug": entry.product_slug,
        "method": entry.method,
        "route_template": entry.route_template,
        "path_params": dict(entry.path_params),
        "status_code": entry.status,
        "correlation_id": entry.correlation_id,
        "role": actor.role,
        "actor_kind": entry.actor_kind,
        "client_hint": entry.client_hint,
        "duration_ms": (
            int(entry.duration_ms) if entry.duration_ms is not None else None
        ),
        # `details` / `before_snapshot` / `ip_address` / `user_agent`
        # stay at their DB defaults ('{}' / '{}' / NULL / NULL) — this
        # sink has no extras left to fold into `details` now that every
        # captured field has a dedicated column, and it never had raw
        # UA/IP to begin with (`client_hint` is the coarse, non-PII
        # substitute — see migration 053's LGPD note).
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


def running_under_pytest() -> bool:
    """``True`` for the WHOLE pytest process — collection AND execution.

    Deliberately ``"pytest" in sys.modules``, not ``PYTEST_CURRENT_TEST``
    (only set while a specific test is actively running): a product's
    ``app.main`` builds its app — and this sink — at MODULE IMPORT
    time, during pytest's collection phase, before any test body (and
    therefore before ``PYTEST_CURRENT_TEST``) exists. The broader
    signal is what actually needs to be true at that moment.
    """
    return "pytest" in sys.modules


def make_audit_sink(
    get_admin_client: Optional[Callable[[], Any]] = None,
    *,
    schema: str = _SCHEMA,
    table: str = _TABLE,
    force_real: bool = False,
) -> AuditSink:
    """Return the appropriate sink for the environment.

    Defaults to the in-memory Fake whenever the process is running
    under pytest (:func:`running_under_pytest`) — REGARDLESS of
    ``get_admin_client``. A product's ``app.main`` builds its app (and
    this sink) at IMPORT time, before any per-test
    ``unittest.mock.patch`` on ``DatabaseModule.get_core_client`` is
    active; a ``RealAuditSink`` built from an admin-client accessor at
    that point would attempt a REAL write the moment its flush timer
    fires during ANY test — closed here, at the one place that decides
    Real vs. Fake, rather than trusting every call site to remember.
    ``force_real=True`` is the deliberate escape hatch for a test that
    exercises ``RealAuditSink``'s own wiring on purpose (see
    ``seed/lib/backend/tests/api/audit/test_sink.py``).

    Outside pytest: ``get_admin_client=None`` (no DB wired — a direct
    dev run with no Supabase configured) returns the in-memory Fake;
    otherwise the batched Real adapter.
    """
    if not force_real and running_under_pytest():
        return FakeAuditSink()
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
    "running_under_pytest",
]
