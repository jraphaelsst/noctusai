"""HTTP boundary for the ElevenLabs adapter.

`Transport` is the seam: the default `HttpxTransport` talks to the vendor; a
caller (the MCP connector, tests) may inject its own. Every failure raises
`TtsUpstreamError` (status = upstream status, 502 when unreachable); error text
never carries the key or the request body.
"""
from __future__ import annotations

import json
from typing import Mapping, Optional, Protocol

import httpx

from noctusai_lib.integrations.tts.types import TtsNotConfigured, TtsUpstreamError

DEFAULT_BASE_URL = "https://api.elevenlabs.io"


class Transport(Protocol):
    def json(self, method: str, path: str, *, params: Optional[dict] = None, body: Optional[object] = None,
             timeout: float = 20.0) -> object: ...

    def bytes(self, method: str, path: str, *, params: Optional[dict] = None, body: Optional[object] = None,
              files: Optional[list] = None, data: Optional[dict] = None,
              timeout: float = 120.0) -> tuple[bytes, Mapping[str, str]]: ...


class HttpxTransport:
    def __init__(self, api_key: Optional[str], *, base_url: str = DEFAULT_BASE_URL) -> None:
        self._key = api_key
        self._base = base_url.rstrip("/")

    def bytes(self, method, path, *, params=None, body=None, files=None, data=None, timeout=120.0):
        if not self._key:
            raise TtsNotConfigured()
        params = {k: v for k, v in (params or {}).items() if v is not None}
        label = f"ElevenLabs API {method.upper()} {path}"
        try:
            r = httpx.request(
                method, f"{self._base}{path}", params=params, json=body if files is None else None,
                files=files, data=data, headers={"xi-api-key": self._key}, timeout=timeout,
            )
        except httpx.HTTPError as e:
            raise TtsUpstreamError(f"{label} unreachable ({type(e).__name__})", status=502) from e
        if r.status_code >= 400:
            raise TtsUpstreamError(f"{label} -> HTTP {r.status_code}: {r.text[:200]}", status=r.status_code)
        return r.content, {k.lower(): v for k, v in r.headers.items()}

    def json(self, method, path, *, params=None, body=None, timeout=20.0):
        payload, _ = self.bytes(method, path, params=params, body=body, timeout=timeout)
        if not payload:
            return {}
        try:
            return json.loads(payload.decode("utf-8", "replace"))
        except ValueError as e:
            raise TtsUpstreamError(f"ElevenLabs API {method.upper()} {path} returned non-JSON", status=502) from e
