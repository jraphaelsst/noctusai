"""`fotos.lote_pronto` -> card sync (contract §6). Wraps the seed handler; the seed stays untouched."""
from __future__ import annotations

from typing import Callable

from noctusai_lib.domain.jobs import Job, JobHandler
from noctusai_lib.domain.photo_editing import JobType, PhotoEditingPorts

from app.modules.imobshotai.repository import ImobshotRepository
from app.modules.imobshotai.service import sincronizar_do_lote


def wrap_lote_pronto(
    handlers: dict[str, JobHandler],
    ports: PhotoEditingPorts,
    repo_factory: Callable[[], ImobshotRepository],
) -> dict[str, JobHandler]:
    """A copy of `handlers` whose `LOTE_PRONTO` also syncs the lote's card after the seed handler ran. A sync
    failure is logged inside `sincronizar_do_lote` and never fails (and so never retries) the job."""
    inner = handlers[JobType.LOTE_PRONTO]

    async def lote_pronto(job: Job) -> None:
        await inner(job)
        lote_id = (job.payload or {}).get("lote_id")
        if lote_id:
            await sincronizar_do_lote(repo_factory(), ports, str(lote_id), ator_id=None)

    return {**handlers, JobType.LOTE_PRONTO: lote_pronto}


__all__ = ["wrap_lote_pronto"]
