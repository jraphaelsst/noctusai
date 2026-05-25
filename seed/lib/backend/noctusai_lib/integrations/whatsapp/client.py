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


class WahaSessionNotReady(RuntimeError):
    """Raised by ``get_qr`` when the session is not in ``SCAN_QR_CODE``.

    WAHA returns ``422`` with a structured body
    (``{"status": "WORKING", "expected": ["SCAN_QR_CODE"]}``) when a QR is
    requested for an already-paired (or starting) session. That is an
    expected control-flow signal — not an HTTP failure — so the admin
    router translates it into "no QR needed, session is <status>" rather
    than a 500.
    """

    def __init__(self, status: str | None, detail: str = ""):
        self.status = status
        super().__init__(detail or f"session not scannable (status={status})")


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    """Parse WAHA's response body to a dict, tolerating empty bodies.

    Some WAHA engines / session-admin paths return 2xx with no body (or a
    non-JSON payload). The HTTP status was already validated via
    ``raise_for_status``, so returning ``{}`` lets the caller treat the
    call as successful instead of raising a JSONDecodeError.
    """
    body = response.content
    if not body or not body.strip():
        return {}
    try:
        parsed = response.json()
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {"raw": parsed}


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

    # ------------------------------------------------------------------
    # Session admin — connection lifecycle, QR pairing, webhook wiring.
    #
    # Async-only by design: every caller is a FastAPI handler already on
    # an event loop. Unlike send_text (called from sync worker paths too),
    # session admin is never invoked off-loop, so no sync siblings.
    # ------------------------------------------------------------------

    async def get_session(self) -> dict[str, Any]:
        """GET /api/sessions/{session} — status, me, engine."""
        async with httpx.AsyncClient(base_url=self.base_url, timeout=15) as client:
            response = await client.get(
                f"/api/sessions/{self.session}",
                headers=self._headers(),
            )
            response.raise_for_status()
            return _safe_json(response)

    async def start_session(self) -> dict[str, Any]:
        """POST /api/sessions/{session}/start — create/start a session by name.

        Required to pair a FRESH session (the multi-session case): a session
        must exist and reach ``STARTING`` / ``SCAN_QR_CODE`` before
        ``get_qr`` returns anything. WAHA answers 4xx (409/422) when the
        session already exists / is already started — that is not an error
        for our purposes, so we fall back to the current session state
        instead of raising.
        """
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            response = await client.post(
                f"/api/sessions/{self.session}/start",
                headers=self._headers(json=True),
            )
            if response.status_code in (409, 422):
                return await self.get_session()
            response.raise_for_status()
            return _safe_json(response)

    async def restart_session(self) -> dict[str, Any]:
        """POST /api/sessions/{session}/restart — recover a stuck session.

        Triggers a fresh QR when the session is unpaired; preserves the
        paired account when credentials are still valid on disk.
        """
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            response = await client.post(
                f"/api/sessions/{self.session}/restart",
                headers=self._headers(json=True),
            )
            response.raise_for_status()
            return _safe_json(response)

    async def logout_session(self) -> dict[str, Any]:
        """POST /api/sessions/{session}/logout — unpair the account."""
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            response = await client.post(
                f"/api/sessions/{self.session}/logout",
                headers=self._headers(json=True),
            )
            response.raise_for_status()
            return _safe_json(response)

    async def get_qr(self) -> bytes:
        """GET /api/{session}/auth/qr?format=image — PNG bytes to scan.

        Raises ``WahaSessionNotReady`` when WAHA answers 422 because the
        session is not in ``SCAN_QR_CODE`` (already paired / starting).
        """
        async with httpx.AsyncClient(base_url=self.base_url, timeout=15) as client:
            response = await client.get(
                f"/api/{self.session}/auth/qr",
                params={"format": "image"},
                headers=self._headers(),
            )
            if response.status_code == 422:
                body = _safe_json(response)
                raise WahaSessionNotReady(
                    status=body.get("status"),
                    detail=str(body.get("error") or "session not scannable"),
                )
            response.raise_for_status()
            return response.content

    async def set_webhook(
        self, url: str, events: list[str]
    ) -> dict[str, Any]:
        """PUT /api/sessions/{session} — wire the inbound webhook.

        WAHA restarts the session on a config change; the paired account
        survives (credentials persist on the WAHA volume).
        """
        payload = {
            "config": {
                "webhooks": [
                    {
                        "url": url,
                        "events": events,
                        "hmac": None,
                        "retries": None,
                        "customHeaders": None,
                    }
                ]
            }
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            response = await client.put(
                f"/api/sessions/{self.session}",
                json=payload,
                headers=self._headers(json=True),
            )
            response.raise_for_status()
            return _safe_json(response)

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
