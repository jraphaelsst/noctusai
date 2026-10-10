"""``transcricoes`` dependency seams (storage, queue, transcriber, kill switch, admin).

Every seam is a real production seam that tests replace through
``app.dependency_overrides`` — nothing here is monkeypatched.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

from noctusai_lib.domain.jobs import JobRepository, make_job_repository
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.integrations.transcription import Transcriber, make_transcriber

from app.dependencies import get_admin_client, get_platform_admin_check  # noqa: F401 — re-export (tests override it here)
from app.modules.certidoes.deps import storage_for

logger = logging.getLogger(__name__)

SCHEMA = "social_wiring"
#: PRIVATE bucket (migration 225). Audio is personal data: deleted right after a
#: successful transcription, never served back, never public.
BUCKET = "sw-transcricoes"
#: The platform setting that gates the whole feature (DB first, then env
#: ``TRANSCRICAO_HABILITADA``). Default OFF.
KILL_SWITCH_KEY = "transcricao_habilitada"
_TRUTHY = {"1", "true", "yes", "on", "sim", "ligado"}

TranscriberFactory = Callable[[], Transcriber]
KillSwitch = Callable[[], bool]


def get_transcricao_storage() -> StorageBackend:
    """Blob storage for the audio. Tests MUST override with a ``FakeStorageBackend``."""
    return storage_for(get_admin_client())


def make_jobs_repository(db: Any) -> JobRepository:
    """The queue repo over the ``social_wiring``-default admin client."""
    return make_job_repository(supabase_client=db, schema_name=SCHEMA)


def get_transcricao_jobs() -> JobRepository:
    """Queue repo. Tests override with a ``FakeJobRepository``."""
    return make_jobs_repository(get_admin_client())


def get_transcriber_factory() -> TranscriberFactory:
    """The seed ``make_transcriber`` (env ``TRANSCRIPTION_BACKEND``). A FACTORY, not an
    instance: building a misconfigured ``local_whisper`` raises, and that must not
    pre-empt the kill-switch answer. Tests override with ``lambda: lambda: FakeTranscriber()``."""
    return make_transcriber


def read_kill_switch(resolver: Optional[Callable[[str], Optional[str]]] = None) -> bool:
    """``transcricao_habilitada``: platform_settings first, then env; default OFF.

    ``resolver`` is the DI seam (default: the seed's ``resolve_credential`` chain
    ``platform_settings`` -> env ``TRANSCRICAO_HABILITADA``)."""
    if resolver is None:
        from noctusai_lib.config.credentials import resolve_credential as resolver
    try:
        value = resolver(KILL_SWITCH_KEY)
    except Exception:  # noqa: BLE001 - an unreadable switch reads as OFF (fail closed)
        logger.exception("transcricoes: could not read %s; treating as OFF", KILL_SWITCH_KEY)
        return False
    return str(value or "").strip().lower() in _TRUTHY


def get_kill_switch() -> KillSwitch:
    """Seam for the kill switch. Tests override with ``lambda: lambda: True``."""
    return read_kill_switch


class CachedSwitch:
    """TTL cache over a kill-switch reader, for the worker's per-poll claim gate
    (an un-cached read would hit the DB every 2 seconds)."""

    def __init__(self, reader: KillSwitch, ttl_s: float) -> None:
        self._reader = reader
        self._ttl = ttl_s
        self._at = 0.0
        self._value = False

    def __call__(self) -> bool:
        now = time.monotonic()
        if now - self._at >= self._ttl:
            self._value = bool(self._reader())
            self._at = now
        return self._value


__all__ = [
    "BUCKET",
    "CachedSwitch",
    "KILL_SWITCH_KEY",
    "SCHEMA",
    "get_kill_switch",
    "get_platform_admin_check",
    "get_transcricao_jobs",
    "get_transcricao_storage",
    "get_transcriber_factory",
    "make_jobs_repository",
    "read_kill_switch",
]
