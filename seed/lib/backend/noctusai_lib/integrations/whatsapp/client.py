"""WAHA HTTP client (sync + async).

Ported from `whatsapp-google-scheduling/app/services/waha/client.py`
2026-05-03. Both async and sync paths are exposed: async for FastAPI
webhook handlers (already on an event loop); sync for worker code paths
that don't have a running loop. Mixing `asyncio.run(...)` inside sync
handlers used to work but breaks the moment any caller wraps the worker
in an event loop, so we expose explicit sync siblings instead.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

import httpx

from noctusai_lib.integrations.whatsapp.mappers import (
    build_send_text_body,
    rewrite_vendor_media_url,
)

logger = logging.getLogger(__name__)

# Session statuses `recover_session`'s ladder treats as "recovered enough
# to stop": SCAN_QR_CODE (fresh pairing needed, but the session is alive
# and not stuck) or WORKING (already paired and connected).
RECOVER_READY_STATUSES = {"SCAN_QR_CODE", "WORKING"}

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


async def _call_tolerating_expected_conflict(
    action: Callable[[], Awaitable[dict[str, Any]]], *, label: str
) -> None:
    """Invoke a WAHA session-admin action, tolerating its documented
    "already in this state" 409/422 responses.

    ``recover_session`` cares about the resulting session STATUS (read
    fresh via ``get_session`` right after) — not whether the admin call
    itself returned 2xx. WAHA answers 409/422 for a restart/logout issued
    against a session that is not exactly in the state it expects, which
    is precisely the "stuck" case the ladder exists to recover from.
    Anything else (5xx, network failure, an unexpected status code) is a
    genuine failure and is re-raised — never swallowed silently.
    """
    try:
        await action()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code not in (409, 422):
            raise
        logger.warning(
            "WahaClient.recover_session: %s answered %s (expected "
            "state-conflict); continuing to poll session status",
            label,
            status_code,
        )


def recovery_outcome(state: dict[str, Any], stage: str) -> dict[str, Any]:
    """Shape a `get_session`-like state dict into `recover_session`'s
    return contract. Pure/stateless — shared verbatim by `WahaClient`
    (real) and `FakeWahaClient` (fake) so both ladders emit the exact
    same result shape without duplicating this formatting twice."""
    me = state.get("me")
    return {
        "status": state.get("status"),
        "stage": stage,
        "paired": bool(me),
        "me": me,
    }


def _session_config(webhooks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build a FULL WAHA session-config payload — ALWAYS carries the NOWEB store.

    🔴 WAHA's ``PUT /api/sessions/{name}`` (and the config on ``/start``) is a
    full config REPLACE, not a merge: any key you omit is DROPPED. The
    2026-06-23 empty-inbox bug was exactly this — ``set_webhook`` PUT a config
    with only ``webhooks`` and clobbered the ``noweb.store`` block that
    ``start_session`` had set, so the NOWEB engine kept no history and
    ``GET /api/{session}/chats`` 400'd. The cure is structural: NO caller
    hand-assembles a partial config; every config-writing path routes through
    here so the store block is always present. ``fullSync`` backfills history
    at authentication, so a FRESH pairing (logout → start → scan QR) is what
    actually populates existing chats — a restart of an already-paired session
    will not re-pull history.

    🔴 WAHA's NOWEB config key is **camelCase** ``fullSync`` (not
    ``full_sync``). The 2026-0X silent bug: this helper emitted
    ``full_sync`` (snake_case), WAHA silently dropped the unrecognized key
    and applied its own default (``false``), so NOWEB never backfilled
    history — nothing raised, nothing logged, the inbox was just quietly
    empty/stale. Confirmed live: ``GET /api/sessions/default`` reports
    ``"noweb": {"store": {"enabled": true, "fullSync": false}}`` for a
    session started under the old snake_case payload. See
    ``test_session_config_wire_key_is_camel_case_full_sync`` — it pins
    the exact wire-format key so this cannot regress silently again.
    """
    config: dict[str, Any] = {
        "noweb": {"store": {"enabled": True, "fullSync": True}}
    }
    if webhooks is not None:
        config["webhooks"] = webhooks
    return {"config": config}


class WahaClient:
    # NOC-REMEDIATE[rate-limit]: this client opens a fresh httpx client
    # per method (sync + async paths) rather than one chokepoint — pace
    # each call site via `rate_limit.acquire("whatsapp")` (sync methods) /
    # `await rate_limit.acquire_async("whatsapp")` (async methods), or
    # refactor to a single `_request` helper first. Deferred: WAHA calls
    # are largely user-paced today (chat sends), but the chat-history
    # backfill loop is a burst risk. See
    # KB § PATTERNS/common/outbound-rate-limiting.md.
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

    async def send_seen(
        self,
        chat_id: str,
        message_id: str | None = None,
        participant: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/sendSeen — mark a chat (or a specific message) as read.

        WAHA's ``SendSeenRequest`` requires ``chatId`` + ``session``;
        ``messageId`` and ``participant`` are optional. Omitting
        ``message_id`` marks the whole chat as seen (blue ticks on the
        latest message). ``participant`` is NOWEB-only — the JID of the
        group member whose message is being acknowledged; irrelevant for
        1:1 chats. WAHA's current schema also accepts a plural
        ``messageIds`` array (``messageId`` singular is flagged
        deprecated-but-still-accepted) — this client sticks to the
        documented singular field since a single-message read-receipt is
        the only call shape this connector needs today.
        """
        body: dict[str, Any] = {"session": self.session, "chatId": chat_id}
        if message_id is not None:
            body["messageId"] = message_id
        if participant is not None:
            body["participant"] = participant
        async with httpx.AsyncClient(base_url=self.base_url, timeout=15) as client:
            response = await client.post(
                "/api/sendSeen",
                json=body,
                headers=self._headers(json=True),
            )
            response.raise_for_status()
            return _safe_json(response)

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
        chat/message history. Without ``store.enabled=true`` + ``fullSync=true``
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
        restart after deploy also activates ``fullSync`` on the revived session.
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

    async def _poll_until_ready(self, seconds: float) -> dict[str, Any]:
        """Poll ``get_session`` until status lands in
        ``RECOVER_READY_STATUSES`` or ``seconds`` elapses; returns the
        last-read state either way (caller decides ready vs. still-stuck)."""
        deadline = time.monotonic() + seconds
        state = await self.get_session()
        while (
            state.get("status") not in RECOVER_READY_STATUSES
            and time.monotonic() < deadline
        ):
            await asyncio.sleep(0.5)
            state = await self.get_session()
        return state

    async def recover_session(self, *, settle_seconds: float = 8.0) -> dict[str, Any]:
        """Escalation ladder to recover a session stuck outside
        ``{SCAN_QR_CODE, WORKING}`` — stops at the first rung that gets
        there:

        1. ``get_session()`` — already ``WORKING``? return immediately.
        2. ``start_session()`` → poll ``get_session()`` up to
           ``settle_seconds``.
        3. still not ready → ``restart_session()`` → poll again.
        4. still not ready → ``logout_session()`` then ``start_session()``
           → poll again.

        Root-cause context (proven on the live fleet session): a session
        that HAS stored (but dead) credentials answers ``restart`` by
        retrying those dead credentials and hanging in ``STARTING`` for
        minutes before WAHA force-stops it back to ``FAILED`` — only
        ``logout`` actually clears the stored credentials so the NOWEB
        engine can re-enter ``SCAN_QR_CODE``. The ladder's value is
        CONVERGENCE regardless of which single rung is individually
        "the fix": a never-paired session converges at rung 2 (cheap),
        a session with a live-but-stalled connection may recover at
        rung 3, and a session wedged on dead stored credentials only
        converges at rung 4 — callers don't have to pre-diagnose which
        case they're in.

        Never raises on an intermediate rung's expected WAHA 409/422
        (``start_session`` already tolerates those internally;
        ``restart_session``/``logout_session`` are wrapped here via
        ``_call_tolerating_expected_conflict``) — anything else
        (5xx, network failure, an unexpected status code) surfaces.

        Returns ``{"status": <final WAHA status>, "stage":
        <"already_working"|"start"|"restart"|"logout_start">, "paired":
        <bool>, "me": <session "me" dict or None>}``.
        """
        state = await self.get_session()
        if state.get("status") == "WORKING":
            return recovery_outcome(state, "already_working")

        await self.start_session()
        state = await self._poll_until_ready(settle_seconds)
        if state.get("status") in RECOVER_READY_STATUSES:
            return recovery_outcome(state, "start")

        await _call_tolerating_expected_conflict(
            self.restart_session, label="restart_session"
        )
        state = await self._poll_until_ready(settle_seconds)
        if state.get("status") in RECOVER_READY_STATUSES:
            return recovery_outcome(state, "restart")

        await _call_tolerating_expected_conflict(
            self.logout_session, label="logout_session"
        )
        await self.start_session()
        state = await self._poll_until_ready(settle_seconds)
        return recovery_outcome(state, "logout_start")

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
        (``store.enabled=true, fullSync=true``). WAHA returns 400 when the
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

    async def get_chats_overview(self, limit: int = 50) -> list[dict[str, Any]]:
        """GET /api/{session}/chats/overview — chat list pre-shaped for a UI.

        Verified present on the live fleet WAHA build (2026.6.1 CORE,
        ``https://waha.noctusai.com``) via its own OpenAPI spec:
        ``operationId: ChatsController_getChatsOverview``, tag "💬 Chats".
        WAHA also ships a ``POST`` sibling for callers with too many
        ``ids`` for a GET query string; not needed here.

        Returns a list of WAHA ``ChatSummary`` objects as emitted:
        ``{"id": ..., "name": ..., "picture": ..., "lastMessage": {...},
        "_chat": {...}}``. Per WAHA's documented ``ChatSummary`` schema,
        ``unreadCount`` is **not** a top-level field — the schema only
        declares ``id``/``name``/``picture``/``lastMessage``/``_chat``.
        WAHA's raw (untyped) chat object nested under ``_chat`` is where
        an unread count would live when the underlying engine populates
        it; callers wanting unread counts should read
        ``chat.get("_chat", {}).get("unreadCount")`` defensively rather
        than assume a top-level key — this was NOT observed on a live
        paired session (the fleet session is currently ``FAILED``, see
        ``recover_session``), so the nested shape is documented-schema
        inference, not a directly-observed sample.

        Requires the NOWEB store (same precondition as ``list_chats``);
        WAHA returns 422 when the session is not ``WORKING``.
        """
        async with httpx.AsyncClient(base_url=self.base_url, timeout=_WAHA_READ_TIMEOUT) as client:
            response = await client.get(
                f"/api/{self.session}/chats/overview",
                params={"limit": limit},
                headers=self._headers(),
            )
            response.raise_for_status()
            body = response.json()
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
