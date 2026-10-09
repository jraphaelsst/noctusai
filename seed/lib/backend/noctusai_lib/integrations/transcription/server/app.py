"""FastAPI app for the transcriber worker.

Routes: GET /healthz · POST /v1/probe · POST /v1/transcribe (raw audio body).
Error envelope: `{"codigo": ..., "mensagem": ...}`. The worker has NO internal
queue: a busy semaphore is a 503 and the durable queue is the product's DB.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from noctusai_lib.integrations.transcription.server.engine import (
    EngineTimeout,
    TranscriptionEngine,
)
from noctusai_lib.integrations.transcription.server.media import (
    SAMPLE_RATE,
    MediaError,
    decode_to_float32,
    probe_bytes,
)

log = logging.getLogger("noctus.transcriber")

MAX_HARD_S = 1800.0
DEFAULT_MAX_SECONDS = 600.0
MIN_SECONDS = 1.0
DAILY_BACKSTOP_MIN = 600.0
MAX_UPLOAD_BYTES = 15 * 1024 * 1024 + 1024  # product caps at 15 MB; small slack
PROBE_CONCURRENCY = 2
PROBE_TIMEOUT_S = 5.0
RETRY_AFTER_S = "15"


def _err(status: int, codigo: str, mensagem: str, headers: Optional[dict[str, str]] = None):
    return JSONResponse(
        {"codigo": codigo, "mensagem": mensagem}, status_code=status, headers=headers
    )


class _DailyMinutes:
    """In-memory UTC-day counter (backstop only; the product's Postgres quota is canonical)."""

    def __init__(self, limit_min: float) -> None:
        self.limit_min = limit_min
        self._day = ""
        self._used = 0.0

    def _roll(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._day:
            self._day, self._used = today, 0.0

    def would_exceed(self, minutes: float) -> bool:
        self._roll()
        return self._used + minutes > self.limit_min

    def add(self, minutes: float) -> None:
        self._roll()
        self._used += minutes


def create_app(
    engine: TranscriptionEngine,
    *,
    token: Optional[str] = None,
    daily_limit_min: float = DAILY_BACKSTOP_MIN,
    load_in_background: bool = True,
) -> FastAPI:
    """`token` defaults to env TRANSCRIBER_TOKEN; an empty token refuses every call (fail closed)."""
    expected = (token if token is not None else os.environ.get("TRANSCRIBER_TOKEN", "")).encode()
    busy = asyncio.Semaphore(1)
    probe_sem = asyncio.Semaphore(PROBE_CONCURRENCY)
    daily = _DailyMinutes(daily_limit_min)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if not engine.loaded:
            if load_in_background:
                asyncio.get_running_loop().run_in_executor(None, engine.load)
            else:
                engine.load()
        yield

    app = FastAPI(
        title="noctus-transcriber", docs_url=None, redoc_url=None, openapi_url=None,
        lifespan=lifespan,
    )

    def _authorized(request: Request) -> bool:
        got = request.headers.get("X-Transcriber-Token", "").encode()
        # constant-time; empty configured token never authorizes
        return bool(expected) and hmac.compare_digest(got, expected)

    async def _read_body(request: Request):
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_UPLOAD_BYTES:
            return None
        buf = bytearray()
        async for chunk in request.stream():
            buf += chunk
            if len(buf) > MAX_UPLOAD_BYTES:
                return None
        return bytes(buf)

    @app.get("/healthz")
    async def healthz():
        if not engine.loaded:
            return _err(503, "modelo_carregando", "modelo ainda carregando")
        return {"status": "ok", "modelo": engine.model_name}

    @app.post("/v1/probe")
    async def probe(request: Request):
        if not _authorized(request):
            return _err(401, "nao_autorizado", "token invalido")
        body = await _read_body(request)
        if body is None:
            return _err(413, "arquivo_grande", "arquivo excede o limite")
        if not body:
            return _err(422, "audio_vazio", "corpo vazio")
        async with probe_sem:  # <=2 concurrent; independent of the transcription semaphore
            try:
                info = await probe_bytes(body, timeout=PROBE_TIMEOUT_S)
            except MediaError as exc:
                return _err(422, "audio_corrompido", str(exc))
        return {
            "duracao_s": info.duracao_s,
            "codec": info.codec,
            "container": info.container,
            "sample_rate": info.sample_rate,
            "canais": info.canais,
        }

    @app.post("/v1/transcribe")
    async def transcribe(
        request: Request,
        language: str = Query("pt"),
        max_seconds: float = Query(DEFAULT_MAX_SECONDS, gt=0),
    ):
        if not _authorized(request):
            return _err(401, "nao_autorizado", "token invalido")
        if not engine.loaded:
            return _err(503, "modelo_carregando", "modelo ainda carregando",
                        {"Retry-After": RETRY_AFTER_S})
        if busy.locked():
            return _err(503, "ocupado", "transcritor ocupado", {"Retry-After": RETRY_AFTER_S})
        async with busy:
            body = await _read_body(request)
            if body is None:
                return _err(413, "arquivo_grande", "arquivo excede o limite")
            if not body:
                return _err(422, "audio_vazio", "corpo vazio")
            started = time.monotonic()
            try:
                # decode up to max_seconds + 1 so an over-long file is detectable
                audio = await decode_to_float32(body, max_seconds=max_seconds + 1.0)
            except MediaError as exc:
                return _err(422, "audio_corrompido", str(exc))
            duracao = len(audio) / SAMPLE_RATE
            if duracao < MIN_SECONDS:
                return _err(422, "audio_vazio", "audio muito curto")
            if duracao > max_seconds:
                return _err(422, "duracao_excedida", "audio excede a duracao maxima")
            minutes = duracao / 60.0
            if daily.would_exceed(minutes):
                return _err(503, "capacidade_diaria", "capacidade diaria esgotada",
                            {"Retry-After": "3600"})
            cap = min(MAX_HARD_S, 3.0 * duracao)
            deadline = time.monotonic() + cap
            try:
                result: Any = await asyncio.to_thread(
                    engine.transcribe, audio, language=language, deadline=deadline
                )
            except EngineTimeout:
                log.warning("transcribe hard cap hit: duracao_s=%.1f cap_s=%.1f", duracao, cap)
                return _err(504, "tempo_excedido", "transcricao excedeu o tempo maximo")
            daily.add(minutes)
            wall = time.monotonic() - started
            # never log transcript text or audio
            log.info("transcribed duracao_s=%.1f wall_s=%.1f", duracao, wall)
            return {
                "text": result.text,
                "duracao_s": duracao,
                "idioma": language,
                "modelo": engine.model_name,
                "rtf": round(wall / duracao, 3),
                "segmentos": result.segmentos,
            }

    return app
