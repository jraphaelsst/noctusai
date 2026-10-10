"""The library transcription worker (geracao-contract 3.4): job type ``transcricao.biblioteca``.

A SECOND seed ``Worker`` (concurrency 1, lease 300 s with heartbeat) next to the voice
worker, sharing its handler (so audio is deleted right after transcription, a 503 busy is
``RescheduleLater`` without consuming a retry, the completion hook runs once) but with a
stricter ``claim_gate``. It takes the transcriber ONLY when all of these hold:

1. ``transcricao_habilitada`` is on (the same kill switch as the voice lane);
2. no ``transcricao`` (voice) job is due or running — voice answers always go first;
3. the transcriber is healthy: ``/healthz`` answers OK (cached a few seconds) AND the last
   ``FAILURE_STREAK`` calls did not all end in ``TranscriberUnavailable`` (so reels do not
   burn their retries while the transcriber restarts; after ``COOLDOWN_S`` one call is
   let through to find out whether it is back).

NOC-REMEDIATE[transcription-fairness]: the real fix is a platform-level priority queue across
SW and core (transcription-contract.md section 6); this gate is the named stand-in. — 2026-10-10
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
from typing import Any, Awaitable, Callable, Optional

import httpx
from noctusai_lib.domain.jobs import Job, JobRepository, Worker
from noctusai_lib.domain.jobs.lifecycle import WorkerHandle
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.integrations.transcription import TranscriberUnavailable

from app.modules.transcricoes.deps import (
    CachedSwitch,
    KillSwitch,
    TranscriberFactory,
    make_jobs_repository,
    read_kill_switch,
)
from app.modules.transcricoes.service import JOB_TYPE, JOB_TYPE_BIBLIOTECA
from app.modules.transcricoes.worker import RETRY_POLICY, STOP_TIMEOUT_SECONDS, build_handler

logger = logging.getLogger(__name__)

HealthProbe = Callable[[], Awaitable[bool]]

HEALTH_TTL_S = 5.0
HEALTH_TIMEOUT_S = 3.0
#: Consecutive ``TranscriberUnavailable`` outcomes that close the gate ...
FAILURE_STREAK = 3
#: ... for this long, after which a single call is let through again.
COOLDOWN_S = 60.0

_handle: Optional[WorkerHandle] = None


def worker_id() -> str:
    return f"sw-transcricao-biblioteca-{socket.gethostname()}-{os.getpid()}"


async def probe_transcriber_health() -> bool:
    """``GET {TRANSCRIBER_URL}/healthz`` for the ``local_whisper`` backend. Other backends
    (openai, fake) have no worker to restart, so they read as healthy. DI seam: the worker
    takes ``health_probe``; tests pass their own."""
    if (os.environ.get("TRANSCRIPTION_BACKEND") or "").strip().lower() != "local_whisper":
        return True
    url = (os.environ.get("TRANSCRIBER_URL") or "").strip().rstrip("/")
    if not url:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{url}/healthz", timeout=HEALTH_TIMEOUT_S)
        return resp.status_code == 200
    except httpx.HTTPError:
        logger.warning("transcricoes: transcriber /healthz unreachable")
        return False


class TranscriberHealth:
    """Cached ``/healthz`` + a consecutive-failure breaker fed by the handler's outcomes."""

    def __init__(
        self,
        probe: HealthProbe = probe_transcriber_health,
        *,
        ttl_s: float = HEALTH_TTL_S,
        streak: int = FAILURE_STREAK,
        cooldown_s: float = COOLDOWN_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._probe = probe
        self._ttl = ttl_s
        self._streak = streak
        self._cooldown = cooldown_s
        self._clock = clock
        self._probed_at: Optional[float] = None
        self._probed_ok = False
        self._failures = 0
        self._tripped_at: Optional[float] = None

    def record(self, *, unavailable: bool) -> None:
        if not unavailable:
            self._failures = 0
            self._tripped_at = None
            return
        self._failures += 1
        if self._failures >= self._streak:
            self._tripped_at = self._clock()

    def breaker_open(self) -> bool:
        if self._tripped_at is None:
            return False
        if self._clock() - self._tripped_at >= self._cooldown:
            # half-open: let one call through; a further failure re-trips at once
            self._tripped_at = None
            self._failures = self._streak - 1
            return False
        return True

    async def healthy(self) -> bool:
        if self.breaker_open():
            return False
        now = self._clock()
        if self._probed_at is None or now - self._probed_at >= self._ttl:
            try:
                self._probed_ok = bool(await self._probe())
            except Exception:  # noqa: BLE001 - an unreadable health reads as unhealthy (fail closed)
                logger.exception("transcricoes: health probe raised; treating as unhealthy")
                self._probed_ok = False
            self._probed_at = now
        return self._probed_ok


def _is_unavailable(exc: BaseException) -> bool:
    return isinstance(exc, TranscriberUnavailable) or isinstance(exc.__cause__, TranscriberUnavailable)


def _com_saude(handler: Callable[[Job], Any], health: TranscriberHealth) -> Callable[[Job], Any]:
    """Feed the breaker with each call's outcome; the handler's own behaviour is untouched."""

    async def handle(job: Job) -> None:
        try:
            await handler(job)
        except Exception as exc:  # re-raised: the Worker owns retry / dead-letter / reschedule
            health.record(unavailable=_is_unavailable(exc))
            raise
        health.record(unavailable=False)

    return handle


async def voz_ocupada(repo: JobRepository) -> bool:
    """A voice (``transcricao``) job is due, running, or running on an expired lease."""
    stats = await repo.queue_stats(job_types=[JOB_TYPE])
    return (stats.due + stats.running + stats.lease_expired) > 0


def build_worker(
    repo: JobRepository, db: Any, storage: StorageBackend, cfg: Any,
    transcriber_factory: TranscriberFactory, kill_switch: KillSwitch = read_kill_switch,
    health: Optional[TranscriberHealth] = None,
) -> Worker:
    switch = CachedSwitch(kill_switch, float(cfg.transcricao_gate_ttl_seconds))
    health = health or TranscriberHealth()

    async def claim_gate() -> bool:
        # NOC-REMEDIATE[transcription-fairness]: platform-level priority queue (SW + core) — 2026-10-10
        if not await asyncio.to_thread(switch):
            return False
        if await voz_ocupada(repo):
            return False
        return await health.healthy()

    return Worker(
        repo,
        worker_id=worker_id(),
        handlers={JOB_TYPE_BIBLIOTECA: _com_saude(build_handler(db, storage, transcriber_factory), health)},
        retry_policy=RETRY_POLICY,
        poll_interval_seconds=float(cfg.transcricao_poll_seconds),
        lease_seconds=float(cfg.transcricao_lease_seconds),
        claim_gate=claim_gate,
    )


async def start_worker(
    cfg: Any, *, db: Any = None, repo: Optional[JobRepository] = None,
    storage: Optional[StorageBackend] = None, transcriber_factory: Optional[TranscriberFactory] = None,
    health: Optional[TranscriberHealth] = None,
) -> bool:
    """Start the library worker. Returns whether it is running."""
    global _handle
    if not cfg.transcricao_worker_enabled:
        logger.info("transcricoes: worker da biblioteca DESLIGADO (TRANSCRICAO_WORKER_ENABLED=false).")
        return False
    if is_running():
        return True
    if db is None:
        from app.dependencies import _use_sqlite, get_admin_client

        if _use_sqlite:
            logger.warning("transcricoes: worker da biblioteca não iniciado — requer o Supabase (backend sqlite).")
            return False
        db = get_admin_client()
    if db is None:
        logger.warning("transcricoes: worker da biblioteca não iniciado — sem cliente admin do Supabase.")
        return False
    if storage is None:
        from app.modules.certidoes.deps import storage_for

        storage = storage_for(db)
    if transcriber_factory is None:
        from noctusai_lib.integrations.transcription import make_transcriber

        transcriber_factory = make_transcriber
    worker = build_worker(repo or make_jobs_repository(db), db, storage, cfg, transcriber_factory, health=health)
    _handle = WorkerHandle(worker, name="transcricao-biblioteca-worker", stop_timeout=STOP_TIMEOUT_SECONDS)
    _handle.start()
    logger.info("transcricoes: worker da biblioteca iniciado (%s).", worker_id())
    return True


async def stop_worker() -> None:
    global _handle
    handle, _handle = _handle, None
    if handle is not None:
        await handle.stop()


def is_running() -> bool:
    return _handle is not None and _handle.is_running()


__all__ = [
    "TranscriberHealth", "build_worker", "is_running", "probe_transcriber_health",
    "start_worker", "stop_worker", "voz_ocupada",
]
