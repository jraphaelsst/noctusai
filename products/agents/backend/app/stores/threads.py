"""Thread store — the SHARED lead thread's identity, participants and audit (Julia v2).

A lead's conversation is ONE ``agents.conversations`` row (``tipo='thread_lead'``,
see :mod:`app.stores.conversations`) shared by every agent that ever talks to the
lead; this module owns what hangs off it (migration 033, contract §6):

* ``lead_refs`` — the lead identity (SW ``julia_contatos.id`` is ``ref_externa``);
* ``thread_participantes`` — each agent's state in the thread
  (``ativo|pausado|concluido|encerrado|transferido``), at most ONE ``ativo`` per
  thread (a partial unique index — risk 11), moved only by a compare-and-set;
* ``thread_participante_eventos`` — the per-thread transition audit;
* ``thread_skill_aberturas`` — which skill was opened in the thread under which
  ``compiled_hash`` (the mandatory-skill gate, D7);
* the multi-agent history read (§6.3): :func:`historico_do_agente` /
  :func:`rotular_historico` — what THIS agent sees of a thread other agents and
  humans also wrote in, without repeating what was already said.

Seed IO shape: ``ThreadStore`` Protocol + ``FakeThreadStore`` +
``SupabaseThreadStore`` (Real) + ``get_thread_store(settings)`` factory. Every
method is org-scoped.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from app.stores._db_errors import exec_query, exec_rpc
from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import Conflict, NotFound

__all__ = [
    "ATOR_TIPOS",
    "ESTADOS",
    "PRODUTO_SW",
    "OPT_IN_ORIGENS",
    "PAPEL_DONO_ORG",
    "ContextoThread",
    "FakeThreadStore",
    "HandoffDestino",
    "HandoffRecord",
    "HistoricoItem",
    "LeadRefRecord",
    "OutroAgenteAtivo",
    "ParticipanteEvento",
    "ParticipanteRecord",
    "SupabaseThreadStore",
    "ThreadAberto",
    "ThreadStore",
    "contexto_thread",
    "get_thread_store",
    "historico_do_agente",
    "mapa_agentes",
    "rotular_historico",
]

_SCHEMA = "agents"
PRODUTO_SW = "social-wiring"

#: ``thread_participantes.estado`` CHECK (033).
ESTADOS = ("ativo", "pausado", "concluido", "encerrado", "transferido")
#: ``thread_participante_eventos.ator_tipo`` CHECK (033).
ATOR_TIPOS = ("agente", "usuario", "token", "sistema")
#: ``lead_refs.opt_in_origem`` CHECK (033): how the lead consented to be contacted.
OPT_IN_ORIGENS = ("lead_iniciou", "formulario_meta", "campanha_ctwa", "importado")
#: The default hand-off target for now: the org owner, who redirects to a broker (owner requirement;
#: configurable per org later).
PAPEL_DONO_ORG = "dono_org"


class OutroAgenteAtivo(Conflict):
    """Another agent is the ACTIVE participant of the thread (the one-active index)."""


@dataclass(frozen=True)
class LeadRefRecord:
    id: UUID
    org_id: UUID
    produto: str
    ref_externa: str
    crm_lead_id: UUID | None
    #: ``{nome, telefone_e164}`` — personal data; the only PII copy next to the qualification.
    contato: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    #: Messaging-policy consent: when/how the lead opted in, and when they asked to stop.
    opt_in_em: datetime | None = None
    opt_in_origem: str | None = None
    opt_out_em: datetime | None = None

    @property
    def opt_out_ativo(self) -> bool:
        """The lead asked to stop and has not opted in again since."""
        if self.opt_out_em is None:
            return False
        return self.opt_in_em is None or self.opt_in_em < self.opt_out_em


@dataclass(frozen=True)
class ParticipanteRecord:
    thread_id: UUID
    agent_id: UUID
    org_id: UUID
    estado: str
    entrou_em: datetime
    saiu_em: datetime | None
    motivo: str | None
    ultimo_turno_em: datetime | None
    #: A timed pause: past this instant the participant counts as active again.
    pausado_ate: datetime | None = None


@dataclass(frozen=True)
class ParticipanteEvento:
    id: UUID
    org_id: UUID
    thread_id: UUID
    agent_id: UUID
    de: str | None
    para: str
    ator_tipo: str
    ator_id: UUID | None
    motivo: str | None
    created_at: datetime
    ate: datetime | None = None


@dataclass(frozen=True)
class HandoffDestino:
    """To whom a hand-off goes: another agent, a human (user) or a role nobody holds yet."""

    tipo: str  # agente | humano | papel
    agent_id: UUID | None = None
    user_id: UUID | None = None
    papel: str | None = None

    def __post_init__(self) -> None:
        ok = {
            "agente": self.agent_id is not None and self.user_id is None and self.papel is None,
            "humano": self.user_id is not None and self.agent_id is None and self.papel is None,
            "papel": bool(self.papel) and self.agent_id is None and self.user_id is None,
        }.get(self.tipo)
        if not ok:
            raise ValueError(f"hand-off destination {self.tipo!r} needs exactly its own target")

    @classmethod
    def dono_da_org(cls) -> "HandoffDestino":
        """The default operator for now: the org owner (who redirects to a broker)."""
        return cls("papel", papel=PAPEL_DONO_ORG)


@dataclass(frozen=True)
class HandoffRecord:
    """The note that travels with a thread when an agent lets go: what the next operator (a human
    for now) reads first. ``identificacao_mascarada`` holds MASKED fields only; the raw documents
    live in the qualification slice's encrypted store and are merely referenced."""

    id: UUID
    org_id: UUID
    thread_id: UUID
    lead_ref_id: UUID | None
    de_agent_id: UUID
    para: HandoffDestino
    motivo_codigo: str
    resumo: str
    perfil: dict[str, Any]
    identificacao_completa: bool
    identificacao_mascarada: dict[str, Any]
    perguntas_abertas: list[Any]
    compromissos: list[Any]
    created_at: datetime
    aceito_em: datetime | None = None
    aceito_por: UUID | None = None


@dataclass(frozen=True)
class ThreadAberto:
    """One open thread of an agent (the drain progress): its ACTIVE participant
    plus the last LEAD message (``None`` when the lead never wrote)."""

    thread_id: UUID
    agent_id: UUID
    entrou_em: datetime
    ultima_mensagem_lead_em: datetime | None


class ThreadStore(Protocol):
    # ── lead identity ────────────────────────────────────────────────────
    def upsert_lead_ref(
        self, org_id: UUID, ref_externa: str, *, crm_lead_id: UUID | None = None,
        contato: dict[str, Any] | None = None, produto: str = PRODUTO_SW,
    ) -> LeadRefRecord:
        """Create the lead_ref, or refresh the one that exists: ``crm_lead_id`` /
        ``contato`` are written only when given (a later call with ``None`` never
        erases what an earlier one stored). A concurrent create returns the row that won."""
        ...

    def get_lead_ref(self, org_id: UUID, id: UUID) -> LeadRefRecord | None: ...

    def get_lead_ref_by_externa(
        self, org_id: UUID, ref_externa: str, *, produto: str = PRODUTO_SW
    ) -> LeadRefRecord | None: ...

    def registrar_opt_in(
        self, org_id: UUID, ref_externa: str, *, origem: str, em: datetime | None = None
    ) -> LeadRefRecord:
        """The lead consented to be contacted (``origem`` in :data:`OPT_IN_ORIGENS`). Creates the
        lead_ref when unknown. A LATER opt-in lifts an earlier opt-out."""
        ...

    def registrar_opt_out(self, org_id: UUID, ref_externa: str, *, em: datetime | None = None) -> int:
        """The lead asked to stop: stamp ``opt_out_em`` and end EVERY agent's participation in every
        thread of the lead (``ativo``/``pausado`` -> ``encerrado``, motivo ``opt_out``). Idempotent.
        Returns how many participants moved; ``-1`` when the lead is unknown."""
        ...

    # ── participants ─────────────────────────────────────────────────────
    def add_participante(
        self, org_id: UUID, thread_id: UUID, agent_id: UUID, *, motivo: str | None = None,
        ator_tipo: str = "sistema", ator_id: UUID | None = None,
    ) -> ParticipanteRecord:
        """Join the agent to the thread as ``ativo`` (+ an audit event). Idempotent:
        an agent that already participates is returned unchanged. Raises
        :class:`OutroAgenteAtivo` when ANOTHER agent is the active participant."""
        ...

    def get_participante(
        self, org_id: UUID, thread_id: UUID, agent_id: UUID
    ) -> ParticipanteRecord | None: ...

    def list_participantes(self, org_id: UUID, thread_id: UUID) -> list[ParticipanteRecord]: ...

    def transicionar(
        self, org_id: UUID, thread_id: UUID, agent_id: UUID, *, de: Sequence[str], para: str,
        ator_tipo: str, ator_id: UUID | None = None, motivo: str | None = None,
        ate: datetime | None = None,
    ) -> bool:
        """Compare-and-set the participant's state: ``True`` when it moved from one
        of ``de`` to ``para`` (the event row, and for a pause/resume the audit row,
        are written in the SAME transaction); ``False`` when it was not in ``de``
        (somebody else moved it first — the caller re-reads). Raises
        :class:`NotFound` (no such participant) and :class:`OutroAgenteAtivo`
        (``para='ativo'`` while another agent is active). ``ate`` (a pause only) is when it ends."""
        ...

    # ── hand-off ─────────────────────────────────────────────────────────
    def registrar_handoff(
        self, org_id: UUID, thread_id: UUID, de_agent_id: UUID, *, para: HandoffDestino, motivo_codigo: str,
        resumo: str, perfil: dict[str, Any] | None = None, identificacao_completa: bool = False,
        identificacao_mascarada: dict[str, Any] | None = None, perguntas_abertas: Sequence[Any] = (),
        compromissos: Sequence[Any] = (), para_estado: str = "transferido",
        de: Sequence[str] = ("ativo",), ator_tipo: str = "agente", ator_id: UUID | None = None,
    ) -> HandoffRecord:
        """Write the hand-off note AND move the giver (``ativo`` -> ``para_estado``: ``transferido`` or
        ``pausado``) in ONE transaction: the note is written first and a refused move rolls it back, so a
        transferred thread never exists without its note. A hand-off to another AGENT also makes that agent
        the active participant. Raises :class:`NotFound` (the giver does not take part) and
        :class:`Conflict` (the giver was no longer in ``de``)."""
        ...

    def get_handoff(self, org_id: UUID, handoff_id: UUID) -> HandoffRecord | None: ...

    def list_handoffs(self, org_id: UUID, thread_id: UUID) -> list[HandoffRecord]:
        """The thread's hand-offs, oldest first."""
        ...

    def ultimo_handoff(
        self, org_id: UUID, thread_id: UUID, *, para_agent_id: UUID | None = None
    ) -> HandoffRecord | None:
        """The newest hand-off of the thread (to ``para_agent_id`` when given)."""
        ...

    def aceitar_handoff(self, org_id: UUID, handoff_id: UUID, user_id: UUID) -> HandoffRecord:
        """The receiving operator took it (``aceito_em`` / ``aceito_por``). Idempotent. Raises :class:`NotFound`."""
        ...

    def marcar_turno(self, org_id: UUID, thread_id: UUID, agent_id: UUID) -> None:
        """Stamp ``ultimo_turno_em = now`` (the agent just answered in the thread)."""
        ...

    def list_eventos(self, org_id: UUID, thread_id: UUID) -> list[ParticipanteEvento]:
        """The thread's transition audit, oldest first."""
        ...

    def list_abertos(self, org_id: UUID, agent_id: UUID) -> list[ThreadAberto]:
        """Every thread where ``agent_id`` is the ACTIVE participant (drain progress)."""
        ...

    # ── mandatory skills (D7) ────────────────────────────────────────────
    def registrar_abertura_skill(
        self, org_id: UUID, thread_id: UUID, skill: str, compiled_hash: str
    ) -> None:
        """Record that ``skill`` was opened in this thread under ``compiled_hash``. Idempotent."""
        ...

    def skill_aberta(self, org_id: UUID, thread_id: UUID, skill: str, compiled_hash: str) -> bool: ...


# ── Fake ────────────────────────────────────────────────────────────────────


class FakeThreadStore:
    """In-memory :class:`ThreadStore`. ``conversations`` (a ``ConversationStore``)
    is only needed by :meth:`list_abertos` (the last-lead-message clock)."""

    def __init__(self, conversations: Any = None) -> None:
        self._conversations = conversations
        self._leads: dict[UUID, LeadRefRecord] = {}
        self._participantes: dict[tuple[UUID, UUID], ParticipanteRecord] = {}
        self._eventos: list[ParticipanteEvento] = []
        self._skills: set[tuple[UUID, str, str]] = set()
        self._handoffs: dict[UUID, HandoffRecord] = {}

    # lead identity
    def upsert_lead_ref(
        self, org_id: UUID, ref_externa: str, *, crm_lead_id: UUID | None = None,
        contato: dict[str, Any] | None = None, produto: str = PRODUTO_SW,
    ) -> LeadRefRecord:
        now = utcnow()
        existing = self.get_lead_ref_by_externa(org_id, ref_externa, produto=produto)
        if existing is None:
            rec = LeadRefRecord(
                id=uuid4(), org_id=org_id, produto=produto, ref_externa=ref_externa,
                crm_lead_id=crm_lead_id, contato=dict(contato) if contato is not None else None,
                created_at=now, updated_at=now,
            )
        else:
            rec = replace(
                existing,
                crm_lead_id=crm_lead_id if crm_lead_id is not None else existing.crm_lead_id,
                contato=dict(contato) if contato is not None else existing.contato,
                updated_at=now,
            )
        self._leads[rec.id] = rec
        return rec

    def get_lead_ref(self, org_id: UUID, id: UUID) -> LeadRefRecord | None:
        rec = self._leads.get(id)
        return rec if rec is not None and rec.org_id == org_id else None

    def get_lead_ref_by_externa(
        self, org_id: UUID, ref_externa: str, *, produto: str = PRODUTO_SW
    ) -> LeadRefRecord | None:
        for rec in self._leads.values():
            if rec.org_id == org_id and rec.produto == produto and rec.ref_externa == ref_externa:
                return rec
        return None

    def registrar_opt_in(
        self, org_id: UUID, ref_externa: str, *, origem: str, em: datetime | None = None
    ) -> LeadRefRecord:
        if origem not in OPT_IN_ORIGENS:
            raise ValueError(f"origem must be one of {OPT_IN_ORIGENS}; got {origem!r}")
        lead = self.upsert_lead_ref(org_id, ref_externa)
        lead = replace(lead, opt_in_em=em or utcnow(), opt_in_origem=origem, updated_at=utcnow())
        self._leads[lead.id] = lead
        return lead

    def registrar_opt_out(self, org_id: UUID, ref_externa: str, *, em: datetime | None = None) -> int:
        lead = self.get_lead_ref_by_externa(org_id, ref_externa)
        if lead is None:
            return -1
        self._leads[lead.id] = replace(lead, opt_out_em=em or utcnow(), updated_at=utcnow())
        moved = 0
        for key, p in list(self._participantes.items()):
            if p.org_id != org_id or p.estado not in ("ativo", "pausado"):
                continue
            conv = self._conversations.get(org_id, p.thread_id) if self._conversations is not None else None
            if conv is None or conv.lead_ref_id != lead.id:
                continue
            self._participantes[key] = replace(p, estado="encerrado", motivo="opt_out", saiu_em=utcnow(), pausado_ate=None)
            self._evento(org_id, p.thread_id, p.agent_id, p.estado, "encerrado", "sistema", None, "opt_out", None)
            moved += 1
        return moved

    # participants
    def _evento(
        self, org_id: UUID, thread_id: UUID, agent_id: UUID, de: str | None, para: str,
        ator_tipo: str, ator_id: UUID | None, motivo: str | None, ate: datetime | None = None,
    ) -> None:
        self._eventos.append(ParticipanteEvento(
            id=uuid4(), org_id=org_id, thread_id=thread_id, agent_id=agent_id, de=de, para=para,
            ator_tipo=ator_tipo, ator_id=ator_id, motivo=motivo, created_at=utcnow(), ate=ate,
        ))

    def _outro_ativo(self, org_id: UUID, thread_id: UUID, agent_id: UUID) -> bool:
        return any(
            p.thread_id == thread_id and p.org_id == org_id and p.agent_id != agent_id and p.estado == "ativo"
            for p in self._participantes.values()
        )

    def add_participante(
        self, org_id: UUID, thread_id: UUID, agent_id: UUID, *, motivo: str | None = None,
        ator_tipo: str = "sistema", ator_id: UUID | None = None,
    ) -> ParticipanteRecord:
        existing = self._participantes.get((thread_id, agent_id))
        if existing is not None and existing.org_id == org_id:
            return existing
        if self._outro_ativo(org_id, thread_id, agent_id):
            raise OutroAgenteAtivo("another agent is the active participant of this thread")
        rec = ParticipanteRecord(
            thread_id=thread_id, agent_id=agent_id, org_id=org_id, estado="ativo",
            entrou_em=utcnow(), saiu_em=None, motivo=motivo, ultimo_turno_em=None,
        )
        self._participantes[(thread_id, agent_id)] = rec
        self._evento(org_id, thread_id, agent_id, None, "ativo", ator_tipo, ator_id, motivo)
        return rec

    def get_participante(self, org_id: UUID, thread_id: UUID, agent_id: UUID) -> ParticipanteRecord | None:
        rec = self._participantes.get((thread_id, agent_id))
        return rec if rec is not None and rec.org_id == org_id else None

    def list_participantes(self, org_id: UUID, thread_id: UUID) -> list[ParticipanteRecord]:
        rows = [p for p in self._participantes.values() if p.org_id == org_id and p.thread_id == thread_id]
        rows.sort(key=lambda p: p.entrou_em)
        return rows

    def transicionar(
        self, org_id: UUID, thread_id: UUID, agent_id: UUID, *, de: Sequence[str], para: str,
        ator_tipo: str, ator_id: UUID | None = None, motivo: str | None = None,
        ate: datetime | None = None,
    ) -> bool:
        if para not in ESTADOS:
            raise ValueError(f"estado must be one of {ESTADOS}; got {para!r}")
        if ator_tipo not in ATOR_TIPOS:
            raise ValueError(f"ator_tipo must be one of {ATOR_TIPOS}; got {ator_tipo!r}")
        rec = self.get_participante(org_id, thread_id, agent_id)
        if rec is None:
            raise NotFound(f"participante {agent_id} not found in thread {thread_id}")
        if rec.estado not in de:
            return False
        if para == "ativo" and self._outro_ativo(org_id, thread_id, agent_id):
            raise OutroAgenteAtivo("another agent is the active participant of this thread")
        now = utcnow()
        saiu = None if para == "ativo" else (rec.saiu_em if para == "pausado" else now)
        self._participantes[(thread_id, agent_id)] = replace(
            rec, estado=para, motivo=motivo, saiu_em=saiu, pausado_ate=ate if para == "pausado" else None
        )
        self._evento(org_id, thread_id, agent_id, rec.estado, para, ator_tipo, ator_id, motivo, ate)
        return True

    def registrar_handoff(
        self, org_id: UUID, thread_id: UUID, de_agent_id: UUID, *, para: HandoffDestino, motivo_codigo: str,
        resumo: str, perfil: dict[str, Any] | None = None, identificacao_completa: bool = False,
        identificacao_mascarada: dict[str, Any] | None = None, perguntas_abertas: Sequence[Any] = (),
        compromissos: Sequence[Any] = (), para_estado: str = "transferido",
        de: Sequence[str] = ("ativo",), ator_tipo: str = "agente", ator_id: UUID | None = None,
    ) -> HandoffRecord:
        if para_estado not in ("transferido", "pausado"):
            raise ValueError("para_estado must be 'transferido' or 'pausado'")
        if not motivo_codigo or not resumo:
            raise ValueError("a hand-off needs motivo_codigo and resumo")
        giver = self.get_participante(org_id, thread_id, de_agent_id)
        if giver is None:
            raise NotFound(f"participante {de_agent_id} not found in thread {thread_id}")
        if giver.estado not in de:
            raise Conflict("participante_estado_mudou")
        if para.tipo == "agente" and any(
            p.thread_id == thread_id and p.org_id == org_id and p.estado == "ativo"
            and p.agent_id not in (de_agent_id, para.agent_id)
            for p in self._participantes.values()
        ):
            raise OutroAgenteAtivo("another agent is the active participant of this thread")  # the giver leaves first
        lead_ref_id = None
        if self._conversations is not None:
            lead_ref_id = self._conversations.get(org_id, thread_id).lead_ref_id
        rec = HandoffRecord(
            id=uuid4(), org_id=org_id, thread_id=thread_id, lead_ref_id=lead_ref_id, de_agent_id=de_agent_id,
            para=para, motivo_codigo=motivo_codigo, resumo=resumo, perfil=dict(perfil or {}),
            identificacao_completa=identificacao_completa,
            identificacao_mascarada=dict(identificacao_mascarada or {}),
            perguntas_abertas=list(perguntas_abertas), compromissos=list(compromissos), created_at=utcnow(),
        )
        self._handoffs[rec.id] = rec  # the note first, then the move (one transaction in the Real store)
        self.transicionar(
            org_id, thread_id, de_agent_id, de=de, para=para_estado, ator_tipo=ator_tipo, ator_id=ator_id,
            motivo=motivo_codigo,
        )
        if para.tipo == "agente":
            now = utcnow()
            self._participantes[(thread_id, para.agent_id)] = ParticipanteRecord(
                thread_id=thread_id, agent_id=para.agent_id, org_id=org_id, estado="ativo", entrou_em=now,
                saiu_em=None, motivo=motivo_codigo, ultimo_turno_em=None,
            )
            self._evento(org_id, thread_id, para.agent_id, None, "ativo", ator_tipo, ator_id, motivo_codigo)
        return rec

    def get_handoff(self, org_id: UUID, handoff_id: UUID) -> HandoffRecord | None:
        rec = self._handoffs.get(handoff_id)
        return rec if rec is not None and rec.org_id == org_id else None

    def list_handoffs(self, org_id: UUID, thread_id: UUID) -> list[HandoffRecord]:
        rows = [h for h in self._handoffs.values() if h.org_id == org_id and h.thread_id == thread_id]
        rows.sort(key=lambda h: h.created_at)
        return rows

    def ultimo_handoff(
        self, org_id: UUID, thread_id: UUID, *, para_agent_id: UUID | None = None
    ) -> HandoffRecord | None:
        rows = [h for h in self.list_handoffs(org_id, thread_id)
                if para_agent_id is None or h.para.agent_id == para_agent_id]
        return rows[-1] if rows else None

    def aceitar_handoff(self, org_id: UUID, handoff_id: UUID, user_id: UUID) -> HandoffRecord:
        rec = self.get_handoff(org_id, handoff_id)
        if rec is None:
            raise NotFound(f"handoff {handoff_id} not found")
        if rec.aceito_em is None:
            rec = replace(rec, aceito_em=utcnow(), aceito_por=user_id)
            self._handoffs[rec.id] = rec
        return rec

    def marcar_turno(self, org_id: UUID, thread_id: UUID, agent_id: UUID) -> None:
        rec = self.get_participante(org_id, thread_id, agent_id)
        if rec is not None:
            self._participantes[(thread_id, agent_id)] = replace(rec, ultimo_turno_em=utcnow())

    def list_eventos(self, org_id: UUID, thread_id: UUID) -> list[ParticipanteEvento]:
        return [e for e in self._eventos if e.org_id == org_id and e.thread_id == thread_id]

    def list_abertos(self, org_id: UUID, agent_id: UUID) -> list[ThreadAberto]:
        out = []
        for p in self._participantes.values():
            if p.org_id != org_id or p.agent_id != agent_id or p.estado != "ativo":
                continue
            ultima = None
            if self._conversations is not None:
                try:
                    ultima = self._conversations.get(org_id, p.thread_id).ultima_mensagem_lead_em
                except NotFound:
                    continue  # the thread is gone (purged): not open
            out.append(ThreadAberto(p.thread_id, p.agent_id, p.entrou_em, ultima))
        return out

    # skills
    def registrar_abertura_skill(self, org_id: UUID, thread_id: UUID, skill: str, compiled_hash: str) -> None:
        self._skills.add((thread_id, skill, compiled_hash))

    def skill_aberta(self, org_id: UUID, thread_id: UUID, skill: str, compiled_hash: str) -> bool:
        return (thread_id, skill, compiled_hash) in self._skills

    # test-double halves of the SQL cascades (the Real ones are FK cascades / agents.apagar_lead)
    def purge_thread(self, org_id: UUID, thread_id: UUID) -> None:
        """Participants, events and skill openings go with their thread."""
        for key in [k for k, p in self._participantes.items() if p.org_id == org_id and p.thread_id == thread_id]:
            del self._participantes[key]
        self._eventos = [e for e in self._eventos if not (e.org_id == org_id and e.thread_id == thread_id)]
        self._skills = {s for s in self._skills if s[0] != thread_id}
        self._handoffs = {k: h for k, h in self._handoffs.items() if not (h.org_id == org_id and h.thread_id == thread_id)}

    def purge_lead_ref(self, org_id: UUID, lead_ref_id: UUID) -> None:
        rec = self._leads.get(lead_ref_id)
        if rec is not None and rec.org_id == org_id:
            del self._leads[lead_ref_id]


# ── Real ────────────────────────────────────────────────────────────────────


class SupabaseThreadStore:
    """Real :class:`ThreadStore` — Postgres via the admin client (PostgREST)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, table: str):
        return self._client.schema(_SCHEMA).table(table)

    # lead identity
    def upsert_lead_ref(
        self, org_id: UUID, ref_externa: str, *, crm_lead_id: UUID | None = None,
        contato: dict[str, Any] | None = None, produto: str = PRODUTO_SW,
    ) -> LeadRefRecord:
        existing = self.get_lead_ref_by_externa(org_id, ref_externa, produto=produto)
        patch: dict[str, Any] = {}
        if crm_lead_id is not None:
            patch["crm_lead_id"] = str(crm_lead_id)
        if contato is not None:
            patch["contato"] = contato
        if existing is not None:
            if not patch:
                return existing
            resp = (
                self._t("lead_refs").update(patch)
                .eq("id", str(existing.id)).eq("org_id", str(org_id)).execute()
            )
            rows = resp.data or []
            return self._lead(rows[0]) if rows else existing
        payload = {"org_id": str(org_id), "produto": produto, "ref_externa": ref_externa, **patch}
        try:
            resp = exec_query(self._t("lead_refs").insert(payload), unique_code="lead_ref_exists")
        except Conflict:
            # A concurrent first call of the same lead won the unique: reuse ITS row.
            winner = self.get_lead_ref_by_externa(org_id, ref_externa, produto=produto)
            if winner is None:  # pragma: no cover — the conflicting row vanished mid-flight
                raise
            return winner
        rows = resp.data or []
        return self._lead(rows[0])

    def get_lead_ref(self, org_id: UUID, id: UUID) -> LeadRefRecord | None:
        rows = (
            self._t("lead_refs").select("*").eq("id", str(id)).eq("org_id", str(org_id)).execute().data or []
        )
        return self._lead(rows[0]) if rows else None

    def get_lead_ref_by_externa(
        self, org_id: UUID, ref_externa: str, *, produto: str = PRODUTO_SW
    ) -> LeadRefRecord | None:
        rows = (
            self._t("lead_refs").select("*")
            .eq("org_id", str(org_id)).eq("produto", produto).eq("ref_externa", ref_externa)
            .limit(1).execute().data or []
        )
        return self._lead(rows[0]) if rows else None

    def registrar_opt_in(
        self, org_id: UUID, ref_externa: str, *, origem: str, em: datetime | None = None
    ) -> LeadRefRecord:
        if origem not in OPT_IN_ORIGENS:
            raise ValueError(f"origem must be one of {OPT_IN_ORIGENS}; got {origem!r}")
        lead = self.upsert_lead_ref(org_id, ref_externa)
        rows = (
            self._t("lead_refs")
            .update({"opt_in_em": (em or utcnow()).isoformat(), "opt_in_origem": origem})
            .eq("id", str(lead.id)).eq("org_id", str(org_id)).execute().data or []
        )
        return self._lead(rows[0]) if rows else lead

    def registrar_opt_out(self, org_id: UUID, ref_externa: str, *, em: datetime | None = None) -> int:
        resp = exec_rpc(self._client, _SCHEMA, "registrar_opt_out", {
            "p_org_id": str(org_id), "p_produto": PRODUTO_SW, "p_ref_externa": ref_externa,
            "p_em": (em or utcnow()).isoformat(),
        })
        return int(resp.data if resp.data is not None else -1)

    # participants
    def add_participante(
        self, org_id: UUID, thread_id: UUID, agent_id: UUID, *, motivo: str | None = None,
        ator_tipo: str = "sistema", ator_id: UUID | None = None,
    ) -> ParticipanteRecord:
        existing = self.get_participante(org_id, thread_id, agent_id)
        if existing is not None:
            return existing
        payload = {
            "thread_id": str(thread_id), "agent_id": str(agent_id), "org_id": str(org_id),
            "estado": "ativo", "motivo": motivo,
        }
        try:
            resp = exec_query(self._t("thread_participantes").insert(payload), unique_code="participante_exists")
        except Conflict as exc:
            # Either the (thread, agent) PK (a concurrent join of the SAME agent: reuse it) or
            # the one-active index (ANOTHER agent is active).
            winner = self.get_participante(org_id, thread_id, agent_id)
            if winner is not None:
                return winner
            raise OutroAgenteAtivo("another agent is the active participant of this thread") from exc
        rec = self._participante((resp.data or [payload])[0])
        exec_query(self._t("thread_participante_eventos").insert({
            "org_id": str(org_id), "thread_id": str(thread_id), "agent_id": str(agent_id),
            "de": None, "para": "ativo", "ator_tipo": ator_tipo,
            "ator_id": str(ator_id) if ator_id else None, "motivo": motivo,
        }))
        return rec

    def get_participante(self, org_id: UUID, thread_id: UUID, agent_id: UUID) -> ParticipanteRecord | None:
        rows = (
            self._t("thread_participantes").select("*")
            .eq("org_id", str(org_id)).eq("thread_id", str(thread_id)).eq("agent_id", str(agent_id))
            .limit(1).execute().data or []
        )
        return self._participante(rows[0]) if rows else None

    def list_participantes(self, org_id: UUID, thread_id: UUID) -> list[ParticipanteRecord]:
        rows = (
            self._t("thread_participantes").select("*")
            .eq("org_id", str(org_id)).eq("thread_id", str(thread_id))
            .order("entrou_em").limit(100).execute().data or []
        )
        return [self._participante(r) for r in rows]

    def transicionar(
        self, org_id: UUID, thread_id: UUID, agent_id: UUID, *, de: Sequence[str], para: str,
        ator_tipo: str, ator_id: UUID | None = None, motivo: str | None = None,
        ate: datetime | None = None,
    ) -> bool:
        if para not in ESTADOS:
            raise ValueError(f"estado must be one of {ESTADOS}; got {para!r}")
        if ator_tipo not in ATOR_TIPOS:
            raise ValueError(f"ator_tipo must be one of {ATOR_TIPOS}; got {ator_tipo!r}")
        try:
            resp = exec_rpc(self._client, _SCHEMA, "set_participante_estado", {
                "p_org_id": str(org_id), "p_thread_id": str(thread_id), "p_agent_id": str(agent_id),
                "p_de": list(de), "p_para": para, "p_ator_tipo": ator_tipo,
                "p_ator_id": str(ator_id) if ator_id else None, "p_motivo": motivo,
                "p_ate": ate.isoformat() if ate is not None else None,
            }, unique_code="outro_agente_ativo")
        except Conflict as exc:
            raise OutroAgenteAtivo("another agent is the active participant of this thread") from exc
        return bool(resp.data)

    def registrar_handoff(
        self, org_id: UUID, thread_id: UUID, de_agent_id: UUID, *, para: HandoffDestino, motivo_codigo: str,
        resumo: str, perfil: dict[str, Any] | None = None, identificacao_completa: bool = False,
        identificacao_mascarada: dict[str, Any] | None = None, perguntas_abertas: Sequence[Any] = (),
        compromissos: Sequence[Any] = (), para_estado: str = "transferido",
        de: Sequence[str] = ("ativo",), ator_tipo: str = "agente", ator_id: UUID | None = None,
    ) -> HandoffRecord:
        if not motivo_codigo or not resumo:
            raise ValueError("a hand-off needs motivo_codigo and resumo")
        if ator_tipo not in ATOR_TIPOS:
            raise ValueError(f"ator_tipo must be one of {ATOR_TIPOS}; got {ator_tipo!r}")
        try:
            resp = exec_rpc(self._client, _SCHEMA, "transferir_thread", {
                "p_org_id": str(org_id), "p_thread_id": str(thread_id), "p_de_agent_id": str(de_agent_id),
                "p_de": list(de), "p_para_estado": para_estado, "p_para_tipo": para.tipo,
                "p_para_agent_id": str(para.agent_id) if para.agent_id else None,
                "p_para_user_id": str(para.user_id) if para.user_id else None, "p_para_papel": para.papel,
                "p_motivo_codigo": motivo_codigo, "p_resumo": resumo,
                "p_perguntas": list(perguntas_abertas), "p_compromissos": list(compromissos),
                "p_ator_tipo": ator_tipo, "p_ator_id": str(ator_id) if ator_id else None,
                "p_perfil": perfil or {}, "p_identificacao_completa": identificacao_completa,
                "p_identificacao_mascarada": identificacao_mascarada or {},
            }, unique_code="outro_agente_ativo")
        except Conflict as exc:
            if getattr(exc, "code", None) == "outro_agente_ativo":
                raise OutroAgenteAtivo("another agent is the active participant of this thread") from exc
            raise  # participante_estado_mudou: the giver moved under us, the note was rolled back
        found = self.get_handoff(org_id, UUID(str(resp.data)))
        if found is None:  # pragma: no cover — the row the RPC just wrote vanished
            raise NotFound("handoff vanished after being written")
        return found

    def get_handoff(self, org_id: UUID, handoff_id: UUID) -> HandoffRecord | None:
        rows = (
            self._t("thread_handoffs").select("*")
            .eq("id", str(handoff_id)).eq("org_id", str(org_id)).limit(1).execute().data or []
        )
        return self._handoff(rows[0]) if rows else None

    def list_handoffs(self, org_id: UUID, thread_id: UUID) -> list[HandoffRecord]:
        rows = (
            self._t("thread_handoffs").select("*")
            .eq("org_id", str(org_id)).eq("thread_id", str(thread_id))
            .order("created_at").limit(200).execute().data or []
        )
        return [self._handoff(r) for r in rows]

    def ultimo_handoff(
        self, org_id: UUID, thread_id: UUID, *, para_agent_id: UUID | None = None
    ) -> HandoffRecord | None:
        q = self._t("thread_handoffs").select("*").eq("org_id", str(org_id)).eq("thread_id", str(thread_id))
        if para_agent_id is not None:
            q = q.eq("para_agent_id", str(para_agent_id))
        rows = q.order("created_at", desc=True).limit(1).execute().data or []
        return self._handoff(rows[0]) if rows else None

    def aceitar_handoff(self, org_id: UUID, handoff_id: UUID, user_id: UUID) -> HandoffRecord:
        # Conditional on `aceito_em IS NULL`: the first acceptance wins, a retry changes nothing.
        (
            self._t("thread_handoffs")
            .update({"aceito_em": utcnow_iso(), "aceito_por": str(user_id)})
            .eq("id", str(handoff_id)).eq("org_id", str(org_id)).is_("aceito_em", "null").execute()
        )
        found = self.get_handoff(org_id, handoff_id)
        if found is None:
            raise NotFound(f"handoff {handoff_id} not found")
        return found

    def marcar_turno(self, org_id: UUID, thread_id: UUID, agent_id: UUID) -> None:
        (
            self._t("thread_participantes").update({"ultimo_turno_em": utcnow_iso()})
            .eq("org_id", str(org_id)).eq("thread_id", str(thread_id)).eq("agent_id", str(agent_id))
            .execute()
        )

    def list_eventos(self, org_id: UUID, thread_id: UUID) -> list[ParticipanteEvento]:
        rows = (
            self._t("thread_participante_eventos").select("*")
            .eq("org_id", str(org_id)).eq("thread_id", str(thread_id))
            .order("created_at").limit(500).execute().data or []
        )
        return [self._evento_rec(r) for r in rows]

    def list_abertos(self, org_id: UUID, agent_id: UUID) -> list[ThreadAberto]:
        from noctusai_lib.integrations.persistence.paging import iter_paged_rows

        def _page(start: int, end: int):
            return (
                self._t("thread_participantes")
                .select("thread_id, agent_id, entrou_em, conversations!inner(ultima_mensagem_lead_em)")
                .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("estado", "ativo")
                .order("thread_id").range(start, end).execute().data
            )

        out = []
        # One active participation per (agent, thread): thread_id is unique within this result set.
        for r in iter_paged_rows(_page, id_key="thread_id", label="threads abertos"):
            conv = r.get("conversations") or {}
            out.append(ThreadAberto(
                thread_id=UUID(str(r["thread_id"])), agent_id=UUID(str(r["agent_id"])),
                entrou_em=r["entrou_em"], ultima_mensagem_lead_em=conv.get("ultima_mensagem_lead_em"),
            ))
        return out

    # skills
    def registrar_abertura_skill(self, org_id: UUID, thread_id: UUID, skill: str, compiled_hash: str) -> None:
        # The PK (thread, skill, hash) makes the second opening a no-op, not an error.
        self._t("thread_skill_aberturas").upsert(
            {"thread_id": str(thread_id), "org_id": str(org_id), "skill": skill, "compiled_hash": compiled_hash},
            on_conflict="thread_id,skill,compiled_hash", ignore_duplicates=True,
        ).execute()

    def skill_aberta(self, org_id: UUID, thread_id: UUID, skill: str, compiled_hash: str) -> bool:
        rows = (
            self._t("thread_skill_aberturas").select("thread_id")
            .eq("org_id", str(org_id)).eq("thread_id", str(thread_id))
            .eq("skill", skill).eq("compiled_hash", compiled_hash).limit(1).execute().data or []
        )
        return bool(rows)

    # row mappers
    @staticmethod
    def _lead(row: dict[str, Any]) -> LeadRefRecord:
        return LeadRefRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), produto=row["produto"],
            ref_externa=row["ref_externa"],
            crm_lead_id=UUID(str(row["crm_lead_id"])) if row.get("crm_lead_id") else None,
            contato=row.get("contato"), created_at=row["created_at"], updated_at=row["updated_at"],
            opt_in_em=row.get("opt_in_em"), opt_in_origem=row.get("opt_in_origem"), opt_out_em=row.get("opt_out_em"),
        )

    @staticmethod
    def _participante(row: dict[str, Any]) -> ParticipanteRecord:
        return ParticipanteRecord(
            thread_id=UUID(str(row["thread_id"])), agent_id=UUID(str(row["agent_id"])),
            org_id=UUID(str(row["org_id"])), estado=row.get("estado", "ativo"),
            entrou_em=row.get("entrou_em") or utcnow_iso(), saiu_em=row.get("saiu_em"),
            motivo=row.get("motivo"), ultimo_turno_em=row.get("ultimo_turno_em"),
            pausado_ate=row.get("pausado_ate"),
        )

    @staticmethod
    def _evento_rec(row: dict[str, Any]) -> ParticipanteEvento:
        return ParticipanteEvento(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), thread_id=UUID(str(row["thread_id"])),
            agent_id=UUID(str(row["agent_id"])), de=row.get("de"), para=row["para"],
            ator_tipo=row["ator_tipo"], ator_id=UUID(str(row["ator_id"])) if row.get("ator_id") else None,
            motivo=row.get("motivo"), created_at=row["created_at"], ate=row.get("ate"),
        )

    @staticmethod
    def _handoff(row: dict[str, Any]) -> HandoffRecord:
        def _u(v: Any) -> UUID | None:
            return UUID(str(v)) if v else None

        return HandoffRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), thread_id=UUID(str(row["thread_id"])),
            lead_ref_id=_u(row.get("lead_ref_id")), de_agent_id=UUID(str(row["de_agent_id"])),
            para=HandoffDestino(
                tipo=row["para_tipo"], agent_id=_u(row.get("para_agent_id")),
                user_id=_u(row.get("para_user_id")), papel=row.get("para_papel"),
            ),
            motivo_codigo=row["motivo_codigo"], resumo=row["resumo"], perfil=row.get("perfil") or {},
            identificacao_completa=bool(row.get("identificacao_completa")),
            identificacao_mascarada=row.get("identificacao_mascarada") or {},
            perguntas_abertas=list(row.get("perguntas_abertas") or []),
            compromissos=list(row.get("compromissos") or []), created_at=row["created_at"],
            aceito_em=row.get("aceito_em"), aceito_por=_u(row.get("aceito_por")),
        )


def get_thread_store(settings: Any) -> ThreadStore:
    """Real when a Supabase service-role key is configured, Fake otherwise — same
    signal as :func:`app.stores.agents.get_agent_store`."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeThreadStore()
    from app.database import get_admin_client

    return SupabaseThreadStore(get_admin_client())


# ── multi-agent history (contract §6.3) ─────────────────────────────────────

Origem = Literal["proprio", "lead", "outro_agente", "humano", "evento"]


@dataclass(frozen=True)
class HistoricoItem:
    """One message of a thread as ONE agent should read it."""

    origem: Origem
    texto: str
    created_at: datetime
    #: The AUTHOR agent's key / name (``outro_agente`` only).
    agent_key: str | None = None
    agent_nome: str | None = None
    autor_user_id: UUID | None = None


def mapa_agentes(studio_store: Any, org_id: UUID) -> dict[UUID, tuple[str, str]]:
    """``agent_id -> (key, nome)`` for every agent of the org — the name lookup the
    history needs to label another agent's lines."""
    return {a.id: (a.key, a.nome) for a in studio_store.list_agents(org_id)}


def historico_do_agente(
    messages: Any, agentes: Mapping[UUID, tuple[str, str]], org_id: UUID, thread_id: UUID,
    agent_id: UUID, *, limite: int,
) -> list[HistoricoItem]:
    """The last ``limite`` messages of the thread, classified for ``agent_id``:

    * its own ``assistant`` rows -> ``proprio`` (an unauthored legacy row — written
      before 033 stamped ``agent_id`` — is read as the thread opener's, i.e. own);
    * the lead's ``user`` rows -> ``lead``;
    * ANOTHER agent's ``assistant`` rows -> ``outro_agente`` (with its key / name);
    * ``humano`` / ``evento`` rows as such.

    ``system`` rows are route notices, never model input; empty assistant rows (the
    cost-booking rows of a silent turn) are skipped.
    """
    out: list[HistoricoItem] = []
    for r in messages.list(org_id, thread_id, limite=limite):
        if r.role == "user" and r.texto:
            out.append(HistoricoItem("lead", r.texto, r.created_at))
        elif r.role == "assistant" and r.texto and r.texto.strip():
            if r.agent_id is None or r.agent_id == agent_id:
                out.append(HistoricoItem("proprio", r.texto, r.created_at))
            else:
                key, nome = agentes.get(r.agent_id, (None, None))
                out.append(HistoricoItem("outro_agente", r.texto, r.created_at, agent_key=key, agent_nome=nome))
        elif r.role == "humano" and r.texto:
            out.append(HistoricoItem("humano", r.texto, r.created_at, autor_user_id=r.autor_user_id))
        elif r.role == "evento" and r.texto:
            out.append(HistoricoItem("evento", r.texto, r.created_at))
    return out


def rotular_historico(
    itens: Sequence[HistoricoItem], *, rotulo_agente: str | None, rotulo_humano: str | None,
    rotulo_evento: str | None,
) -> list[tuple[str, str]]:
    """Chat-history lines ``(role, texto)`` from classified items: own -> ``assistant``,
    the lead -> ``user``, everything else -> a ``user`` line prefixed by its label.

    The label TEMPLATES are content (D2) — the caller reads them from the agent
    version's textos (``historico.rotulo_agente`` ``"{nome}:"``, ``historico.rotulo_humano``,
    ``historico.rotulo_evento``); ``{nome}`` is the only placeholder. No default is
    substituted: an item that needs a label whose template is missing raises
    ``ValueError`` (the turn is refused, never answered with an invented prefix).
    """
    out: list[tuple[str, str]] = []
    for it in itens:
        if it.origem == "proprio":
            out.append(("assistant", it.texto))
        elif it.origem == "lead":
            out.append(("user", it.texto))
        else:
            template = {"outro_agente": rotulo_agente, "humano": rotulo_humano, "evento": rotulo_evento}[it.origem]
            if not template or not template.strip():
                raise ValueError(f"rotulo_ausente: historico.rotulo_{it.origem.replace('outro_', '')}")
            prefix = template.replace("{nome}", it.agent_nome or it.agent_key or "")
            out.append(("user", f"{prefix} {it.texto}"))
    return out


# ── per-agent context (dossier is the qualification slice's; this is the thread half) ──


@dataclass(frozen=True)
class ContextoThread:
    """What ONE agent needs from a thread: the last N messages (labelled by author), the newest
    hand-off addressed to it and its OWN tool activity — not the full history."""

    mensagens: list[HistoricoItem]
    #: The newest hand-off to this agent; falls back to the thread's newest hand-off when none was
    #: addressed to an agent (a hand-off to a human / role is context for whoever speaks next).
    handoff: HandoffRecord | None
    #: The tool-call blocks of this agent's OWN assistant messages in the window (its private
    #: scratchpad): another agent's tool traffic is never shown to it.
    blocos_proprios: list[dict[str, Any]]


def contexto_thread(
    messages: Any, threads: Any, agentes: Mapping[UUID, tuple[str, str]], org_id: UUID, thread_id: UUID,
    agent_id: UUID, *, n: int,
) -> ContextoThread:
    """The per-agent context of a thread (see :class:`ContextoThread`). ``n`` is the version's
    ``historico_mensagens``. A function over the stores (not a store method) because it joins the
    message store and the thread store."""
    janela = messages.list(org_id, thread_id, limite=n)
    proprios: list[dict[str, Any]] = []
    for r in janela:
        if r.role == "assistant" and (r.agent_id is None or r.agent_id == agent_id):
            proprios.extend(b for b in (r.blocks or []) if isinstance(b, dict))
    handoff = threads.ultimo_handoff(org_id, thread_id, para_agent_id=agent_id) or threads.ultimo_handoff(
        org_id, thread_id
    )
    return ContextoThread(
        mensagens=historico_do_agente(messages, agentes, org_id, thread_id, agent_id, limite=n),
        handoff=handoff,
        blocos_proprios=proprios,
    )
