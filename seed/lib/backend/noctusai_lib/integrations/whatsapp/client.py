"""WAHA HTTP client (sync + async).

Ported from `whatsapp-google-scheduling/app/services/waha/client.py`
2026-05-03. Both async and sync paths are exposed: async for FastAPI
webhook handlers (already on an event loop); sync for worker code paths
that don't have a running loop. Mixing `asyncio.run(...)` inside sync
handlers used to work but breaks the moment any caller wraps the worker
in an event loop, so we expose explicit sync siblings instead.
"""

from __future__ import annotations

from typing import Any

import httpx

from noctusai_lib.integrations.whatsapp.mappers import build_send_text_body


class WahaClient:
    """WAHA HTTP client with both sync and async send paths."""

    def __init__(self, base_url: str, api_key: str | None, session: str = "default"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = session

    def _headers(self, *, json: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {}
        if json:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

    async def send_text(self, chat_id: str, text: str) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=15) as client:
            response = await client.post(
                "/api/sendText",
                json=build_send_text_body(self.session, chat_id, text),
                headers=self._headers(json=True),
            )
            response.raise_for_status()
            return response.json()

    def send_text_sync(self, chat_id: str, text: str) -> dict[str, Any]:
        with httpx.Client(base_url=self.base_url, timeout=15) as client:
            response = client.post(
                "/api/sendText",
                json=build_send_text_body(self.session, chat_id, text),
                headers=self._headers(json=True),
            )
            response.raise_for_status()
            return response.json()

    async def download_media(self, url: str) -> bytes:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=self._headers())
            response.raise_for_status()
            return response.content

    def download_media_sync(self, url: str) -> bytes:
        with httpx.Client(timeout=30) as client:
            response = client.get(url, headers=self._headers())
            response.raise_for_status()
            return response.content
