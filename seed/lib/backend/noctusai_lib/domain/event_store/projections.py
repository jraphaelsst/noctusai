"""Projection runners and the rebuild helper.

Two delivery guarantees, chosen by WHERE the projection's effect lands:

* **In-DB read model -> exactly-once effect.** `store.run_projection(name)` (the `es_run_projection` RPC) applies
  one batch AND moves the checkpoint in ONE transaction; a failing batch moves neither. Drive it from the seed
  jobs worker with `projection_job_handler(store)` (the queue's `FOR UPDATE SKIP LOCKED` claim + lease decides
  which worker runs; the checkpoint row's own `SKIP LOCKED` lock answers `busy` to a second concurrent runner).
* **External effect (email, webhook, another service) -> at-least-once.** `ExternalProjectionRunner` reads
  `read_all` from a `CheckpointStore` cursor, calls a Python handler, then advances the checkpoint with a
  compare-and-set. A crash between the effect and the advance repeats the batch: the handler must be idempotent
  (use `event_id` as the dedupe key downstream).

`rebuild_projection(store, name)` replays a projection from position 0 into a shadow table, swaps the contents
in, and resets the checkpoint (`es_rebuild_begin` -> `es_rebuild_step`* -> `es_rebuild_swap`). Exposed to agents
as `noctus.dev.projection_rebuild`.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Sequence

from .types import Cursor, RebuildOutcome, StoredEvent
from .upcasting import Upcasters

#: Job type the seed jobs worker dispatches to `projection_job_handler`; payload `{"projection": <name>}`.
PROJECTION_JOB_TYPE = "event_store.project"


def projection_job_handler(store: Any, *, batch: int = 500, max_batches: int = 20) -> Callable[[Any], Awaitable[None]]:
    """A `domain.jobs.Worker` handler that drains one async projection (up to `max_batches` batches per job).

    `error` -> raises (the job retries with backoff; the checkpoint already holds `last_error`);
    `refused` (unknown / not async) -> `DeadLetterError` (retrying cannot help); `busy` / `idle` -> done."""
    from noctusai_lib.domain.jobs import DeadLetterError

    async def handle(job: Any) -> None:
        name = (job.payload or {}).get("projection")
        if not isinstance(name, str) or not name:
            raise DeadLetterError(f"{PROJECTION_JOB_TYPE} job without a projection name")
        for _ in range(max(1, max_batches)):
            run = await asyncio.to_thread(store.run_projection, name, limit=batch)
            if run.status == "refused":
                raise DeadLetterError(f"projection {name}: refused ({run.code})")
            if run.status == "error":
                raise RuntimeError(f"projection {name}: batch failed at {run.cursor}: {run.error}")
            if run.status in ("idle", "busy") or run.applied < batch:
                return

    return handle


@dataclass(frozen=True)
class ExternalRun:
    status: str  # "ok" | "idle" | "conflict" | "error"
    applied: int = 0
    cursor: Cursor = Cursor()
    error: Optional[str] = None


class ExternalProjectionRunner:
    """At-least-once delivery of the log to a Python handler with an effect OUTSIDE the database."""

    def __init__(self, store: Any, checkpoints: Any, name: str, handler: Callable[[list[StoredEvent]], None], *,
                 stream_types: Optional[Sequence[str]] = None, upcasters: Optional[Upcasters] = None) -> None:
        self.store, self.checkpoints, self.name, self.handler = store, checkpoints, name, handler
        self.stream_types, self.upcasters = stream_types, upcasters

    def run_once(self, *, limit: int = 500) -> ExternalRun:
        start = self.checkpoints.get(self.name).cursor
        batch = self.store.read_all(start, limit=limit, stream_types=self.stream_types)
        if not batch.events:
            return ExternalRun("idle", 0, start)
        events = [self.upcasters.upcast(e) for e in batch.events] if self.upcasters else list(batch.events)
        try:
            self.handler(events)
        except Exception as exc:  # noqa: BLE001 -- recorded on the checkpoint and returned, never swallowed
            self.checkpoints.record_error(self.name, str(exc))
            return ExternalRun("error", 0, start, str(exc))
        if self.checkpoints.advance(self.name, expected=start, to=batch.next) == "conflict":
            # another runner advanced meanwhile: our effects were duplicates of its own (at-least-once)
            return ExternalRun("conflict", len(events), start)
        return ExternalRun("ok", len(events), batch.next)


def rebuild_projection(store: Any, name: str, *, batch: int = 1000, max_steps: Optional[int] = None) -> RebuildOutcome:
    """Shadow table <- replay from 0 (one transaction per step, the live projection keeps serving) <- swap.

    Stops at `max_steps` WITHOUT swapping (status refused, code `max_steps`); the shadow stays, a later call
    resumes with `es_rebuild_begin` again (a rebuild always restarts from 0)."""
    code = store.rebuild_begin(name)
    if code:
        return RebuildOutcome("refused", code=code)
    steps = 0
    while True:
        step = store.rebuild_step(name, limit=batch)
        steps += 1
        if step.status != "ok":
            return RebuildOutcome("refused", steps=steps, code=step.code)
        if step.done:
            break
        if max_steps is not None and steps >= max_steps:
            return RebuildOutcome("refused", steps=steps, cursor=step.cursor, code="max_steps")
    out = store.rebuild_swap(name)
    return RebuildOutcome(out.status, out.rows, out.cursor, steps, out.code)


__all__ = [
    "ExternalProjectionRunner",
    "ExternalRun",
    "PROJECTION_JOB_TYPE",
    "projection_job_handler",
    "rebuild_projection",
]
