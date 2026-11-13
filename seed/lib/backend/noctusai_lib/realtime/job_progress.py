"""Live job progress over SSE — push instead of poll
(`KB § PATTERNS/common/realtime-sse-bus.md` § Job progress).

A long job (transcription, CoreStudio geração, photo editing, video edits)
used to hand off to polling: every open tab re-reads the job every 2-5 s for
minutes. That is O(tabs × interval) load for a value that changes a few times.
This module is the push half: the worker PUBLISHES `{status, progress, stage,
message}` onto a per-job scope of the existing `RealtimeBus`, and one SSE
endpoint streams it to the browser, which writes it into the TanStack cache
(`useJobProgress`, `@noctusai/lib`) and falls back to the polling hand-off if
the stream cannot be kept.

    # worker (any async job body)
    await publish_job_progress(bus, org_id, job_id,
        JobProgress(status="processando", progress=0.4, stage="estrutura 2 de 5"))
    ...
    await publish_job_progress(bus, org_id, job_id,
        JobProgress(status="completo", progress=1, terminal=True))

    # router (the product supplies auth, the org, and the truth-of-record read)
    app.include_router(create_job_progress_router(
        bus,
        auth_dependency=get_current_user_org,     # REQUIRED — no default, no None
        org_resolver=lambda request, auth: auth[2],
        snapshot_loader=load_job_progress,        # -> JobProgress | None (None = 404)
    ), prefix="/api/things/jobs")                 # GET /api/things/jobs/{job_id}

Design points (each one exists because the obvious version fails in prod):
- The seed does not know a product's status words: `terminal` is an explicit
  flag on the payload, never inferred from `status`.
- SCOPE = org + job, and the org comes from the AUTHENTICATED context, never
  from the URL: a user can only ever subscribe to their own org's jobs.
  `snapshot_loader` also proves the job exists for that org (None -> 404).
- On connect the stream first sends a SNAPSHOT of the job (the source of truth,
  from the product's own table), so a client that connects late or reconnects
  after a dropped stream sees the current state immediately. A terminal
  snapshot is sent and the stream closes at once.
- Heartbeat comments + `X-Accel-Buffering: no` keep it alive through
  Cloudflare/nginx. `Last-Event-ID` / `?since=` resumes.
- The stream CLOSES after the terminal event, and after `max_seconds` (default
  10 min) so a client that missed the terminal frame reconnects and re-reads
  the snapshot instead of hanging on heartbeats.
- Publishing is best-effort by default: a Redis blip must never fail the job —
  the polling fallback + the snapshot still deliver the truth. It is logged,
  never silent.
- Access tier: `org` (the product's own authenticated user) via `make_router`.
"""

from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.realtime.bus import RealtimeBus, RealtimeEvent
from noctusai_lib.realtime.sse import sse_event_stream

logger = logging.getLogger(__name__)

JOB_PROGRESS_EVENT = "job.progress"
DEFAULT_MAX_STREAM_SECONDS = 600.0
_DEFAULT_HEARTBEAT_SECONDS = 15.0


@dataclass(frozen=True)
class JobProgress:
    """One progress update. `progress` is 0..1 (None = indeterminate); `terminal`
    marks the last update of the job (the stream closes after it)."""

    status: str
    progress: float | None = None
    stage: str | None = None
    message: str | None = None
    terminal: bool = False

    def __post_init__(self) -> None:
        if self.progress is not None:
            object.__setattr__(self, "progress", max(0.0, min(1.0, float(self.progress))))

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "progress": self.progress,
            "stage": self.stage,
            "message": self.message,
            "terminal": self.terminal,
        }


def job_progress_scope(org_id: str, job_id: str) -> str:
    """Bus scope of one org's job. Org first: two orgs can never share a scope."""
    return f"job:progress:{org_id}:{job_id}"


async def publish_job_progress(
    bus: RealtimeBus,
    org_id: str,
    job_id: str,
    progress: JobProgress,
    *,
    best_effort: bool = True,
) -> str | None:
    """Publish one update. `best_effort=True` (default) logs and returns None on a
    bus failure so the job itself never fails on its own progress reporting."""
    try:
        return await bus.publish(job_progress_scope(org_id, job_id), JOB_PROGRESS_EVENT, progress.to_payload())
    except Exception:
        if not best_effort:
            raise
        logger.warning("job progress publish failed job=%s (clients fall back to polling)", job_id, exc_info=True)
        return None


def _frame(progress: JobProgress) -> str:
    data = json.dumps(progress.to_payload(), separators=(",", ":"))
    # No `id:` — a snapshot is not a position in the stream and must not move the resume cursor.
    return f"event: {JOB_PROGRESS_EVENT}\ndata: {data}\n\n"


def _is_terminal(event: RealtimeEvent) -> bool:
    return bool(event.payload.get("terminal"))


async def job_progress_stream(
    bus: RealtimeBus,
    scope: str,
    snapshot: JobProgress,
    *,
    last_event_id: str | None = None,
    heartbeat_seconds: float = _DEFAULT_HEARTBEAT_SECONDS,
    max_seconds: float | None = DEFAULT_MAX_STREAM_SECONDS,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    disconnect_poll_seconds: float = 1.0,
) -> AsyncIterator[str]:
    """Snapshot frame, then the live events of `scope`, closing on a terminal one."""
    yield _frame(snapshot)
    if snapshot.terminal:
        return
    inner = sse_event_stream(
        bus,
        scope,
        last_event_id=last_event_id,
        heartbeat_seconds=heartbeat_seconds,
        is_disconnected=is_disconnected,
        disconnect_poll_seconds=disconnect_poll_seconds,
        stop_after=_is_terminal,
        max_seconds=max_seconds,
    )
    try:
        async for frame in inner:
            yield frame
    finally:
        await inner.aclose()


OrgResolver = Callable[[Request, Any], "str | Awaitable[str]"]
SnapshotLoader = Callable[[Request, Any, str], "JobProgress | None | Awaitable[JobProgress | None]"]


def create_job_progress_router(
    bus: RealtimeBus,
    *,
    auth_dependency: Callable[..., Any],
    org_resolver: OrgResolver,
    snapshot_loader: SnapshotLoader,
    heartbeat_seconds: float = _DEFAULT_HEARTBEAT_SECONDS,
    max_seconds: float | None = DEFAULT_MAX_STREAM_SECONDS,
    path: str = "/{job_id}",
):
    """`GET <path>` -> `text/event-stream` of one job's progress.

    `auth_dependency` is REQUIRED (unauthenticated -> the dependency's 401); a stream
    with no auth is how a job id becomes a read of another org's data."""
    router = make_router(tier="org", guard=auth_dependency)

    @router.get(path)
    async def job_progress(
        job_id: str,
        request: Request,
        since: str | None = Query(default=None),
        last_event_id_header: str | None = Header(default=None, alias="Last-Event-ID"),
        auth_ctx: Any = Depends(auth_dependency),
    ) -> StreamingResponse:
        org_id = org_resolver(request, auth_ctx)
        if inspect.isawaitable(org_id):
            org_id = await org_id
        snapshot = snapshot_loader(request, auth_ctx, job_id)
        if inspect.isawaitable(snapshot):
            snapshot = await snapshot
        if snapshot is None:
            raise HTTPException(status_code=404, detail="job not found")
        return StreamingResponse(
            job_progress_stream(
                bus,
                job_progress_scope(str(org_id), job_id),
                snapshot,
                last_event_id=last_event_id_header or since,
                heartbeat_seconds=heartbeat_seconds,
                max_seconds=max_seconds,
                is_disconnected=request.is_disconnected,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router
