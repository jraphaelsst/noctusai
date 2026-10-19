"""Agent controls store — ``agents.agents.modo_operacao`` / ``dreno_inatividade_dias``
(migration 034, Julia v2 contract §5).

* ``ligado`` — the agent replies and takes new leads;
* ``drenando`` — it keeps chatting in threads that are already open, takes no new lead;
* ``desligado`` — it replies to nobody (the default of a brand-new agent).

The turn path reads this on EVERY turn (the control is never cached in SW), so a
failure to read it is a refusal upstream (fail closed — :mod:`app.channels.controles`).
Writes go through ``agents.set_agent_modo`` (one transaction; an attributed audit row
lands via the ``audit_agent_modo_change`` trigger).

Seed IO shape: ``AgentControleStore`` Protocol + ``FakeAgentControleStore`` +
``SupabaseAgentControleStore`` (Real) + ``get_agent_controle_store(settings)`` factory.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.stores._db_errors import exec_rpc
from app.stores.errors import NotFound

__all__ = [
    "DRENO_DIAS_PADRAO",
    "MODOS",
    "AgentControleStore",
    "ControleRecord",
    "FakeAgentControleStore",
    "SupabaseAgentControleStore",
    "get_agent_controle_store",
]

_SCHEMA = "agents"

#: ``agents.modo_operacao`` CHECK (034).
MODOS = ("ligado", "drenando", "desligado")
#: ``agents.dreno_inatividade_dias`` column default (034) — owner answer Q3.
DRENO_DIAS_PADRAO = 7


@dataclass(frozen=True)
class ControleRecord:
    agent_id: UUID
    org_id: UUID
    modo: str
    dreno_inatividade_dias: int

    @property
    def aceita_novos_leads(self) -> bool:
        return self.modo == "ligado"


class AgentControleStore(Protocol):
    def get(self, org_id: UUID, agent_id: UUID) -> ControleRecord:
        """The agent's control row. Raises :class:`NotFound` for an unknown / other-org agent."""
        ...

    def set(
        self, org_id: UUID, agent_id: UUID, *, modo: str, dreno_inatividade_dias: int | None = None,
        actor: UUID | None = None,
    ) -> ControleRecord:
        """Change the mode (and optionally the drain idle days; ``None`` keeps the value)
        with an attributed audit row. Raises :class:`NotFound`, :class:`ValueError`
        (unknown mode / days outside 1..365)."""
        ...


def _validate(modo: str, dias: int | None) -> None:
    if modo not in MODOS:
        raise ValueError(f"modo must be one of {MODOS}; got {modo!r}")
    if dias is not None and not 1 <= dias <= 365:
        raise ValueError("dreno_inatividade_dias must be within 1..365")


class FakeAgentControleStore:
    """In-memory :class:`AgentControleStore`. An agent never ``set`` reads as the DB
    default (``desligado``, 7 days) — what a freshly created agent row holds."""

    def __init__(self) -> None:
        self._rows: dict[tuple[UUID, UUID], ControleRecord] = {}
        #: ``(agent_id, actor, antes, depois)`` per change — the audit the trigger writes.
        self.auditoria: list[tuple[UUID, UUID | None, dict[str, Any], dict[str, Any]]] = []
        #: Set to an exception to simulate the control being unreadable (fail-closed tests).
        self.falha: Exception | None = None

    def get(self, org_id: UUID, agent_id: UUID) -> ControleRecord:
        if self.falha is not None:
            raise self.falha
        return self._rows.get(
            (org_id, agent_id), ControleRecord(agent_id, org_id, "desligado", DRENO_DIAS_PADRAO)
        )

    def set(
        self, org_id: UUID, agent_id: UUID, *, modo: str, dreno_inatividade_dias: int | None = None,
        actor: UUID | None = None,
    ) -> ControleRecord:
        _validate(modo, dreno_inatividade_dias)
        before = self.get(org_id, agent_id)
        rec = ControleRecord(
            agent_id, org_id, modo,
            dreno_inatividade_dias if dreno_inatividade_dias is not None else before.dreno_inatividade_dias,
        )
        self._rows[(org_id, agent_id)] = rec
        if (rec.modo, rec.dreno_inatividade_dias) != (before.modo, before.dreno_inatividade_dias):
            self.auditoria.append((
                agent_id, actor,
                {"modo_operacao": before.modo, "dreno_inatividade_dias": before.dreno_inatividade_dias},
                {"modo_operacao": rec.modo, "dreno_inatividade_dias": rec.dreno_inatividade_dias},
            ))
        return rec


class SupabaseAgentControleStore:
    """Real :class:`AgentControleStore` — Postgres via the admin client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get(self, org_id: UUID, agent_id: UUID) -> ControleRecord:
        rows = (
            self._client.schema(_SCHEMA).table("agents")
            .select("id, org_id, modo_operacao, dreno_inatividade_dias")
            .eq("id", str(agent_id)).eq("org_id", str(org_id)).limit(1).execute().data or []
        )
        if not rows:
            raise NotFound(f"agent {agent_id} not found for org {org_id}")
        return self._record(rows[0])

    def set(
        self, org_id: UUID, agent_id: UUID, *, modo: str, dreno_inatividade_dias: int | None = None,
        actor: UUID | None = None,
    ) -> ControleRecord:
        _validate(modo, dreno_inatividade_dias)
        exec_rpc(self._client, _SCHEMA, "set_agent_modo", {
            "p_org_id": str(org_id), "p_agent_id": str(agent_id), "p_modo": modo,
            "p_dreno_dias": dreno_inatividade_dias, "p_actor": str(actor) if actor else None,
        })
        return self.get(org_id, agent_id)

    @staticmethod
    def _record(row: dict[str, Any]) -> ControleRecord:
        return ControleRecord(
            agent_id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])),
            modo=row["modo_operacao"], dreno_inatividade_dias=int(row["dreno_inatividade_dias"]),
        )


def get_agent_controle_store(settings: Any) -> AgentControleStore:
    """Real when a Supabase service-role key is configured, Fake otherwise — same
    signal as :func:`app.stores.agents.get_agent_store`."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeAgentControleStore()
    from app.database import get_admin_client

    return SupabaseAgentControleStore(get_admin_client())
