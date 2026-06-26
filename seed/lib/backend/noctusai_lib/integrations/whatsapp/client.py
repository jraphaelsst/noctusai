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

# 🔴 BOUNDARY: read/identity calls (chats, messages, contact, lids) hit WAHA in
# request hot paths (chat-list render, message-thread render, inbound webhook).
# They MUST be tightly bounded so WAHA latency/drift degrades gracefully instead
# of hanging the request. The 2026-06-24 regression was an UNBOUNDED per-JID
# fanout at the old 15-30s timeouts → ~49s thread loads + a blocked reply path.
# Session-admin writes (start/restart/webhook/send) keep their longer timeouts.
_WAHA_READ_TIMEOUT = 6.0
# fetch_chat_messages (full chat history) is inherently slow on NOWEB (~13s
# observed) and is the SOURCE OF TRUTH for a thread, so it gets a longer budget.
# Callers MUST cache the result (the thread endpoint caches per chat) so this
# slow call happens at most once per TTL — never once per 3s poll.
_WAHA_HISTORY_TIMEOUT = 20.0


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


def _session_config(webhooks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build a FULL WAHA session-config payload — ALWAYS carries the NOWEB store.

    🔴 WAHA's ``PUT /api/sessions/{name}`` (and the config on ``/start``) is a
    full config REPLACE, not a merge: any key you omit is DROPPED. The
    2026-06-23 empty-inbox bug was exactly this — ``set_webhook`` PUT a config
    with only ``webhooks`` and clobbered the ``noweb.store`` block that
    ``start_session`` had set, so the NOWEB engine kept no history and
    ``GET /api/{session}/chats`` 400'd. The cure is structural: NO caller
    hand-assembles a partial config; every config-writing path routes through
    here so the store block is always present. ``full_sync`` backfills history
    at authentication, so a FRESH pairing (logout → start → scan QR) is what
    actually populates existing chats — a restart of an already-paired session
    will not re-pull history.
    """
    config: dict[str, Any] = {
        "noweb": {"store": {"enabled": True, "full_sync": True}}
    }
    if webhooks is not None:
        config["webhooks"] = webhooks
    return {"config": config}


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

        The NOWEB store config is included so that WAHA maintains and syncs
        chat/message history. Without ``store.enabled=true`` + ``full_sync=true``
        the NOWEB engine keeps no history — ``GET /api/{session}/chats`` returns
        a 400 and the inbox stays empty until the first inbound webhook fires.
        This is the canonical fleet default: any chat-capable product needs the
        store on.
        """
        payload = _session_config()
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            response = await client.post(
                f"/api/sessions/{self.session}/start",
                json=payload,
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

        Sends the same NOWEB store config as ``start_session`` so that a
        restart after deploy also activates ``full_sync`` on the revived session.
        (NOTE: WAHA 2026.x ignores a config body on ``/restart`` — it restarts
        with the stored config — so the durable guarantee is that EVERY config
        write, incl. ``set_webhook``, carries the store; see ``_session_config``.)
        """
        payload = _session_config()
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            response = await client.post(
                f"/api/sessions/{self.session}/restart",
                json=payload,
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

        🔴 The PUT is a full config REPLACE — so this re-asserts the NOWEB
        store block alongside the webhook (via ``_session_config``). Sending
        only ``webhooks`` here is what silently dropped the store and emptied
        the chat inbox on 2026-06-23.
        """
        payload = _session_config(
            webhooks=[
                {
                    "url": url,
                    "events": events,
                    "hmac": None,
                    "retries": None,
                    "customHeaders": None,
                }
            ]
        )
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            response = await client.put(
                f"/api/sessions/{self.session}",
                json=payload,
                headers=self._headers(json=True),
            )
            response.raise_for_status()
            return _safe_json(response)

    async def list_chats(self, limit: int = 50) -> list[dict[str, Any]]:
        """GET /api/{session}/chats — list conversations from the NOWEB store.

        Returns a list of chat objects as WAHA emits them:
        ``{"id": {"_serialized": "..."}, "name": ..., "lastMessage": {...}}``.

        Requires the session to have been started with the NOWEB store config
        (``store.enabled=true, full_sync=true``). WAHA returns 400 when the
        store is not enabled; callers should treat that as an empty list rather
        than raising (use the graceful-fallback pattern in the router).
        """
        async with httpx.AsyncClient(base_url=self.base_url, timeout=_WAHA_READ_TIMEOUT) as client:
            response = await client.get(
                f"/api/{self.session}/chats",
                params={"limit": limit},
                headers=self._headers(),
            )
            response.raise_for_status()
            body = response.json()
            # WAHA returns a JSON array at the top level.
            return body if isinstance(body, list) else []

    async def fetch_chat_messages(
        self, chat_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """GET /api/{session}/chats/{chatId}/messages — fetch message history.

        Returns a list of message objects as WAHA emits them:
        ``{"id": {"_serialized": ..., "id": ...}, "body": ..., "from": ...,
           "timestamp": ..., "fromMe": ...}``.

        ``chat_id`` is a WhatsApp JID such as ``5511999999999@c.us``.
        Requires the NOWEB store to be enabled; callers handle the 400 case.
        """
        async with httpx.AsyncClient(base_url=self.base_url, timeout=_WAHA_HISTORY_TIMEOUT) as client:
            response = await client.get(
                f"/api/{self.session}/chats/{chat_id}/messages",
                params={"limit": limit},
                headers=self._headers(),
            )
            response.raise_for_status()
            body = response.json()
            return body if isinstance(body, list) else []

    # ------------------------------------------------------------------
    # Contact identity resolution — WAHA 2026.x endpoints
    # ------------------------------------------------------------------

    async def get_contact(self, contact_id: str) -> dict[str, Any]:
        """GET /api/contacts?contactId={contact_id}&session={session}.

        For a phone-JID (``5511974693365@c.us``) returns::

            {"id": "5511974693365@c.us",
             "lid": "33613018058989@lid",
             "name": "João Raphael",
             "phoneNumber": "5511974693365@s.whatsapp.net"}

        For a LID JID (``33613018058989@lid``) returns::

            {"id": "33613018058989@lid", "pushname": "J. Raphael"}

        Returns an empty dict on non-200 — callers must tolerate partial
        data and log warnings; never silently swallow.
        """
        async with httpx.AsyncClient(base_url=self.base_url, timeout=_WAHA_READ_TIMEOUT) as client:
            response = await client.get(
                "/api/contacts",
                params={"contactId": contact_id, "session": self.session},
                headers=self._headers(),
            )
            if response.status_code >= 400:
                return {}
            return _safe_json(response)

    async def get_lid_phone(self, lid: str) -> str | None:
        """GET /api/{session}/lids/{lid} — resolve a LID to its phone JID.

        Returns the ``pn`` field (e.g. ``5511974693365@c.us``) on success,
        or ``None`` on 404 / any error.  Never raises — a missing LID
        mapping is not an error condition.
        """
        async with httpx.AsyncClient(base_url=self.base_url, timeout=_WAHA_READ_TIMEOUT) as client:
            response = await client.get(
                f"/api/{self.session}/lids/{lid}",
                headers=self._headers(),
            )
            if response.status_code >= 400:
                return None
            data = _safe_json(response)
            return data.get("pn") or None

    async def list_lids(self) -> list[dict[str, Any]]:
        """GET /api/{session}/lids — bulk LID→phone map.

        Returns a list of ``{"lid": "...", "pn": "..@c.us"}`` entries.
        Returns an empty list on any error (WAHA not configured / unavailable).
        """
        async with httpx.AsyncClient(base_url=self.base_url, timeout=_WAHA_READ_TIMEOUT) as client:
            response = await client.get(
                f"/api/{self.session}/lids",
                headers=self._headers(),
            )
            if response.status_code >= 400:
                return []
            body = response.json()
            return body if isinstance(body, list) else []

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
