"""Channel inbound ledger — ``agents.channel_inbound`` (migration 025).

The idempotency record of the product turn API (Lais contract §10.1 M2): one
row per inbound provider message, unique on ``(org_id, connection_id,
provider_message_id)``. It carries the sha256 of the message text (a replay of
an id with DIFFERENT text is a 409 ``idempotency_conflict``, never a second
turn) and, once the turn finished, the stored reply (replaying an id returns
it — the model never runs twice for one inbound message).

Seed IO shape: ``ChannelInboundStore`` Protocol + ``FakeChannelInboundStore`` +
``SupabaseChannelInboundStore`` (Real) + ``get_channel_inbound_store(settings)``
factory. Every method is org-scoped and the DB cascades the rows with their
conversation (deletion on request / the 180-day purge take them too).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.stores._db_errors import StudioConflict, exec_query
from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import Conflict

__all__ = [
    "ChannelInboundRecord",
    "ChannelInboundStore",
    "FakeChannelInboundStore",
    "SupabaseChannelInboundStore",
    "get_channel_inbound_store",
]

_SCHEMA = "agents"
_TABLE = "channel_inbound"


@dataclass(frozen=True)
class ChannelInboundRecord:
    org_id: UUID
    connection_id: UUID
    provider_message_id: str
    conversation_id: UUID
    texto_sha256: str
    reply: dict[str, Any] | None
    replied_at: datetime | None
    created_at: datetime


class ChannelInboundStore(Protocol):
    def find(
        self, org_id: UUID, connection_id: UUID, provider_message_ids: Sequence[str]
    ) -> dict[str, ChannelInboundRecord]:
        """The known rows among ``provider_message_ids``, keyed by id."""
        ...

    def add(
        self, org_id: UUID, connection_id: UUID, conversation_id: UUID,
        provider_message_id: str, texto_sha256: str,
    ) -> ChannelInboundRecord:
        """Record one inbound message. Raises :class:`~app.stores.errors.Conflict`
        when the id is already recorded (the unique index) — the caller already
        read :meth:`find` under the turn lock, so reaching it means a race."""
        ...

    def set_reply(
        self, org_id: UUID, connection_id: UUID, provider_message_ids: Sequence[str],
        reply: dict[str, Any],
    ) -> None:
        """Store the turn's reply on every message of the batch."""
        ...


class FakeChannelInboundStore:
    """In-memory :class:`ChannelInboundStore`."""

    def __init__(self) -> None:
        self._rows: dict[tuple[UUID, UUID, str], ChannelInboundRecord] = {}

    def find(self, org_id, connection_id, provider_message_ids):
        out = {}
        for pmid in provider_message_ids:
            row = self._rows.get((org_id, connection_id, pmid))
            if row is not None:
                out[pmid] = row
        return out

    def add(self, org_id, connection_id, conversation_id, provider_message_id, texto_sha256):
        key = (org_id, connection_id, provider_message_id)
        if key in self._rows:
            raise Conflict(f"inbound message {provider_message_id!r} already recorded")
        row = ChannelInboundRecord(
            org_id=org_id, connection_id=connection_id,
            provider_message_id=provider_message_id, conversation_id=conversation_id,
            texto_sha256=texto_sha256, reply=None, replied_at=None, created_at=utcnow(),
        )
        self._rows[key] = row
        return row

    def set_reply(self, org_id, connection_id, provider_message_ids, reply):
        from dataclasses import replace

        now = utcnow()
        for pmid in provider_message_ids:
            key = (org_id, connection_id, pmid)
            row = self._rows.get(key)
            if row is not None:
                self._rows[key] = replace(row, reply=dict(reply), replied_at=now)

    def purge_conversation(self, org_id: UUID, conversation_id: UUID) -> int:
        """Test-double half of the cascade (the Real one is the FK cascade)."""
        keys = [
            k for k, r in self._rows.items()
            if r.org_id == org_id and r.conversation_id == conversation_id
        ]
        for k in keys:
            del self._rows[k]
        return len(keys)


class SupabaseChannelInboundStore:
    """Real :class:`ChannelInboundStore` — Postgres via the admin client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _table(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    def find(self, org_id, connection_id, provider_message_ids):
        ids = list(provider_message_ids)
        if not ids:
            return {}
        out: dict[str, ChannelInboundRecord] = {}
        # A batch is <= 20 ids, far under the URL-length ceiling; one query.
        resp = (
            self._table().select("*")
            .eq("org_id", str(org_id)).eq("connection_id", str(connection_id))
            .in_("provider_message_id", ids)
            .execute()
        )
        for row in resp.data or []:
            rec = self._record(row)
            out[rec.provider_message_id] = rec
        return out

    def add(self, org_id, connection_id, conversation_id, provider_message_id, texto_sha256):
        payload = {
            "org_id": str(org_id), "connection_id": str(connection_id),
            "conversation_id": str(conversation_id),
            "provider_message_id": provider_message_id, "texto_sha256": texto_sha256,
        }
        try:
            resp = exec_query(self._table().insert(payload), unique_code="inbound_exists")
        except StudioConflict as exc:
            raise Conflict(f"inbound message {provider_message_id!r} already recorded") from exc
        rows = resp.data or []
        return self._record(rows[0] if rows else {**payload, "created_at": utcnow_iso()})

    def set_reply(self, org_id, connection_id, provider_message_ids, reply):
        ids = list(provider_message_ids)
        if not ids:
            return
        (
            self._table()
            .update({"reply": reply, "replied_at": utcnow_iso()})
            .eq("org_id", str(org_id)).eq("connection_id", str(connection_id))
            .in_("provider_message_id", ids)
            .execute()
        )

    @staticmethod
    def _record(row: dict[str, Any]) -> ChannelInboundRecord:
        return ChannelInboundRecord(
            org_id=UUID(str(row["org_id"])),
            connection_id=UUID(str(row["connection_id"])),
            provider_message_id=row["provider_message_id"],
            conversation_id=UUID(str(row["conversation_id"])),
            texto_sha256=row["texto_sha256"],
            reply=row.get("reply"),
            replied_at=row.get("replied_at"),
            created_at=row["created_at"],
        )


def get_channel_inbound_store(settings: Any) -> ChannelInboundStore:
    """Real when a Supabase service-role key is configured, Fake otherwise —
    same signal as :func:`app.stores.agents.get_agent_store`."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeChannelInboundStore()
    from app.database import get_admin_client

    return SupabaseChannelInboundStore(get_admin_client())
