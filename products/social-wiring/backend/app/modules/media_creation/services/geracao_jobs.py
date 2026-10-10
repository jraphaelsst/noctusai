"""The Geração job layer: handler registry + the ``geracao`` and ``biblioteca`` workers.

Two seed ``domain.jobs.Worker`` loops over ``social_wiring.jobs`` (contract
``specs/geracao-contract.md`` section 3.1), each owned by a seed ``WorkerHandle`` and started /
stopped through the ``ModuleRegistration`` startup / shutdown hooks of
``media_creation.register()``:

=============  ===========================================================  ============================
Worker         Job types                                                    Switch
=============  ===========================================================  ============================
``geracao``    ``headline.gerar`` · ``roteiro.perguntas`` · ``roteiro.gerar``  env ``GERACAO_WORKER_ENABLED``
``biblioteca`` ``biblioteca.sync_perfil`` · ``.classificar`` · ``.transcrever`` platform setting
                                                                            ``biblioteca_ingestao_habilitada``
                                                                            (DB first, then env, **default OFF**)
=============  ===========================================================  ============================

The slices that own a job type register their handler with :func:`register_handler` (at import,
from their own module): BE-2 the three ``biblioteca.*``, BE-4 ``headline.gerar``, BE-5 the two
``roteiro.*``. A handler is ``async def handler(job: Job) -> None`` and gets its DB / config from
its own service. Handlers are resolved at call time, so a module imported after the worker was
built still serves. A job whose type has no handler is dead-lettered (loud), never dropped.

``on_dead_letter`` (optional per handler) is what keeps a UI from showing a spinner forever when a
queue row dead-letters: :mod:`app.modules.media_creation.geracao_scheduler` sweeps the dead-lettered
rows and calls it so the DOMAIN row moves to ``falha``.

The library claim gate is **fail-closed**: an unreadable ``biblioteca_ingestao_habilitada`` reads
as OFF, and the setting is OFF until the owner flips it (security review, contract 9.2).
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
from typing import Any, Awaitable, Callable, Optional, Union

from fastapi import HTTPException

from noctusai_lib.integrations.llm import LLMBudgetExceeded, enforce_budget

from noctusai_lib.domain.jobs import (
    DeadLetterError,
    Job,
    JobRepository,
    RetryPolicy,
    Worker,
    make_job_repository,
)
from noctusai_lib.domain.jobs.lifecycle import WorkerHandle

logger = logging.getLogger(__name__)

SCHEMA = "social_wiring"
STOP_TIMEOUT_SECONDS = 10.0
#: 2 retries, 5 s apart (contract 3.1): an infra blip, not a storm. A missing row is a
#: ``DeadLetterError`` in the handler, which skips the retries.
RETRY_POLICY = RetryPolicy(max_retries=2, backoff_seconds=5.0)

GERACAO_JOB_TYPES: tuple[str, ...] = ("headline.gerar", "roteiro.perguntas", "roteiro.gerar")
BIBLIOTECA_JOB_TYPES: tuple[str, ...] = (
    "biblioteca.sync_perfil",
    "biblioteca.classificar",
    "biblioteca.transcrever",
)
ALL_JOB_TYPES: tuple[str, ...] = GERACAO_JOB_TYPES + BIBLIOTECA_JOB_TYPES

#: The platform setting that gates library ingestion (DB first, then env
#: ``BIBLIOTECA_INGESTAO_HABILITADA``). Default OFF.
INGESTAO_SWITCH_KEY = "biblioteca_ingestao_habilitada"
_TRUTHY = {"1", "true", "yes", "on", "sim", "ligado"}

Handler = Callable[[Job], Union[Awaitable[None], None]]
#: ``(db, job) -> None``: move the job's domain row to ``falha`` (idempotent, terminal rows untouched).
DeadLetterReconciler = Callable[[Any, Job], None]

_handlers: dict[str, Handler] = {}
_reconcilers: dict[str, DeadLetterReconciler] = {}


class HandlerAlreadyRegistered(RuntimeError):
    """Two modules claimed the same job type: a wiring bug, never silently last-wins."""


def register_handler(
    job_type: str,
    fn: Handler,
    *,
    on_dead_letter: Optional[DeadLetterReconciler] = None,
) -> None:
    """Register ``fn`` as the handler of ``job_type`` (one of :data:`ALL_JOB_TYPES`).

    Re-registering the SAME function is a no-op (import twice is harmless); a DIFFERENT
    function for a type raises :class:`HandlerAlreadyRegistered`.
    """
    if job_type not in ALL_JOB_TYPES:
        raise ValueError(f"unknown geracao job type {job_type!r}; expected one of {ALL_JOB_TYPES}")
    existing = _handlers.get(job_type)
    if existing is not None and existing is not fn:
        raise HandlerAlreadyRegistered(f"job type {job_type!r} already has a handler ({existing!r})")
    _handlers[job_type] = fn
    if on_dead_letter is not None:
        _reconcilers[job_type] = on_dead_letter


def get_handler(job_type: str) -> Optional[Handler]:
    return _handlers.get(job_type)


def get_reconciler(job_type: str) -> Optional[DeadLetterReconciler]:
    return _reconcilers.get(job_type)


def clear_handlers() -> None:
    """Test seam: empty the registry (the registry is process-global)."""
    _handlers.clear()
    _reconcilers.clear()


def _dispatcher(job_type: str) -> Callable[[Job], Awaitable[None]]:
    async def dispatch(job: Job) -> None:
        fn = _handlers.get(job_type)
        if fn is None:
            raise DeadLetterError(f"nenhum handler registrado para {job_type}")
        result = fn(job)
        if asyncio.iscoroutine(result):
            await result

    return dispatch


def worker_id(name: str) -> str:
    return f"sw-{name}-{socket.gethostname()}-{os.getpid()}"


def make_jobs_repository(db: Any) -> JobRepository:
    """The queue repo over the ``social_wiring``-default admin client."""
    return make_job_repository(supabase_client=db, schema_name=SCHEMA)


# ── the library switch (fail-closed) ───────────────────────────────────────────


def read_ingestao_habilitada(resolver: Optional[Callable[[str], Optional[str]]] = None) -> bool:
    """``biblioteca_ingestao_habilitada``: platform_settings first, then env; default OFF.

    ``resolver`` is the DI seam (default: the seed ``resolve_credential`` chain). An unreadable
    switch reads as OFF -- ingestion fetches third-party media and spends LLM money, so "we could
    not check" must never mean "go"."""
    if resolver is None:
        from noctusai_lib.config.credentials import resolve_credential as resolver
    try:
        value = resolver(INGESTAO_SWITCH_KEY)
    except Exception:  # noqa: BLE001 - an unreadable switch reads as OFF (fail closed)
        logger.exception("geracao: could not read %s; treating as OFF", INGESTAO_SWITCH_KEY)
        return False
    return str(value or "").strip().lower() in _TRUTHY


OPTOUT_CONTATO_KEY = "biblioteca_optout_contato"


def read_optout_contato(resolver: Optional[Callable[[str], Optional[str]]] = None) -> str:
    """``biblioteca_optout_contato``: platform_settings first, then env
    ``BIBLIOTECA_OPTOUT_CONTATO``, then ``settings.biblioteca_optout_contato``.

    The e-mail where a third-party creator asks not to be monitored (LGPD data-subject channel).
    An unreadable chain falls back to the configured default -- a creator must always have a
    contact to write to. The privacy policy carries a static copy of the default."""
    from app.config import settings

    if resolver is None:
        from noctusai_lib.config.credentials import resolve_credential as resolver
    try:
        value = resolver(OPTOUT_CONTATO_KEY)
    except Exception:  # noqa: BLE001 - fall back to the configured default, never to "no contact"
        logger.exception("geracao: could not read %s; using the configured default", OPTOUT_CONTATO_KEY)
        value = None
    return str(value or "").strip() or settings.biblioteca_optout_contato


class _CachedSwitch:
    """A short TTL around a blocking switch read (the claim gate runs on every poll)."""

    def __init__(self, reader: Callable[[], bool], ttl_s: float) -> None:
        import time

        self._reader = reader
        self._ttl = ttl_s
        self._at = float("-inf")
        self._value = False
        self._clock = time.monotonic

    def __call__(self) -> bool:
        now = self._clock()
        if now - self._at >= self._ttl:
            self._value = bool(self._reader())
            self._at = now
        return self._value


# ── workers ────────────────────────────────────────────────────────────────────


def build_geracao_worker(repo: JobRepository, cfg: Any) -> Worker:
    return Worker(
        repo,
        worker_id=worker_id("geracao"),
        handlers={t: _dispatcher(t) for t in GERACAO_JOB_TYPES},
        retry_policy=RETRY_POLICY,
        poll_interval_seconds=float(cfg.geracao_poll_seconds),
        lease_seconds=float(cfg.geracao_lease_seconds),
    )


def build_biblioteca_worker(
    repo: JobRepository,
    cfg: Any,
    switch: Callable[[], bool] = read_ingestao_habilitada,
) -> Worker:
    gate = _CachedSwitch(switch, float(cfg.biblioteca_gate_ttl_seconds))

    async def claim_gate() -> bool:
        return await asyncio.to_thread(gate)

    return Worker(
        repo,
        worker_id=worker_id("biblioteca"),
        handlers={t: _dispatcher(t) for t in BIBLIOTECA_JOB_TYPES},
        retry_policy=RETRY_POLICY,
        poll_interval_seconds=float(cfg.biblioteca_poll_seconds),
        lease_seconds=float(cfg.biblioteca_lease_seconds),
        claim_gate=claim_gate,
    )


geracao_handle: Optional[WorkerHandle] = None
biblioteca_handle: Optional[WorkerHandle] = None


def _running(handle: Optional[WorkerHandle]) -> bool:
    return handle is not None and handle.is_running()


def _resolve_db(db: Any, label: str) -> Any:
    """The admin client, or ``None`` (logged) when the process cannot serve a worker."""
    if db is not None:
        return db
    from app.dependencies import _use_sqlite, get_admin_client

    if _use_sqlite:
        logger.warning("%s: worker não iniciado — requer o Supabase (backend sqlite).", label)
        return None
    db = get_admin_client()
    if db is None:
        logger.warning("%s: worker não iniciado — sem cliente admin do Supabase.", label)
    return db


async def start_geracao_worker(
    cfg: Any = None, *, db: Any = None, repo: Optional[JobRepository] = None
) -> bool:
    """Start the ``geracao`` worker. Returns whether it is running."""
    if cfg is None:
        from app.config import settings as cfg
    if not cfg.geracao_worker_enabled:
        logger.info("geracao: worker DESLIGADO (GERACAO_WORKER_ENABLED=false).")
        return False
    global geracao_handle
    if _running(geracao_handle):
        return True
    if repo is None:
        db = _resolve_db(db, "geracao")
        if db is None:
            return False
        repo = make_jobs_repository(db)
    geracao_handle = WorkerHandle(
        build_geracao_worker(repo, cfg), name="geracao-worker", stop_timeout=STOP_TIMEOUT_SECONDS
    )
    geracao_handle.start()
    logger.info("geracao: worker iniciado (%s).", worker_id("geracao"))
    return True


async def stop_geracao_worker() -> None:
    global geracao_handle
    handle, geracao_handle = geracao_handle, None
    if handle is not None:
        await handle.stop()


async def start_biblioteca_worker(
    cfg: Any = None,
    *,
    db: Any = None,
    repo: Optional[JobRepository] = None,
    switch: Callable[[], bool] = read_ingestao_habilitada,
) -> bool:
    """Start the ``biblioteca`` worker. It claims NOTHING while ``biblioteca_ingestao_habilitada``
    is off (the default), so starting it is always safe."""
    if cfg is None:
        from app.config import settings as cfg
    global biblioteca_handle
    if _running(biblioteca_handle):
        return True
    if repo is None:
        db = _resolve_db(db, "biblioteca")
        if db is None:
            return False
        repo = make_jobs_repository(db)
    biblioteca_handle = WorkerHandle(
        build_biblioteca_worker(repo, cfg, switch), name="biblioteca-worker", stop_timeout=STOP_TIMEOUT_SECONDS
    )
    biblioteca_handle.start()
    logger.info("biblioteca: worker iniciado (%s) — só processa com a ingestão habilitada.", worker_id("biblioteca"))
    return True


async def stop_biblioteca_worker() -> None:
    global biblioteca_handle
    handle, biblioteca_handle = biblioteca_handle, None
    if handle is not None:
        await handle.stop()


async def startup_hook(starters: Optional[list] = None) -> None:
    """``ModuleRegistration.startup`` hook: both workers, each isolated (a failure is logged at
    ERROR and never aborts startup: a worker is a side effect, not a precondition for serving)."""
    # ``starters``: DI seam, ``[(label, async callable)]``; default = both workers.
    for label, start in starters or (("geracao", start_geracao_worker), ("biblioteca", start_biblioteca_worker)):
        try:
            await start()
        except Exception:
            logger.exception("%s: worker NÃO iniciado — os jobs ficam na fila.", label)


async def shutdown_hook() -> None:
    """``ModuleRegistration.shutdown`` hook."""
    for label, stop in (("geracao", stop_geracao_worker), ("biblioteca", stop_biblioteca_worker)):
        try:
            await stop()
        except Exception:
            logger.exception("%s: erro ao parar o worker", label)


def assert_geracao_disponivel(cfg: Any = None) -> None:
    """Submit-side guard: 503 ``geracao_indisponivel`` when the ``geracao`` worker is switched off
    (a job enqueued while nothing will ever claim it is a spinner forever)."""
    if cfg is None:
        from app.config import settings as cfg
    if not cfg.geracao_worker_enabled:
        raise HTTPException(
            status_code=503,
            detail={"code": "geracao_indisponivel", "message": "A geração está indisponível no momento."},
        )


MSG_ORCAMENTO_IA = "O orçamento de IA da organização foi excedido."


async def assert_orcamento_ia(
    org_id: Optional[str], *, enforce: Callable[[Optional[str]], Awaitable[None]] = enforce_budget
) -> None:
    """Submit-side guard (contract 9.4): 503 ``orcamento_ia_excedido`` BEFORE a job is enqueued, via the
    seed's ``enforce_budget`` pre-check (fail-open by the seed's own design when the budget module is
    unconfigured or its read fails; the worker still settles ``falha`` if the cap is crossed mid-queue)."""
    try:
        await enforce(org_id)
    except LLMBudgetExceeded as exc:
        raise HTTPException(
            status_code=503, detail={"code": "orcamento_ia_excedido", "message": MSG_ORCAMENTO_IA}
        ) from exc


def is_running() -> dict[str, bool]:
    return {"geracao": _running(geracao_handle), "biblioteca": _running(biblioteca_handle)}


__all__ = [
    "ALL_JOB_TYPES",
    "BIBLIOTECA_JOB_TYPES",
    "GERACAO_JOB_TYPES",
    "INGESTAO_SWITCH_KEY",
    "HandlerAlreadyRegistered",
    "assert_geracao_disponivel",
    "build_biblioteca_worker",
    "build_geracao_worker",
    "clear_handlers",
    "get_handler",
    "get_reconciler",
    "is_running",
    "make_jobs_repository",
    "read_ingestao_habilitada",
    "register_handler",
    "shutdown_hook",
    "start_biblioteca_worker",
    "start_geracao_worker",
    "startup_hook",
    "stop_biblioteca_worker",
    "stop_geracao_worker",
]
