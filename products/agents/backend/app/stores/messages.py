"""Messages store — ``agents.messages`` rows (contract §E.1).

Seed IO shape: ``MessageStore`` Protocol + ``FakeMessageStore`` +
``SupabaseMessageStore`` (Real) + ``get_message_store(settings)`` factory.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._util import utcnow

__all__ = [
    "ROLES",
    "MessageRecord",
    "MessageStore",
    "FakeMessageStore",
    "SupabaseMessageStore",
    "get_message_store",
]

_SCHEMA = "agents"
_TABLE = "messages"

#: Contract §E.1 `role` CHECK.
ROLES = ("user", "assistant", "system")


@dataclass(frozen=True)
class MessageRecord:
    id: UUID
    org_id: UUID
    conversation_id: UUID
    role: str
    texto: str
    blocks: list[dict[str, Any]] = field(default_factory=list)
    token_usage: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


class MessageStore(Protocol):
    def add(
        self,
        org_id: UUID,
        conversation_id: UUID,
        role: str,
        texto: str,
        *,
        blocks: list[dict[str, Any]] | None = None,
        token_usage: dict[str, Any] | None = None,
    ) -> MessageRecord:
        ...

    def list(
        self,
        org_id: UUID,
        conversation_id: UUID,
        *,
        before: UUID | None = None,
        limite: int = 50,
    ) -> list[MessageRecord]:
        """Contract §E.2 "Newest last" — always returns oldest-first within
        the returned page. ``before`` (a message id) pages backward: the
        page returned is the ``limite`` messages immediately preceding
        that message, still oldest-first."""
        ...


class FakeMessageStore:
    """In-memory :class:`MessageStore`."""

    def __init__(self) -> None:
        # (org_id, conversation_id) -> list[dict], append-order == created_at order
        self._rows: dict[tuple[UUID, UUID], list[dict[str, Any]]] = {}

    def add(
        self,
        org_id: UUID,
        conversation_id: UUID,
        role: str,
        texto: str,
        *,
        blocks: list[dict[str, Any]] | None = None,
        token_usage: dict[str, Any] | None = None,
    ) -> MessageRecord:
        if role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}; got {role!r}")
        now = utcnow()
        row = {
            "id": uuid4(),
            "org_id": org_id,
            "conversation_id": conversation_id,
            "role": role,
            "texto": texto,
            "blocks": list(blocks or []),
            "token_usage": token_usage,
            "created_at": now,
            "updated_at": now,
        }
        self._rows.setdefault((org_id, conversation_id), []).append(row)
        return self._to_record(row)

    def list(
        self,
        org_id: UUID,
        conversation_id: UUID,
        *,
        before: UUID | None = None,
        limite: int = 50,
    ) -> list[MessageRecord]:
        rows = self._rows.get((org_id, conversation_id), [])
        if before is not None:
            cutoff_idx = next(
                (i for i, r in enumerate(rows) if r["id"] == before), None
            )
            candidates = rows if cutoff_idx is None else rows[:cutoff_idx]
        else:
            candidates = rows
        page = candidates[-limite:] if limite > 0 else []
        return [self._to_record(r) for r in page]

    @staticmethod
    def _to_record(row: dict[str, Any]) -> MessageRecord:
        return MessageRecord(**row)


class SupabaseMessageStore:
    """Real :class:`MessageStore` — Postgres via the admin client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _table(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    def add(
        self,
        org_id: UUID,
        conversation_id: UUID,
        role: str,
        texto: str,
        *,
        blocks: list[dict[str, Any]] | None = None,
        token_usage: dict[str, Any] | None = None,
    ) -> MessageRecord:
        if role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}; got {role!r}")
        payload = {
            "org_id": str(org_id),
            "conversation_id": str(conversation_id),
            "role": role,
            "texto": texto,
            "blocks": list(blocks or []),
            "token_usage": token_usage,
        }
        resp = self._table().insert(payload).execute()
        rows = resp.data or []
        return self._record(rows[0] if rows else payload)

    def list(
        self,
        org_id: UUID,
        conversation_id: UUID,
        *,
        before: UUID | None = None,
        limite: int = 50,
    ) -> list[MessageRecord]:
        query = (
            self._table()
            .select("*")
            .eq("org_id", str(org_id))
            .eq("conversation_id", str(conversation_id))
        )
        if before is not None:
            cursor_resp = (
                self._table().select("created_at").eq("id", str(before)).execute()
            )
            cursor_rows = cursor_resp.data or []
            if cursor_rows:
                query = query.lt("created_at", cursor_rows[0]["created_at"])
        resp = (
            query.order("created_at", desc=True).limit(max(limite, 0)).execute()
        )
        rows = list(resp.data or [])
        rows.reverse()  # newest-last within the page
        return [self._record(row) for row in rows]

    @staticmethod
    def _record(row: dict[str, Any]) -> MessageRecord:
        return MessageRecord(
            id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            conversation_id=UUID(str(row["conversation_id"])),
            role=row["role"],
            texto=row["texto"],
            blocks=list(row.get("blocks") or []),
            token_usage=row.get("token_usage"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def get_message_store(settings: Any) -> MessageStore:
    """Real when a Supabase service-role key is configured, Fake otherwise
    — same signal as :func:`app.stores.agents.get_agent_store`."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeMessageStore()
    from app.database import get_admin_client

    return SupabaseMessageStore(get_admin_client())
