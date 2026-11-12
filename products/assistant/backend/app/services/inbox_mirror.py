"""The owner's conversations: the seed inbox store fed by the SAME webhook event as the intake queue.

Owner decision 2026-11-12: the personal line's 1:1 conversations are kept, BOTH directions (what people wrote, what the
owner and the assistant answered), so the owner can read and reply in the app (`/conversas`) and the assistant can be
evaluated over time. The seed ingest persists through ONE `WhatsAppChatStore`; `MirrorChatStore` is that store:

* every 1:1 message the pre-store predicate lets through lands in the seed inbox tables (`whatsapp_chats` /
  `whatsapp_messages`, migration 022) -- including the owner's own sends and the assistant's replies (`from_me`);
* an INBOUND text that also passes the intake input contract (`inbound_one_to_one_only`, unchanged) is ALSO appended to
  the intake queue, exactly as before -- the classifier still never sees a `from_me` or a group;
* the intake feed is live-only: a message older than `INTAKE_MAX_AGE` (a backfill of history) goes to the inbox only,
  so pulling 90 days of history never floods the classifier with `skipped` rows.

LGPD: nothing here logs a body, a phone or a chat id.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from noctusai_lib.integrations.whatsapp.inbox import InboxChat, InboxMessage
from noctusai_lib.integrations.whatsapp.inbox.ingest import ChatIdentity, ShouldStore, is_non_conversation_jid
from noctusai_lib.integrations.whatsapp.inbox.predicates import (
    SKIP_BROADCAST, SKIP_EXCLUDED, SKIP_GROUP, inbound_one_to_one_only,
)

#: A message older than this is history (backfill), not live traffic: it is stored in the inbox but not taken into intake.
INTAKE_MAX_AGE = timedelta(hours=24)


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", (value or "").split("@", 1)[0])


def conversation_should_store(excluded: Iterable[str] = ()) -> ShouldStore:
    """The inbox's pre-store contract: 1:1 conversations only (no group, status, broadcast / newsletter), minus the
    exclusion list (compared by digits). Unlike the intake contract it KEEPS `from_me` and API-sourced messages: the
    owner's sends and the assistant's replies are exactly what the evaluation reads."""
    blocked = {d for d in (_digits(x) for x in excluded) if d}

    def should_store(message: InboxMessage, chat: ChatIdentity) -> "bool | str":
        if chat.is_group or message.chat_id.endswith("@g.us"):
            return SKIP_GROUP
        if is_non_conversation_jid(message.chat_id):
            return SKIP_BROADCAST
        if blocked and (_digits(chat.phone) in blocked or _digits(chat.chat_id) in blocked):
            return SKIP_EXCLUDED
        return True

    return should_store


def _identity(chat_id: str, phone: str | None = None, is_group: bool | None = None) -> ChatIdentity:
    return ChatIdentity(
        chat_id=chat_id, phone=phone or _digits(chat_id) or None, name=None,
        is_group=chat_id.endswith("@g.us") if is_group is None else is_group,
    )


def intake_wanted(intake_predicate: ShouldStore, message: InboxMessage, chat: ChatIdentity) -> bool:
    """True when the message also belongs to the intake queue / the live reply (inbound, 1:1, not excluded)."""
    return intake_predicate(message, chat) is True


def guarded_on_message(
    inner: Callable[..., Any], intake_predicate: ShouldStore, forward_human: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """The live-reply seam only sees what the intake contract admits: the inbox now also stores the owner's sends and
    delivers them to `on_message`, and the live reply must never react to them (nor to a group). The owner's own text is
    instead handed to `forward_human` (append to the agent's thread, no turn) so the agent knows what the owner said.

    NOC-REMEDIATE[assistant-inbox-pause-delete]: per-chat agent pause + per-chat LGPD delete land in the seed organ on
    feat/seed-inbox-pause-delete; wire `on_pause` / `on_delete_chat` here once that branch is on dev — 2026-11-12"""

    async def on_message(org_id, connection_id, chat: InboxChat, message: InboxMessage) -> None:
        identity = _identity(message.chat_id, chat.phone, chat.is_group)
        if message.from_me:
            if forward_human is not None and conversation_should_store()(message, identity) is True:
                await forward_human(org_id, connection_id, chat, message)
            return
        if not intake_wanted(intake_predicate, message, identity):
            return
        await inner(org_id, connection_id, chat, message)

    return on_message


def _is_live(message: InboxMessage, now: datetime) -> bool:
    try:
        ts = datetime.fromisoformat(str(message.timestamp).replace("Z", "+00:00"))
    except ValueError:
        return True  # an unparsable timestamp is treated as live: the intake function itself dedups and gates by paired_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return now - ts <= INTAKE_MAX_AGE


class MirrorChatStore:
    """`WhatsAppChatStore` = the seed inbox store + the intake feed on `insert_message`. Every other call is the inbox
    store's own (reads, mark-read, backfill bookkeeping, acks): the intake keeps no chat log."""

    def __init__(
        self, inbox: Any, intake: Any, intake_predicate: ShouldStore, *, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._inbox = inbox
        self._intake = intake
        self._intake_predicate = intake_predicate
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def insert_message(self, *, org_id, connection_id, message: InboxMessage) -> bool:
        """The intake append goes FIRST and its failure propagates (the webhook answers 5xx, WAHA retries, both dedup on
        the WAHA message id). The returned bool is the INBOX's: it drives the realtime publish and `on_message`."""
        if _is_live(message, self._clock()) and intake_wanted(self._intake_predicate, message, _identity(message.chat_id)):
            self._intake.insert_message(org_id=org_id, connection_id=connection_id, message=message)
        return self._inbox.insert_message(org_id=org_id, connection_id=connection_id, message=message)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inbox, name)


def build_mirror_store(inbox: Any, intake: Any, excluded: Iterable[str] = ()) -> MirrorChatStore:
    return MirrorChatStore(inbox, intake, inbound_one_to_one_only(list(excluded)))


__all__ = [
    "INTAKE_MAX_AGE", "MirrorChatStore", "build_mirror_store", "conversation_should_store",
    "guarded_on_message", "intake_wanted",
]
