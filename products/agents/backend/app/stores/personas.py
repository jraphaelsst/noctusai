"""Persona store — append-only-by-version rows in ``agents.agent_personas``
(contract §E.1).

Seed IO shape: ``PersonaStore`` Protocol + ``FakePersonaStore`` +
``SupabasePersonaStore`` (Real) + ``get_persona_store(settings)`` factory.

Versioning invariant: ``create_version`` inserts ``versao = max+1`` and
flips ``ativa`` in ONE transaction (contract §E.1). The Fake does this
in-process (single-threaded, trivially atomic). The Real store calls the
``agents.create_persona_version`` SECURITY DEFINER function via ``.rpc()``
— one PostgREST request, one Postgres transaction — declared in
``migrations/006_agents.sql`` (see that file's header for the "why not two
separate `.update()`/`.insert()` calls" rationale).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._util import utcnow
from app.stores.errors import NotFound

__all__ = [
    "MODELS",
    "EFFORTS",
    "PersonaInput",
    "PersonaRecord",
    "PersonaStore",
    "FakePersonaStore",
    "SupabasePersonaStore",
    "get_persona_store",
]

_SCHEMA = "agents"
_TABLE = "agent_personas"

#: Contract §E.1 `model` CHECK.
MODELS = ("claude-opus-5", "claude-sonnet-5")
#: Contract §E.1 `effort` CHECK.
EFFORTS = ("low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class PersonaInput:
    """The editable fields of a persona version — everything ``PUT
    /api/agents/julia/persona`` (contract §E.2) accepts."""

    nome: str
    papel: str
    model: str
    effort: str
    tom: str | None = None
    system_prompt_append: str | None = None
    idioma: str = "pt-BR"
    org_display_name: str | None = None
    project_display_name: str | None = None


@dataclass(frozen=True)
class PersonaRecord:
    id: UUID
    org_id: UUID
    agent_id: UUID
    versao: int
    nome: str
    papel: str
    tom: str | None
    system_prompt_append: str | None
    model: str
    effort: str
    idioma: str
    org_display_name: str | None
    project_display_name: str | None
    ativa: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class PersonaStore(Protocol):
    def create_version(
        self, org_id: UUID, agent_id: UUID, data: PersonaInput, created_by: UUID
    ) -> PersonaRecord:
        """Insert the next version and flip ``ativa`` in one transaction."""
        ...

    def get_active(self, org_id: UUID, agent_id: UUID) -> PersonaRecord:
        """Raises :class:`~app.stores.errors.NotFound` when the agent has
        no active persona version yet."""
        ...


class FakePersonaStore:
    """In-memory :class:`PersonaStore`."""

    def __init__(self) -> None:
        # keyed by (org_id, agent_id) -> list[dict], insertion order == versao order
        self._rows: dict[tuple[UUID, UUID], list[dict[str, Any]]] = {}

    def create_version(
        self, org_id: UUID, agent_id: UUID, data: PersonaInput, created_by: UUID
    ) -> PersonaRecord:
        if data.model not in MODELS:
            raise ValueError(f"model must be one of {MODELS}; got {data.model!r}")
        if data.effort not in EFFORTS:
            raise ValueError(f"effort must be one of {EFFORTS}; got {data.effort!r}")

        versions = self._rows.setdefault((org_id, agent_id), [])
        for existing in versions:
            existing["ativa"] = False

        now = utcnow()
        row = {
            "id": uuid4(),
            "org_id": org_id,
            "agent_id": agent_id,
            "versao": len(versions) + 1,
            "nome": data.nome,
            "papel": data.papel,
            "tom": data.tom,
            "system_prompt_append": data.system_prompt_append,
            "model": data.model,
            "effort": data.effort,
            "idioma": data.idioma,
            "org_display_name": data.org_display_name,
            "project_display_name": data.project_display_name,
            "ativa": True,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }
        versions.append(row)
        return self._to_record(row)

    def get_active(self, org_id: UUID, agent_id: UUID) -> PersonaRecord:
        for row in self._rows.get((org_id, agent_id), []):
            if row["ativa"]:
                return self._to_record(row)
        raise NotFound(f"no active persona for agent {agent_id} in org {org_id}")

    @staticmethod
    def _to_record(row: dict[str, Any]) -> PersonaRecord:
        return PersonaRecord(**row)


class SupabasePersonaStore:
    """Real :class:`PersonaStore` — Postgres via the admin client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _table(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    def create_version(
        self, org_id: UUID, agent_id: UUID, data: PersonaInput, created_by: UUID
    ) -> PersonaRecord:
        if data.model not in MODELS:
            raise ValueError(f"model must be one of {MODELS}; got {data.model!r}")
        if data.effort not in EFFORTS:
            raise ValueError(f"effort must be one of {EFFORTS}; got {data.effort!r}")

        params = {
            "p_org_id": str(org_id),
            "p_agent_id": str(agent_id),
            "p_nome": data.nome,
            "p_papel": data.papel,
            "p_tom": data.tom,
            "p_system_prompt_append": data.system_prompt_append,
            "p_model": data.model,
            "p_effort": data.effort,
            "p_idioma": data.idioma,
            "p_org_display_name": data.org_display_name,
            "p_project_display_name": data.project_display_name,
            "p_created_by": str(created_by),
        }
        resp = (
            self._client.schema(_SCHEMA)
            .rpc("create_persona_version", params)
            .execute()
        )
        row = resp.data
        if isinstance(row, list):
            row = row[0]
        return self._record(row)

    def get_active(self, org_id: UUID, agent_id: UUID) -> PersonaRecord:
        resp = (
            self._table()
            .select("*")
            .eq("org_id", str(org_id))
            .eq("agent_id", str(agent_id))
            .eq("ativa", True)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"no active persona for agent {agent_id} in org {org_id}")
        return self._record(rows[0])

    @staticmethod
    def _record(row: dict[str, Any]) -> PersonaRecord:
        return PersonaRecord(
            id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            agent_id=UUID(str(row["agent_id"])),
            versao=int(row["versao"]),
            nome=row["nome"],
            papel=row["papel"],
            tom=row.get("tom"),
            system_prompt_append=row.get("system_prompt_append"),
            model=row["model"],
            effort=row["effort"],
            idioma=row["idioma"],
            org_display_name=row.get("org_display_name"),
            project_display_name=row.get("project_display_name"),
            ativa=bool(row.get("ativa", False)),
            created_by=UUID(str(row["created_by"])),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def get_persona_store(settings: Any) -> PersonaStore:
    """Real when a Supabase service-role key is configured, Fake otherwise
    — same signal as :func:`app.stores.agents.get_agent_store`."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakePersonaStore()
    from app.database import get_admin_client

    return SupabasePersonaStore(get_admin_client())
