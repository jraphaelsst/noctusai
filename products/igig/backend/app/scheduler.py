"""IgIg background jobs — on the seed scheduler primitive.

``noctusai_lib.api.scheduler`` owns the AsyncIOScheduler, the misfire policy
and the ``NOCTUS_SCHEDULERS_ENABLED`` guard (only a deployed container runs
jobs). This module only REGISTERS igig's jobs; ``app/main.py`` calls
:func:`configure` and wires ``start_scheduler`` / ``stop_scheduler`` into the
lifespan.

Jobs:
  * ``igig_gmail_watch_renovar`` — daily 06:15 (São Paulo). A Gmail
    ``users.watch`` lapses after ≤7 days and then SILENTLY stops delivering;
    Google recommends renewing daily (KB § INTEGRATIONS/google.md § 5a).
  * ``igig_automacoes_sla`` — every 15 min. SLA/stale sweep of the automation
    rules → ``sla_estourado`` notification, once per stage entry (slice E2,
    roadmap R11; ``app/services/automacoes.py::varrer_sla``).
  * ``igig_pautas_extensao`` — daily 06:45 (São Paulo). Rolling calendar fill
    for every ACCEPTED orçamento (`app/services/pautas.py::estender_pendentes`)
    — the accept-time generation only ever covered the first 30 days, with
    nothing renewing it past that window or across a month boundary (achado
    17). Per-day idempotent, so a misfire/retry never duplicates a pauta.
  * ``igig_financeiro_inadimplencia`` — daily 06:00 (São Paulo). Marks overdue
    faturas `vencida` and flips clientes `inadimplente`/`ativo` off that
    (`financeiro_service.atualizar_inadimplencia` — MVP closeout: the sweep
    existed since the financeiro slice but was never registered anywhere).
  * ``igig_publicacao_fila`` — every 5 minutes. First recovers any publicação
    a crashed worker left claimed (`publicacao_publisher.liberar_travadas`),
    then drains the due-publication queue org by org
    (`publicacao_publisher.processar_fila_publicacao`) — the worker the
    router's docstring always described and nothing ever ran.
  * ``igig_lembretes_pendentes`` — every 5 minutes. Turns every DUE card-hub
    reminder (Clientes/Comercial cards) into an in-app notification
    (`app/services/notificacoes.py::processar_lembretes_pendentes` — plat
    achado #9: rows were materialised and nothing ever delivered one).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import anyio
from noctusai_lib.api import scheduler as seed_scheduler
from noctusai_lib.integrations.persistence import SupabaseRecordStore

from app import database
from app.email_deps import current_email_settings, real_gmail_client
from app.config import settings
from app.repositories import Repositorios
from app.services import financeiro_service
from app.services import notificacoes
from app.services import orcamento_email
from app.services import pautas
from app.services import publicacao_publisher
from app.services.automacoes import PortasAutomacao, varrer_sla
from app.store import get_repositorios_admin

logger = logging.getLogger(__name__)

__all__ = [
    "configure", "job_automacoes_sla", "job_financeiro_inadimplencia", "job_lembretes_pendentes",
    "job_pautas_extensao", "job_publicacao_fila", "renovar_gmail_watches_job",
    "start_scheduler", "stop_scheduler",
]

SLA_INTERVALO_MINUTOS = 15

start_scheduler = seed_scheduler.start_scheduler
stop_scheduler = seed_scheduler.stop_scheduler


async def renovar_gmail_watches_job() -> None:
    try:
        await orcamento_email.renovar_watches(
            database._db.get_admin_client(),
            get_repositorios_admin(),
            gmail_factory=real_gmail_client,
            settings=current_email_settings(),
        )
    except Exception:  # noqa: BLE001 — a job failure must be loud, not fatal to the loop
        logger.exception("job igig_gmail_watch_renovar falhou")


async def job_automacoes_sla() -> None:
    """Cross-org sweep on the igig SERVICE-ROLE client (no request, no RLS
    org); `varrer_sla` filters `org_id` on every query and isolates one rule's
    failure from the next."""
    try:
        admin = database._db.get_admin_client()
        portas = PortasAutomacao(
            db=admin, admin_db=admin, core_db=database._db.get_core_client(), cfg=settings
        )
        await varrer_sla(portas)
    except Exception:  # noqa: BLE001 — a job failure must be loud, not fatal to the loop
        logger.exception("job igig_automacoes_sla falhou")


async def job_pautas_extensao() -> None:
    try:
        admin = database._db.get_admin_client()
        await anyio.to_thread.run_sync(pautas.estender_pendentes, admin)
    except Exception:  # noqa: BLE001 — a job failure must be loud, not fatal to the loop
        logger.exception("job igig_pautas_extensao falhou")


async def job_financeiro_inadimplencia() -> None:
    try:
        admin = database._db.get_admin_client()
        await financeiro_service.atualizar_inadimplencia(admin)
    except Exception:  # noqa: BLE001 — a job failure must be loud, not fatal to the loop
        logger.exception("job igig_financeiro_inadimplencia falhou")


async def job_publicacao_fila() -> None:
    try:
        admin = database._db.get_admin_client()
        repos = Repositorios(SupabaseRecordStore(admin))
        agora = datetime.now(timezone.utc)
        recuperadas = await anyio.to_thread.run_sync(
            lambda: publicacao_publisher.liberar_travadas(admin, agora=agora)
        )
        if recuperadas:
            logger.info("job igig_publicacao_fila: %d travada(s) recuperada(s)", recuperadas)
        pendentes = await anyio.to_thread.run_sync(
            lambda: publicacao_publisher.orgs_com_publicacao_pendente(admin, agora.isoformat())
        )
        for org_id in pendentes:
            try:
                await publicacao_publisher.processar_fila_publicacao(
                    repos, org_id, settings, agora=agora
                )
            except Exception:  # noqa: BLE001 — one org's failure must not stop the sweep
                logger.exception("job igig_publicacao_fila falhou org=%s", org_id)
    except Exception:  # noqa: BLE001 — a job failure must be loud, not fatal to the loop
        logger.exception("job igig_publicacao_fila falhou")


async def job_lembretes_pendentes() -> None:
    try:
        admin = database._db.get_admin_client()
        core = database._db.get_core_client()
        resumo = await anyio.to_thread.run_sync(
            notificacoes.processar_lembretes_pendentes, admin, core
        )
        if resumo.get("processados"):
            logger.info("job igig_lembretes_pendentes: %s", resumo)
    except Exception:  # noqa: BLE001 — a job failure must be loud, not fatal to the loop
        logger.exception("job igig_lembretes_pendentes falhou")


def configure() -> None:
    seed_scheduler.register(
        "igig_gmail_watch_renovar", renovar_gmail_watches_job,
        cron="15 6 * * *", misfire_grace_time=3600,
    )
    seed_scheduler.register(
        "igig_automacoes_sla", job_automacoes_sla, minutes=SLA_INTERVALO_MINUTOS,
    )
    seed_scheduler.register(
        "igig_pautas_extensao", job_pautas_extensao,
        cron="45 6 * * *", misfire_grace_time=3600,
    )
    seed_scheduler.register(
        "igig_financeiro_inadimplencia", job_financeiro_inadimplencia,
        cron="0 6 * * *", misfire_grace_time=3600,
    )
    seed_scheduler.register(
        "igig_publicacao_fila", job_publicacao_fila, minutes=5,
    )
    seed_scheduler.register(
        "igig_lembretes_pendentes", job_lembretes_pendentes, minutes=5,
    )
