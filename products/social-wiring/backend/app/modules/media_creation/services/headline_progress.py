"""Live progress of a headline batch (lote), pushed over SSE — the pilot of the seed job-progress channel
(`noctusai_lib.realtime.job_progress`; `KB § PATTERNS/common/realtime-sse-bus.md` § Job progress).

Why this job: the CoreStudio "Gerar headlines" modal polls `GET /lotes/{id}` every 3 s for the whole run
(one request per open tab, ~5 DB round trips each) to show "estrutura 3 de 5". The worker already knows that
number at the moment it changes, so it publishes it and the modal stops polling while the stream is open.

The batch row stays the source of truth: the stream's snapshot is read from it, a publish failure never
fails the batch, and the frontend falls back to the polling hand-off if the stream cannot be kept.
"""
from __future__ import annotations

from typing import Any, Mapping

from noctusai_lib.realtime import (
    JobProgress,
    RealtimeBus,
    get_shared_realtime_bus,
    publish_job_progress,
)

from app.config import settings

TERMINAL_STATUS = frozenset({"completo", "falha"})


def headline_progress_bus() -> RealtimeBus:
    return get_shared_realtime_bus(settings.redis_url, label="Headline job-progress")


def lote_progress(row: Mapping[str, Any]) -> JobProgress:
    """Project a `headline_lotes` row into the wire shape. `progress` = structures done / total."""
    total = int(row.get("estruturas_total") or 0)
    done = int(row.get("estruturas_processadas") or 0)
    status = str(row["status"])
    terminal = status in TERMINAL_STATUS
    progress = 1.0 if status == "completo" else (done / total if total else None)
    return JobProgress(
        status=status,
        progress=progress,
        stage=row.get("etapa"),
        message=row.get("erro") if status == "falha" else None,
        terminal=terminal,
    )


async def publish_lote_progress(org_id: str, lote_id: str, row: Mapping[str, Any], bus: RealtimeBus | None = None) -> None:
    await publish_job_progress(bus or headline_progress_bus(), str(org_id), str(lote_id), lote_progress(row))
