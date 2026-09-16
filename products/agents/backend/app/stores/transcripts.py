"""Transcript store — ``agents.session_transcript_entries`` rows plus
``agents.conversations.transcript_estado`` (contract §E.11 "Durable
transcripts", migration `009_session_transcripts.sql`).

Seed IO shape: ``TranscriptStore`` Protocol + ``FakeTranscriptStore`` +
``SupabaseTranscriptStore`` (Real) + ``get_transcript_store(settings)``
factory — same shape as every other store in this product (see
``app/stores/approvals.py``).

This store is the persistence half of
``app.runtime.transcript_mirror.ConversationTranscriptMirror``, the SDK
``SessionStore`` adapter (§E.9 amendment: "transcripts go through an
injected TranscriptStore seam, like the approval broker" — the ONE named
exception to "the runtime never writes to the database").

**Idempotency key.** The SDK's own contract
(``claude_agent_sdk.types.SessionStore.append`` docstring, verified against
the installed 0.2.152 wheel): "Most entries carry a stable ``uuid`` that
adapters should treat as an idempotency key ... Entries without a ``uuid``
... should be appended without dedup." The migration's
``entry_uuid TEXT NOT NULL`` column has no room for "absent", so an entry
with no SDK-supplied ``uuid`` gets a FRESH synthetic one per call
(``str(uuid4())``) — that satisfies both the NOT NULL constraint and the
"never dedup" rule simultaneously, since a fresh random value can never
collide with a prior append.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import NotFound

__all__ = [
    "TRANSCRIPT_ESTADOS",
    "TranscriptEntry",
    "TranscriptStore",
    "FakeTranscriptStore",
    "SupabaseTranscriptStore",
    "get_transcript_store",
]

_SCHEMA = "agents"
_TABLE = "session_transcript_entries"
_CONVERSATIONS_TABLE = "conversations"

#: Contract §E.1/§E.11 `agents.conversations.transcript_estado` CHECK.
TRANSCRIPT_ESTADOS = ("ok", "truncado", "incompleto", "invalido")


def _entry_byte_size(entry: dict[str, Any]) -> int:
    """Wire size of one transcript entry, in bytes — the unit the §E.11
    24 MiB cap is measured in. Shared by the Fake and Real stores so both
    count bytes identically."""
    return len(json.dumps(entry).encode("utf-8"))


@dataclass(frozen=True)
class TranscriptEntry:
    """One stored transcript row — the SDK's ``SessionStoreEntry`` JSON
    blob (``entry``) plus this store's own bookkeeping (``seq``,
    ``byte_size``). Not returned by :meth:`TranscriptStore.load` (which
    returns bare entry dicts, matching the SDK's own ``load`` contract) —
    this dataclass exists for callers that need the bookkeeping too, and
    for the store's internal representation."""

    id: UUID
    org_id: UUID
    conversation_id: UUID
    sdk_session_id: str
    seq: int
    entry: dict[str, Any]
    entry_uuid: str
    byte_size: int
    created_at: datetime


class TranscriptStore(Protocol):
    def append_entries(
        self,
        org_id: UUID,
        conversation_id: UUID,
        sdk_session_id: str,
        entries: list[dict[str, Any]],
    ) -> int:
        """Idempotent by ``entry_uuid`` — a re-append of an entry whose SDK
        ``uuid`` already exists for this ``(conversation_id,
        sdk_session_id)`` is skipped, never re-inserted, never re-counted.
        Assigns ``seq`` monotonically per ``(conversation_id,
        sdk_session_id)``, continuing from whatever is already stored
        (never resetting to 0 on a later batch/turn).

        Returns the number of BYTES actually added (0 for a fully-
        duplicate batch) — ``ConversationTranscriptMirror``'s 24 MiB cap
        check reads this return value directly rather than re-summing."""
        ...

    def total_bytes(
        self, org_id: UUID, conversation_id: UUID, sdk_session_id: str
    ) -> int:
        """Sum of ``byte_size`` stored so far for this session. The mirror
        reads this once at construction time (resuming a session that
        already has stored entries) rather than replaying every prior
        ``append_entries`` return value."""
        ...

    def load(
        self, org_id: UUID, conversation_id: UUID, sdk_session_id: str
    ) -> list[dict[str, Any]] | None:
        """Ordered by ``seq``. ``None`` for a session with no stored
        entries — the same ``None`` the SDK's own
        ``SessionStore.load`` return-type expects."""
        ...

    def get_estado(self, org_id: UUID, conversation_id: UUID) -> str:
        """Raises :class:`~app.stores.errors.NotFound` for an unknown
        conversation id, or one belonging to another org."""
        ...

    def set_estado(self, org_id: UUID, conversation_id: UUID, estado: str) -> None:
        """Raises :class:`~app.stores.errors.NotFound` for an unknown/
        other-org conversation; ``ValueError`` if ``estado`` is outside
        :data:`TRANSCRIPT_ESTADOS`."""
        ...

    def delete_session(
        self, org_id: UUID, conversation_id: UUID, sdk_session_id: str
    ) -> int:
        """Removes every entry for this ``(conversation_id,
        sdk_session_id)`` — used when a fresh session replaces a truncated
        one (contract §E.11 "a fresh session starts"), so the old,
        capped-out entries never linger under a session id nothing will
        ever resume from again. Returns the number of rows removed (``0``,
        never a raise, when the session has no stored entries)."""
        ...


class FakeTranscriptStore:
    """In-memory :class:`TranscriptStore`."""

    def __init__(self) -> None:
        # (org_id, conversation_id, sdk_session_id) -> ordered row list.
        self._sessions: dict[tuple[UUID, UUID, str], list[dict[str, Any]]] = {}
        # (org_id, conversation_id) -> transcript_estado. Absence means
        # "no conversation known to this store" — get_estado/set_estado
        # raise NotFound, mirroring SupabaseTranscriptStore reading/
        # writing the real `agents.conversations` row (the actual source
        # of existence there). This Fake has no other channel to learn a
        # conversation exists (it is a SEPARATE store from
        # FakeConversationStore), so tests call `register_conversation`
        # once per fixture conversation before exercising the NotFound
        # path — the same seam shape as any other cross-store dependency.
        self._estados: dict[tuple[UUID, UUID], str] = {}

    @staticmethod
    def _key(
        org_id: UUID, conversation_id: UUID, sdk_session_id: str
    ) -> tuple[UUID, UUID, str]:
        return (org_id, conversation_id, sdk_session_id)

    def register_conversation(
        self, org_id: UUID, conversation_id: UUID, estado: str = "ok"
    ) -> None:
        """Test-only seam — see the ``_estados`` docstring above."""
        self._estados[(org_id, conversation_id)] = estado

    def append_entries(
        self,
        org_id: UUID,
        conversation_id: UUID,
        sdk_session_id: str,
        entries: list[dict[str, Any]],
    ) -> int:
        rows = self._sessions.setdefault(
            self._key(org_id, conversation_id, sdk_session_id), []
        )
        existing_uuids = {r["entry_uuid"] for r in rows if r["_has_real_uuid"]}
        next_seq = rows[-1]["seq"] + 1 if rows else 1
        added_bytes = 0
        for entry in entries:
            raw_uuid = entry.get("uuid")
            has_real_uuid = raw_uuid is not None
            if has_real_uuid and raw_uuid in existing_uuids:
                continue  # idempotent skip — already stored
            entry_uuid = raw_uuid if has_real_uuid else str(uuid4())
            size = _entry_byte_size(entry)
            rows.append(
                {
                    "id": uuid4(),
                    "org_id": org_id,
                    "conversation_id": conversation_id,
                    "sdk_session_id": sdk_session_id,
                    "seq": next_seq,
                    "entry": dict(entry),
                    "entry_uuid": entry_uuid,
                    "byte_size": size,
                    "created_at": utcnow(),
                    "_has_real_uuid": has_real_uuid,
                }
            )
            if has_real_uuid:
                existing_uuids.add(entry_uuid)
            next_seq += 1
            added_bytes += size
        return added_bytes

    def total_bytes(
        self, org_id: UUID, conversation_id: UUID, sdk_session_id: str
    ) -> int:
        rows = self._sessions.get(self._key(org_id, conversation_id, sdk_session_id), [])
        return sum(r["byte_size"] for r in rows)

    def load(
        self, org_id: UUID, conversation_id: UUID, sdk_session_id: str
    ) -> list[dict[str, Any]] | None:
        rows = self._sessions.get(self._key(org_id, conversation_id, sdk_session_id))
        if not rows:
            return None
        return [dict(r["entry"]) for r in sorted(rows, key=lambda r: r["seq"])]

    def get_estado(self, org_id: UUID, conversation_id: UUID) -> str:
        key = (org_id, conversation_id)
        if key not in self._estados:
            raise NotFound(f"conversation {conversation_id} not found for org {org_id}")
        return self._estados[key]

    def set_estado(self, org_id: UUID, conversation_id: UUID, estado: str) -> None:
        if estado not in TRANSCRIPT_ESTADOS:
            raise ValueError(f"estado must be one of {TRANSCRIPT_ESTADOS}; got {estado!r}")
        key = (org_id, conversation_id)
        if key not in self._estados:
            raise NotFound(f"conversation {conversation_id} not found for org {org_id}")
        self._estados[key] = estado

    def delete_session(
        self, org_id: UUID, conversation_id: UUID, sdk_session_id: str
    ) -> int:
        rows = self._sessions.pop(self._key(org_id, conversation_id, sdk_session_id), None)
        return len(rows) if rows else 0


class SupabaseTranscriptStore:
    """Real :class:`TranscriptStore` — Postgres via the admin client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _table(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    def _conversations_table(self):
        return self._client.schema(_SCHEMA).table(_CONVERSATIONS_TABLE)

    def append_entries(
        self,
        org_id: UUID,
        conversation_id: UUID,
        sdk_session_id: str,
        entries: list[dict[str, Any]],
    ) -> int:
        if not entries:
            return 0
        # Best-effort seq assignment: read the current max seq for this
        # session, then upsert with a fresh seq per row. Safe under this
        # product's single-in-flight-turn-per-conversation invariant
        # (contract §E.2 turn lock, §E.11 I1) — two concurrent appends to
        # the SAME (conversation_id, sdk_session_id) never happen in
        # practice, so this read-then-write window is not a live race.
        resp = (
            self._table()
            .select("seq")
            .eq("conversation_id", str(conversation_id))
            .eq("sdk_session_id", sdk_session_id)
            .order("seq", desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        next_seq = (rows[0]["seq"] + 1) if rows else 1

        payload = []
        for entry in entries:
            raw_uuid = entry.get("uuid")
            entry_uuid = raw_uuid if raw_uuid is not None else str(uuid4())
            payload.append(
                {
                    "org_id": str(org_id),
                    "conversation_id": str(conversation_id),
                    "sdk_session_id": sdk_session_id,
                    "seq": next_seq,
                    "entry": dict(entry),
                    "entry_uuid": entry_uuid,
                    "byte_size": _entry_byte_size(entry),
                }
            )
            next_seq += 1

        # ON CONFLICT (conversation_id, sdk_session_id, entry_uuid) DO
        # NOTHING — the migration's UNIQUE constraint IS the conflict
        # target. `ignore_duplicates=True` makes Postgres skip (never
        # overwrite) a row whose entry_uuid already exists for this
        # session; the response then carries ONLY the rows actually
        # inserted, so summing their byte_size is exactly "bytes added by
        # this call".
        resp = (
            self._table()
            .upsert(
                payload,
                on_conflict="conversation_id,sdk_session_id,entry_uuid",
                ignore_duplicates=True,
            )
            .execute()
        )
        inserted = resp.data or []
        return sum(int(row["byte_size"]) for row in inserted)

    def total_bytes(
        self, org_id: UUID, conversation_id: UUID, sdk_session_id: str
    ) -> int:
        resp = (
            self._table()
            .select("byte_size")
            .eq("org_id", str(org_id))
            .eq("conversation_id", str(conversation_id))
            .eq("sdk_session_id", sdk_session_id)
            .execute()
        )
        return sum(int(row["byte_size"]) for row in (resp.data or []))

    def load(
        self, org_id: UUID, conversation_id: UUID, sdk_session_id: str
    ) -> list[dict[str, Any]] | None:
        resp = (
            self._table()
            .select("*")
            .eq("org_id", str(org_id))
            .eq("conversation_id", str(conversation_id))
            .eq("sdk_session_id", sdk_session_id)
            .order("seq")
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        return [dict(row["entry"]) for row in rows]

    def get_estado(self, org_id: UUID, conversation_id: UUID) -> str:
        resp = (
            self._conversations_table()
            .select("transcript_estado")
            .eq("id", str(conversation_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"conversation {conversation_id} not found for org {org_id}")
        return rows[0]["transcript_estado"]

    def set_estado(self, org_id: UUID, conversation_id: UUID, estado: str) -> None:
        if estado not in TRANSCRIPT_ESTADOS:
            raise ValueError(f"estado must be one of {TRANSCRIPT_ESTADOS}; got {estado!r}")
        resp = (
            self._conversations_table()
            .update({"transcript_estado": estado, "updated_at": utcnow_iso()})
            .eq("id", str(conversation_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        if not (resp.data or []):
            raise NotFound(f"conversation {conversation_id} not found for org {org_id}")

    def delete_session(
        self, org_id: UUID, conversation_id: UUID, sdk_session_id: str
    ) -> int:
        resp = (
            self._table()
            .delete()
            .eq("org_id", str(org_id))
            .eq("conversation_id", str(conversation_id))
            .eq("sdk_session_id", sdk_session_id)
            .execute()
        )
        return len(resp.data or [])


def get_transcript_store(settings: Any) -> TranscriptStore:
    """Real when a Supabase service-role key is configured, Fake otherwise
    — same signal as :func:`app.stores.agents.get_agent_store`."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeTranscriptStore()
    from app.database import get_admin_client

    return SupabaseTranscriptStore(get_admin_client())
