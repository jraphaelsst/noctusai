"""Recover matrícula extractions that were started and never finished.

The sibling of `card_hub.extracao_scheduler`, and the same safety net for the
same reason — see `app.services.extraction_sweep` for why the wiring has one
definition and why neither sweep takes a lease.

WHY :43 AND NOT :17
-------------------
`card_hub`'s sweep runs at :17. A different minute, deliberately: both sweeps
walk documents and mint storage reads, and landing them on the same minute
would double the burst for no benefit. Neither is time-sensitive —
`STALE_APOS` (20 minutes) is what decides whether a document is abandoned;
the cron only decides how quickly a genuinely stranded one is noticed.
"""
from __future__ import annotations

import logging

from app.services.extraction_sweep import configure_sweep, make_sweep_job

logger = logging.getLogger(__name__)

JOB_ID = "imovel_hub_matricula_sweep"

#: Every hour at :43 — see the module docstring for why not :17.
CRON = "43 * * * *"


async def _sweep(admin, storage) -> dict:
    from app.modules.imovel_hub import matricula_extracao_service as matricula_svc
    from app.modules.imovel_hub.deps import get_matricula_extractor_factory

    return await matricula_svc.varrer_pendentes(
        admin, storage, extractor_factory=get_matricula_extractor_factory()
    )


matricula_sweep_job = make_sweep_job(label="imovel_hub", sweep=_sweep)


def configure() -> None:
    """Register the sweep on the seed-side scheduler. Idempotent.

    Must be called at IMPORT time, before `start_scheduler()` fires in
    `app/lifespan.py`, or the job is never registered and the safety net
    silently does not exist.
    """
    configure_sweep(
        job_id=JOB_ID,
        cron=CRON,
        label="imovel_hub",
        sweep=_sweep,
        job=matricula_sweep_job,
    )


__all__ = ["CRON", "JOB_ID", "configure", "matricula_sweep_job"]
