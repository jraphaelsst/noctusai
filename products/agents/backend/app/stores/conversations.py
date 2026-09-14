"""Conversations store — ``agents.conversations`` rows (contract §E.1) plus
the one-in-flight-turn lock (§E.2, "409 turn_in_progress").

Seed IO shape: ``ConversationStore`` Protocol + ``FakeConversationStore`` +
``SupabaseConversationStore`` (Real) + ``get_conversation_store(settings)``
factory. See ``migrations/006_agents.sql`` header for the turn-lock design
rationale (single atomic ``UPDATE ... WHERE`` compare-and-swap, no advisory
lock, no separate SELECT-then-UPDATE pair).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import NotFound

__all__ = [
    "STATUSES",
    "ConversationRecord",
    "ConversationStore",
    "FakeConversationStore",
    "SupabaseConversationStore",
    "get_conversation_store",
]

_SCHEMA = "agents"
_TABLE = "conversations"

#: Contract §E.1 `status` CHECK.
STATUSES = ("ativa", "arquivada")


@dataclass(frozen=True)
class ConversationRecord:
    id: UUID
    org_id: UUID
    agent_id: UUID
    owner_user_id: UUID
    titulo: str | None
    sdk_session_id: str | None
    status: str
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ConversationStore(Protocol):
    def create(
        self, org_id: UUID, agent_id: UUID, owner_user_id: UUID,
        titulo: str | None = None,
    ) -> ConversationRecord:
        ...

    def get_owned(
        self, org_id: UUID, id: UUID, user_id: UUID
    ) -> ConversationRecord:
        """Raises :class:`~app.stores.errors.NotFound` unless ``user_id``
        owns the conversation (or it doesn't exist / belongs to another
        org) — both cases collapse to the same error on purpose."""
        ...

    def list_owned(
        self, org_id: UUID, user_id: UUID
    ) -> list[ConversationRecord]:
        ...

    def try_acquire_turn(
        self, org_id: UUID, id: UUID, instance_id: str, ttl_seconds: int
    ) -> bool:
        """Atomically claim the turn lock. Returns ``False`` when another
        (unexpired) instance already holds it — never raises for the
        contention case, since 409 ``turn_in_progress`` is the expected,
        frequent outcome, not an error."""
        ...

    def release_turn(self, org_id: UUID, id: UUID, instance_id: str) -> None:
        """Clear the lock, ONLY if ``instance_id`` is the current holder.
        A stale/foreign instance releasing a lock it doesn't hold is a
        silent no-op — it must never clear another instance's live lock."""
        ...


class FakeConversationStore:
    """In-memory :class:`ConversationStore`."""

    def __init__(self) -> None:
        self._rows: dict[UUID, dict[str, Any]] = {}

    def create(
        self, org_id: UUID, agent_id: UUID, owner_user_id: UUID,
        titulo: str | None = None,
    ) -> ConversationRecord:
        now = utcnow()
        row: dict[str, Any] = {
            "id": uuid4(),
            "org_id": org_id,
            "agent_id": agent_id,
            "owner_user_id": owner_user_id,
            "titulo": titulo,
            "sdk_session_id": None,
            "status": "ativa",
            "last_message_at": None,
            "created_at": now,
            "updated_at": now,
            "_turn_lock_until": None,
            "_turn_lock_instance_id": None,
        }
        self._rows[row["id"]] = row
        return self._to_record(row)

    def get_owned(
        self, org_id: UUID, id: UUID, user_id: UUID
    ) -> ConversationRecord:
        row = self._rows.get(id)
        if (
            row is None
            or row["org_id"] != org_id
            or row["owner_user_id"] != user_id
        ):
            raise NotFound(f"conversation {id} not found for user {user_id}")
        return self._to_record(row)

    def list_owned(
        self, org_id: UUID, user_id: UUID
    ) -> list[ConversationRecord]:
        return [
            self._to_record(row)
            for row in self._rows.values()
            if row["org_id"] == org_id and row["owner_user_id"] == user_id
        ]

    def try_acquire_turn(
        self, org_id: UUID, id: UUID, instance_id: str, ttl_seconds: int
    ) -> bool:
        row = self._rows.get(id)
        if row is None or row["org_id"] != org_id:
            raise NotFound(f"conversation {id} not found for org {org_id}")
        now = utcnow()
        held_until = row["_turn_lock_until"]
        if held_until is not None and held_until >= now:
            return False
        row["_turn_lock_until"] = now + timedelta(seconds=ttl_seconds)
        row["_turn_lock_instance_id"] = instance_id
        row["updated_at"] = now
        return True

    def release_turn(self, org_id: UUID, id: UUID, instance_id: str) -> None:
        row = self._rows.get(id)
        if row is None or row["org_id"] != org_id:
            return
        if row["_turn_lock_instance_id"] != instance_id:
            return
        row["_turn_lock_until"] = None
        row["_turn_lock_instance_id"] = None
        row["updated_at"] = utcnow()

    @staticmethod
    def _to_record(row: dict[str, Any]) -> ConversationRecord:
        return ConversationRecord(
            id=row["id"],
            org_id=row["org_id"],
            agent_id=row["agent_id"],
            owner_user_id=row["owner_user_id"],
            titulo=row["titulo"],
            sdk_session_id=row["sdk_session_id"],
            status=row["status"],
            last_message_at=row["last_message_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class SupabaseConversationStore:
    """Real :class:`ConversationStore` — Postgres via the admin client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _table(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    def create(
        self, org_id: UUID, agent_id: UUID, owner_user_id: UUID,
        titulo: str | None = None,
    ) -> ConversationRecord:
        payload = {
            "org_id": str(org_id),
            "agent_id": str(agent_id),
            "owner_user_id": str(owner_user_id),
            "titulo": titulo,
            "status": "ativa",
        }
        resp = self._table().insert(payload).execute()
        rows = resp.data or []
        return self._record(rows[0] if rows else payload)

    def get_owned(
        self, org_id: UUID, id: UUID, user_id: UUID
    ) -> ConversationRecord:
        resp = (
            self._table()
            .select("*")
            .eq("id", str(id))
            .eq("org_id", str(org_id))
            .eq("owner_user_id", str(user_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"conversation {id} not found for user {user_id}")
        return self._record(rows[0])

    def list_owned(
        self, org_id: UUID, user_id: UUID
    ) -> list[ConversationRecord]:
        resp = (
            self._table()
            .select("*")
            .eq("org_id", str(org_id))
            .eq("owner_user_id", str(user_id))
            .execute()
        )
        return [self._record(row) for row in (resp.data or [])]

    def try_acquire_turn(
        self, org_id: UUID, id: UUID, instance_id: str, ttl_seconds: int
    ) -> bool:
        now = utcnow()
        now_iso = now.isoformat()
        until_iso = (now + timedelta(seconds=ttl_seconds)).isoformat()
        resp = (
            self._table()
            .update(
                {
                    "turn_lock_until": until_iso,
                    "turn_lock_instance_id": instance_id,
                    "updated_at": now_iso,
                }
            )
            .eq("id", str(id))
            .eq("org_id", str(org_id))
            .or_(f"turn_lock_until.is.null,turn_lock_until.lt.{now_iso}")
            .execute()
        )
        rows = resp.data or []
        if rows:
            return True
        # Distinguish "conversation doesn't exist" from "lock contention" —
        # a missing conversation must still surface as NotFound, not a
        # silent False that looks identical to a live lock.
        exists = (
            self._table()
            .select("id")
            .eq("id", str(id))
            .eq("org_id", str(org_id))
            .execute()
        )
        if not (exists.data or []):
            raise NotFound(f"conversation {id} not found for org {org_id}")
        return False

    def release_turn(self, org_id: UUID, id: UUID, instance_id: str) -> None:
        self._table().update(
            {
                "turn_lock_until": None,
                "turn_lock_instance_id": None,
                "updated_at": utcnow_iso(),
            }
        ).eq("id", str(id)).eq("org_id", str(org_id)).eq(
            "turn_lock_instance_id", instance_id
        ).execute()

    @staticmethod
    def _record(row: dict[str, Any]) -> ConversationRecord:
        return ConversationRecord(
            id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            agent_id=UUID(str(row["agent_id"])),
            owner_user_id=UUID(str(row["owner_user_id"])),
            titulo=row.get("titulo"),
            sdk_session_id=row.get("sdk_session_id"),
            status=row.get("status", "ativa"),
            last_message_at=row.get("last_message_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def get_conversation_store(settings: Any) -> ConversationStore:
    """Real when a Supabase service-role key is configured, Fake otherwise
    — same signal as :func:`app.stores.agents.get_agent_store`."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeConversationStore()
    from app.database import get_admin_client

    return SupabaseConversationStore(get_admin_client())
