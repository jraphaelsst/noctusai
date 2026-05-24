"""Runs service — fire-and-track extraction-pipeline executions over HTTP.

The pipeline (Drive → transcribe → summarize) is long-running and hits external
services, so ``POST /api/runs`` schedules it on a FastAPI ``BackgroundTask`` and
returns 202 immediately; progress is observed via the catalog (lessons appear as
they're produced) + this in-memory status registry. Limitation: the registry is
in-memory — a container restart forgets in-flight runs (acceptable for v1; a
durable job store is a follow-up).

The executor is a DI seam (:class:`RunExecutor`) so router tests inject a fake
that never touches OpenAI/Drive — never monkeypatching our own code.
"""
from __future__ import annotations

import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

logger = logging.getLogger(__name__)

_MAX_RUNS = 50  # cap the in-memory registry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunStatus:
    run_id: str
    status: str  # "running" | "done" | "error"
    mode: str  # "drive" | "fake"
    started_at: str
    finished_at: str | None = None
    detail: str | None = None


_RUNS: "OrderedDict[str, RunStatus]" = OrderedDict()


def register_run(mode: str) -> RunStatus:
    run = RunStatus(run_id=uuid.uuid4().hex, status="running", mode=mode, started_at=_now())
    _RUNS[run.run_id] = run
    while len(_RUNS) > _MAX_RUNS:
        _RUNS.popitem(last=False)
    return run


def mark_done(run_id: str, detail: str | None = None) -> None:
    r = _RUNS.get(run_id)
    if r:
        r.status, r.finished_at, r.detail = "done", _now(), detail


def mark_error(run_id: str, detail: str) -> None:
    r = _RUNS.get(run_id)
    if r:
        r.status, r.finished_at, r.detail = "error", _now(), detail


def list_runs() -> list[RunStatus]:
    """Most-recent-first."""
    return list(reversed(_RUNS.values()))


class RunExecutor(Protocol):
    async def __call__(self, run_id: str, mode: str, drive_url: str | None) -> None: ...


async def default_executor(run_id: str, mode: str, drive_url: str | None) -> None:
    """Real executor — builds + runs the extraction pipeline, then rebuilds the index."""
    from app.pipeline import build_default_pipeline, build_fake_pipeline
    from app.services.indexing import build_index

    try:
        if mode == "fake":
            pipeline = build_fake_pipeline()
            results = await pipeline.run_from_drive("fake://demo")
        else:
            pipeline = build_default_pipeline()
            results = await pipeline.run_from_drive(drive_url or "")
        build_index(pipeline.data_dir)
        mark_done(run_id, f"{len(results)} aula(s) processada(s)")
    except Exception as exc:  # noqa: BLE001 — surface into the registry, never swallow
        logger.exception("run %s (%s) failed", run_id, mode)
        mark_error(run_id, str(exc))


async def run_and_track(
    executor: RunExecutor, run_id: str, mode: str, drive_url: str | None
) -> None:
    """BackgroundTask entry. The executor owns status updates; this guard ensures a
    buggy executor still can't leave a run stuck 'running'."""
    try:
        await executor(run_id, mode, drive_url)
    except Exception as exc:  # noqa: BLE001 — logged, recorded; never silent
        logger.exception("run %s crashed in executor wrapper", run_id)
        mark_error(run_id, str(exc))
