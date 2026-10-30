"""httpx client for the self-hosted `noctus-transcriber` worker.

Worker HTTP contract (see transcription-contract.md §1/§2):
- `POST /v1/probe`      body = raw audio -> 200 AudioProbe JSON
- `POST /v1/transcribe?language=pt[&max_seconds=N]` body = raw audio (no N = any length)
  -> 200 TranscriptResult JSON
- header `X-Transcriber-Token` on every call
- 503 `{"codigo":"ocupado"}` + `Retry-After` -> TranscriberBusy
- 422 `{"codigo","mensagem"}` -> TranscriptionRejected
"""

from __future__ import annotations

from typing import Optional

import httpx

from noctusai_lib.integrations.transcription.types import (
    AudioProbe,
    TranscriberBusy,
    TranscriberUnavailable,
    TranscriptionRejected,
    TranscriptResult,
)

PROBE_TIMEOUT_S = 15.0
# Transcription has no read deadline: the worker never cuts a job off (owner,
# 2026-10-30 — "whatever length, we shall read it"), so neither does its client.
# Only connecting is bounded, so a down worker still fails fast.
CONNECT_TIMEOUT_S = 10.0
TRANSCRIBE_TIMEOUT = httpx.Timeout(None, connect=CONNECT_TIMEOUT_S)


class LocalWhisperTranscriber:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._client = http_client

    def _headers(self) -> dict[str, str]:
        return {
            "X-Transcriber-Token": self._token,
            "Content-Type": "application/octet-stream",
        }

    async def _post(
        self, path: str, audio: bytes, *, timeout: float | httpx.Timeout, params=None
    ) -> dict:
        url = f"{self._base_url}{path}"
        try:
            if self._client is not None:
                resp = await self._client.post(
                    url, content=audio, headers=self._headers(), params=params, timeout=timeout
                )
            else:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        url, content=audio, headers=self._headers(), params=params, timeout=timeout
                    )
        except httpx.TimeoutException as exc:
            raise TranscriberUnavailable(f"transcriber timeout: {exc}") from exc
        except httpx.TransportError as exc:
            raise TranscriberUnavailable(f"transcriber unreachable: {exc}") from exc

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError as exc:
                raise TranscriberUnavailable("transcriber returned non-JSON body") from exc
        if resp.status_code == 503:
            try:
                retry_after = float(resp.headers.get("Retry-After", "15"))
            except ValueError:
                retry_after = 15.0
            raise TranscriberBusy(retry_after)
        if resp.status_code == 422:
            codigo, mensagem = "audio_corrompido", ""
            try:
                body = resp.json()
                codigo = body.get("codigo", codigo)
                mensagem = body.get("mensagem", "")
            except ValueError:
                pass
            raise TranscriptionRejected(codigo, mensagem)
        raise TranscriberUnavailable(f"transcriber HTTP {resp.status_code}")

    async def probe(self, audio: bytes) -> AudioProbe:
        data = await self._post("/v1/probe", audio, timeout=PROBE_TIMEOUT_S)
        try:
            return AudioProbe(
                duracao_s=float(data["duracao_s"]),
                codec=data["codec"],
                container=data["container"],
                sample_rate=data.get("sample_rate"),
                canais=data.get("canais"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise TranscriberUnavailable(f"malformed probe response: {exc}") from exc

    async def transcribe(
        self, audio: bytes, *, language: str = "pt", max_seconds: Optional[float] = None
    ) -> TranscriptResult:
        data = await self._post(
            "/v1/transcribe",
            audio,
            timeout=TRANSCRIBE_TIMEOUT,
            params={"language": language}
            | ({"max_seconds": max_seconds} if max_seconds is not None else {}),
        )
        try:
            return TranscriptResult(
                text=data["text"],
                duracao_s=data.get("duracao_s"),
                idioma=data.get("idioma", language),
                modelo=data.get("modelo", "local-whisper"),
                rtf=data.get("rtf"),
                segmentos=data.get("segmentos"),
            )
        except (KeyError, TypeError) as exc:
            raise TranscriberUnavailable(f"malformed transcribe response: {exc}") from exc
