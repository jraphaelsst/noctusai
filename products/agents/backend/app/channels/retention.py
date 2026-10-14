"""Retention of channel conversations — LGPD (Lais contract §10.1 M5).

Two operations, both ONE transaction in production
(``agents.delete_channel_conversation`` / ``agents.purge_channel_conversations``,
migration 025: messages, approvals, the idempotency rows and the conversation —
the first two FK the conversation without a cascade, so a bare conversation
DELETE would fail):

* **deletion on request** — ``DELETE /api/channels/conversations`` ("apagar
  meus dados"): one conversation, org-scoped;
* **the retention purge** — a daily cron: every channel conversation whose last
  activity is older than ``settings.channel_retention_days`` (180).

Seed IO shape: ``ChannelRetention`` Protocol + ``FakeChannelRetention`` (over
the shared Fake stores of a test) + ``SupabaseChannelRetention`` (Real, RPC) +
``get_channel_retention(settings)`` factory.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import UUID

from app.stores._db_errors import exec_rpc

logger = logging.getLogger(__name__)

__all__ = [
    "ChannelRetention",
    "FakeChannelRetention",
    "SupabaseChannelRetention",
    "get_channel_retention",
    "purge_expired",
]

_SCHEMA = "agents"


class ChannelRetention(Protocol):
    def delete_conversation(self, org_id: UUID, conversation_id: UUID) -> bool:
        """Erase one CHANNEL conversation of ``org_id`` (messages, approvals,
        idempotency rows, the conversation + its contact). ``False`` when it
        does not exist for this org — a user conversation is never touched."""
        ...

    def purge_older_than(self, cutoff: datetime) -> int:
        """Erase every channel conversation whose last activity is before
        ``cutoff`` (and holds no live turn lock). Returns how many."""
        ...


class FakeChannelRetention:
    """Test double over the SAME Fake stores the app under test uses."""

    def __init__(self, conversations: Any, messages: Any, inbound: Any) -> None:
        self._conversations = conversations
        self._messages = messages
        self._inbound = inbound

    def delete_conversation(self, org_id: UUID, conversation_id: UUID) -> bool:
        if not self._conversations.purge_conversation(org_id, conversation_id):
            return False
        self._messages.purge_conversation(org_id, conversation_id)
        self._inbound.purge_conversation(org_id, conversation_id)
        return True

    def purge_older_than(self, cutoff: datetime) -> int:
        victims = self._conversations.channel_ids_inactive_since(cutoff)
        return sum(1 for org_id, cid in victims if self.delete_conversation(org_id, cid))


class SupabaseChannelRetention:
    """Real :class:`ChannelRetention` — the two SQL functions of migration 025."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def delete_conversation(self, org_id: UUID, conversation_id: UUID) -> bool:
        resp = exec_rpc(self._client, _SCHEMA, "delete_channel_conversation", {
            "p_org_id": str(org_id), "p_conversation_id": str(conversation_id),
        })
        return bool(resp.data)

    def purge_older_than(self, cutoff: datetime) -> int:
        resp = exec_rpc(self._client, _SCHEMA, "purge_channel_conversations", {
            "p_cutoff": cutoff.isoformat(),
        })
        return int(resp.data or 0)


def get_channel_retention(settings: Any) -> ChannelRetention:
    """Real when a Supabase service-role key is configured; otherwise the Fake
    over fresh Fake stores (a bare process with no database has nothing to
    purge — tests install their own shared instance through the DI seam)."""
    if not getattr(settings, "supabase_service_role_key", None):
        from app.stores.channel_inbound import FakeChannelInboundStore
        from app.stores.conversations import FakeConversationStore
        from app.stores.messages import FakeMessageStore

        return FakeChannelRetention(
            FakeConversationStore(), FakeMessageStore(), FakeChannelInboundStore()
        )
    from app.database import get_admin_client

    return SupabaseChannelRetention(get_admin_client())


def purge_expired(
    retention: ChannelRetention, *, retention_days: int,
    now: datetime | None = None,
) -> int:
    """The cron body: erase channel conversations idle for ``retention_days``.
    Logs the count only — never a conversation id or any lead data."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=int(retention_days))
    purged = retention.purge_older_than(cutoff)
    logger.info("agents.channel.retention_purge purged=%s retention_days=%s", purged, retention_days)
    return purged
