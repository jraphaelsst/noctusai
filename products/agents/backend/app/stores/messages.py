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
from app.stores.errors import NotFound

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
    #: Agent Studio §A7/§E4 (012 columns): the version + exact compiled
    #: prompt hash an assistant message of a studio agent ran with.
    version_id: UUID | None = None
    compiled_hash: str | None = None
    #: Contract §L "Controle de custo" (014 columns): an assistant message's
    #: turn cost + token counts, straight off the SDK's `ResultMessage`
    #: (`app.runtime.claude_runtime.run_turn`'s final `session.status`
    #: event). `None` for `user`/`system` rows and for every Bia message
    #: whose turn reported no `ResultMessage`.
    custo_usd: float | None = None
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    #: Lais F-AG (029): sha256 of the per-turn `contexto` an assistant message
    #: ran with (channel turns only; `None` everywhere else).
    contexto_hash: str | None = None


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
        version_id: UUID | None = None,
        compiled_hash: str | None = None,
        contexto_hash: str | None = None,
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

    def update_blocks(
        self,
        org_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        blocks: list[dict[str, Any]],
    ) -> MessageRecord:
        """G1b addition (contract §E.9 "tool.* -> appended into the current
        assistant message's blocks" / "approval.* -> an approval block").
        Overwrites ``blocks`` wholesale — the turn-loop caller reads the
        current in-memory accumulator, appends the new block, and writes
        the whole list back; there is no partial-append at the store layer.
        Raises :class:`~app.stores.errors.NotFound` if the message doesn't
        exist for this org/conversation."""
        ...

    def set_turn_cost(
        self,
        org_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        *,
        custo_usd: float | None,
        tokens_entrada: int | None,
        tokens_saida: int | None,
    ) -> MessageRecord:
        """Contract §L: stamps the turn's cost/token counts on the assistant
        message the turn loop persisted (`app.routers.conversations_router.
        _run_turn_background`, on the final `session.status` event).
        Overwrites wholesale, like :meth:`update_blocks` — there is only
        ever one turn's cost per message. Raises
        :class:`~app.stores.errors.NotFound` if the message doesn't exist
        for this org/conversation."""
        ...

    def sum_cost_usd_since(self, org_id: UUID, since: datetime) -> float:
        """Lais A1 (daily org cap): the total ``custo_usd`` stamped on this
        org's messages created at or after ``since``. Messages with no cost
        (user/system rows, turns that reported none) count 0."""
        ...

    def usage_between(self, org_id: UUID, since: datetime, until: datetime) -> tuple[int, float]:
        """Lais w9 (Painel): ``(turnos, custo_usd)`` for this org over
        ``[since, until)`` — turns = assistant messages, cost = summed
        ``custo_usd``."""
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
        version_id: UUID | None = None,
        compiled_hash: str | None = None,
        contexto_hash: str | None = None,
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
            "version_id": version_id,
            "compiled_hash": compiled_hash,
            "contexto_hash": contexto_hash,
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

    def update_blocks(
        self,
        org_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        blocks: list[dict[str, Any]],
    ) -> MessageRecord:
        rows = self._rows.get((org_id, conversation_id), [])
        for row in rows:
            if row["id"] == message_id:
                row["blocks"] = list(blocks)
                row["updated_at"] = utcnow()
                return self._to_record(row)
        raise NotFound(f"message {message_id} not found for conversation {conversation_id}")

    def set_turn_cost(
        self,
        org_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        *,
        custo_usd: float | None,
        tokens_entrada: int | None,
        tokens_saida: int | None,
    ) -> MessageRecord:
        rows = self._rows.get((org_id, conversation_id), [])
        for row in rows:
            if row["id"] == message_id:
                row["custo_usd"] = custo_usd
                row["tokens_entrada"] = tokens_entrada
                row["tokens_saida"] = tokens_saida
                row["updated_at"] = utcnow()
                return self._to_record(row)
        raise NotFound(f"message {message_id} not found for conversation {conversation_id}")

    def sum_cost_usd_since(self, org_id: UUID, since: datetime) -> float:
        total = 0.0
        for (row_org, _conv), rows in self._rows.items():
            if row_org != org_id:
                continue
            total += sum(
                float(r.get("custo_usd") or 0.0) for r in rows if r["created_at"] >= since
            )
        return total

    def usage_between(self, org_id: UUID, since: datetime, until: datetime) -> tuple[int, float]:
        turns, total = 0, 0.0
        for (row_org, _conv), rows in self._rows.items():
            if row_org != org_id:
                continue
            for r in rows:
                if r["role"] == "assistant" and since <= r["created_at"] < until:
                    turns += 1
                    total += float(r.get("custo_usd") or 0.0)
        return turns, total

    def purge_conversation(self, org_id: UUID, conversation_id: UUID) -> int:
        """Test-double half of ``agents.delete_channel_conversation`` (the Real
        one is a single SQL transaction): drop every message of the
        conversation. Returns how many."""
        return len(self._rows.pop((org_id, conversation_id), []))

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
        version_id: UUID | None = None,
        compiled_hash: str | None = None,
        contexto_hash: str | None = None,
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
        # Studio-only columns — omitted for Bia (her insert is unchanged).
        if version_id is not None:
            payload["version_id"] = str(version_id)
        if compiled_hash is not None:
            payload["compiled_hash"] = compiled_hash
        if contexto_hash is not None:
            payload["contexto_hash"] = contexto_hash
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

    def update_blocks(
        self,
        org_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        blocks: list[dict[str, Any]],
    ) -> MessageRecord:
        resp = (
            self._table()
            .update({"blocks": list(blocks)})
            .eq("id", str(message_id))
            .eq("org_id", str(org_id))
            .eq("conversation_id", str(conversation_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(
                f"message {message_id} not found for conversation {conversation_id}"
            )
        return self._record(rows[0])

    def set_turn_cost(
        self,
        org_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        *,
        custo_usd: float | None,
        tokens_entrada: int | None,
        tokens_saida: int | None,
    ) -> MessageRecord:
        resp = (
            self._table()
            .update({
                "custo_usd": custo_usd, "tokens_entrada": tokens_entrada, "tokens_saida": tokens_saida,
            })
            .eq("id", str(message_id))
            .eq("org_id", str(org_id))
            .eq("conversation_id", str(conversation_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(
                f"message {message_id} not found for conversation {conversation_id}"
            )
        return self._record(rows[0])

    def sum_cost_usd_since(self, org_id: UUID, since: datetime) -> float:
        from noctusai_lib.integrations.persistence.paging import iter_paged_rows

        def _page(start: int, end: int):
            return (
                self._table()
                .select("id, custo_usd")
                .eq("org_id", str(org_id))
                .gte("created_at", since.isoformat())
                .gt("custo_usd", 0)
                .order("id")
                .range(start, end)
                .execute()
                .data
            )

        return sum(float(row["custo_usd"] or 0.0) for row in iter_paged_rows(_page))

    def usage_between(self, org_id: UUID, since: datetime, until: datetime) -> tuple[int, float]:
        from noctusai_lib.integrations.persistence.paging import iter_paged_rows

        def _page(start: int, end: int):
            return (
                self._table()
                .select("id, custo_usd")
                .eq("org_id", str(org_id))
                .eq("role", "assistant")
                .gte("created_at", since.isoformat())
                .lt("created_at", until.isoformat())
                .order("id")
                .range(start, end)
                .execute()
                .data
            )

        rows = list(iter_paged_rows(_page))
        return len(rows), sum(float(r.get("custo_usd") or 0.0) for r in rows)

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
            version_id=UUID(str(row["version_id"])) if row.get("version_id") else None,
            compiled_hash=row.get("compiled_hash"),
            contexto_hash=row.get("contexto_hash"),
            custo_usd=float(row["custo_usd"]) if row.get("custo_usd") is not None else None,
            tokens_entrada=row.get("tokens_entrada"),
            tokens_saida=row.get("tokens_saida"),
        )


def get_message_store(settings: Any) -> MessageStore:
    """Real when a Supabase service-role key is configured, Fake otherwise
    — same signal as :func:`app.stores.agents.get_agent_store`."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeMessageStore()
    from app.database import get_admin_client

    return SupabaseMessageStore(get_admin_client())
