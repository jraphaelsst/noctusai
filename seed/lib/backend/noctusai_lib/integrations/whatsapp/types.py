"""WhatsApp inbound message value objects + payload errors.

Ported verbatim from `whatsapp-google-scheduling/app/services/waha/types.py`
2026-05-03 via `projects/whatsapp-seed-absorption/`. Provider-neutral
naming (`InboundMessage`, `Media`) preferred; the legacy `Waha*` aliases
are kept so call sites built against the sibling shape work without a
rename pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class WhatsAppMedia:
    """Media attachment on an inbound WhatsApp message."""

    url: str | None
    mimetype: str | None


@dataclass(frozen=True)
class WhatsAppInboundMessage:
    """Parsed WhatsApp inbound message (provider-agnostic shape).

    Today populated by `parse_waha_inbound_message`; future Twilio /
    Cloud-API parsers populate the same shape.

    `group_id` / `author_id` are additive (default `None`) — a 1:1 chat
    leaves both unset. `group_id` is the `@g.us` chat id when the
    message came from a group (existing `chat_id`/`from_phone` stay
    populated exactly as before: `from_phone` is still derived from
    `chat_id`, so today it names the GROUP, not the sending
    participant — a known gap, not fixed by this addition, see
    `KB § CONTEXT/INTEGRATIONS/whatsapp.md`). `author_id` is the
    sending participant's JID within that group (WAHA's `participant` /
    `author` field) — the field a consumer needs to attribute a group
    message to its actual sender.
    """

    provider_message_id: str | None
    chat_id: str
    from_phone: str
    text: str
    session: str
    media: WhatsAppMedia | None = None
    from_name: str | None = None
    group_id: str | None = None
    author_id: str | None = None


class WhatsAppPayloadError(ValueError):
    """Inbound payload failed validation (missing chat_id / no text or media)."""


class WhatsAppIgnoredEvent(ValueError):
    """Inbound payload is structurally valid but the event type / source
    is intentionally ignored (e.g. `session.status`, own-message echoes)."""


@runtime_checkable
class WhatsAppClient(Protocol):
    """Send / download surface every WhatsApp connector implements.

    Both `WahaClient` (real, httpx-backed) and `FakeWahaClient`
    (in-memory deterministic) satisfy this Protocol naturally. Future
    Twilio / WhatsApp Cloud-API connectors land against the same shape.

    Per `KB § PATTERNS/seed-fake-real-adapter.md`: the Protocol is the
    contract that the gold-standard pattern's `get_<name>_adapter(...)`
    factory returns.
    """

    async def send_text(self, chat_id: str, text: str) -> dict[str, Any]: ...

    def send_text_sync(self, chat_id: str, text: str) -> dict[str, Any]: ...

    async def send_seen(
        self,
        chat_id: str,
        message_id: str | None = None,
        participant: str | None = None,
    ) -> dict[str, Any]: ...

    async def download_media(self, url: str) -> bytes: ...

    def download_media_sync(self, url: str) -> bytes: ...

    async def list_chats(self, limit: int = 50) -> list[dict[str, Any]]: ...

    async def get_chats_overview(self, limit: int = 50) -> list[dict[str, Any]]: ...

    async def fetch_chat_messages(
        self, chat_id: str, limit: int = 50
    ) -> list[dict[str, Any]]: ...

    # Identity resolution — WAHA 2026.x contact endpoints
    async def get_contact(self, contact_id: str) -> dict[str, Any]: ...

    async def get_lid_phone(self, lid: str) -> str | None: ...

    async def list_lids(self) -> list[dict[str, Any]]: ...

    # Session admin — connection lifecycle, QR pairing, webhook wiring.
    # Both `WahaClient` and `FakeWahaClient` have shipped these methods
    # since the multi-session pairing work; they were absent from this
    # Protocol (a partial connector still type-checked clean) until the
    # 2026-08 realtime-inbox seed-client slice added them here.
    async def get_session(self) -> dict[str, Any]: ...

    async def start_session(self) -> dict[str, Any]: ...

    async def restart_session(self) -> dict[str, Any]: ...

    async def logout_session(self) -> dict[str, Any]: ...

    async def get_qr(self) -> bytes: ...

    async def set_webhook(self, url: str, events: list[str]) -> dict[str, Any]: ...

    async def recover_session(self, *, settle_seconds: float = 8.0) -> dict[str, Any]: ...


@dataclass(frozen=True)
class GroupParticipant:
    """One member of a WhatsApp group, as WAHA's Groups API reports it."""

    id: str
    role: Literal["participant", "admin", "superadmin"] = "participant"


@dataclass(frozen=True)
class GroupInfo:
    """A WhatsApp group, as `create_group` / `list_groups` / `get_group`
    return it. `participants` defaults to `[]` on the list-groups summary
    shape — call `list_participants(group_id)` for the authoritative,
    always-populated roster."""

    id: str
    name: str
    participants: list[GroupParticipant] = field(default_factory=list)
    owner: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class ParticipantChangeResult:
    """One participant's outcome from `add_participants` / `remove_participants`.

    WAHA answers group membership changes per-participant rather than
    all-or-nothing — WhatsApp itself silently refuses some adds when the
    target's privacy settings block group invites, which WAHA surfaces
    as a per-participant non-2xx rather than a client-level error. That
    refusal maps to `"invite_required"` here so a bulk-add caller can
    tell "actually added" apart from "needs the invite link instead"
    without inspecting a raw status code itself.
    """

    id: str
    outcome: Literal["added", "removed", "invite_required", "failed"]
    code: int | None = None


@runtime_checkable
class WhatsAppGroupClient(Protocol):
    """WhatsApp group-management surface — deliberately separate from
    `WhatsAppClient` so a 1:1-only connector (the Meta Cloud API client
    has no group-management endpoints) isn't forced to implement group
    ops it structurally cannot support. `WahaClient` + `FakeWahaClient`
    satisfy this Protocol; `MetaCloudClient` does not.

    Broadcast to an existing group needs nothing new here: `send_text`
    (on `WhatsAppClient`) already accepts a `@g.us` chat id.
    """

    async def create_group(
        self, name: str, participant_ids: list[str]
    ) -> GroupInfo: ...

    async def list_groups(self, limit: int = 50, offset: int = 0) -> list[GroupInfo]: ...

    async def get_group(self, group_id: str) -> GroupInfo: ...

    async def list_participants(self, group_id: str) -> list[GroupParticipant]: ...

    async def add_participants(
        self, group_id: str, participant_ids: list[str]
    ) -> list[ParticipantChangeResult]: ...

    async def remove_participants(
        self, group_id: str, participant_ids: list[str]
    ) -> list[ParticipantChangeResult]: ...

    async def promote_admins(self, group_id: str, participant_ids: list[str]) -> None: ...

    async def demote_admins(self, group_id: str, participant_ids: list[str]) -> None: ...

    async def get_invite_link(self, group_id: str) -> str: ...

    async def revoke_invite_link(self, group_id: str) -> str: ...

    async def set_messages_admin_only(self, group_id: str, on: bool) -> None: ...

    async def delete_message(self, chat_id: str, message_id: str) -> None: ...

    async def leave_group(self, group_id: str) -> None: ...


# Legacy WAHA-prefixed aliases (kept for call-site portability).
WahaMedia = WhatsAppMedia
WahaInboundMessage = WhatsAppInboundMessage
WahaPayloadError = WhatsAppPayloadError
WahaIgnoredEvent = WhatsAppIgnoredEvent
