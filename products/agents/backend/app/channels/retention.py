"""Retention of channel conversations — LGPD (Lais contract §10.1 M5).

Three operations, each ONE transaction in production
(``agents.delete_channel_conversation`` / ``agents.purge_channel_conversations`` /
``agents.apagar_lead``, migrations 025 + 033: messages, approvals, the idempotency
rows and the conversation — the first two FK the conversation without a cascade, so
a bare conversation DELETE would fail; participants / events / skill openings /
feedback go with the thread by FK cascade):

* **deletion on request** — ``DELETE /api/channels/conversations`` ("apagar
  meus dados"): one conversation, org-scoped (the pre-v2 alias);
* **delete-by-lead** — ``DELETE /api/channels/leads/{ref}`` (Julia v2, §6.4): EVERY
  thread of the lead across all agents, the qualification records and the lead_ref;
* **the retention purge** — a daily cron: every channel conversation whose last
  activity (any agent's, the lead's or a human's) is older than
  ``settings.channel_retention_days`` (180). When the last thread of a lead is
  purged the lead_ref — and the qualification that hangs off it — goes too.

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
from app.stores.errors import NotFound
from app.stores.threads import PRODUTO_SW

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

    def delete_lead(self, org_id: UUID, ref_externa: str) -> bool:
        """Erase one LEAD across every agent: all its threads and everything that
        hangs off them, its qualification and the lead_ref itself. ``False`` when
        the lead is unknown for this org (idempotent — the caller treats it as done)."""
        ...

    def purge_older_than(self, cutoff: datetime) -> int:
        """Erase every channel conversation whose last activity is before
        ``cutoff`` (and holds no live turn lock). Returns how many."""
        ...


class FakeChannelRetention:
    """Test double over the SAME Fake stores the app under test uses."""

    def __init__(self, conversations: Any, messages: Any, inbound: Any, threads: Any = None) -> None:
        self._conversations = conversations
        self._messages = messages
        self._inbound = inbound
        #: A ``FakeThreadStore`` (Julia v2): participants / events / skill openings and lead_refs.
        self._threads = threads

    def delete_conversation(self, org_id: UUID, conversation_id: UUID) -> bool:
        lead_ref_id = self._lead_of(org_id, conversation_id)
        if not self._conversations.purge_conversation(org_id, conversation_id):
            return False
        self._messages.purge_conversation(org_id, conversation_id)
        self._inbound.purge_conversation(org_id, conversation_id)
        if self._threads is not None:
            self._threads.purge_thread(org_id, conversation_id)
            self._drop_orphan_lead(org_id, lead_ref_id)
        return True

    def delete_lead(self, org_id: UUID, ref_externa: str) -> bool:
        if self._threads is None:
            return False
        lead = self._threads.get_lead_ref_by_externa(org_id, ref_externa)
        if lead is None:
            return False
        for thread in self._conversations.list_threads_for_lead(org_id, lead.id):
            self.delete_conversation(org_id, thread.id)
        self._threads.purge_lead_ref(org_id, lead.id)
        return True

    def _lead_of(self, org_id: UUID, conversation_id: UUID) -> UUID | None:
        try:
            return self._conversations.get(org_id, conversation_id).lead_ref_id
        except NotFound:
            return None

    def _drop_orphan_lead(self, org_id: UUID, lead_ref_id: UUID | None) -> None:
        """The SQL functions drop a lead_ref with its LAST thread (and the qualification with it)."""
        if lead_ref_id is not None and not self._conversations.list_threads_for_lead(org_id, lead_ref_id):
            self._threads.purge_lead_ref(org_id, lead_ref_id)

    def purge_older_than(self, cutoff: datetime) -> int:
        victims = self._conversations.channel_ids_inactive_since(cutoff)
        return sum(1 for org_id, cid in victims if self.delete_conversation(org_id, cid))


class SupabaseChannelRetention:
    """Real :class:`ChannelRetention` — the SQL functions of migrations 025 + 033."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def delete_conversation(self, org_id: UUID, conversation_id: UUID) -> bool:
        resp = exec_rpc(self._client, _SCHEMA, "delete_channel_conversation", {
            "p_org_id": str(org_id), "p_conversation_id": str(conversation_id),
        })
        return bool(resp.data)

    def delete_lead(self, org_id: UUID, ref_externa: str) -> bool:
        resp = exec_rpc(self._client, _SCHEMA, "apagar_lead", {
            "p_org_id": str(org_id), "p_produto": PRODUTO_SW, "p_ref_externa": ref_externa,
        })
        data = resp.data
        return bool(data.get("encontrado")) if isinstance(data, dict) else False

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
        from app.stores.threads import FakeThreadStore

        conversations = FakeConversationStore()
        return FakeChannelRetention(
            conversations, FakeMessageStore(), FakeChannelInboundStore(), FakeThreadStore(conversations)
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
