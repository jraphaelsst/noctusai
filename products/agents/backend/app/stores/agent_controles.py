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

from dataclasses import dataclass, replace
from typing import Any, Protocol
from uuid import UUID

from app.stores._db_errors import exec_rpc
from app.stores.errors import NotFound

__all__ = [
    "AVALIACAO_NUMEROS_MAX",
    "CONTATOS_PERMITIDOS_MAX",
    "normalizar_contatos",
    "normalizar_e164",
    "normalizar_usuarios",
    "DRENO_DIAS_PADRAO",
    "MODOS",
    "AgentControleStore",
    "AvaliacaoSomenteNoNucleo",
    "ControleRecord",
    "NucleoIndisponivel",
    "FakeAgentControleStore",
    "SupabaseAgentControleStore",
    "get_agent_controle_store",
]

_SCHEMA = "agents"
#: 056 ``avaliacao_usuarios`` CHECK: at most this many allow-listed users.
AVALIACAO_NUMEROS_MAX = 20
#: 084 ``set_agent_contatos_permitidos``: at most this many allow-listed phone numbers.
CONTATOS_PERMITIDOS_MAX = 100


def normalizar_e164(bruto: Any) -> str | None:
    """``"+55 (11) 99999-0000"`` / ``"5511999990000"`` -> ``"+5511999990000"``; ``None`` when it is not a plausible
    E.164 number (8..15 digits). Only the digits count, so a formatted and a bare number compare equal."""
    if bruto is None:
        return None
    digitos = "".join(ch for ch in str(bruto) if ch.isdigit())
    return f"+{digitos}" if 8 <= len(digitos) <= 15 else None


def normalizar_contatos(brutos: list[Any]) -> tuple[str, ...]:
    """The phone allow-list (084), each number as E.164, de-duplicated, order kept. Raises :class:`ValueError` on a number
    that is not a plausible phone or on more than :data:`CONTATOS_PERMITIDOS_MAX`."""
    out: list[str] = []
    for b in brutos:
        n = normalizar_e164(b)
        if n is None:
            raise ValueError(f"contatos_permitidos: not a valid phone number: {str(b)[:24]!r}")
        if n not in out:
            out.append(n)
    if len(out) > CONTATOS_PERMITIDOS_MAX:
        raise ValueError(f"contatos_permitidos allows at most {CONTATOS_PERMITIDOS_MAX} numbers")
    return tuple(out)


def normalizar_usuarios(brutos: list[Any]) -> tuple[UUID, ...]:
    """The allow-list of noctus user ids, de-duplicated, order kept. Raises :class:`ValueError` on a non-UUID or more
    than :data:`AVALIACAO_NUMEROS_MAX` (the 056 CHECK)."""
    out: list[UUID] = []
    for b in brutos:
        try:
            u = b if isinstance(b, UUID) else UUID(str(b))
        except ValueError as exc:
            raise ValueError("avaliacao_usuarios must be user ids (UUID)") from exc
        if u not in out:
            out.append(u)
    if len(out) > AVALIACAO_NUMEROS_MAX:
        raise ValueError(f"avaliacao_usuarios allows at most {AVALIACAO_NUMEROS_MAX} users")
    return tuple(out)


#: ``agents.modo_operacao`` CHECK (034).
MODOS = ("ligado", "drenando", "desligado")
#: ``agents.dreno_inatividade_dias`` column default (034) — owner answer Q3.
DRENO_DIAS_PADRAO = 7


class AvaliacaoSomenteNoNucleo(ValueError):
    """The testing switch (evaluation mode + list) is ONE switch on Julia's core (the ``plataforma`` definition row); an
    INSTANCE (a company's own row) never carries it (owner 2026-11-05)."""


class NucleoIndisponivel(RuntimeError):
    """An instance's core (``definition_agent_id``) could not be resolved or read: the testing state is unknown, so every
    caller fails CLOSED (``controle_indisponivel``, nothing is sent)."""


@dataclass(frozen=True)
class ControleRecord:
    agent_id: UUID
    org_id: UUID
    modo: str
    dreno_inatividade_dias: int
    #: 056 evaluation mode (Julia v3 §12.12): while on, the agent answers only the phones (from noc) of the listed users.
    modo_avaliacao: bool = False
    avaliacao_usuarios: tuple[UUID, ...] = ()
    #: The org that OWNS the evaluation list (the core's org: the evaluators are NoctusAI users, not the company's). ``None`` =
    #: this row's own org. For an instance the three evaluation fields above are the CORE's, never the instance's own
    #: columns (NOC-REMEDIATE[drop-instance-modo-avaliacao]: the instance columns are dead, an old image still reads them).
    avaliacao_org_id: UUID | None = None
    #: True for an instance: the evaluation state is inherited from Julia's core and is read-only here.
    avaliacao_herdada: bool = False
    #: 084 per-agent phone allow-list (E.164). EMPTY = every number is answered; non-empty = ONLY these numbers. Always the
    #: agent row's own (never inherited from a core, unlike the evaluation state).
    contatos_permitidos: tuple[str, ...] = ()

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

    def set_avaliacao(
        self, org_id: UUID, agent_id: UUID, *, modo_avaliacao: bool | None = None,
        usuarios: list[UUID] | None = None, actor: UUID | None = None,
    ) -> ControleRecord:
        """Change the evaluation mode and/or its allow-list (``None`` keeps a value) with an audit row
        (``modo_avaliacao_alterado``; the row carries the user COUNT). Raises
        :class:`NotFound`, :class:`ValueError` (a non-UUID user id, more than 20)."""
        ...

    def set_contatos_permitidos(
        self, org_id: UUID, agent_id: UUID, *, numeros: list[str], actor: UUID | None = None,
    ) -> ControleRecord:
        """Replace the phone allow-list (084; E.164-normalised, de-duplicated; empty = every number) with an audit row
        (``contatos_permitidos_alterados``; counts only). Raises :class:`NotFound`, :class:`ValueError` (a non-phone, more than 100)."""
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
        #: ``(agent_id, actor, antes, depois)`` per evaluation change: ``(modo, n_usuarios)`` pairs.
        self.auditoria_avaliacao: list[tuple[UUID, UUID | None, tuple[bool, int], tuple[bool, int]]] = []
        #: ``(agent_id, actor, antes, depois)`` per allow-list change: the number of listed phones before / after.
        self.auditoria_contatos: list[tuple[UUID, UUID | None, int, int]] = []
        #: instance (org, agent) -> its core (org, agent); an entry whose core row is absent models an unresolvable core.
        self._nucleos: dict[tuple[UUID, UUID], tuple[UUID, UUID]] = {}

    def vincular_nucleo(self, org_id: UUID, agent_id: UUID, nucleo_org_id: UUID, nucleo_agent_id: UUID) -> None:
        """Declare ``(org_id, agent_id)`` an INSTANCE of the core ``(nucleo_org_id, nucleo_agent_id)``."""
        self._nucleos[(org_id, agent_id)] = (nucleo_org_id, nucleo_agent_id)

    def _propria(self, org_id: UUID, agent_id: UUID) -> ControleRecord:
        return self._rows.get((org_id, agent_id), ControleRecord(agent_id, org_id, "desligado", DRENO_DIAS_PADRAO))

    def get(self, org_id: UUID, agent_id: UUID) -> ControleRecord:
        if self.falha is not None:
            raise self.falha
        propria = self._propria(org_id, agent_id)
        nucleo = self._nucleos.get((org_id, agent_id))
        if nucleo is None:
            return propria
        if nucleo not in self._rows:
            raise NucleoIndisponivel(f"core {nucleo[1]} of instance {agent_id} not found")
        n = self._rows[nucleo]
        return replace(propria, modo_avaliacao=n.modo_avaliacao, avaliacao_usuarios=n.avaliacao_usuarios,
                       avaliacao_org_id=n.org_id, avaliacao_herdada=True)

    def set(
        self, org_id: UUID, agent_id: UUID, *, modo: str, dreno_inatividade_dias: int | None = None,
        actor: UUID | None = None,
    ) -> ControleRecord:
        _validate(modo, dreno_inatividade_dias)
        before = self._propria(org_id, agent_id)
        rec = replace(
            before, modo=modo,
            dreno_inatividade_dias=dreno_inatividade_dias if dreno_inatividade_dias is not None else before.dreno_inatividade_dias,
        )
        self._rows[(org_id, agent_id)] = rec
        if (rec.modo, rec.dreno_inatividade_dias) != (before.modo, before.dreno_inatividade_dias):
            self.auditoria.append((
                agent_id, actor,
                {"modo_operacao": before.modo, "dreno_inatividade_dias": before.dreno_inatividade_dias},
                {"modo_operacao": rec.modo, "dreno_inatividade_dias": rec.dreno_inatividade_dias},
            ))
        return rec

    def set_avaliacao(
        self, org_id: UUID, agent_id: UUID, *, modo_avaliacao: bool | None = None,
        usuarios: list[UUID] | None = None, actor: UUID | None = None,
    ) -> ControleRecord:
        novos = normalizar_usuarios(usuarios) if usuarios is not None else None
        if (org_id, agent_id) in self._nucleos:
            raise AvaliacaoSomenteNoNucleo("the testing switch lives on Julia's core, not on a company instance")
        before = self._propria(org_id, agent_id)
        rec = replace(
            before,
            modo_avaliacao=before.modo_avaliacao if modo_avaliacao is None else bool(modo_avaliacao),
            avaliacao_usuarios=before.avaliacao_usuarios if novos is None else novos,
        )
        self._rows[(org_id, agent_id)] = rec
        if (rec.modo_avaliacao, rec.avaliacao_usuarios) != (before.modo_avaliacao, before.avaliacao_usuarios):
            self.auditoria_avaliacao.append((
                agent_id, actor, (before.modo_avaliacao, len(before.avaliacao_usuarios)),
                (rec.modo_avaliacao, len(rec.avaliacao_usuarios))))
        return rec

    def set_contatos_permitidos(
        self, org_id: UUID, agent_id: UUID, *, numeros: list[str], actor: UUID | None = None,
    ) -> ControleRecord:
        novos = normalizar_contatos(numeros)
        before = self._propria(org_id, agent_id)
        rec = replace(before, contatos_permitidos=novos)
        self._rows[(org_id, agent_id)] = rec
        if novos != before.contatos_permitidos:
            self.auditoria_contatos.append((agent_id, actor, len(before.contatos_permitidos), len(novos)))
        return rec


class SupabaseAgentControleStore:
    """Real :class:`AgentControleStore` — Postgres via the admin client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get(self, org_id: UUID, agent_id: UUID) -> ControleRecord:
        rows = (
            self._client.schema(_SCHEMA).table("agents")
            .select("id, org_id, modo_operacao, dreno_inatividade_dias, modo_avaliacao, avaliacao_usuarios, "
                    "definition_scope, definition_agent_id")
            .eq("id", str(agent_id)).eq("org_id", str(org_id)).limit(1).execute().data or []
        )
        if not rows:
            raise NotFound(f"agent {agent_id} not found for org {org_id}")
        row = rows[0]
        if row.get("definition_scope") != "instancia":
            return self._record(row)
        # An INSTANCE never carries the testing state: it is the CORE's (031 FK ``definition_agent_id`` -> the ``plataforma``
        # definition row). Unresolvable / not a core => NucleoIndisponivel (every caller fails closed).
        nucleo = None
        if row.get("definition_agent_id"):
            nucleos = (
                self._client.schema(_SCHEMA).table("agents")
                .select("id, org_id, definition_scope, modo_avaliacao, avaliacao_usuarios")
                .eq("id", str(row["definition_agent_id"])).limit(1).execute().data or []
            )
            nucleo = nucleos[0] if nucleos else None
        if nucleo is None or nucleo.get("definition_scope") != "plataforma":
            raise NucleoIndisponivel(f"core of instance {agent_id} could not be resolved")
        return replace(
            self._record(row),
            modo_avaliacao=bool(nucleo.get("modo_avaliacao", False)),
            avaliacao_usuarios=tuple(UUID(str(u)) for u in (nucleo.get("avaliacao_usuarios") or ())),
            avaliacao_org_id=UUID(str(nucleo["org_id"])), avaliacao_herdada=True,
        )

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

    def set_avaliacao(
        self, org_id: UUID, agent_id: UUID, *, modo_avaliacao: bool | None = None,
        usuarios: list[UUID] | None = None, actor: UUID | None = None,
    ) -> ControleRecord:
        novos = normalizar_usuarios(usuarios) if usuarios is not None else None
        if self.get(org_id, agent_id).avaliacao_herdada:
            raise AvaliacaoSomenteNoNucleo("the testing switch lives on Julia's core, not on a company instance")
        exec_rpc(self._client, _SCHEMA, "set_agent_avaliacao", {
            "p_org_id": str(org_id), "p_agent_id": str(agent_id),
            "p_modo_avaliacao": None if modo_avaliacao is None else bool(modo_avaliacao),
            "p_usuarios": None if novos is None else [str(u) for u in novos], "p_actor": str(actor) if actor else None,
        })
        return self.get(org_id, agent_id)

    def set_contatos_permitidos(
        self, org_id: UUID, agent_id: UUID, *, numeros: list[str], actor: UUID | None = None,
    ) -> ControleRecord:
        novos = normalizar_contatos(numeros)
        exec_rpc(self._client, _SCHEMA, "set_agent_contatos_permitidos", {
            "p_org_id": str(org_id), "p_agent_id": str(agent_id), "p_numeros": list(novos),
            "p_actor": str(actor) if actor else None,
        })
        return self.get(org_id, agent_id)

    @staticmethod
    def _record(row: dict[str, Any]) -> ControleRecord:
        return ControleRecord(
            agent_id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])),
            modo=row["modo_operacao"], dreno_inatividade_dias=int(row["dreno_inatividade_dias"]),
            modo_avaliacao=bool(row.get("modo_avaliacao", False)),
            avaliacao_usuarios=tuple(UUID(str(u)) for u in (row.get("avaliacao_usuarios") or ())),
            contatos_permitidos=tuple(str(n) for n in (row.get("contatos_permitidos") or ())),
        )


def get_agent_controle_store(settings: Any) -> AgentControleStore:
    """Real when a Supabase service-role key is configured, Fake otherwise — same
    signal as :func:`app.stores.agents.get_agent_store`."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeAgentControleStore()
    from app.database import get_admin_client

    return SupabaseAgentControleStore(get_admin_client())
