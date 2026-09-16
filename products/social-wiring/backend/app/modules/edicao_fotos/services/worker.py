"""Lifecycle of the photo-editing job worker (seed `domain.jobs.Worker`).

Two switches, deliberately different (W8):

- **Hard kill switch** — `EDICAO_FOTOS_WORKER_ENABLED` (env, default ON).
  Off ⇒ the worker is never built in this process.
- **Live pause** — `fotos_platform_settings.processamento_ativo` (the UI
  toggle, default OFF). The worker is built and running, but its claim gate
  (`ProcessingGate`) answers "closed" until a platform admin turns it on —
  so it is ready for when OpenAI has credits (PROJECT.md §4c) without
  spending anything before that, and pausing/resuming needs no redeploy.

Started from `app/lifespan.py`. "When the process allows it": a process
that cannot build the engine ports (SQLite dev backend, no service role)
logs why and keeps serving — the worker is a side effect, never a
precondition. One worker task per process; the job table's lease
(`claim_next_job`) keeps several processes from running the same job.

The same start also runs the model-catalog refresher: every process
reloads the platform admin's catalog overrides (`llm.catalog_overrides`)
on a timer, so a price saved through another process reaches this one.

`status()` describes THIS process only — the panel says so.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from noctusai_lib.domain.photo_editing import ProcessingGate, build_worker
from noctusai_lib.domain.jobs import Worker
from noctusai_lib.integrations.llm import ModelCatalogStore, refresh_model_overrides

from app.modules.edicao_fotos.services import ports as ports_service

logger = logging.getLogger(__name__)

STOP_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class WorkerStatus:
    """What this process's worker is doing (the processing panel reads it)."""

    kill_switch_ativo: bool = True  # env EDICAO_FOTOS_WORKER_ENABLED
    rodando: bool = False
    worker_id: Optional[str] = None
    iniciado_em: Optional[datetime] = None
    #: Why it is not running, when it is not (pt-BR, operator-facing).
    motivo_parado: Optional[str] = None
    #: The claim gate's last read failure (the worker is paused while set).
    erro_gate: Optional[str] = None
    catalogo_atualizado_em: Optional[datetime] = None
    erro_catalogo: Optional[str] = None


_task: Optional[asyncio.Task] = None
_refresher: Optional[asyncio.Task] = None
_stop: Optional[asyncio.Event] = None
_worker: Optional[Worker] = None
_gate: Optional[ProcessingGate] = None
_status = WorkerStatus(motivo_parado="Worker ainda não iniciado neste processo.")


def worker_id() -> str:
    return f"sw-edicao-fotos-{socket.gethostname()}-{os.getpid()}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _set_status(**changes: Any) -> None:
    global _status
    _status = replace(_status, **changes)


async def refresh_catalog(store: ModelCatalogStore) -> Optional[int]:
    """Reload the catalog overlay now. Returns the override count, or
    ``None`` when the read failed — logged at ERROR, recorded on the status
    (the panel shows it), and the previous overlay stays in force."""
    try:
        count = await refresh_model_overrides(store)
    except Exception as exc:  # noqa: BLE001 — surfaced via log + status, never swallowed
        logger.exception("edicao_fotos: catálogo de modelos NÃO recarregado")
        _set_status(erro_catalogo=f"{type(exc).__name__}: {exc}")
        return None
    _set_status(catalogo_atualizado_em=_now(), erro_catalogo=None)
    return count


async def _refresh_loop(store: ModelCatalogStore, interval: float, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except asyncio.TimeoutError:
            pass
        await refresh_catalog(store)  # a failure is logged + on the status; retried next tick


async def start_worker(
    cfg: Any,
    *,
    ports_factory: Optional[Callable[[Any], Any]] = None,
    store_factory: Optional[Callable[[], ModelCatalogStore]] = None,
) -> bool:
    """Start the worker (paused by the platform setting until turned on).
    Returns whether it is running."""
    global _task, _refresher, _stop, _worker, _gate
    if not cfg.edicao_fotos_worker_enabled:
        _set_status(
            kill_switch_ativo=False,
            rodando=False,
            motivo_parado="Desligado pela variável EDICAO_FOTOS_WORKER_ENABLED=false.",
        )
        logger.info("edicao_fotos: worker DESLIGADO (EDICAO_FOTOS_WORKER_ENABLED=false).")
        return False
    if _task is not None and not _task.done():
        return True
    try:
        ports = (ports_factory or ports_service.get_ports)(cfg)
        store = (store_factory or ports_service.get_catalog_store)()
    except ports_service.EdicaoFotosUnavailable as exc:
        _set_status(kill_switch_ativo=True, rodando=False, motivo_parado=str(exc))
        logger.warning("edicao_fotos: worker não iniciado — %s", exc)
        return False
    # A failed first load is logged + on the status; the static catalog
    # serves until the refresher's next tick succeeds.
    await refresh_catalog(store)
    _gate = ProcessingGate(ports, ttl_seconds=float(cfg.edicao_fotos_gate_ttl_seconds))
    _worker = build_worker(
        ports,
        worker_id=worker_id(),
        poll_interval_seconds=float(cfg.edicao_fotos_worker_poll_seconds),
        claim_gate=_gate,
    )
    _stop = asyncio.Event()
    _task = asyncio.create_task(_worker.run_forever(stop_event=_stop), name="edicao-fotos-worker")
    _refresher = asyncio.create_task(
        _refresh_loop(store, float(cfg.edicao_fotos_catalog_refresh_seconds), _stop),
        name="edicao-fotos-catalog-refresh",
    )
    _set_status(
        kill_switch_ativo=True,
        rodando=True,
        worker_id=worker_id(),
        iniciado_em=_now(),
        motivo_parado=None,
    )
    logger.info(
        "edicao_fotos: worker iniciado (%s) — só processa com 'processamento ativo' ligado.",
        worker_id(),
    )
    return True


async def stop_worker() -> None:
    global _task, _refresher, _stop, _worker, _gate
    if _task is None:
        return
    assert _stop is not None
    _stop.set()
    for task in (_task, _refresher):
        if task is None:
            continue
        try:
            await asyncio.wait_for(task, timeout=STOP_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning("edicao_fotos: tarefa %s não parou em %.0fs — cancelando",
                           task.get_name(), STOP_TIMEOUT_SECONDS)
            task.cancel()
    _task = _refresher = _stop = _worker = _gate = None
    _set_status(rodando=False, motivo_parado="Worker parado (desligamento do processo).")


def is_running() -> bool:
    return _task is not None and not _task.done()


def invalidate_gate() -> None:
    """Make this process's worker re-read `processamento_ativo` on its next
    claim (other processes pick the change up within the gate TTL)."""
    if _gate is not None:
        _gate.invalidate()


def status() -> WorkerStatus:
    running = is_running()
    current = _status
    if current.rodando and not running:
        # The task ended on its own — never report a dead worker as alive.
        current = replace(current, rodando=False, motivo_parado="O worker terminou inesperadamente; veja os logs.")
    if _worker is not None:
        current = replace(current, erro_gate=_worker.last_gate_error)
    return current


__all__ = [
    "WorkerStatus",
    "invalidate_gate",
    "is_running",
    "refresh_catalog",
    "start_worker",
    "status",
    "stop_worker",
    "worker_id",
]
