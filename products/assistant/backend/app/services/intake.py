"""The Assistant's intake seam: the chat store the seed ingest writes into IS the intake queue.

The seed ingest pipeline (`ingest_waha_event`) persists through a `WhatsAppChatStore`. The Assistant deliberately does
NOT keep a chat log (raw third-party phones, history it never reads back), so this store implements only the four
calls the ingest makes and turns `insert_message` into ONE `assistant.append_intake(...)` RPC: the intake row and its
append-only `recebida` event are written in the same transaction, deduplicated on the WAHA message id, forward-only
from `paired_at`, text-only -- all decided inside that function (migration 015).

Why the write is in `insert_message` and not in the `on_message` seam: `notify_message` swallows every exception, so a
failed append would be lost behind a 200 ack. An exception here propagates, the webhook answers 5xx and WAHA retries;
the dedup key makes the retry safe.

LGPD: the only identifier that leaves this module is `chat_ref`, a keyed HMAC of the chat id. Nothing here logs a
phone, a chat id or a body.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.domain.jobs.wake import notify_enqueued
from noctusai_lib.integrations.whatsapp.inbox import ChatState, InboxChat, InboxMessage
from noctusai_lib.primitives.not_configured import IntegrationNotConfigured

logger = logging.getLogger(__name__)

#: Job type the intake trigger enqueues (migration 017); `app.shadow.worker.JOB_CLASSIFICAR` is the same string.
CLASSIFY_JOB_TYPE = "assistant.classificar_intake"


class IdentityKeyNotConfigured(RuntimeError, IntegrationNotConfigured):
    """`ASSISTANT_IDENTITY_HMAC_KEY` is unset: refuse to store anything rather than store a raw identifier."""


def chat_ref(key: str, chat_id: str) -> str:
    """Opaque, stable, keyed identifier of a conversation (HMAC-SHA256 over the chat id's digits-or-jid)."""
    if not key:
        raise IdentityKeyNotConfigured("ASSISTANT_IDENTITY_HMAC_KEY is not set")
    digits = re.sub(r"\D", "", chat_id.split("@", 1)[0])
    basis = digits or chat_id  # an unresolved @lid keeps its opaque id
    return hmac.new(key.encode("utf-8"), basis.encode("utf-8"), hashlib.sha256).hexdigest()


def _received_at(message: InboxMessage) -> str:
    try:
        parsed = datetime.fromisoformat(str(message.timestamp).replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


class IntakeChatStore:
    """Implements the slice of `WhatsAppChatStore` the ingest calls; everything else is intentionally absent."""

    def __init__(self, client_factory: Callable[[], Any], identity_key: Callable[[], str]) -> None:
        self._client_factory = client_factory
        self._identity_key = identity_key

    def _chat(self, chat_id: str) -> InboxChat:
        return InboxChat(
            chat_id=chat_ref(self._identity_key(), chat_id), name="", phone=None, is_group=False,
            last_message_preview="", last_message_at=None, last_message_from_me=None, unread_count=0,
        )

    def ensure_chat(self, *, org_id, connection_id, chat_id, name, phone, is_group, origin) -> ChatState:
        return ChatState(chat=self._chat(chat_id), origin=origin, created=False, notification_pending=False)

    def insert_message(self, *, org_id: UUID, connection_id: UUID, message: InboxMessage) -> bool:
        """True when a NEW intake row was written; False for a duplicate (replayed webhook)."""
        resp = self._client_factory().rpc(
            "append_intake",
            {
                "p_org_id": str(org_id),
                "p_connection_id": str(connection_id),
                "p_waha_message_id": message.id,
                "p_chat_ref": chat_ref(self._identity_key(), message.chat_id),
                "p_msg_type": message.type or "chat",
                "p_body": message.body or "",
                "p_received_at": _received_at(message),
            },
        ).execute()
        rows = getattr(resp, "data", None) or []
        if rows:
            outcome = rows[0].get("outcome")
            logger.info("intake appended connection=%s outcome=%s", connection_id, outcome)
            if outcome == "pending":
                # The classification job was enqueued by the database in this same transaction (trigger, migration
                # 017); wake the in-process classifier worker instead of letting it find the job on its next poll.
                notify_enqueued(CLASSIFY_JOB_TYPE)
        return bool(rows)

    def refresh_chat_after_message(self, *, org_id, connection_id, chat_id, message, name=None, phone=None) -> InboxChat:
        return self._chat(chat_id)

    # `apply_ack` is reached by `message.ack` events: the Assistant keeps no acks, so nothing was stored.
    def apply_ack(self, *, org_id, connection_id, waha_message_id, ack) -> Optional[InboxChat]:
        return None
