"""Deterministic in-memory WAHA client (no network).

Mirrors `WahaClient`'s send/download surface; adds bi-directional
`inject_inbound` + `sent_messages` for end-to-end test driving.

Use as the dev/local fallback when no `WAHA_BASE_URL` is configured,
or in tests as a deterministic stand-in. Same shape as
`google_maps.StaticRoutingAdapter` and `google_calendar.FakeCalendarAdapter`
per `KB § PATTERNS/seed-fake-real-adapter.md`.
"""

from __future__ import annotations

import asyncio
import copy
from typing import Any

from noctusai_lib.integrations.whatsapp.client import (
    RECOVER_READY_STATUSES,
    WahaGroupError,
    WahaNumberCheckError,
    WahaNumberNotOnWhatsApp,
    WahaSessionNotReady,
    WahaWebhookError,
    _default_owned_prefix,
    _session_config,
    _webhook_owned,
    recovery_outcome,
)
from noctusai_lib.integrations.whatsapp.line_policy import (
    FAKE_LINE_URL,
    LineEventSink,
    LinePolicy,
    LinePolicyDrift,
    LinePolicyGuard,
    LineRepairRefused,
    PolicyReadback,
    check_session_against_policy,
    resolve_line_policy,
)
from noctusai_lib.integrations.whatsapp.types import (
    GroupInfo,
    GroupParticipant,
    ParticipantChangeResult,
    ResolvedChat,
    WhatsAppInboundMessage,
)
from noctusai_lib.primitives.phone import br_mobile_variants

# 1x1 transparent PNG — deterministic stand-in for a real QR image so
# frontend/route tests can assert "bytes were served" without a browser.
_FAKE_QR_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
    b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeWahaClient(LinePolicyGuard):
    """In-memory WAHA stand-in. Records sent messages, serves
    pre-populated media, accepts injected inbound messages.

    Test pattern:
        client = FakeWahaClient()
        client.inject_text(chat_id="...", from_phone="...", text="...")
        # ... drive the consumer code that reads inbound_queue ...
        assert client.sent_messages[0]["text"] == "expected reply"
    """

    def __init__(
        self,
        *,
        session: str = "default",
        line_policy: LinePolicy | None = None,
        line_event_sink: LineEventSink | None = None,
    ):
        self.session = session
        # Same policy contract as WahaClient (KB § whatsapp.md § 6a): explicit > the SAME registry (key `fake://waha`,
        # then "*") > fail-closed UNDECLARED. A suite that drives sends declares `"*"` through the public registry.
        self._init_line_policy(
            label=f"fake#{session}",
            policy=resolve_line_policy(FAKE_LINE_URL, session, explicit=line_policy),
            sink=line_event_sink,
        )
        #: the `noweb` block the last `start_session` actually wrote (None before any start) -- what get_session echoes.
        self.session_noweb: dict[str, Any] | None = None
        self.sent_messages: list[dict[str, Any]] = []
        #: channels the fake line "owns/admins/follows": [{"id","name","role",...}] (WahaChannels reads these)
        self.fake_channels: list[dict[str, Any]] = []
        #: channel posts recorded by `channel_backend` (text + image), policy-guarded like every send
        self.channel_posts: list[dict[str, Any]] = []
        self.inbound_queue: list[WhatsAppInboundMessage] = []
        self.media_bytes: dict[str, bytes] = {}
        # Session-admin state machine. Unpaired by default — mirrors a
        # fresh WAHA container before any QR scan.
        self.session_status: str = "SCAN_QR_CODE"
        #: the paired account (`WahaClient.me()` is the public READ of it; renamed from `me`, which now names that method)
        self.paired_me: dict[str, Any] | None = None
        self.webhook_config: dict[str, Any] | None = None
        # Models WAHA's config.webhooks list (shared-session semantics).
        self.session_webhooks: list[dict[str, Any]] = []
        # When True, set/remove_webhook raise WahaWebhookError (mirrors an
        # unreadable session GET) and leave state untouched.
        self.fail_webhook_read: bool = False
        self.restart_count = 0
        self.start_count = 0
        # When True, start_session/restart_session leave session_status
        # UNCHANGED (mirrors a real WAHA session whose STORED credentials
        # are dead: restart retries them and hangs, then WAHA force-stops
        # it back to the same status) — only logout_session (which clears
        # credentials) unsticks it. Set via simulate_stuck_session();
        # drives recover_session's full ladder to its "logout_start" rung.
        self.credentials_dead: bool = False
        # Capture the last payload passed to start/restart so tests can assert
        # the NOWEB store config is included.
        self.last_start_payload: dict[str, Any] | None = None
        self.last_restart_payload: dict[str, Any] | None = None
        # Pre-populated chat list for list_chats / fetch_chat_messages.
        # Seed via client.fake_chats[chat_id] = [msg_dict, ...] and
        # client.fake_chat_list = [chat_dict, ...].
        self.fake_chat_list: list[dict[str, Any]] = []
        self.fake_chat_messages: dict[str, list[dict[str, Any]]] = {}
        # Pre-populated overview list for get_chats_overview. Separate from
        # fake_chat_list because the real WAHA shapes differ: list_chats
        # returns raw chat objects, chats/overview returns pre-shaped
        # ChatSummary objects ({id, name, picture, lastMessage, _chat}).
        # Seed via client.fake_chats_overview = [{...}, ...].
        self.fake_chats_overview: list[dict[str, Any]] = []
        # Identity resolution: seed before calling get_contact/get_lid_phone/list_lids.
        self.fake_contacts: dict[str, dict[str, Any]] = {}
        self.fake_lid_phones: dict[str, str] = {}
        self.fake_lids: list[dict[str, Any]] = []
        # send_seen call log — assert against this to verify read-receipt calls.
        self.seen_calls: list[dict[str, Any]] = []
        # Group management state. Seed `privacy_restricted_ids` before
        # `add_participants` to simulate a target whose privacy settings
        # block group invites (mirrors WAHA's real per-participant
        # "invite_required" outcome).
        self.fake_groups: dict[str, GroupInfo] = {}
        self._group_counter = 0
        self.privacy_restricted_ids: set[str] = set()
        self.invite_links: dict[str, str] = {}
        self.messages_admin_only: dict[str, bool] = {}
        self.deleted_messages: list[dict[str, str]] = []
        self.left_groups: list[str] = []
        # BR 9th-digit resolution. None = every number is "registered"
        # (legacy behaviour); a set of bare-digit numbers restricts which
        # spellings exist on WhatsApp. Set check_unavailable=True to model
        # WAHA's check-exists being down (send-then-retry path).
        self.registered_numbers: set[str] | None = None
        self.check_unavailable: bool = False

    # ------------------------------------------------------------------
    # Outbound — mirrors WahaClient.send_text / send_text_sync
    # ------------------------------------------------------------------

    async def send_text(self, chat_id: str, text: str) -> dict[str, Any]:
        return self._record_send(chat_id, text)

    @property
    def channel_backend(self) -> "_FakeChannelBackend":
        """Transport seam for `whatsapp.channels.WahaChannels` (same contract as the real HTTP backend)."""
        return _FakeChannelBackend(self)

    def send_text_sync(self, chat_id: str, text: str) -> dict[str, Any]:
        return self._record_send(chat_id, text)

    async def check_exists(self, phone: str) -> dict[str, Any]:
        if self.check_unavailable:
            raise WahaNumberCheckError(phone, 503)
        digits = "".join(c for c in phone if c.isdigit())
        exists = self.registered_numbers is None or digits in self.registered_numbers
        return {"numberExists": exists, "chatId": f"{digits}@c.us" if exists else None}

    async def resolve_chat_id(self, phone: str) -> ResolvedChat:
        candidates = br_mobile_variants(phone)
        if not candidates:
            raise WahaNumberNotOnWhatsApp([str(phone)])
        for candidate in candidates:
            body = await self.check_exists(candidate)
            if body["numberExists"]:
                return ResolvedChat(str(phone), body["chatId"], candidate != candidates[0], "check-exists")
        raise WahaNumberNotOnWhatsApp(candidates)

    async def send_text_to_phone(self, phone: str, text: str) -> dict[str, Any]:
        try:
            resolved = await self.resolve_chat_id(phone)
        except WahaNumberCheckError:
            candidates = br_mobile_variants(phone)
            if not candidates:
                raise WahaNumberNotOnWhatsApp([str(phone)])
            for index, candidate in enumerate(candidates):
                if self.registered_numbers is None or candidate in self.registered_numbers:
                    record = self._record_send(f"{candidate}@c.us", text)
                    return {**record, "resolvedChatId": record["chatId"],
                            "resolvedVariantUsed": index > 0, "resolutionMethod": "send-retry"}
            raise WahaNumberNotOnWhatsApp(candidates)
        record = self._record_send(resolved.chat_id, text)
        return {**record, "resolvedChatId": resolved.chat_id,
                "resolvedVariantUsed": resolved.variant_used, "resolutionMethod": resolved.method}

    def check_exists_sync(self, phone: str) -> dict[str, Any]:
        return asyncio.run(self.check_exists(phone))

    def resolve_chat_id_sync(self, phone: str) -> ResolvedChat:
        return asyncio.run(self.resolve_chat_id(phone))

    def send_text_to_phone_sync(self, phone: str, text: str) -> dict[str, Any]:
        return asyncio.run(self.send_text_to_phone(phone, text))

    def _record_send(self, chat_id: str, text: str) -> dict[str, Any]:
        self._guard_write("post", "/api/sendText")
        message_id = f"fake-msg-{len(self.sent_messages) + 1}"
        record = {
            "id": message_id,
            "session": self.session,
            "chatId": chat_id,
            "text": text,
        }
        self.sent_messages.append(record)
        return record

    async def send_seen(
        self,
        chat_id: str,
        message_id: str | None = None,
        participant: str | None = None,
    ) -> dict[str, Any]:
        """Record the call in ``seen_calls`` — mirrors WahaClient.send_seen.

        Assert against ``client.seen_calls`` for the exact call shape.
        """
        self._guard_write("post", "/api/sendSeen")
        record: dict[str, Any] = {
            "session": self.session,
            "chatId": chat_id,
            "messageId": message_id,
            "participant": participant,
        }
        self.seen_calls.append(record)
        return {"success": True}

    # ------------------------------------------------------------------
    # Outbound — mirrors WahaClient.download_media / download_media_sync
    # ------------------------------------------------------------------

    async def download_media(self, url: str) -> bytes:
        return self._fetch_media(url)

    def download_media_sync(self, url: str) -> bytes:
        return self._fetch_media(url)

    def _fetch_media(self, url: str) -> bytes:
        if url not in self.media_bytes:
            raise KeyError(
                f"FakeWahaClient: no media pre-populated for url={url}. "
                "Call client.media_bytes[url] = b'...' before downloading."
            )
        return self.media_bytes[url]

    # ------------------------------------------------------------------
    # Session admin — mirrors WahaClient session lifecycle / QR / webhook
    # ------------------------------------------------------------------

    async def get_session(self) -> dict[str, Any]:
        return {
            "name": self.session,
            "status": self.session_status,
            "me": self.paired_me,
            "engine": {"engine": "FAKE"},
            "config": {
                "webhooks": [dict(h) for h in self.session_webhooks],
                **({"noweb": copy.deepcopy(self.session_noweb)} if self.session_noweb else {}),
            },
        }

    async def provision_session(self) -> PolicyReadback:
        """Mirror of ``WahaClient.provision_session``: the ONLY thing that sets the Fake's session config."""
        policy = self._config_policy()
        if policy is None or not self.line_policy.declared:
            raise LineRepairRefused(line=self._line_label, op="provision_session", reason="not_config_authoritative")
        self.session_noweb = copy.deepcopy(_session_config(policy=policy)["config"]["noweb"])
        return await self.verify_line_policy()

    async def verify_line_policy(self) -> PolicyReadback:
        return check_session_against_policy(await self.get_session(), self.line_policy)

    async def me(self) -> dict[str, Any]:
        return dict(self.paired_me) if isinstance(self.paired_me, dict) else {}

    def me_sync(self) -> dict[str, Any]:
        return dict(self.paired_me) if isinstance(self.paired_me, dict) else {}

    async def start_session(self) -> dict[str, Any]:
        self.start_count += 1
        # what a real start writes: the line policy's flags (UNDECLARED's when undeclared), or the legacy default
        # WAHA's POST /start takes NO body: the payload is recorded for assertions but it never becomes the session's
        # config (only `provision_session` -- WAHA's create/PUT -- does). So an unprovisioned Fake reads back as drift.
        self.last_start_payload = _session_config(policy=self._config_policy())
        if self.credentials_dead:
            # Mirrors WAHA answering 409 "already started" on a session
            # that's genuinely stuck — nothing changes; the caller must
            # escalate (real start_session() already tolerates this 409).
            return {"name": self.session, "status": self.session_status}
        # Starting a fresh (unpaired) session puts it into SCAN_QR_CODE so
        # a QR is available; an already-paired session stays WORKING.
        if self.paired_me is None:
            self.session_status = "SCAN_QR_CODE"
        return {"name": self.session, "status": self.session_status}

    async def restart_session(self) -> dict[str, Any]:
        self._guard_repair("restart_session")
        self.restart_count += 1
        if self.credentials_dead:
            # Mirrors the live-fleet bug: restart retries the dead stored
            # credentials and hangs, then WAHA force-stops it back to the
            # same status — restart alone cannot recover this session.
            return {"name": self.session, "status": self.session_status}
        # A restart drops an unpaired session back to QR; a paired one
        # (credentials would persist on a real WAHA volume) comes back up.
        if self.paired_me is None:
            self.session_status = "SCAN_QR_CODE"
        else:
            self.session_status = "WORKING"
        return {"name": self.session, "status": self.session_status}

    async def logout_session(self) -> dict[str, Any]:
        self._guard_repair("logout_session")
        self.paired_me = None
        self.credentials_dead = False
        self.session_status = "SCAN_QR_CODE"
        return {"name": self.session, "status": self.session_status}

    async def get_qr(self) -> bytes:
        if not self.line_policy.send_enabled and self.line_policy.declared:
            rb = await self.verify_line_policy()
            if not rb.ok:
                raise LinePolicyDrift(line=self._line_label, mismatches=rb.mismatches)
        if self.session_status != "SCAN_QR_CODE":
            raise WahaSessionNotReady(status=self.session_status)
        return _FAKE_QR_PNG

    async def set_webhook(
        self, url: str, events: list[str], *, owned_prefix: str | None = None
    ) -> dict[str, Any]:
        """Mirror ``WahaClient.set_webhook``: MERGE into ``session_webhooks``
        (drop own url / ``owned_prefix`` entries, append the new one).
        ``webhook_config`` stays the last-registered entry (back-compat)."""
        self._guard_webhook(url)
        if self.fail_webhook_read:
            raise WahaWebhookError("set_webhook", "cannot read current webhooks")
        prefix = owned_prefix if owned_prefix is not None else _default_owned_prefix(url)
        self.session_webhooks = [
            h for h in self.session_webhooks if not _webhook_owned(h, url, prefix)
        ]
        self.webhook_config = {"url": url, "events": list(events)}
        self.session_webhooks.append(
            {**self.webhook_config, "hmac": None, "retries": None, "customHeaders": None}
        )
        # Real WAHA restarts on config change; mirror the status churn.
        return {
            "name": self.session,
            "status": self.session_status,
            "config": {"webhooks": [dict(h) for h in self.session_webhooks]},
        }

    async def remove_webhook(self, url_or_prefix: str) -> dict[str, Any]:
        """Mirror ``WahaClient.remove_webhook`` (no-op when nothing matches)."""
        self._guard_webhook(url_or_prefix)
        if self.fail_webhook_read:
            raise WahaWebhookError("remove_webhook", "cannot read current webhooks")
        kept = [
            h for h in self.session_webhooks
            if not _webhook_owned(h, url_or_prefix, url_or_prefix)
        ]
        removed = len(self.session_webhooks) - len(kept)
        self.session_webhooks = kept
        if self.webhook_config and not any(
            h.get("url") == self.webhook_config["url"] for h in kept
        ):
            self.webhook_config = None
        return {"removed": removed}

    async def recover_session(self, *, settle_seconds: float = 8.0) -> dict[str, Any]:
        """Deterministic mirror of ``WahaClient.recover_session``'s ladder.

        State transitions here happen synchronously through the same
        start/restart/logout state machine above (no real network, so no
        real settling time is needed) — ``settle_seconds`` is accepted
        for signature/Protocol parity but not actually waited on. Drive
        the FAILED-with-dead-credentials scenario via
        ``simulate_stuck_session()`` to exercise the full ladder down to
        the ``"logout_start"`` rung.
        """
        self._guard_repair("recover_session")
        state = await self.get_session()
        if state.get("status") == "WORKING":
            return recovery_outcome(state, "already_working")

        state = await self.start_session()
        if state.get("status") in RECOVER_READY_STATUSES:
            return recovery_outcome(await self.get_session(), "start")

        state = await self.restart_session()
        if state.get("status") in RECOVER_READY_STATUSES:
            return recovery_outcome(await self.get_session(), "restart")

        await self.logout_session()
        await self.start_session()
        return recovery_outcome(await self.get_session(), "logout_start")

    # ------------------------------------------------------------------
    # Chat history — mirrors WahaClient.list_chats / fetch_chat_messages
    # ------------------------------------------------------------------

    async def list_chats(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Return ``fake_chat_list[offset:offset + limit]``.

        Seed via ``client.fake_chat_list = [{...}, ...]`` before the call
        to simulate a WAHA store that already has history.
        """
        return self.fake_chat_list[offset : offset + limit]

    async def get_chats_overview(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return ``fake_chats_overview[:limit]``.

        Seed via ``client.fake_chats_overview = [{"id": ..., "name": ...,
        "picture": ..., "lastMessage": {...}, "_chat": {...}}, ...]``.
        """
        return self.fake_chats_overview[:limit]

    async def fetch_chat_messages(
        self, chat_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Return ``fake_chat_messages[chat_id][:limit]``.

        Seed via ``client.fake_chat_messages[chat_id] = [{...}, ...]``.
        """
        return self.fake_chat_messages.get(chat_id, [])[:limit]

    # ------------------------------------------------------------------
    # Identity resolution — mirrors WahaClient.get_contact/get_lid_phone/list_lids
    # ------------------------------------------------------------------

    async def get_contact(self, contact_id: str) -> dict[str, Any]:
        """Return ``fake_contacts[contact_id]`` or ``{}`` if not seeded.

        Seed via ``client.fake_contacts["5511@c.us"] = {"id": ..., "name": ...}``.
        """
        return self.fake_contacts.get(contact_id, {})

    async def get_lid_phone(self, lid: str) -> str | None:
        """Return ``fake_lid_phones[lid]`` or ``None`` if not seeded.

        Seed via ``client.fake_lid_phones["33613018058989@lid"] = "5511974693365@c.us"``.
        """
        return self.fake_lid_phones.get(lid)

    async def list_lids(self) -> list[dict[str, Any]]:
        """Return ``fake_lids``.

        Seed via ``client.fake_lids = [{"lid": "...", "pn": "..@c.us"}, ...]``.
        """
        return list(self.fake_lids)

    def simulate_pair(
        self, *, phone: str = "5511999999999", push_name: str = "Fake"
    ) -> None:
        """Test helper: flip the fake to a paired/WORKING session."""
        self.paired_me = {"id": f"{phone}@c.us", "pushName": push_name}
        self.session_status = "WORKING"

    def simulate_stuck_session(
        self,
        *,
        status: str = "FAILED",
        phone: str = "5511999999999",
        push_name: str = "Stuck",
    ) -> None:
        """Test helper: put the fake into the paired-but-dead-credentials
        stuck state ``recover_session``'s ladder exists to recover from
        (mirrors the live fleet bug: stored creds, ``restart`` retries
        them and hangs, only ``logout`` clears them). ``start_session``
        and ``restart_session`` become no-ops (status stays ``status``)
        until ``logout_session`` runs.
        """
        self.paired_me = {"id": f"{phone}@c.us", "pushName": push_name}
        self.session_status = status
        self.credentials_dead = True

    # ------------------------------------------------------------------
    # Bi-directional — test-driving inbound messages
    # ------------------------------------------------------------------

    def inject_inbound(self, message: WhatsAppInboundMessage) -> None:
        """Queue an inbound message as if WAHA delivered it via webhook.
        Consumers reading `inbound_queue` see messages in injection order."""
        self.inbound_queue.append(message)

    def inject_text(
        self,
        *,
        chat_id: str,
        from_phone: str,
        text: str,
        provider_message_id: str | None = None,
        from_name: str | None = None,
    ) -> WhatsAppInboundMessage:
        """Convenience: build + inject a text-only WhatsAppInboundMessage."""
        message = WhatsAppInboundMessage(
            provider_message_id=provider_message_id,
            chat_id=chat_id,
            from_phone=from_phone,
            text=text,
            session=self.session,
            from_name=from_name,
        )
        self.inject_inbound(message)
        return message

    def clear(self) -> None:
        """Reset between test cases."""
        self.sent_messages.clear()
        self.inbound_queue.clear()
        self.media_bytes.clear()
        self.fake_chat_list.clear()
        self.fake_chat_messages.clear()
        self.fake_chats_overview.clear()
        self.fake_contacts.clear()
        self.fake_lid_phones.clear()
        self.fake_lids.clear()
        self.seen_calls.clear()
        self.fake_groups.clear()
        self.privacy_restricted_ids.clear()
        self.invite_links.clear()
        self.messages_admin_only.clear()
        self.deleted_messages.clear()
        self.left_groups.clear()

    # ------------------------------------------------------------------
    # Group management — mirrors WahaClient's group surface (WahaGroupError
    # on an unknown group_id, ParticipantChangeResult per add/remove target)
    # ------------------------------------------------------------------

    async def create_group(self, name: str, participant_ids: list[str]) -> GroupInfo:
        self._guard_write("post", f"/api/{self.session}/groups")
        self._group_counter += 1
        group_id = f"fake-group-{self._group_counter}@g.us"
        info = GroupInfo(
            id=group_id,
            name=name,
            participants=[GroupParticipant(id=pid, role="participant") for pid in participant_ids],
        )
        self.fake_groups[group_id] = info
        return info

    async def list_groups(self, limit: int = 50, offset: int = 0) -> list[GroupInfo]:
        return list(self.fake_groups.values())[offset : offset + limit]

    async def get_group(self, group_id: str) -> GroupInfo:
        try:
            return self.fake_groups[group_id]
        except KeyError as exc:
            raise WahaGroupError(
                op="get_group", status=404, detail=f"group not found: {group_id}"
            ) from exc

    async def list_participants(self, group_id: str) -> list[GroupParticipant]:
        return list((await self.get_group(group_id)).participants)

    def _replace_participants(
        self, group_id: str, participants: list[GroupParticipant]
    ) -> None:
        group = self.fake_groups[group_id]
        self.fake_groups[group_id] = GroupInfo(
            id=group.id,
            name=group.name,
            participants=participants,
            owner=group.owner,
            description=group.description,
        )

    async def add_participants(
        self, group_id: str, participant_ids: list[str]
    ) -> list[ParticipantChangeResult]:
        """Adds each id unless seeded into `privacy_restricted_ids`
        (mirrors WAHA's real per-participant privacy-refusal outcome —
        ``ParticipantChangeResult(outcome="invite_required")``)."""
        self._guard_write("post", f"/api/{self.session}/groups/{group_id}/participants/add")
        group = await self.get_group(group_id)
        existing_ids = {p.id for p in group.participants}
        participants = list(group.participants)
        results: list[ParticipantChangeResult] = []
        for pid in participant_ids:
            if pid in existing_ids:
                results.append(ParticipantChangeResult(id=pid, outcome="added", code=200))
            elif pid in self.privacy_restricted_ids:
                results.append(
                    ParticipantChangeResult(id=pid, outcome="invite_required", code=403)
                )
            else:
                participants.append(GroupParticipant(id=pid, role="participant"))
                existing_ids.add(pid)
                results.append(ParticipantChangeResult(id=pid, outcome="added", code=200))
        self._replace_participants(group_id, participants)
        return results

    async def remove_participants(
        self, group_id: str, participant_ids: list[str]
    ) -> list[ParticipantChangeResult]:
        self._guard_write("post", f"/api/{self.session}/groups/{group_id}/participants/remove")
        group = await self.get_group(group_id)
        existing_ids = {p.id for p in group.participants}
        remaining = [p for p in group.participants if p.id not in participant_ids]
        self._replace_participants(group_id, remaining)
        return [
            ParticipantChangeResult(
                id=pid,
                outcome="removed" if pid in existing_ids else "failed",
                code=200 if pid in existing_ids else 404,
            )
            for pid in participant_ids
        ]

    async def _set_role(
        self, group_id: str, participant_ids: list[str], *, role: str
    ) -> None:
        self._guard_write("post", f"/api/{self.session}/groups/{group_id}/admin/{role}")
        group = await self.get_group(group_id)
        target_ids = set(participant_ids)
        updated = [
            GroupParticipant(id=p.id, role=role) if p.id in target_ids else p  # type: ignore[arg-type]
            for p in group.participants
        ]
        self._replace_participants(group_id, updated)

    async def promote_admins(self, group_id: str, participant_ids: list[str]) -> None:
        await self._set_role(group_id, participant_ids, role="admin")

    async def demote_admins(self, group_id: str, participant_ids: list[str]) -> None:
        await self._set_role(group_id, participant_ids, role="participant")

    async def get_invite_link(self, group_id: str) -> str:
        await self.get_group(group_id)  # raises WahaGroupError if unknown
        return self.invite_links.setdefault(
            group_id, f"https://chat.whatsapp.com/fake-{group_id.split('@')[0]}"
        )

    async def revoke_invite_link(self, group_id: str) -> str:
        self._guard_write("post", f"/api/{self.session}/groups/{group_id}/invite-code/revoke")
        await self.get_group(group_id)
        new_link = f"https://chat.whatsapp.com/fake-{group_id.split('@')[0]}-r{len(self.invite_links) + 1}"
        self.invite_links[group_id] = new_link
        return new_link

    async def set_messages_admin_only(self, group_id: str, on: bool) -> None:
        self._guard_write("put", f"/api/{self.session}/groups/{group_id}/settings/security/messages-admin-only")
        await self.get_group(group_id)
        self.messages_admin_only[group_id] = on

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        self._guard_write("delete", f"/api/{self.session}/chats/{chat_id}/messages/{message_id}")
        self.deleted_messages.append({"chatId": chat_id, "messageId": message_id})

    async def leave_group(self, group_id: str) -> None:
        self._guard_write("post", f"/api/{self.session}/groups/{group_id}/leave")
        self.fake_groups.pop(group_id, None)
        self.left_groups.append(group_id)


class _FakeChannelBackend:
    def __init__(self, client: FakeWahaClient):
        self._c = client

    async def list_raw(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._c.fake_channels)

    async def post(self, path: str, body: dict[str, Any], op: str) -> dict[str, Any]:
        self._c._guard_write("post", path)
        record = {"id": f"fake-chan-msg-{len(self._c.channel_posts) + 1}", "op": op, **copy.deepcopy(body)}
        self._c.channel_posts.append(record)
        return record
