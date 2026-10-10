"""httpx client for the self-hosted `noctus-transcriber` worker.

Worker HTTP contract (see transcription-contract.md §1/§2):
- `POST /v1/probe`      body = raw audio -> 200 AudioProbe JSON
- `POST /v1/transcribe?language=pt&max_seconds=N` body = raw audio
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
# Matches the worker's MAX_HARD_S (9000 s) — a client that gives up before the
# worker would abandon a job the worker is still allowed to finish.
MAX_TIMEOUT_S = 9000.0


def transcribe_timeout(duracao_s: float) -> float:
    """`min(MAX_TIMEOUT_S, 3*duracao + 60)` seconds (worker cap + 60 s of slack)."""
    return min(MAX_TIMEOUT_S, 3.0 * duracao_s + 60.0)


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

    async def _post(self, path: str, audio: bytes, *, timeout: float, params=None) -> dict:
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
        self, audio: bytes, *, language: str = "pt", max_seconds: float
    ) -> TranscriptResult:
        data = await self._post(
            "/v1/transcribe",
            audio,
            timeout=transcribe_timeout(max_seconds),
            params={"language": language, "max_seconds": max_seconds},
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
