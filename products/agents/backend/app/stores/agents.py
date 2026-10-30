"""Agents store — the ``agents.agents`` control-plane rows (contract §E.1).

Seed IO shape: ``AgentStore`` Protocol + ``FakeAgentStore`` (in-memory,
deterministic) + ``SupabaseAgentStore`` (Real, Postgres via the admin
client) + ``get_agent_store(settings)`` factory. See
``KB § PATTERNS/backend/seed-fake-real-adapter.md``.

Every method takes ``org_id`` explicitly and filters by it — routes use the
admin client and therefore bypass RLS (contract §B.0/§E.0), so this filter
IS the authorization boundary, not a redundant belt-and-braces check.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import NotFound

__all__ = [
    "RUNTIMES",
    "DEFAULT_AGENT_KEYS",
    "legacy_chat_agent",
    "AgentRecord",
    "AgentStore",
    "FakeAgentStore",
    "SupabaseAgentStore",
    "get_agent_store",
]

_SCHEMA = "agents"
_TABLE = "agents"

#: Contract §E.1 `runtime` CHECK.
RUNTIMES = ("claude_sdk", "external")

#: The two rows `ensure_default_agents` seeds, per org. Never inserted by
#: the migration itself (org_id is per-org) — the migration header notes
#: this; this module is the idempotent seeding path. Platform-defined agents are NOT here: they are data
#: (``definition_scope='plataforma'`` rows); a key that is a platform definition is refused for an org agent by the
#: create route (``store.get_platform_definition``).
DEFAULT_AGENT_KEYS = ("bia", "one-chat")


@dataclass(frozen=True)
class AgentRecord:
    id: UUID
    org_id: UUID
    key: str
    nome: str
    runtime: str
    owner_product: str | None
    external_ref: dict[str, Any] | None
    ativo: bool
    created_at: datetime
    updated_at: datetime
    #: 012: ``legacy`` (code-defined: Bia, One Chat) | ``studio`` (a Studio row -- same table, every other agent).
    definition_mode: str = "legacy"

    @property
    def chat_legado(self) -> bool:
        """A code-defined agent served by the in-app ``claude_sdk`` chat runtime (the pre-Studio conversation
        path). Decided by the row's data -- never by its key -- so the Renata cutover is a data change."""
        return self.definition_mode == "legacy" and self.runtime == "claude_sdk"


def legacy_chat_agent(store: "AgentStore", org_id: UUID, key: str | None = None) -> AgentRecord | None:
    """The org's legacy chat agent named ``key`` (or, with ``key=None``, its only one), else ``None`` -- an explicit
    "maybe" read over the rows the org has, not an ``except NotFound`` fallback."""
    rows = [a for a in store.list(org_id) if a.chat_legado and (key is None or a.key == key)]
    if key is None and len(rows) > 1:
        raise LookupError(f"org {org_id} has {len(rows)} legacy chat agents; name one (agent_key)")
    return rows[0] if rows else None


class AgentStore(Protocol):
    def list(self, org_id: UUID) -> list[AgentRecord]:
        """Every agent row for ``org_id``."""
        ...

    def get_by_key(self, org_id: UUID, key: str) -> AgentRecord:
        """Raises :class:`~app.stores.errors.NotFound` if ``key`` doesn't
        exist for this org."""
        ...

    def set_active(self, org_id: UUID, key: str, ativo: bool) -> AgentRecord:
        """Toggle ``ativo``. Raises :class:`NotFound` on an unknown key."""
        ...

    def set_external_ref(
        self, org_id: UUID, key: str, ref: dict[str, Any] | None
    ) -> AgentRecord:
        """Set (or clear, with ``ref=None``) ``external_ref``. Raises
        :class:`NotFound` on an unknown key."""
        ...

    def ensure_default_agents(self, org_id: UUID) -> None:
        """Idempotently create ``bia`` (claude_sdk) and ``one-chat``
        (external, owner_product=social-wiring), both ``ativo=false``, for
        ``org_id``. Safe to call every request — a no-op once the rows
        exist."""
        ...


class FakeAgentStore:
    """In-memory :class:`AgentStore`. Deterministic; no IO."""

    def __init__(self) -> None:
        self._rows: dict[tuple[UUID, str], dict[str, Any]] = {}

    def list(self, org_id: UUID) -> list[AgentRecord]:
        return [
            self._to_record(row)
            for row in self._rows.values()
            if row["org_id"] == org_id
        ]

    def get_by_key(self, org_id: UUID, key: str) -> AgentRecord:
        row = self._rows.get((org_id, key))
        if row is None:
            raise NotFound(f"agent {key!r} not found for org {org_id}")
        return self._to_record(row)

    def set_active(self, org_id: UUID, key: str, ativo: bool) -> AgentRecord:
        row = self._rows.get((org_id, key))
        if row is None:
            raise NotFound(f"agent {key!r} not found for org {org_id}")
        row["ativo"] = ativo
        row["updated_at"] = utcnow()
        return self._to_record(row)

    def set_external_ref(
        self, org_id: UUID, key: str, ref: dict[str, Any] | None
    ) -> AgentRecord:
        row = self._rows.get((org_id, key))
        if row is None:
            raise NotFound(f"agent {key!r} not found for org {org_id}")
        row["external_ref"] = ref
        row["updated_at"] = utcnow()
        return self._to_record(row)

    def ensure_default_agents(self, org_id: UUID) -> None:
        self._ensure_one(
            org_id, key="bia", nome="Bia", runtime="claude_sdk",
            owner_product=None,
        )
        self._ensure_one(
            org_id, key="one-chat", nome="One Chat", runtime="external",
            owner_product="social-wiring",
        )

    def _ensure_one(
        self, org_id: UUID, *, key: str, nome: str, runtime: str,
        owner_product: str | None,
    ) -> None:
        if (org_id, key) in self._rows:
            return
        now = utcnow()
        self._rows[(org_id, key)] = {
            "id": uuid4(),
            "org_id": org_id,
            "key": key,
            "nome": nome,
            "runtime": runtime,
            "owner_product": owner_product,
            "external_ref": None,
            "ativo": False,
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    def _to_record(row: dict[str, Any]) -> AgentRecord:
        return AgentRecord(**row)


class SupabaseAgentStore:
    """Real :class:`AgentStore` — Postgres via an admin (service-role) client.

    ``client`` is expected already bound to nothing in particular; every
    call goes through ``client.schema(<schema>).table(<table>)`` — bare
    table names, never ``schema.table`` string-concatenated (the client
    already carries the schema; see
    ``KB § PATTERNS/backend/postgrest-schema-targeting.md``).
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    def _table(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    def list(self, org_id: UUID) -> list[AgentRecord]:
        resp = self._table().select("*").eq("org_id", str(org_id)).execute()
        return [self._record(row) for row in (resp.data or [])]

    def get_by_key(self, org_id: UUID, key: str) -> AgentRecord:
        resp = (
            self._table()
            .select("*")
            .eq("org_id", str(org_id))
            .eq("key", key)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"agent {key!r} not found for org {org_id}")
        return self._record(rows[0])

    def set_active(self, org_id: UUID, key: str, ativo: bool) -> AgentRecord:
        resp = (
            self._table()
            .update({"ativo": ativo, "updated_at": utcnow_iso()})
            .eq("org_id", str(org_id))
            .eq("key", key)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"agent {key!r} not found for org {org_id}")
        return self._record(rows[0])

    def set_external_ref(
        self, org_id: UUID, key: str, ref: dict[str, Any] | None
    ) -> AgentRecord:
        resp = (
            self._table()
            .update({"external_ref": ref, "updated_at": utcnow_iso()})
            .eq("org_id", str(org_id))
            .eq("key", key)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"agent {key!r} not found for org {org_id}")
        return self._record(rows[0])

    def ensure_default_agents(self, org_id: UUID) -> None:
        defaults = [
            {
                "org_id": str(org_id),
                "key": "bia",
                "nome": "Bia",
                "runtime": "claude_sdk",
                "owner_product": None,
                "ativo": False,
            },
            {
                "org_id": str(org_id),
                "key": "one-chat",
                "nome": "One Chat",
                "runtime": "external",
                "owner_product": "social-wiring",
                "ativo": False,
            },
        ]
        # on_conflict on the (org_id, key) unique constraint — idempotent:
        # an existing row (e.g. an admin already toggled ativo) is left
        # untouched, never clobbered back to the defaults.
        self._table().upsert(
            defaults, on_conflict="org_id,key", ignore_duplicates=True
        ).execute()

    @staticmethod
    def _record(row: dict[str, Any]) -> AgentRecord:
        return AgentRecord(
            id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            key=row["key"],
            nome=row["nome"],
            runtime=row["runtime"],
            owner_product=row.get("owner_product"),
            external_ref=row.get("external_ref"),
            ativo=bool(row.get("ativo", False)),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            definition_mode=row.get("definition_mode") or "legacy",
        )


def get_agent_store(settings: Any) -> AgentStore:
    """Return the Real store when a Supabase service-role key is configured,
    the Fake otherwise. Mirrors the signal ``app/database.py`` already uses
    for ``supabase_admin`` — no new environment convention introduced.
    """
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeAgentStore()
    from app.database import get_admin_client

    return SupabaseAgentStore(get_admin_client())
