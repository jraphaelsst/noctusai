"""Every cap, window and timeout of the transcription API, in ONE place
(CONTRACT §3 / §5). The durable quotas (per caller / org / global) live in the
SQL RPC ``reservar_transcricao_api``; what is here is the Python side."""
from __future__ import annotations

import math
import time
from datetime import timedelta
from typing import Any, Callable, Optional

from noctusai_lib.integrations.transcription import TranscriptionLimits

MIB = 1024 * 1024

#: Max upload (stream cut here -> 413 ``arquivo_grande``).
MAX_UPLOAD_BYTES = 150 * MIB
#: multipart framing + form fields ride on top of the file bytes; the body-size
#: middleware is set to ``MAX_UPLOAD_BYTES + MULTIPART_SLACK_BYTES`` so the
#: handler (not the middleware) is what answers an over-cap file with the
#: ``{codigo, mensagem}`` envelope.
MULTIPART_SLACK_BYTES = 1 * MIB
MIN_DURATION_S = 1.0
#: Contract ceiling (45 min). Until slice E raises the worker cap, the
#: *effective* ceiling is ``settings.transcription_api_max_s`` (default 600).
CONTRACT_MAX_DURATION_S = 45 * 60.0

ROTULO_MAX_CHARS = 120
LANGUAGES = frozenset({"pt", "en", "es"})

JOB_TYPE = "transcricao_api"
JOB_MAX_RETRIES = 2
LEASE_SECONDS = 300.0
POLL_INTERVAL_S = 2.0

#: Rough real-time factor used ONLY for the ``estimativa_s`` hint.
RTF_ESTIMADO = 0.5

AUDIO_RETENTION_FAILED = timedelta(hours=72)
TEXT_RETENTION = timedelta(days=30)
SWEEP_INTERVAL_S = 15 * 60

#: Burst limits keyed by caller identity (CONTRACT §3).
BURST_POLICY = {"POST": "10/minute", "GET": "120/minute", "DELETE": "30/minute"}

KILL_SWITCH_KEY = "transcricao_api_habilitada"
KILL_SWITCH_TTL_S = 15.0
KILL_SWITCH_RETRY_AFTER_S = 300.0
TRANSCRIBER_RETRY_AFTER_S = 30.0

BUCKET = "core-transcricoes"


def build_limits(max_duration_s: float) -> TranscriptionLimits:
    """The core override of the seed ``TranscriptionLimits`` (150 MB, 1 s min,
    duration = the effective ceiling, never above the 45-min contract cap)."""
    return TranscriptionLimits(
        max_bytes=MAX_UPLOAD_BYTES,
        max_duration_s=min(float(max_duration_s), CONTRACT_MAX_DURATION_S),
        min_duration_s=MIN_DURATION_S,
    )


def call_timeout_s(duracao_s: float) -> float:
    """Worker call timeout: ``3 x duracao + 60`` s (CONTRACT §3)."""
    return 3.0 * float(duracao_s) + 60.0


def stuck_deadline(duracao_s: float, *, started: bool) -> timedelta:
    """How long a job may stay unfinished before the sweep fails it: ``3 x
    duracao + 1 h`` after ``iniciado_em``; 6 h after ``criado_em`` if never
    started (CONTRACT §3 Timeouts)."""
    if started:
        return timedelta(seconds=3.0 * float(duracao_s)) + timedelta(hours=1)
    return timedelta(hours=6)


class KillSwitch:
    """``transcricao_api_habilitada`` — DB first (platform_settings), env
    fallback, ships FALSE. Cached for a few seconds: the worker polls every
    couple of seconds and must not turn each poll into a DB round-trip. An
    unreadable switch reads as CLOSED (fail closed)."""

    _TRUE = frozenset({"true", "1", "yes", "sim", "on"})

    def __init__(
        self,
        reader: Callable[[], Optional[str]],
        *,
        ttl_s: float = KILL_SWITCH_TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._reader = reader
        self._ttl = ttl_s
        self._clock = clock
        self._value: Optional[bool] = None
        self._at = 0.0

    def habilitada(self) -> bool:
        now = self._clock()
        if self._value is None or now - self._at >= self._ttl:
            try:
                raw = self._reader()
                self._value = str(raw or "").strip().lower() in self._TRUE
            except Exception:  # noqa: BLE001 — fail closed, logged
                import logging

                logging.getLogger(__name__).exception("transcricao.kill_switch_read_failed")
                self._value = False
            self._at = now
        return self._value


def read_kill_switch_setting() -> Optional[str]:
    """Default reader: the seed credential chain (platform_settings, then the
    ``TRANSCRICAO_API_HABILITADA`` env var)."""
    from noctusai_lib.config.credentials import resolve_credential

    return resolve_credential(KILL_SWITCH_KEY)


class BurstLimiter:
    """Per-identity request-rate limits on core's own limiter (Redis-backed
    when ``REDIS_URL`` is set — ``app.rate_limit.limiter``).

    Uses the limiter's strategy directly instead of the ``@limiter.limit``
    decorator because the decorator answers with the fleet-wide
    ``RATE_LIMITED`` body and no ``Retry-After``; this API's contract is the
    ``{codigo: limite_requisicoes}`` envelope + ``Retry-After``."""

    def __init__(self, limiter: Any, policy: Optional[dict[str, str]] = None) -> None:
        from limits import parse

        self._strategy = limiter.limiter
        self._items = {m: parse(spec) for m, spec in (policy or BURST_POLICY).items()}

    def retry_after_if_limited(self, method: str, identity: str) -> Optional[int]:
        """``None`` when the request may proceed; else seconds until the
        window resets (>= 1)."""
        item = self._items.get(method)
        if item is None:
            return None
        if self._strategy.hit(item, "transcricoes", method, identity):
            return None
        stats = self._strategy.get_window_stats(item, "transcricoes", method, identity)
        return max(1, int(math.ceil(stats.reset_time - time.time())))
