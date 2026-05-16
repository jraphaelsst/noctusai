"""Durable conversation persistence + UNIQUE-driven idempotency oracle.

Reconciled 2026-05-16 from the live-validated
`youtube-crawler/app/services/message_store.py`
(`projects/social-wiring-absorption/` W1.E1, manifest `multimodal-stack`).

Every inbound + outbound message is persisted to a
``conversation_messages`` table with ``UNIQUE(provider_message_id)``
driving dedup: the duplicate-INSERT attempt trips the unique
constraint, the caller catches :class:`DuplicateMessage` and treats it
as "already processed". This is atomic across the
``message`` + ``message.any`` race that WAHA subscribes consumers to,
and — unlike a Redis SETNX shim — it survives process restarts.

Divergence reconciled vs. the validated source (sibling-validated wins
per project §3.2, but seed-shape generalizations applied per §3.3):

  - Hardcoded ``_SCHEMA = "youtube_crawler"`` → constructor arg
    (every consuming product owns its own schema).
  - Bare class (no Protocol/Fake) → canonical
    Protocol + Real + Fake + factory shape
    (`KB § PATTERNS/seed-fake-real-adapter.md`) — this is an IO module
    (Supabase writes), so the Fake exercises a genuinely different code
    path (in-memory dedup vs. PostgREST IntegrityError sniffing).
  - Behaviour (payload shape, duplicate-error sniffing, the
    ``list_for_session`` cold-recall fallback) preserved exactly.

────────────────────────────────────────────────────────────────────────
message_store ↔ WHATSAPP dedup seam contract (stated for Engineer
WHATSAPP / W1.E2 — the Redis SETNX layer is theirs):

  - This module is the **durable backstop**. ``record(...)`` raising
    :class:`DuplicateMessage` is the authoritative "already processed"
    signal and survives restarts.
  - The WhatsApp webhook handler (W1.E2) SHOULD additionally short-
    circuit duplicate WAHA deliveries with a Redis ``SETNX`` keyed on
    ``provider_message_id`` at the TOP of the handler so the second of
    the ``message`` / ``message.any`` pair returns 200 in ~25ms WITHOUT
    paying OpenAI/media-download cost. That SETNX layer is a
    performance pre-filter ONLY — it is NOT the source of truth and is
    NOT shipped here.
  - Required ordering at the consumer: SETNX pre-filter (fast, lossy on
    restart) → media resolve → ``MessageStore.record(...)`` (durable,
    catches the residual race the SETNX missed across a restart).
  - Contract for W1.E2: catch :class:`DuplicateMessage` from
    ``record(...)`` and return HTTP 200 without further side effects.
    The exception type + the ``provider_message_id``-as-arg shape are
    the stable seam; the SETNX key naming is W1.E2's to define.
────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import uuid as _uuid
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

logger = logging.getLogger(__name__)

_DEFAULT_TABLE = "conversation_messages"


class DuplicateMessage(Exception):
    """Raised when a record with the same ``provider_message_id`` already
    exists. Webhook handlers catch this and return 200 OK without
    further processing — the inbound is a duplicate WAHA delivery."""


@dataclass(frozen=True)
class StoredMessage:
    """The persisted row, normalized. ``id`` is the row UUID."""

    id: UUID
    session_id: str
    direction: str
    body: str
    provider_message_id: str | None
    authorized: bool


@runtime_checkable
class MessageStore(Protocol):
    """The durable conversation-persistence surface.

    `@runtime_checkable` so consumers/tests can
    `isinstance(store, MessageStore)` — matches the convention the
    other seed adapters follow per
    `KB § PATTERNS/seed-fake-real-adapter.md`.
    """

    def record(
        self,
        *,
        session_id: str,
        direction: str,
        body: str,
        provider_message_id: str | None = None,
        raw_sender: str | None = None,
        authorized: bool = True,
        structured_payload: dict[str, Any] | None = None,
    ) -> StoredMessage:
        """Insert one message row. Raises :class:`DuplicateMessage` when
        ``provider_message_id`` already exists."""
        ...

    def list_for_session(
        self, *, session_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Return recent messages for a session, oldest first. The
        chatbot's cold-recall fallback when Redis memory is empty."""
        ...


def _validate_direction(direction: str) -> None:
    if direction not in {"inbound", "outbound"}:
        raise ValueError(f"invalid direction: {direction}")


class SupabaseMessageStore:
    """Real :class:`MessageStore` — persists to a Supabase/Postgres
    ``conversation_messages`` table via the service-role client (the
    webhook has no JWT context; RLS is service-role-open for writes,
    authenticated-read for the operator UI).

    Schema-neutral: each consuming product passes its own ``schema``
    (the validated source hardcoded ``youtube_crawler`` — that coupling
    is removed here per the full-reconcile seed-shape rule).
    """

    def __init__(
        self,
        *,
        admin_supabase: Any,
        org_id: UUID,
        schema: str,
        table: str = _DEFAULT_TABLE,
    ):
        self._admin = admin_supabase
        self._org_id = org_id
        self._schema = schema
        self._table = table

    def record(
        self,
        *,
        session_id: str,
        direction: str,
        body: str,
        provider_message_id: str | None = None,
        raw_sender: str | None = None,
        authorized: bool = True,
        structured_payload: dict[str, Any] | None = None,
    ) -> StoredMessage:
        _validate_direction(direction)
        payload = {
            "id": str(_uuid.uuid4()),
            "org_id": str(self._org_id),
            "session_id": session_id,
            "raw_sender": raw_sender,
            "direction": direction,
            "provider_message_id": provider_message_id or None,
            "body": body,
            "authorized": authorized,
            "structured_payload": (
                json.dumps(structured_payload, separators=(",", ":"))
                if structured_payload
                else None
            ),
        }
        try:
            response = (
                self._admin.schema(self._schema)
                .table(self._table)
                .insert(payload)
                .execute()
            )
        except Exception as exc:
            if provider_message_id and self._is_duplicate_error(
                exc, provider_message_id
            ):
                raise DuplicateMessage(provider_message_id) from exc
            raise
        rows = response.data or []
        row = rows[0] if rows else payload
        return StoredMessage(
            id=UUID(row["id"]),
            session_id=row["session_id"],
            direction=row["direction"],
            body=row["body"],
            provider_message_id=row.get("provider_message_id"),
            authorized=bool(row.get("authorized", False)),
        )

    def _is_duplicate_error(
        self, exc: Exception, provider_message_id: str
    ) -> bool:
        """Best-effort cross-backend duplicate detection.

        SQLite raises ``IntegrityError`` with ``UNIQUE constraint
        failed: …provider_message_id``; Postgres/PostgREST surfaces
        code ``23505`` / ``duplicate key``. Sniff the message (cheap),
        then fall back to a SELECT existence check (durable)."""
        msg = str(exc).lower()
        if "unique" in msg and "provider_message_id" in msg:
            return True
        if "23505" in msg or "duplicate key" in msg:
            return True
        try:
            existing = (
                self._admin.schema(self._schema)
                .table(self._table)
                .select("id")
                .eq("provider_message_id", provider_message_id)
                .limit(1)
                .execute()
            )
            return bool(existing.data)
        except Exception:
            return False

    def list_for_session(
        self, *, session_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        response = (
            self._admin.schema(self._schema)
            .table(self._table)
            .select("*")
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        return list(response.data or [])


class FakeMessageStore:
    """In-memory :class:`MessageStore` keyed on ``provider_message_id``
    for the dedup contract. Default for tests + dev paths that must not
    touch Supabase. The duplicate-INSERT semantics are reproduced
    faithfully so tests exercise the SAME ``DuplicateMessage`` seam the
    Real adapter raises."""

    def __init__(self, *, org_id: UUID | None = None):
        self._org_id = org_id or UUID("00000000-0000-4000-8000-000000000001")
        self._rows: list[dict[str, Any]] = []
        self._seen_provider_ids: set[str] = set()

    def record(
        self,
        *,
        session_id: str,
        direction: str,
        body: str,
        provider_message_id: str | None = None,
        raw_sender: str | None = None,
        authorized: bool = True,
        structured_payload: dict[str, Any] | None = None,
    ) -> StoredMessage:
        _validate_direction(direction)
        if provider_message_id and provider_message_id in self._seen_provider_ids:
            raise DuplicateMessage(provider_message_id)
        row_id = _uuid.uuid4()
        row = {
            "id": str(row_id),
            "org_id": str(self._org_id),
            "session_id": session_id,
            "raw_sender": raw_sender,
            "direction": direction,
            "provider_message_id": provider_message_id or None,
            "body": body,
            "authorized": authorized,
            "structured_payload": structured_payload,
        }
        self._rows.append(row)
        if provider_message_id:
            self._seen_provider_ids.add(provider_message_id)
        return StoredMessage(
            id=row_id,
            session_id=session_id,
            direction=direction,
            body=body,
            provider_message_id=provider_message_id or None,
            authorized=authorized,
        )

    def list_for_session(
        self, *, session_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        matching = [r for r in self._rows if r["session_id"] == session_id]
        return matching[:limit]


def make_message_store(
    *,
    admin_supabase: Any | None = None,
    org_id: UUID | None = None,
    schema: str | None = None,
    table: str = _DEFAULT_TABLE,
    use_fake: bool = False,
) -> MessageStore:
    """Factory — returns a :class:`FakeMessageStore` when ``use_fake`` is
    True (or no ``admin_supabase``/``schema`` given), else a
    :class:`SupabaseMessageStore`. Mirrors the
    `make_<adapter>` convention of the other seed integrations."""
    if use_fake or admin_supabase is None or schema is None:
        return FakeMessageStore(org_id=org_id)
    if org_id is None:
        raise ValueError("SupabaseMessageStore requires org_id")
    return SupabaseMessageStore(
        admin_supabase=admin_supabase,
        org_id=org_id,
        schema=schema,
        table=table,
    )


__all__ = [
    "DuplicateMessage",
    "FakeMessageStore",
    "MessageStore",
    "StoredMessage",
    "SupabaseMessageStore",
    "make_message_store",
]
