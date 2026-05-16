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

from noctusai_lib.integrations.whatsapp.mappers import (
    build_send_text_body,
    rewrite_vendor_media_url,
)


class WahaClient:
    """WAHA HTTP client with both sync and async send paths.

    Vendor-URL rewrite (SESSION-NOTES §4.3, workspace commit ``fedd4cf``):
    WAHA emits media URLs against its OWN external-facing host (the URL
    a browser would use, e.g. ``http://localhost:3000/...``). Inside the
    docker network that host is unreachable from the ``app`` container.
    ``external_base_url`` is the host WAHA *emits* (browser-facing);
    ``base_url`` / ``internal_base_url`` is the host the app *reaches*
    (docker-DNS, e.g. ``http://waha:3000``). ``download_media`` rewrites
    any media URL whose authority matches ``external_base_url`` onto the
    internal host before fetching; external CDN URLs pass through.

    When ``external_base_url`` is not supplied it defaults to
    ``base_url`` (single-host dev / no rewrite needed — no-op).
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        session: str = "default",
        *,
        external_base_url: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = session
        # The host WAHA emits in media URLs (browser-facing). Defaults
        # to base_url ⇒ rewrite is a no-op when both are the same.
        self.external_base_url = (
            external_base_url.rstrip("/") if external_base_url else self.base_url
        )

    def _resolve_media_url(self, url: str) -> str:
        return rewrite_vendor_media_url(
            url,
            external_base_url=self.external_base_url,
            internal_base_url=self.base_url,
        )

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
        resolved = self._resolve_media_url(url)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(resolved, headers=self._headers())
            response.raise_for_status()
            return response.content

    def download_media_sync(self, url: str) -> bytes:
        resolved = self._resolve_media_url(url)
        with httpx.Client(timeout=30) as client:
            response = client.get(resolved, headers=self._headers())
            response.raise_for_status()
            return response.content
