"""Close out matrícula extractions that were started and never finished.

The third sibling of `card_hub.extracao_scheduler` and
`imovel_hub.extracao_scheduler`, and the same safety net for the same
reason — see `app.services.extraction_sweep` for why the wiring has one
definition and why none of the three takes a lease.

WHY :29, AND WHY THAT MATTERS LESS HERE
---------------------------------------
`card_hub` sweeps at :17, `imovel_hub` at :43. A third distinct minute,
deliberately: the other two mint storage reads and landing them together
would burst for no benefit. This one issues no storage read at all (see
`service.varrer_pendentes` — there is no stored blob to read), so it is the
cheapest of the three; a distinct minute is still the right default rather
than a coincidence to rely on.

None of them is time-sensitive: `STALE_APOS` (20 minutes) decides whether a
row is abandoned; the cron only decides how quickly an abandoned one is
noticed.
"""
from __future__ import annotations

import logging

from app.services.extraction_sweep import configure_sweep, make_sweep_job

logger = logging.getLogger(__name__)

JOB_ID = "matriculas_extracao_sweep"

#: Every hour at :29 — see the module docstring for why not :17 or :43.
CRON = "29 * * * *"


async def _sweep(admin, storage) -> dict:
    from app.modules.matriculas import service as matriculas_svc

    return await matriculas_svc.varrer_pendentes(admin, storage)


matriculas_sweep_job = make_sweep_job(label="matriculas", sweep=_sweep)


def configure() -> None:
    """Register the sweep on the seed-side scheduler. Idempotent.

    Must be called at IMPORT time, before `start_scheduler()` fires in
    `app/lifespan.py`, or the job is never registered and the safety net
    silently does not exist.
    """
    configure_sweep(
        job_id=JOB_ID,
        cron=CRON,
        label="matriculas",
        sweep=_sweep,
        job=matriculas_sweep_job,
    )


__all__ = ["CRON", "JOB_ID", "configure", "matriculas_sweep_job"]
