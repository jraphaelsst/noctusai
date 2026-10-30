"""Runtime composition for the brand identity API — ONE object holding the seams
the router and the worker share. Production builds it lazily from core's
settings; tests build it from the seed Fakes and hand it to the router through
``app.dependency_overrides[get_runtime]`` (the DI seam) — nothing is patched."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from noctusai_lib.api.scheduler import schedulers_enabled
from noctusai_lib.domain.jobs import RetryPolicy, Worker, make_job_repository
from noctusai_lib.integrations.storage import make_storage_backend

from app.services.brand.repository import SupabaseBrandRepo
from app.services.brand.service import JOB_TYPE, BrandService

logger = logging.getLogger(__name__)

#: Per-org ingestion ceiling (each run is a paid LLM call).
INGEST_RATE = "10/hour"
POLL_INTERVAL_S = 2.0
LEASE_SECONDS = 180.0

Authenticate = Callable[[Optional[str], Any], Awaitable[tuple]]


class IngestRateLimit:
    """Per-org hit counter on core's limiter strategy (Redis-backed when configured)."""

    def __init__(self, limiter: Any, spec: str = INGEST_RATE) -> None:
        from limits import parse

        self._strategy = limiter.limiter
        self._item = parse(spec)

    def allow(self, org_id: str) -> bool:
        return bool(self._strategy.hit(self._item, "brand_ingest", org_id))


class AllowAll:
    def allow(self, org_id: str) -> bool:  # noqa: ARG002 — test/dev seam
        return True


@dataclass
class BrandRuntime:
    service: BrandService
    authenticate: Authenticate
    ingest_limit: Any
    worker: Optional["BrandWorker"] = None


def build_worker(service: BrandService, *, worker_id: str = "core-brand-1") -> Worker:
    return Worker(
        service.jobs,
        worker_id=worker_id,
        handlers={JOB_TYPE: service.handle_job},
        retry_policy=RetryPolicy(max_retries=0),
        poll_interval_seconds=POLL_INTERVAL_S,
        lease_seconds=LEASE_SECONDS,
    )


class BrandWorker:
    def __init__(self, service: BrandService) -> None:
        self.worker = build_worker(service)
        self._stop: Optional[asyncio.Event] = None
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop = asyncio.Event()
        self._task = asyncio.ensure_future(self._supervise())

    async def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _supervise(self) -> None:
        """Restart a crashed loop (logged with traceback) instead of dying silent."""
        while not self._stop.is_set():
            try:
                await self.worker.run_forever(stop_event=self._stop)
                return
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("brand.worker_crashed — restarting in 10s")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=10)
                except asyncio.TimeoutError:
                    pass


def build_runtime(*, limiter: Any, admin_client_fn: Callable[[], Any]) -> BrandRuntime:
    from app.dependencies import get_current_user
    from app.services.permissions import require_org_permission

    client = admin_client_fn()
    service = BrandService(
        repo=SupabaseBrandRepo(client),
        storage=make_storage_backend(kind="supabase", client=client),
        jobs=make_job_repository(supabase_client=client, schema_name="public"),
        get_core_client=admin_client_fn,
        require_permission=require_org_permission,
    )

    async def authenticate(authorization: Optional[str], request: Any) -> tuple:
        return await get_current_user(authorization, request)

    return BrandRuntime(
        service=service, authenticate=authenticate,
        ingest_limit=IngestRateLimit(limiter), worker=BrandWorker(service),
    )


_runtime: Optional[BrandRuntime] = None


def get_runtime() -> BrandRuntime:
    """FastAPI dependency (override in tests via ``app.dependency_overrides``)."""
    global _runtime
    if _runtime is None:
        from app.database import get_admin_client
        from app.rate_limit import limiter

        _runtime = build_runtime(limiter=limiter, admin_client_fn=get_admin_client)
    return _runtime


async def start_brand_worker() -> None:
    """Lifespan hook — only in a process carrying ``NOCTUS_SCHEDULERS_ENABLED``."""
    if not schedulers_enabled():
        logger.info("brand.worker_skipped (schedulers disabled in this process)")
        return
    runtime = get_runtime()
    await runtime.worker.start()
    logger.info("brand.worker_started")


async def stop_brand_worker() -> None:
    if _runtime is not None and _runtime.worker is not None:
        await _runtime.worker.stop()
