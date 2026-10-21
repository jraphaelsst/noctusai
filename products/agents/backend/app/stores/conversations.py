"""Conversations store — ``agents.conversations`` rows (contract §E.1) plus
the one-in-flight-turn lock (§E.2, "409 turn_in_progress").

Seed IO shape: ``ConversationStore`` Protocol + ``FakeConversationStore`` +
``SupabaseConversationStore`` (Real) + ``get_conversation_store(settings)``
factory. See ``migrations/006_agents.sql`` header for the turn-lock design
rationale (single atomic ``UPDATE ... WHERE`` compare-and-swap, no advisory
lock, no separate SELECT-then-UPDATE pair).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._db_errors import StudioConflict, exec_query
from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import NotFound

__all__ = [
    "STATUSES",
    "ChannelConversationStore",
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
    #: ``None`` ONLY for a channel conversation (025: a lead on a channel,
    #: driven by a product token — there is no human owner).
    owner_user_id: UUID | None
    titulo: str | None
    sdk_session_id: str | None
    status: str
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime
    #: Agent Studio §D6 (012 columns): the version a studio conversation is
    #: pinned to, and its client brain. Both ``None`` for Bia.
    version_id: UUID | None = None
    client_id: UUID | None = None
    #: Lais A2 (025): the channel identity. ``channel`` is ``None`` for every
    #: user conversation. ``channel_ref`` = ``{"connection_id", "chat_id"}``;
    #: ``contact`` = ``{"phone_e164", "display_name"}`` (display only — never
    #: part of a prompt, §10.1 M3).
    channel: str | None = None
    channel_ref: dict[str, Any] | None = None
    contact: dict[str, Any] | None = None
    #: Julia v2 (033): ``'thread_lead'`` for a channel conversation — the lead's
    #: THREAD, shared by every agent that talks to the lead — ``'chat'`` for a
    #: user conversation. ``lead_ref_id`` links the thread to its ``lead_refs``
    #: row (``None`` until linked); ``ultima_mensagem_lead_em`` is the last LEAD
    #: message (the drain-idle clock).
    tipo: str = "chat"
    lead_ref_id: UUID | None = None
    ultima_mensagem_lead_em: datetime | None = None


class ConversationStore(Protocol):
    def create(
        self, org_id: UUID, agent_id: UUID, owner_user_id: UUID,
        titulo: str | None = None,
        *,
        version_id: UUID | None = None,
        client_id: UUID | None = None,
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
        self, org_id: UUID, user_id: UUID, *, agent_id: UUID | None = None
    ) -> list[ConversationRecord]:
        """``agent_id`` (Agent Studio §D6) narrows the list to one agent."""
        ...

    def pin_version(self, org_id: UUID, id: UUID, version_id: UUID) -> ConversationRecord:
        """Agent Studio §D6: set ``version_id`` ONLY while it is still null (a
        studio conversation created before its agent had a published
        version pins the active one at its first turn). A conversation that
        is already pinned is returned unchanged — a newer publish never
        moves it. Raises :class:`~app.stores.errors.NotFound`."""
        ...

    def get(self, org_id: UUID, id: UUID) -> ConversationRecord:
        """G1b addition — NO owner check (unlike :meth:`get_owned`), for
        the admin-may-read paths (contract §E.2 "404 unless the caller
        owns the conversation; admins may read"). Callers MUST perform
        the role check themselves before falling back to this method —
        it is not itself an authorization boundary. Raises
        :class:`~app.stores.errors.NotFound` if unknown/other-org."""
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

    def set_sdk_session_id(
        self, org_id: UUID, id: UUID, sdk_session_id: str | None
    ) -> ConversationRecord:
        """G1b addition (contract §E.9 point 5: "persists the
        ``sdk_session_id`` carried by the final ``session.status`` payload").
        Raises :class:`~app.stores.errors.NotFound` on an unknown/other-org
        id."""
        ...

    def set_titulo(self, org_id: UUID, id: UUID, titulo: str) -> ConversationRecord:
        """Rename (``PATCH /api/conversations/{conversation_id}``) —
        org-scoped only, same shape as :meth:`set_sdk_session_id`; the
        router verifies ownership itself (``get_owned``) BEFORE calling
        this, so this method is not itself an authorization boundary.
        Raises :class:`~app.stores.errors.NotFound` on an unknown/other-org
        id."""
        ...


class ChannelConversationStore(Protocol):
    """The channel half of the store (Lais A2): conversations a product token
    drives for an external contact. Every method is org-scoped."""

    def find_channel(
        self, org_id: UUID, agent_id: UUID, channel: str, channel_ref: dict[str, Any]
    ) -> ConversationRecord | None:
        """The conversation for ``(org, agent, channel, channel_ref)`` or
        ``None`` (an explicit maybe-read, not an error)."""
        ...

    def find_thread(
        self, org_id: UUID, channel: str, channel_ref: dict[str, Any]
    ) -> ConversationRecord | None:
        """Julia v2: the lead's THREAD for ``(org, channel, channel_ref)`` —
        whichever agent opened it (the thread is shared, §6). ``None`` when the
        lead was never served."""
        ...

    def create_channel(
        self, org_id: UUID, agent_id: UUID, channel: str, channel_ref: dict[str, Any],
        contact: dict[str, Any] | None, *, version_id: UUID | None = None,
        lead_ref_id: UUID | None = None,
    ) -> ConversationRecord:
        """Insert the channel conversation (a ``thread_lead``; ``agent_id`` is
        the agent that OPENED it). A concurrent create of the same identity
        (the 025 unique index) returns the EXISTING row — never a second one,
        never an error."""
        ...

    def touch_lead_message(self, org_id: UUID, id: UUID) -> ConversationRecord:
        """A LEAD message arrived: stamp ``ultima_mensagem_lead_em`` and
        ``last_message_at`` (the drain-idle clock + the 180-day retention
        clock). Raises :class:`NotFound`."""
        ...

    def link_lead_ref(self, org_id: UUID, id: UUID, lead_ref_id: UUID) -> ConversationRecord:
        """Link a thread to its ``lead_refs`` row (M3 / the lazy self-link on the
        first v2 turn). Idempotent: an already-linked thread keeps its link and is
        returned unchanged. Raises :class:`NotFound`."""
        ...

    def list_threads_for_lead(self, org_id: UUID, lead_ref_id: UUID) -> list[ConversationRecord]:
        """Every thread of one lead (one per channel line)."""
        ...

    def count_threads_created_since(
        self, org_id: UUID, agent_id: UUID, since: datetime, *, ate: int
    ) -> int:
        """How many lead threads the agent opened since ``since``, counted up to ``ate`` (the caller only
        compares to a limit, so the read is bounded by it and never meets the PostgREST row cap)."""
        ...

    def list_channel(
        self, org_id: UUID, *, agent_id: UUID | None = None, channel: str | None = None
    ) -> list[ConversationRecord]:
        """Channel conversations of the org (newest first), optionally per
        agent / channel. Read-only listing for the agents UI."""
        ...

    def touch_activity(
        self, org_id: UUID, id: UUID, *, contact: dict[str, Any] | None = None
    ) -> ConversationRecord:
        """Stamp ``last_message_at = now`` (the 180-day retention clock) and,
        when given, refresh ``contact``. Raises :class:`NotFound`."""
        ...


class FakeConversationStore:
    """In-memory :class:`ConversationStore`."""

    def __init__(self) -> None:
        self._rows: dict[UUID, dict[str, Any]] = {}

    def create(
        self, org_id: UUID, agent_id: UUID, owner_user_id: UUID,
        titulo: str | None = None,
        *,
        version_id: UUID | None = None,
        client_id: UUID | None = None,
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
            "version_id": version_id,
            "client_id": client_id,
            "channel": None,
            "channel_ref": None,
            "contact": None,
            "tipo": "chat",
            "lead_ref_id": None,
            "ultima_mensagem_lead_em": None,
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
        self, org_id: UUID, user_id: UUID, *, agent_id: UUID | None = None
    ) -> list[ConversationRecord]:
        return [
            self._to_record(row)
            for row in self._rows.values()
            if row["org_id"] == org_id and row["owner_user_id"] == user_id
            and (agent_id is None or row["agent_id"] == agent_id)
        ]

    def pin_version(self, org_id: UUID, id: UUID, version_id: UUID) -> ConversationRecord:
        row = self._rows.get(id)
        if row is None or row["org_id"] != org_id:
            raise NotFound(f"conversation {id} not found for org {org_id}")
        if row["version_id"] is None:
            row["version_id"] = version_id
            row["updated_at"] = utcnow()
        return self._to_record(row)

    def get(self, org_id: UUID, id: UUID) -> ConversationRecord:
        row = self._rows.get(id)
        if row is None or row["org_id"] != org_id:
            raise NotFound(f"conversation {id} not found for org {org_id}")
        return self._to_record(row)

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

    def set_sdk_session_id(
        self, org_id: UUID, id: UUID, sdk_session_id: str | None
    ) -> ConversationRecord:
        row = self._rows.get(id)
        if row is None or row["org_id"] != org_id:
            raise NotFound(f"conversation {id} not found for org {org_id}")
        row["sdk_session_id"] = sdk_session_id
        row["updated_at"] = utcnow()
        return self._to_record(row)

    def set_titulo(self, org_id: UUID, id: UUID, titulo: str) -> ConversationRecord:
        row = self._rows.get(id)
        if row is None or row["org_id"] != org_id:
            raise NotFound(f"conversation {id} not found for org {org_id}")
        row["titulo"] = titulo
        row["updated_at"] = utcnow()
        return self._to_record(row)

    # ── channel conversations (Lais A2) ─────────────────────────────────

    def find_channel(
        self, org_id: UUID, agent_id: UUID, channel: str, channel_ref: dict[str, Any]
    ) -> ConversationRecord | None:
        for row in self._rows.values():
            if (
                row["org_id"] == org_id and row["agent_id"] == agent_id
                and row["channel"] == channel and row["channel_ref"] == channel_ref
            ):
                return self._to_record(row)
        return None

    def find_thread(
        self, org_id: UUID, channel: str, channel_ref: dict[str, Any]
    ) -> ConversationRecord | None:
        matches = [
            r for r in self._rows.values()
            if r["org_id"] == org_id and r["tipo"] == "thread_lead"
            and r["channel"] == channel and r["channel_ref"] == channel_ref
        ]
        matches.sort(key=lambda r: r["created_at"])
        return self._to_record(matches[0]) if matches else None

    def create_channel(
        self, org_id: UUID, agent_id: UUID, channel: str, channel_ref: dict[str, Any],
        contact: dict[str, Any] | None, *, version_id: UUID | None = None,
        lead_ref_id: UUID | None = None,
    ) -> ConversationRecord:
        existing = self.find_channel(org_id, agent_id, channel, channel_ref)
        if existing is not None:
            return existing
        now = utcnow()
        row: dict[str, Any] = {
            "id": uuid4(), "org_id": org_id, "agent_id": agent_id, "owner_user_id": None,
            "titulo": None, "sdk_session_id": None, "status": "ativa", "last_message_at": None,
            "created_at": now, "updated_at": now, "_turn_lock_until": None,
            "_turn_lock_instance_id": None, "version_id": version_id, "client_id": None,
            "channel": channel, "channel_ref": dict(channel_ref),
            "contact": dict(contact) if contact is not None else None,
            "tipo": "thread_lead", "lead_ref_id": lead_ref_id, "ultima_mensagem_lead_em": None,
        }
        self._rows[row["id"]] = row
        return self._to_record(row)

    def touch_lead_message(self, org_id: UUID, id: UUID) -> ConversationRecord:
        row = self._rows.get(id)
        if row is None or row["org_id"] != org_id:
            raise NotFound(f"conversation {id} not found for org {org_id}")
        now = utcnow()
        row["ultima_mensagem_lead_em"] = now
        row["last_message_at"] = now
        row["updated_at"] = now
        return self._to_record(row)

    def link_lead_ref(self, org_id: UUID, id: UUID, lead_ref_id: UUID) -> ConversationRecord:
        row = self._rows.get(id)
        if row is None or row["org_id"] != org_id:
            raise NotFound(f"conversation {id} not found for org {org_id}")
        if row.get("lead_ref_id") is None:
            row["lead_ref_id"] = lead_ref_id
            row["updated_at"] = utcnow()
        return self._to_record(row)

    def list_threads_for_lead(self, org_id: UUID, lead_ref_id: UUID) -> list[ConversationRecord]:
        rows = [
            r for r in self._rows.values()
            if r["org_id"] == org_id and r.get("lead_ref_id") == lead_ref_id
        ]
        rows.sort(key=lambda r: r["created_at"])
        return [self._to_record(r) for r in rows]

    def count_threads_created_since(
        self, org_id: UUID, agent_id: UUID, since: datetime, *, ate: int
    ) -> int:
        n = sum(
            1 for r in self._rows.values()
            if r["org_id"] == org_id and r["agent_id"] == agent_id and r["tipo"] == "thread_lead"
            and r["created_at"] >= since
        )
        return min(n, ate)

    def list_channel(
        self, org_id: UUID, *, agent_id: UUID | None = None, channel: str | None = None
    ) -> list[ConversationRecord]:
        rows = [
            r for r in self._rows.values()
            if r["org_id"] == org_id and r["channel"] is not None
            and (agent_id is None or r["agent_id"] == agent_id)
            and (channel is None or r["channel"] == channel)
        ]
        rows.sort(key=lambda r: r["last_message_at"] or r["created_at"], reverse=True)
        return [self._to_record(r) for r in rows]

    def touch_activity(
        self, org_id: UUID, id: UUID, *, contact: dict[str, Any] | None = None
    ) -> ConversationRecord:
        row = self._rows.get(id)
        if row is None or row["org_id"] != org_id:
            raise NotFound(f"conversation {id} not found for org {org_id}")
        now = utcnow()
        row["last_message_at"] = now
        row["updated_at"] = now
        if contact is not None:
            row["contact"] = dict(contact)
        return self._to_record(row)

    def purge_conversation(self, org_id: UUID, id: UUID) -> bool:
        """Test-double half of ``agents.delete_channel_conversation`` (the Real
        one is a single SQL transaction): drop the row. Used by
        :class:`~app.channels.retention.FakeChannelRetention`."""
        row = self._rows.get(id)
        if row is None or row["org_id"] != org_id or row["channel"] is None:
            return False
        del self._rows[id]
        return True

    def channel_ids_inactive_since(self, cutoff: datetime) -> list[tuple[UUID, UUID]]:
        """``(org_id, id)`` of channel conversations whose last activity is
        before ``cutoff`` and that hold no live turn lock."""
        now = utcnow()
        out = []
        for r in self._rows.values():
            if r["channel"] is None:
                continue
            held = r["_turn_lock_until"]
            if held is not None and held >= now:
                continue
            if (r["last_message_at"] or r["created_at"]) < cutoff:
                out.append((r["org_id"], r["id"]))
        return out

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
            version_id=row["version_id"],
            client_id=row["client_id"],
            channel=row.get("channel"),
            channel_ref=dict(row["channel_ref"]) if row.get("channel_ref") is not None else None,
            contact=dict(row["contact"]) if row.get("contact") is not None else None,
            tipo=row.get("tipo", "chat"),
            lead_ref_id=row.get("lead_ref_id"),
            ultima_mensagem_lead_em=row.get("ultima_mensagem_lead_em"),
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
        *,
        version_id: UUID | None = None,
        client_id: UUID | None = None,
    ) -> ConversationRecord:
        payload = {
            "org_id": str(org_id),
            "agent_id": str(agent_id),
            "owner_user_id": str(owner_user_id),
            "titulo": titulo,
            "status": "ativa",
        }
        # Studio-only columns — omitted (not sent as null) for Bia so her
        # insert stays exactly what it was before 012.
        if version_id is not None:
            payload["version_id"] = str(version_id)
        if client_id is not None:
            payload["client_id"] = str(client_id)
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
        self, org_id: UUID, user_id: UUID, *, agent_id: UUID | None = None
    ) -> list[ConversationRecord]:
        query = (
            self._table()
            .select("*")
            .eq("org_id", str(org_id))
            .eq("owner_user_id", str(user_id))
        )
        if agent_id is not None:
            query = query.eq("agent_id", str(agent_id))
        resp = query.execute()
        return [self._record(row) for row in (resp.data or [])]

    def pin_version(self, org_id: UUID, id: UUID, version_id: UUID) -> ConversationRecord:
        # Conditional on `version_id IS NULL` — a pinned conversation never moves.
        self._table().update(
            {"version_id": str(version_id), "updated_at": utcnow_iso()}
        ).eq("id", str(id)).eq("org_id", str(org_id)).is_("version_id", "null").execute()
        return self.get(org_id, id)

    def get(self, org_id: UUID, id: UUID) -> ConversationRecord:
        resp = (
            self._table()
            .select("*")
            .eq("id", str(id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"conversation {id} not found for org {org_id}")
        return self._record(rows[0])

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

    def set_sdk_session_id(
        self, org_id: UUID, id: UUID, sdk_session_id: str | None
    ) -> ConversationRecord:
        resp = (
            self._table()
            .update(
                {"sdk_session_id": sdk_session_id, "updated_at": utcnow_iso()}
            )
            .eq("id", str(id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"conversation {id} not found for org {org_id}")
        return self._record(rows[0])

    def set_titulo(self, org_id: UUID, id: UUID, titulo: str) -> ConversationRecord:
        resp = (
            self._table()
            .update({"titulo": titulo, "updated_at": utcnow_iso()})
            .eq("id", str(id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"conversation {id} not found for org {org_id}")
        return self._record(rows[0])

    # ── channel conversations (Lais A2) ─────────────────────────────────

    def find_channel(
        self, org_id: UUID, agent_id: UUID, channel: str, channel_ref: dict[str, Any]
    ) -> ConversationRecord | None:
        resp = (
            self._table()
            .select("*")
            .eq("org_id", str(org_id))
            .eq("agent_id", str(agent_id))
            .eq("channel", channel)
            .eq("channel_ref", json.dumps(channel_ref, sort_keys=True))
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return self._record(rows[0]) if rows else None

    def find_thread(
        self, org_id: UUID, channel: str, channel_ref: dict[str, Any]
    ) -> ConversationRecord | None:
        resp = (
            self._table()
            .select("*")
            .eq("org_id", str(org_id))
            .eq("tipo", "thread_lead")
            .eq("channel", channel)
            .eq("channel_ref", json.dumps(channel_ref, sort_keys=True))
            .order("created_at")
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return self._record(rows[0]) if rows else None

    def create_channel(
        self, org_id: UUID, agent_id: UUID, channel: str, channel_ref: dict[str, Any],
        contact: dict[str, Any] | None, *, version_id: UUID | None = None,
        lead_ref_id: UUID | None = None,
    ) -> ConversationRecord:
        payload: dict[str, Any] = {
            "org_id": str(org_id), "agent_id": str(agent_id), "owner_user_id": None,
            "status": "ativa", "channel": channel, "channel_ref": channel_ref,
            "contact": contact, "tipo": "thread_lead",
        }
        if version_id is not None:
            payload["version_id"] = str(version_id)
        if lead_ref_id is not None:
            payload["lead_ref_id"] = str(lead_ref_id)
        try:
            resp = exec_query(self._table().insert(payload), unique_code="channel_exists")
        except StudioConflict:
            # A concurrent first call of the same chat won the unique index
            # (uq_agents_conversations_channel_ref): reuse ITS row.
            existing = self.find_channel(org_id, agent_id, channel, channel_ref)
            if existing is None:  # pragma: no cover — the conflicting row vanished mid-flight
                raise
            return existing
        rows = resp.data or []
        return self._record(rows[0] if rows else payload)

    def list_channel(
        self, org_id: UUID, *, agent_id: UUID | None = None, channel: str | None = None
    ) -> list[ConversationRecord]:
        from noctusai_lib.integrations.persistence.paging import iter_paged_rows

        def _page(start: int, end: int):
            query = self._table().select("*").eq("org_id", str(org_id)).not_.is_("channel", "null")
            if agent_id is not None:
                query = query.eq("agent_id", str(agent_id))
            if channel is not None:
                query = query.eq("channel", channel)
            return query.order("created_at", desc=True).order("id").range(start, end).execute().data

        return [self._record(r) for r in iter_paged_rows(_page)]

    def touch_activity(
        self, org_id: UUID, id: UUID, *, contact: dict[str, Any] | None = None
    ) -> ConversationRecord:
        patch: dict[str, Any] = {"last_message_at": utcnow_iso(), "updated_at": utcnow_iso()}
        if contact is not None:
            patch["contact"] = contact
        resp = (
            self._table().update(patch).eq("id", str(id)).eq("org_id", str(org_id)).execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"conversation {id} not found for org {org_id}")
        return self._record(rows[0])

    def touch_lead_message(self, org_id: UUID, id: UUID) -> ConversationRecord:
        now = utcnow_iso()
        resp = (
            self._table()
            .update({"ultima_mensagem_lead_em": now, "last_message_at": now, "updated_at": now})
            .eq("id", str(id)).eq("org_id", str(org_id)).execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"conversation {id} not found for org {org_id}")
        return self._record(rows[0])

    def link_lead_ref(self, org_id: UUID, id: UUID, lead_ref_id: UUID) -> ConversationRecord:
        # Conditional on `lead_ref_id IS NULL` — a linked thread never moves.
        self._table().update(
            {"lead_ref_id": str(lead_ref_id), "updated_at": utcnow_iso()}
        ).eq("id", str(id)).eq("org_id", str(org_id)).is_("lead_ref_id", "null").execute()
        return self.get(org_id, id)

    def list_threads_for_lead(self, org_id: UUID, lead_ref_id: UUID) -> list[ConversationRecord]:
        resp = (
            self._table().select("*")
            .eq("org_id", str(org_id)).eq("lead_ref_id", str(lead_ref_id))
            .order("created_at").limit(100).execute()
        )
        return [self._record(r) for r in (resp.data or [])]

    def count_threads_created_since(
        self, org_id: UUID, agent_id: UUID, since: datetime, *, ate: int
    ) -> int:
        resp = (
            self._table().select("id")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("tipo", "thread_lead")
            .gte("created_at", since.isoformat()).limit(max(1, ate)).execute()
        )
        return len(resp.data or [])

    @staticmethod
    def _record(row: dict[str, Any]) -> ConversationRecord:
        owner = row.get("owner_user_id")
        return ConversationRecord(
            id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            agent_id=UUID(str(row["agent_id"])),
            owner_user_id=UUID(str(owner)) if owner else None,
            titulo=row.get("titulo"),
            sdk_session_id=row.get("sdk_session_id"),
            status=row.get("status", "ativa"),
            last_message_at=row.get("last_message_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version_id=UUID(str(row["version_id"])) if row.get("version_id") else None,
            client_id=UUID(str(row["client_id"])) if row.get("client_id") else None,
            channel=row.get("channel"),
            channel_ref=row.get("channel_ref"),
            contact=row.get("contact"),
            tipo=row.get("tipo") or "chat",
            lead_ref_id=UUID(str(row["lead_ref_id"])) if row.get("lead_ref_id") else None,
            ultima_mensagem_lead_em=row.get("ultima_mensagem_lead_em"),
        )


def get_conversation_store(settings: Any) -> ConversationStore:
    """Real when a Supabase service-role key is configured, Fake otherwise
    — same signal as :func:`app.stores.agents.get_agent_store`."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeConversationStore()
    from app.database import get_admin_client

    return SupabaseConversationStore(get_admin_client())
