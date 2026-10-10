"""Runtime composition for the transcription API: ONE object holding the
seams the router and worker share. Production builds it lazily from core's
settings; tests build it from the seed Fakes and hand it to the router through
FastAPI's ``dependency_overrides`` (the DI seam) — no patching of our code."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Optional

from noctusai_lib.api.scheduler import schedulers_enabled
from noctusai_lib.domain.jobs import make_job_repository
from noctusai_lib.integrations.storage import make_storage_backend
from noctusai_lib.integrations.transcription import Transcriber, make_transcriber
from noctusai_lib.integrations.transcription.factory import TOKEN_ENV, URL_ENV

from app.services.transcription_api import limits as L
from app.services.transcription_api.auth import TranscricaoAuth, build_default_auth
from app.services.transcription_api.repository import SupabaseTranscricaoRepo
from app.services.transcription_api.service import TranscricaoService
from app.services.transcription_api.worker import TranscricaoBackground

logger = logging.getLogger(__name__)


@dataclass
class TranscricaoRuntime:
    service: TranscricaoService
    auth: TranscricaoAuth
    burst: L.BurstLimiter
    background: Optional[TranscricaoBackground] = None

    def worker_saudavel(self) -> bool:
        return self.background is not None and self.background.running()


def build_transcriber(settings: Any) -> Transcriber:
    """``make_transcriber`` driven by core settings. ``local_whisper`` without
    URL/token RAISES (the seed factory's ``TranscriptionNotConfigured``) —
    never a silent fallback to OpenAI."""
    # The seed factory reads these two from os.environ; core's settings are the
    # source of truth for .env-file deployments, so bridge them (never override
    # a non-empty value the process environment already carries).
    for env, value in ((URL_ENV, getattr(settings, "transcriber_url", "")),
                       (TOKEN_ENV, getattr(settings, "transcriber_token", ""))):
        if value and not os.environ.get(env, "").strip():
            os.environ[env] = value
    return make_transcriber(getattr(settings, "transcription_backend", "") or None)


def build_runtime(*, settings: Any, limiter: Any, admin_client_fn: Callable[[], Any]) -> TranscricaoRuntime:
    client = admin_client_fn()
    jobs = make_job_repository(supabase_client=client, schema_name="public")
    transcriber_cache: dict[str, Transcriber] = {}

    def get_transcriber() -> Transcriber:
        if "t" not in transcriber_cache:
            transcriber_cache["t"] = build_transcriber(settings)
        return transcriber_cache["t"]

    service = TranscricaoService(
        repo=SupabaseTranscricaoRepo(client),
        jobs=jobs,
        storage=make_storage_backend(kind="supabase", client=client),
        get_transcriber=get_transcriber,
        kill_switch=L.KillSwitch(L.read_kill_switch_setting),
        limits=L.build_limits(settings.transcription_api_max_s),
    )
    return TranscricaoRuntime(
        service=service,
        auth=build_default_auth(),
        burst=L.BurstLimiter(limiter),
        background=TranscricaoBackground(service, jobs),
    )


_runtime: Optional[TranscricaoRuntime] = None


def get_runtime() -> TranscricaoRuntime:
    """FastAPI dependency (override in tests via ``app.dependency_overrides``)."""
    global _runtime
    if _runtime is None:
        from app.config import settings
        from app.database import get_admin_client
        from app.rate_limit import limiter

        _runtime = build_runtime(settings=settings, limiter=limiter, admin_client_fn=get_admin_client)
    return _runtime


async def start_transcription_worker() -> None:
    """Lifespan hook. Like every core background job it only runs in a process
    that carries ``NOCTUS_SCHEDULERS_ENABLED`` — a laptop on the prod ``.env``
    must not drain the production queue."""
    if not schedulers_enabled():
        logger.info("transcricao.worker_skipped (schedulers disabled in this process)")
        return
    runtime = get_runtime()
    await runtime.background.start()
    logger.info("transcricao.worker_started")


async def stop_transcription_worker() -> None:
    if _runtime is not None and _runtime.background is not None:
        await _runtime.background.stop()
