"""Lifecycle of the Julia re-engagement worker (seed `domain.jobs.Worker`, wave 4).

Its OWN worker over the three job types of `julia_reengajamento_service` (a lead turn is an HTTP call to
agents; it must not queue behind -- or hold a lease of -- the Geracao / Biblioteca workers). Started and
stopped through the `ModuleRegistration` startup / shutdown hooks in `app/main.py`; "when the process
allows it": no Supabase admin client logs why and keeps serving -- a worker is a side effect, never a
precondition for serving. The queue row lease keeps several processes from running the same job.

The handler builds its `LeadDeps` at FIRE time from the conversation module (the Redis buffer lives
there); until that module exists the job reschedules itself rather than failing.

🔴 This worker SENDS WhatsApp messages to real leads (re-engagement, réguas, review asks), so it starts only where
the seed's `schedulers_enabled()` holds -- `NOCTUS_SCHEDULERS_ENABLED`, which only the deployed container's compose
block carries, never `.env`. A laptop that loaded the prod `.env` therefore never drains the prod queue.
`JULIA_REENGAJAMENTO_WORKER_ENABLED=false` remains the per-deploy kill switch on top.
"""
from __future__ import annotations

import logging
import os
import socket
from typing import Any, Optional

from noctusai_lib.api.scheduler import SCHEDULERS_ENABLED_ENV, schedulers_enabled
from noctusai_lib.domain.jobs import JobRepository, RetryPolicy, Worker, make_job_repository
from noctusai_lib.domain.jobs.lifecycle import WorkerHandle

from app.services import (
    julia_avaliacoes_service, julia_capi_service, julia_credito_service, julia_envio_service, julia_reengajamento_service as svc,
)

logger = logging.getLogger(__name__)

SCHEMA = "social_wiring"
STOP_TIMEOUT_SECONDS = 10.0
RETRY_POLICY = RetryPolicy(max_retries=svc.JOB_MAX_RETRIES, backoff_seconds=30.0)

_handle: Optional[WorkerHandle] = None


def worker_id() -> str:
    return f"sw-julia-reengajamento-{socket.gethostname()}-{os.getpid()}"


def _lead_deps_factory(cfg: Any):
    def build() -> Any:
        from app.services.conversation_module import get_conversation_module
        from app.services.julia_lead_turn_service import LeadDeps

        module = get_conversation_module()
        if module is None:
            return None
        return LeadDeps(buffer=module.buffer, admin=module.admin_supabase, cfg=cfg)

    return build


def _scoped_client() -> Any:
    from app.dependencies import get_scoped_admin_client

    return get_scoped_admin_client(SCHEMA)


def _enviador_avaliacao(cfg: Any):
    """Wave 13: the review-ask sender over the contato's own connection (built at FIRE time)."""

    def build() -> Any:
        from noctusai_lib.integrations.whatsapp import get_whatsapp_client

        from app.dependencies import get_admin_client
        from app.services.whatsapp_connection_store import build_whatsapp_connection_store

        def lookup(connection_id: Any) -> Any:
            return build_whatsapp_connection_store(get_admin_client(), encryption_key=cfg.encryption_key).get_by_id(connection_id, decrypt=True)

        return julia_avaliacoes_service.enviador_padrao(lookup, get_whatsapp_client)

    return build


def build_worker(repo: JobRepository, cfg: Any) -> Worker:
    from app.services.julia_lead_turn_service import run_reengajamento_turn

    # the cold-lead hook (end of the last attempt) arms `julia_envio_frio` on THIS repo; the same worker fires it
    julia_envio_service.registrar_repo(repo)
    julia_credito_service.registrar_repo(repo)  # the credit analysis (wave 13) is queued on the same repo
    julia_avaliacoes_service.registrar_repo(repo)  # wave 13: the review-ask job
    julia_capi_service.registrar_repo(repo)  # wave 13: the CAPI send job
    return Worker(
        repo,
        worker_id=worker_id(),
        handlers={
            **svc.handlers(deps_factory=_lead_deps_factory(cfg), repo=repo, run_turn=run_reengajamento_turn),
            **julia_envio_service.handlers(),
            **julia_credito_service.handlers(),
            **julia_avaliacoes_service.handlers(client_provider=_scoped_client, enviar_factory=_enviador_avaliacao(cfg)),
            **julia_capi_service.handlers(client_provider=_scoped_client),
        },
        retry_policy=RETRY_POLICY,
        poll_interval_seconds=float(cfg.julia_reengajamento_poll_seconds),
        lease_seconds=float(cfg.julia_reengajamento_lease_seconds),
    )


def is_running() -> bool:
    return _handle is not None and _handle.is_running()


async def start_worker(cfg: Any = None, *, db: Any = None, repo: Optional[JobRepository] = None) -> bool:
    """Start the worker. Returns whether it is running."""
    if cfg is None:
        from app.config import settings as cfg
    global _handle
    if not cfg.julia_reengajamento_worker_enabled:
        logger.info("julia reengajamento: worker DESLIGADO (JULIA_REENGAJAMENTO_WORKER_ENABLED=false).")
        return False
    if not schedulers_enabled():
        logger.info("julia reengajamento: worker DESLIGADO (%s ausente -- só o container implantado envia).", SCHEDULERS_ENABLED_ENV)
        return False
    if is_running():
        return True
    if repo is None:
        if db is None:
            from app.dependencies import _use_sqlite, get_admin_client

            if _use_sqlite:
                logger.warning("julia reengajamento: worker não iniciado — requer o Supabase (backend sqlite).")
                return False
            db = get_admin_client()
        if db is None:
            logger.warning("julia reengajamento: worker não iniciado — sem cliente admin do Supabase.")
            return False
        repo = make_job_repository(supabase_client=db, schema_name=SCHEMA)
    _handle = WorkerHandle(build_worker(repo, cfg), name="julia-reengajamento-worker", stop_timeout=STOP_TIMEOUT_SECONDS)
    _handle.start()
    logger.info("julia reengajamento: worker iniciado (%s).", worker_id())
    return True


async def stop_worker() -> None:
    global _handle
    handle, _handle = _handle, None
    if handle is not None:
        await handle.stop()
        # `build_worker` bound this worker's repo into the services' module slots; a stopped worker must not
        # keep receiving jobs (and a leaked slot silently flips every "no repo -> runs inline" path afterwards).
        for servico in (julia_envio_service, julia_credito_service, julia_avaliacoes_service, julia_capi_service):
            servico.registrar_repo(None)


async def startup_hook() -> None:
    """`ModuleRegistration.startup`: a failure is logged at ERROR and never aborts startup."""
    try:
        await start_worker()
    except Exception:
        logger.exception("julia reengajamento: worker NÃO iniciado — os timers ficam na fila.")


__all__ = ["build_worker", "is_running", "start_worker", "startup_hook", "stop_worker"]
