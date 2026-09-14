"""Approvals store — ``agents.approvals`` rows (contract §E.1/§E.2).

Seed IO shape: ``ApprovalStore`` Protocol + ``FakeApprovalStore`` +
``SupabaseApprovalStore`` (Real) + ``get_approval_store(settings)`` factory.

Two methods deliberately do NOT take ``org_id`` — this mirrors the
contract's own asymmetry, not an oversight:

- ``expire_for_instance(instance_id)`` is the STARTUP sweep (contract §E.2:
  "every pendente row whose instance_id equals this instance becomes
  expirada, never other instances' rows"). One process instance serves
  every org, so the sweep is instance-scoped, not org-scoped, by design.
- ``expire_one(id)`` is called from an already-authorized internal flow
  (the control plane's own timeout timer) that already resolved and
  validated the id; re-deriving an org filter there would be redundant,
  not safer.

``expire_one`` only ever moves a row OUT of ``pendente`` once — it never
clobbers a decision that already landed, which matters because the
timeout timer and a human's decision race by construction.

**``consume`` (contract §E.10, security review 2026-09-14)** replaces the
former ``mark_consumed(id) -> None``, which had no caller and returned
nothing — the escrita handler minted assertions straight from CLI-supplied
fields without ever consulting the store. ``consume(org_id, id) ->
ApprovalRecord | None`` is the atomic, single-use gate: ``UPDATE ... SET
consumed_at = now() WHERE id = ... AND org_id = ... AND decision =
'aprovada' AND consumed_at IS NULL RETURNING *``. It takes ``org_id``
(unlike ``expire_one``) because it IS the authorization boundary the
escrita handler calls directly with a caller-supplied id — scoping by org
here is not redundant, it is the point. Two concurrent calls for the same
row return exactly one non-``None`` record; the loser gets ``None``, which
the handler maps to 409 ``approval_used``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import AlreadyDecided, NotFound

__all__ = [
    "CLASSES",
    "DECISIONS",
    "ApprovalRecord",
    "ApprovalStore",
    "FakeApprovalStore",
    "SupabaseApprovalStore",
    "get_approval_store",
]

_SCHEMA = "agents"
_TABLE = "approvals"

#: Contract §E.1 `classe` CHECK.
CLASSES = ("escrita",)
#: Contract §E.1 `decision` CHECK.
DECISIONS = ("pendente", "aprovada", "negada", "expirada")


@dataclass(frozen=True)
class ApprovalRecord:
    id: UUID
    org_id: UUID
    conversation_id: UUID
    tool_name: str
    tool_input: dict[str, Any]
    classe: str
    resumo: str
    diff: dict[str, Any] | None
    decision: str
    decided_by: UUID | None
    decided_at: datetime | None
    requested_by: UUID
    instance_id: str
    consumed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApprovalStore(Protocol):
    def get(self, org_id: UUID, id: UUID) -> ApprovalRecord:
        """Read-only fetch by id, scoped to ``org_id``. Raises
        :class:`~app.stores.errors.NotFound` if unknown or another org —
        added for ``app.runtime.broker.StoreApprovalBroker.resolve``'s
        NotFound-before-AlreadyDecided-before-Orphaned classification
        (contract §E.9), which needs to read the row's current
        ``decision`` WITHOUT mutating it before deciding whether to call
        :meth:`decide` at all."""
        ...

    def create_pending(
        self,
        org_id: UUID,
        conversation_id: UUID,
        tool_name: str,
        tool_input: dict[str, Any],
        resumo: str,
        instance_id: str,
        requested_by: UUID,
        *,
        diff: dict[str, Any] | None = None,
        classe: str = "escrita",
    ) -> ApprovalRecord:
        ...

    def decide(
        self, org_id: UUID, id: UUID, aprovada: bool, decided_by: UUID
    ) -> ApprovalRecord:
        """Raises :class:`~app.stores.errors.NotFound` if unknown/other-org,
        :class:`~app.stores.errors.AlreadyDecided` if not ``pendente``."""
        ...

    def expire_for_instance(self, instance_id: str) -> int:
        """Flip every ``pendente`` row for THIS instance to ``expirada``.
        Returns the number of rows changed. Never touches another
        instance's rows."""
        ...

    def expire_one(self, id: UUID) -> None:
        """Flip one row to ``expirada`` — a no-op if it is no longer
        ``pendente`` (a human decision already landed first)."""
        ...

    def consume(self, org_id: UUID, id: UUID) -> ApprovalRecord | None:
        """Atomically set ``consumed_at`` — contract §E.10: ``UPDATE ...
        SET consumed_at = now() WHERE id = ... AND org_id = ... AND
        decision = 'aprovada' AND consumed_at IS NULL RETURNING *``.

        Returns the updated record on the FIRST call for a given row;
        returns ``None`` on every subsequent call (already consumed), for
        an unapproved/non-existent row, or for another org — the escrita
        handler treats all three identically (403 ``approval_used`` is
        only correct for the first; the earlier §E.10 checks already
        ruled out the other two, so by the time this is called a
        ``None`` here can only mean "already consumed")."""
        ...

    def list_pending(
        self, org_id: UUID, *, owner_user_id: UUID | None = None
    ) -> list[ApprovalRecord]:
        """``decision == 'pendente'`` rows for the org. ``owner_user_id``
        narrows to approvals ``requested_by`` that user (a non-admin caller
        sees only their own conversations' approvals; admins pass
        ``None`` and see every pending approval in the org)."""
        ...


class FakeApprovalStore:
    """In-memory :class:`ApprovalStore`."""

    def __init__(self) -> None:
        self._rows: dict[UUID, dict[str, Any]] = {}

    def get(self, org_id: UUID, id: UUID) -> ApprovalRecord:
        row = self._rows.get(id)
        if row is None or row["org_id"] != org_id:
            raise NotFound(f"approval {id} not found for org {org_id}")
        return self._to_record(row)

    def create_pending(
        self,
        org_id: UUID,
        conversation_id: UUID,
        tool_name: str,
        tool_input: dict[str, Any],
        resumo: str,
        instance_id: str,
        requested_by: UUID,
        *,
        diff: dict[str, Any] | None = None,
        classe: str = "escrita",
    ) -> ApprovalRecord:
        if classe not in CLASSES:
            raise ValueError(f"classe must be one of {CLASSES}; got {classe!r}")
        now = utcnow()
        row = {
            "id": uuid4(),
            "org_id": org_id,
            "conversation_id": conversation_id,
            "tool_name": tool_name,
            "tool_input": dict(tool_input),
            "classe": classe,
            "resumo": resumo,
            "diff": diff,
            "decision": "pendente",
            "decided_by": None,
            "decided_at": None,
            "requested_by": requested_by,
            "instance_id": instance_id,
            "consumed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self._rows[row["id"]] = row
        return self._to_record(row)

    def decide(
        self, org_id: UUID, id: UUID, aprovada: bool, decided_by: UUID
    ) -> ApprovalRecord:
        row = self._rows.get(id)
        if row is None or row["org_id"] != org_id:
            raise NotFound(f"approval {id} not found for org {org_id}")
        if row["decision"] != "pendente":
            raise AlreadyDecided(
                f"approval {id} already decided ({row['decision']!r})"
            )
        now = utcnow()
        row["decision"] = "aprovada" if aprovada else "negada"
        row["decided_by"] = decided_by
        row["decided_at"] = now
        row["updated_at"] = now
        return self._to_record(row)

    def expire_for_instance(self, instance_id: str) -> int:
        count = 0
        now = utcnow()
        for row in self._rows.values():
            if row["instance_id"] == instance_id and row["decision"] == "pendente":
                row["decision"] = "expirada"
                row["updated_at"] = now
                count += 1
        return count

    def expire_one(self, id: UUID) -> None:
        row = self._rows.get(id)
        if row is None or row["decision"] != "pendente":
            return
        row["decision"] = "expirada"
        row["updated_at"] = utcnow()

    def consume(self, org_id: UUID, id: UUID) -> ApprovalRecord | None:
        row = self._rows.get(id)
        if (
            row is None
            or row["org_id"] != org_id
            or row["decision"] != "aprovada"
            or row["consumed_at"] is not None
        ):
            return None
        row["consumed_at"] = utcnow()
        row["updated_at"] = row["consumed_at"]
        return self._to_record(row)

    def list_pending(
        self, org_id: UUID, *, owner_user_id: UUID | None = None
    ) -> list[ApprovalRecord]:
        return [
            self._to_record(row)
            for row in self._rows.values()
            if row["org_id"] == org_id
            and row["decision"] == "pendente"
            and (owner_user_id is None or row["requested_by"] == owner_user_id)
        ]

    @staticmethod
    def _to_record(row: dict[str, Any]) -> ApprovalRecord:
        return ApprovalRecord(**row)


class SupabaseApprovalStore:
    """Real :class:`ApprovalStore` — Postgres via the admin client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _table(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    def get(self, org_id: UUID, id: UUID) -> ApprovalRecord:
        resp = (
            self._table()
            .select("*")
            .eq("id", str(id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"approval {id} not found for org {org_id}")
        return self._record(rows[0])

    def create_pending(
        self,
        org_id: UUID,
        conversation_id: UUID,
        tool_name: str,
        tool_input: dict[str, Any],
        resumo: str,
        instance_id: str,
        requested_by: UUID,
        *,
        diff: dict[str, Any] | None = None,
        classe: str = "escrita",
    ) -> ApprovalRecord:
        if classe not in CLASSES:
            raise ValueError(f"classe must be one of {CLASSES}; got {classe!r}")
        payload = {
            "org_id": str(org_id),
            "conversation_id": str(conversation_id),
            "tool_name": tool_name,
            "tool_input": dict(tool_input),
            "classe": classe,
            "resumo": resumo,
            "diff": diff,
            "decision": "pendente",
            "requested_by": str(requested_by),
            "instance_id": instance_id,
        }
        resp = self._table().insert(payload).execute()
        rows = resp.data or []
        return self._record(rows[0] if rows else payload)

    def decide(
        self, org_id: UUID, id: UUID, aprovada: bool, decided_by: UUID
    ) -> ApprovalRecord:
        now_iso = utcnow_iso()
        resp = (
            self._table()
            .update(
                {
                    "decision": "aprovada" if aprovada else "negada",
                    "decided_by": str(decided_by),
                    "decided_at": now_iso,
                    "updated_at": now_iso,
                }
            )
            .eq("id", str(id))
            .eq("org_id", str(org_id))
            .eq("decision", "pendente")
            .execute()
        )
        rows = resp.data or []
        if rows:
            return self._record(rows[0])
        # Zero rows: either it doesn't exist/another org, or it exists but
        # is no longer pendente. Disambiguate with one read.
        existing = (
            self._table()
            .select("*")
            .eq("id", str(id))
            .eq("org_id", str(org_id))
            .execute()
        )
        existing_rows = existing.data or []
        if not existing_rows:
            raise NotFound(f"approval {id} not found for org {org_id}")
        raise AlreadyDecided(
            f"approval {id} already decided ({existing_rows[0]['decision']!r})"
        )

    def expire_for_instance(self, instance_id: str) -> int:
        resp = (
            self._table()
            .update({"decision": "expirada", "updated_at": utcnow_iso()})
            .eq("instance_id", instance_id)
            .eq("decision", "pendente")
            .execute()
        )
        return len(resp.data or [])

    def expire_one(self, id: UUID) -> None:
        self._table().update(
            {"decision": "expirada", "updated_at": utcnow_iso()}
        ).eq("id", str(id)).eq("decision", "pendente").execute()

    def consume(self, org_id: UUID, id: UUID) -> ApprovalRecord | None:
        now_iso = utcnow_iso()
        resp = (
            self._table()
            .update({"consumed_at": now_iso, "updated_at": now_iso})
            .eq("id", str(id))
            .eq("org_id", str(org_id))
            .eq("decision", "aprovada")
            .is_("consumed_at", "null")
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        return self._record(rows[0])

    def list_pending(
        self, org_id: UUID, *, owner_user_id: UUID | None = None
    ) -> list[ApprovalRecord]:
        query = (
            self._table()
            .select("*")
            .eq("org_id", str(org_id))
            .eq("decision", "pendente")
        )
        if owner_user_id is not None:
            query = query.eq("requested_by", str(owner_user_id))
        resp = query.execute()
        return [self._record(row) for row in (resp.data or [])]

    @staticmethod
    def _record(row: dict[str, Any]) -> ApprovalRecord:
        return ApprovalRecord(
            id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            conversation_id=UUID(str(row["conversation_id"])),
            tool_name=row["tool_name"],
            tool_input=dict(row.get("tool_input") or {}),
            classe=row.get("classe", "escrita"),
            resumo=row["resumo"],
            diff=row.get("diff"),
            decision=row.get("decision", "pendente"),
            decided_by=UUID(str(row["decided_by"])) if row.get("decided_by") else None,
            decided_at=row.get("decided_at"),
            requested_by=UUID(str(row["requested_by"])),
            instance_id=row["instance_id"],
            consumed_at=row.get("consumed_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def get_approval_store(settings: Any) -> ApprovalStore:
    """Real when a Supabase service-role key is configured, Fake otherwise
    — same signal as :func:`app.stores.agents.get_agent_store`."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeApprovalStore()
    from app.database import get_admin_client

    return SupabaseApprovalStore(get_admin_client())
