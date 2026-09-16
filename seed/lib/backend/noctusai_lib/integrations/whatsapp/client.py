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
from typing import Any, Awaitable, Callable, Literal

import httpx

from noctusai_lib.integrations import rate_limit
from noctusai_lib.integrations.whatsapp.mappers import (
    build_send_text_body,
    group_info_from_waha,
    group_participant_from_waha,
    participant_change_result_from_waha,
    rewrite_vendor_media_url,
)
from noctusai_lib.integrations.whatsapp.types import (
    GroupInfo,
    GroupParticipant,
    ParticipantChangeResult,
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


class WahaGroupError(RuntimeError):
    """Raised by a `WahaClient` group-management call that failed with a
    status this client does not treat as an expected per-participant
    outcome (see `ParticipantChangeResult` / `participant_change_result_from_waha`
    for the add/remove case this does NOT cover) — group not found, an
    unexpected 5xx, or any other status the caller must not silently
    absorb."""

    def __init__(self, op: str, status: int | None, detail: str = ""):
        self.op = op
        self.status = status
        super().__init__(detail or f"WAHA group op {op!r} failed (status={status})")


def _raise_for_group_status(response: httpx.Response, *, op: str) -> None:
    """Group-op status check: wraps httpx's `HTTPStatusError` in a
    `WahaGroupError` carrying the op name, so every group-surface caller
    catches ONE typed error regardless of which op failed (the original
    `HTTPStatusError` is preserved as `__cause__` — nothing is silently
    absorbed). `add_participants`/`remove_participants` do NOT use this —
    they report per-participant via `ParticipantChangeResult` instead."""
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else None
        raise WahaGroupError(op=op, status=status, detail=str(exc)) from exc


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
    """WAHA HTTP client with both sync and async send paths.

    Every request routes through `_request` (async) / `_request_sync`
    (sync) — the single chokepoint that paces via
    `rate_limit.acquire_async("whatsapp")` / `rate_limit.acquire("whatsapp")`
    before opening the connection. This closed the prior
    `NOC-REMEDIATE[rate-limit]` (opened 2026-07-24): a fresh httpx client
    per method with no shared pacing meant a bulk loop — the chat-history
    backfill, and now bulk group-participant adds/removes — could burst
    WAHA fast enough to trip a rate limit or get the paired number
    flagged. Response handling (raise_for_status vs. tolerate a status,
    `_safe_json` vs. a raw list, etc.) stays call-site-specific; the
    helper only owns "pace it, open the client, make the call".

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
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = session
        # The host WAHA emits in media URLs (browser-facing). Defaults
        # to base_url ⇒ rewrite is a no-op when both are the same.
        self.external_base_url = (
            external_base_url.rstrip("/") if external_base_url else self.base_url
        )
        # Test seam: an httpx.MockTransport here lets suites exercise the
        # REAL `_request`/`_request_sync` path without monkey-patching
        # `httpx.AsyncClient`/`httpx.Client` (mirrors
        # `HttpxMailchimpClient`'s `_transport` seam). `None` → httpx's
        # default transport (real network / whatever the caller's own
        # test monkeypatch intercepts).
        self._transport = transport

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

    async def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        use_base_url: bool = True,
    ) -> httpx.Response:
        """Single chokepoint for every async WahaClient HTTP call.

        Paces via `rate_limit.acquire_async("whatsapp")` before opening
        the client — see the `WahaClient` class docstring for why. Every
        call-site keeps its own response handling (raise_for_status vs.
        tolerate a status, list vs. dict body, etc.); this only owns
        pacing + opening the connection + issuing the one HTTP verb.

        `use_base_url=False` (only `download_media` needs it) omits the
        `base_url` kwarg entirely so `path` — already an absolute
        vendor-emitted URL — is used as-is, matching the pre-refactor
        call shape exactly.
        """
        await rate_limit.acquire_async("whatsapp")
        client_kwargs: dict[str, Any] = {"timeout": timeout, "transport": self._transport}
        if use_base_url:
            client_kwargs["base_url"] = self.base_url
        async with httpx.AsyncClient(**client_kwargs) as client:
            verb = getattr(client, method)
            call_kwargs: dict[str, Any] = {}
            if params is not None:
                call_kwargs["params"] = params
            if json is not None:
                call_kwargs["json"] = json
            if headers is not None:
                call_kwargs["headers"] = headers
            return await verb(path, **call_kwargs)

    def _request_sync(
        self,
        method: str,
        path: str,
        *,
        timeout: float,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        use_base_url: bool = True,
    ) -> httpx.Response:
        """Sync twin of `_request` — same chokepoint contract, for the
        worker code paths (`send_text_sync`, `download_media_sync`) that
        call off an event loop."""
        rate_limit.acquire("whatsapp")
        client_kwargs: dict[str, Any] = {"timeout": timeout, "transport": self._transport}
        if use_base_url:
            client_kwargs["base_url"] = self.base_url
        with httpx.Client(**client_kwargs) as client:
            verb = getattr(client, method)
            call_kwargs: dict[str, Any] = {}
            if params is not None:
                call_kwargs["params"] = params
            if json is not None:
                call_kwargs["json"] = json
            if headers is not None:
                call_kwargs["headers"] = headers
            return verb(path, **call_kwargs)

    async def send_text(self, chat_id: str, text: str) -> dict[str, Any]:
        response = await self._request(
            "post",
            "/api/sendText",
            timeout=15,
            json=build_send_text_body(self.session, chat_id, text),
            headers=self._headers(json=True),
        )
        response.raise_for_status()
        return response.json()

    def send_text_sync(self, chat_id: str, text: str) -> dict[str, Any]:
        response = self._request_sync(
            "post",
            "/api/sendText",
            timeout=15,
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
        response = await self._request(
            "post", "/api/sendSeen", timeout=15, json=body, headers=self._headers(json=True)
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
        response = await self._request(
            "get", f"/api/sessions/{self.session}", timeout=15, headers=self._headers()
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
        response = await self._request(
            "post",
            f"/api/sessions/{self.session}/start",
            timeout=30,
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
        response = await self._request(
            "post",
            f"/api/sessions/{self.session}/restart",
            timeout=30,
            json=payload,
            headers=self._headers(json=True),
        )
        response.raise_for_status()
        return _safe_json(response)

    async def logout_session(self) -> dict[str, Any]:
        """POST /api/sessions/{session}/logout — unpair the account."""
        response = await self._request(
            "post",
            f"/api/sessions/{self.session}/logout",
            timeout=30,
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
        response = await self._request(
            "get",
            f"/api/{self.session}/auth/qr",
            timeout=15,
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
        response = await self._request(
            "put",
            f"/api/sessions/{self.session}",
            timeout=30,
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
        response = await self._request(
            "get",
            f"/api/{self.session}/chats",
            timeout=_WAHA_READ_TIMEOUT,
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
        response = await self._request(
            "get",
            f"/api/{self.session}/chats/overview",
            timeout=_WAHA_READ_TIMEOUT,
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
        response = await self._request(
            "get",
            f"/api/{self.session}/chats/{chat_id}/messages",
            timeout=_WAHA_HISTORY_TIMEOUT,
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
        response = await self._request(
            "get",
            "/api/contacts",
            timeout=_WAHA_READ_TIMEOUT,
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
        response = await self._request(
            "get",
            f"/api/{self.session}/lids/{lid}",
            timeout=_WAHA_READ_TIMEOUT,
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
        response = await self._request(
            "get", f"/api/{self.session}/lids", timeout=_WAHA_READ_TIMEOUT, headers=self._headers()
        )
        if response.status_code >= 400:
            return []
        body = response.json()
        return body if isinstance(body, list) else []

    async def download_media(self, url: str) -> bytes:
        resolved = self._resolve_media_url(url)
        response = await self._request(
            "get", resolved, timeout=30, headers=self._headers(), use_base_url=False
        )
        response.raise_for_status()
        return response.content

    def download_media_sync(self, url: str) -> bytes:
        resolved = self._resolve_media_url(url)
        response = self._request_sync(
            "get", resolved, timeout=30, headers=self._headers(), use_base_url=False
        )
        response.raise_for_status()
        return response.content

    # ------------------------------------------------------------------
    # Group management — WAHA Groups API. Endpoint paths/body shapes match
    # the wave0-design.md spec (Slice W) + this client's own established
    # `/api/{session}/...` convention; the fleet runs
    # `WHATSAPP_DEFAULT_ENGINE=NOWEB` (deploy/services/compose.services.yml),
    # the engine WAHA's Groups controller has historically supported on the
    # Core (self-hosted, free) tier — NOT independently re-verified against
    # a live WAHA swagger fetch this pass (no network egress / waha MCP
    # tool bound to this dispatch, and live-VPS reads were denied — see the
    # delivery note). Every call routes through `_request` so a bulk
    # participant add/remove is paced identically to every other WAHA call.
    # ------------------------------------------------------------------

    async def create_group(self, name: str, participant_ids: list[str]) -> GroupInfo:
        """POST /api/{session}/groups — create a group."""
        response = await self._request(
            "post",
            f"/api/{self.session}/groups",
            timeout=15,
            json={
                "session": self.session,
                "name": name,
                "participants": [{"id": pid} for pid in participant_ids],
            },
            headers=self._headers(json=True),
        )
        _raise_for_group_status(response, op="create_group")
        return group_info_from_waha(_safe_json(response))

    async def list_groups(self, limit: int = 50, offset: int = 0) -> list[GroupInfo]:
        """GET /api/{session}/groups — groups the session belongs to."""
        response = await self._request(
            "get",
            f"/api/{self.session}/groups",
            timeout=_WAHA_READ_TIMEOUT,
            params={"limit": limit, "offset": offset},
            headers=self._headers(),
        )
        _raise_for_group_status(response, op="list_groups")
        body = response.json()
        items = body if isinstance(body, list) else []
        return [group_info_from_waha(item) for item in items if isinstance(item, dict)]

    async def get_group(self, group_id: str) -> GroupInfo:
        """GET /api/{session}/groups/{id} — one group's details."""
        response = await self._request(
            "get",
            f"/api/{self.session}/groups/{group_id}",
            timeout=_WAHA_READ_TIMEOUT,
            headers=self._headers(),
        )
        _raise_for_group_status(response, op="get_group")
        return group_info_from_waha(_safe_json(response))

    async def list_participants(self, group_id: str) -> list[GroupParticipant]:
        """GET /api/{session}/groups/{id}/participants.

        WAHA also ships a `/v2` participants variant on some builds
        (paginated, for very large groups) — this client sticks to the
        v1 path used by every other endpoint here.
        """
        response = await self._request(
            "get",
            f"/api/{self.session}/groups/{group_id}/participants",
            timeout=_WAHA_READ_TIMEOUT,
            headers=self._headers(),
        )
        _raise_for_group_status(response, op="list_participants")
        body = response.json()
        items = body if isinstance(body, list) else []
        return [group_participant_from_waha(item) for item in items if isinstance(item, dict)]

    async def _change_participants(
        self,
        group_id: str,
        participant_ids: list[str],
        *,
        action: Literal["added", "removed"],
    ) -> list[ParticipantChangeResult]:
        endpoint = "add" if action == "added" else "remove"
        response = await self._request(
            "post",
            f"/api/{self.session}/groups/{group_id}/participants/{endpoint}",
            timeout=15,
            json={"participants": [{"id": pid} for pid in participant_ids]},
            headers=self._headers(json=True),
        )
        _raise_for_group_status(response, op=f"participants_{endpoint}")
        body = response.json()
        items = body if isinstance(body, list) else []
        if not items:
            # WAHA answered 2xx with no per-participant breakdown — treat
            # every requested id as succeeded rather than silently
            # returning an empty list (no-silent-errors).
            return [
                ParticipantChangeResult(id=pid, outcome=action, code=None)
                for pid in participant_ids
            ]
        return [
            participant_change_result_from_waha(item, action=action)
            for item in items
            if isinstance(item, dict)
        ]

    async def add_participants(
        self, group_id: str, participant_ids: list[str]
    ) -> list[ParticipantChangeResult]:
        """POST /api/{session}/groups/{id}/participants/add.

        WAHA answers per-participant — WhatsApp itself silently refuses
        some adds when the target's privacy settings block group
        invites; see `participant_change_result_from_waha`.
        """
        return await self._change_participants(group_id, participant_ids, action="added")

    async def remove_participants(
        self, group_id: str, participant_ids: list[str]
    ) -> list[ParticipantChangeResult]:
        """POST /api/{session}/groups/{id}/participants/remove."""
        return await self._change_participants(group_id, participant_ids, action="removed")

    async def _admin_change(
        self, group_id: str, participant_ids: list[str], *, endpoint: str
    ) -> None:
        response = await self._request(
            "post",
            f"/api/{self.session}/groups/{group_id}/admin/{endpoint}",
            timeout=15,
            json={"participants": [{"id": pid} for pid in participant_ids]},
            headers=self._headers(json=True),
        )
        _raise_for_group_status(response, op=f"admin_{endpoint}")

    async def promote_admins(self, group_id: str, participant_ids: list[str]) -> None:
        """POST /api/{session}/groups/{id}/admin/promote."""
        await self._admin_change(group_id, participant_ids, endpoint="promote")

    async def demote_admins(self, group_id: str, participant_ids: list[str]) -> None:
        """POST /api/{session}/groups/{id}/admin/demote."""
        await self._admin_change(group_id, participant_ids, endpoint="demote")

    @staticmethod
    def _invite_link_from_body(body: dict[str, Any]) -> str:
        code = body.get("inviteCode") or body.get("code") or ""
        if not code or code.startswith("http"):
            return code
        return f"https://chat.whatsapp.com/{code}"

    async def get_invite_link(self, group_id: str) -> str:
        """GET /api/{session}/groups/{id}/invite-code."""
        response = await self._request(
            "get",
            f"/api/{self.session}/groups/{group_id}/invite-code",
            timeout=15,
            headers=self._headers(),
        )
        _raise_for_group_status(response, op="get_invite_link")
        return self._invite_link_from_body(_safe_json(response))

    async def revoke_invite_link(self, group_id: str) -> str:
        """POST /api/{session}/groups/{id}/invite-code/revoke — regenerate."""
        response = await self._request(
            "post",
            f"/api/{self.session}/groups/{group_id}/invite-code/revoke",
            timeout=15,
            headers=self._headers(json=True),
        )
        _raise_for_group_status(response, op="revoke_invite_link")
        return self._invite_link_from_body(_safe_json(response))

    async def set_messages_admin_only(self, group_id: str, on: bool) -> None:
        """PUT /api/{session}/groups/{id}/settings/security/messages-admin-only."""
        response = await self._request(
            "put",
            f"/api/{self.session}/groups/{group_id}/settings/security/messages-admin-only",
            timeout=15,
            json={"value": on},
            headers=self._headers(json=True),
        )
        _raise_for_group_status(response, op="set_messages_admin_only")

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        """DELETE /api/{session}/chats/{chatId}/messages/{messageId}."""
        response = await self._request(
            "delete",
            f"/api/{self.session}/chats/{chat_id}/messages/{message_id}",
            timeout=15,
            headers=self._headers(),
        )
        _raise_for_group_status(response, op="delete_message")

    async def leave_group(self, group_id: str) -> None:
        """POST /api/{session}/groups/{id}/leave."""
        response = await self._request(
            "post",
            f"/api/{self.session}/groups/{group_id}/leave",
            timeout=15,
            headers=self._headers(json=True),
        )
        _raise_for_group_status(response, op="leave_group")
