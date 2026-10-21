"""Turn controls — the agent's ligado / drenando / desligado and the per-thread
pause, decided BEFORE anything is persisted or any model is called (Julia v2
contract §5, owner answers §0.3 Q3 / Q5).

Two layers:

* :func:`decidir` — a PURE function. Given the agent's mode, the thread, the
  agent's participant row, the trigger and "now" it returns a :class:`Decisao`: the
  response ``status``, whether the lead's inbound message is persisted into the
  shared thread, whether the model runs, and which state transition (if any) the
  decision implies. It implements EVERY row of the §5.2 decision table (exhaustively
  tested) and does no IO.
* :func:`aplicar_controles` — the service the channel turn route calls (A-RT, under
  the turn lock for an existing thread): reads the control + thread + participant
  FAIL CLOSED (any read failure -> :class:`ControleIndisponivel`, mapped to 503
  ``controle_indisponivel``: no reply is ever sent on an unreadable control), runs
  :func:`decidir`, creates the thread (``ligado`` + a brand-new lead) and applies the
  implied transition with a compare-and-set (a lost race re-reads and re-decides).

What the decision table does with the owner's rules:

* ``desligado`` replies to nobody; the lead's and the human attendant's messages are
  still appended to a thread that EXISTS (one end-to-end context, Q5) but a lead
  Julia never served is NEVER stored while off or draining;
* ``drenando`` keeps chatting in open threads and refuses new leads; an open thread
  idle for ``dreno_inatividade_dias`` (Q3, default 7) counts as closed — the
  participant moves to ``encerrado`` (``dreno_inativo``) and the message is only
  appended;
* a paused thread, a thread already handed to a broker (``concluido`` /
  ``transferido``) or owned by another agent is appended to, never answered;
* an ``encerrado`` participant is reopened by a new lead message while ``ligado``
  (``concluido`` / ``transferido`` never reopen: the broker owns the lead). The
  contract names "after >= 24 h" as the new-cycle mark; a lead who answers sooner
  than that is still answered (a conversation is not left unanswered because it
  ended minutes ago) and the decision says which case it is (``novo_ciclo``).
* re-engagement turns run only for an ``ativo`` participant while ``ligado`` /
  ``drenando`` (and, draining, only while the thread is not already idle past the
  drain window); anything else is ``reengajamento_ignorado`` — nothing is persisted.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Callable
from uuid import UUID

from app.stores._util import utcnow
from app.stores.agent_controles import DRENO_DIAS_PADRAO, MODOS
from app.stores.conversations import ConversationRecord
from app.stores.threads import LeadRefRecord, OutroAgenteAtivo, ParticipanteRecord

logger = logging.getLogger(__name__)

__all__ = [
    "CICLO_NOVO_APOS",
    "GATILHOS",
    "STATUS_AGENTE_DESLIGADO",
    "STATUS_CONTROLE_INDISPONIVEL",
    "STATUS_CONVERSA_COM_OUTRO_AGENTE",
    "STATUS_CONVERSA_COM_OUTRO_RESPONSAVEL",
    "STATUS_CONVERSA_PAUSADA",
    "STATUS_LEAD_OPT_OUT",
    "STATUS_NORMAL",
    "STATUS_NOVO_LEAD_LIMITADO",
    "STATUS_NOVO_LEAD_RECUSADO",
    "STATUS_REENGAJAMENTO_IGNORADO",
    "ControleIndisponivel",
    "ControleResultado",
    "Decisao",
    "LeadIdentidade",
    "ParticipanteView",
    "ThreadView",
    "Transicao",
    "aplicar_controles",
    "decidir",
]

GATILHOS = ("mensagem", "reengajamento")

#: ``Decisao.status`` values. ``normal`` is "the turn proceeds"; every other one is
#: the response ``status`` the turn route answers (nothing is sent to the lead).
STATUS_NORMAL = "normal"
STATUS_AGENTE_DESLIGADO = "agente_desligado"
STATUS_NOVO_LEAD_RECUSADO = "novo_lead_recusado"
#: The agent is on, but the new-lead admission limit (per hour / per day / the day's budget share) is spent:
#: SW routes the lead to a human queue, not to silence.
STATUS_NOVO_LEAD_LIMITADO = "novo_lead_limitado"
STATUS_CONVERSA_PAUSADA = "conversa_pausada"
STATUS_CONVERSA_COM_OUTRO_RESPONSAVEL = "conversa_com_outro_responsavel"
STATUS_CONVERSA_COM_OUTRO_AGENTE = "conversa_com_outro_agente"
STATUS_REENGAJAMENTO_IGNORADO = "reengajamento_ignorado"
STATUS_LEAD_OPT_OUT = "lead_opt_out"
STATUS_CONTROLE_INDISPONIVEL = "controle_indisponivel"

#: An ``encerrado`` participant whose lead writes again after this long starts a NEW cycle.
CICLO_NOVO_APOS = timedelta(hours=24)

_MOTIVO_DRENO_INATIVO = "dreno_inativo"
_MOTIVO_LEAD_VOLTOU = "lead_voltou"
_MOTIVO_NOVO_CICLO = "novo_ciclo"
_MOTIVO_NOVO_LEAD = "novo_lead"


class ControleIndisponivel(Exception):
    """The control (mode / thread / participant) could not be read or settled. The turn
    route answers 503 ``controle_indisponivel`` and sends nothing (fail closed)."""

    status_code = 503
    code = STATUS_CONTROLE_INDISPONIVEL
    detail = "Não foi possível verificar o controle do agente."

    def as_http_exception(self):
        """The ``HTTPException`` in agents' flat error shape (lazy import: this module stays pure)."""
        from fastapi import HTTPException

        return HTTPException(status_code=self.status_code, detail={"detail": self.detail, "code": self.code})


@dataclass(frozen=True)
class ParticipanteView:
    """The agent's own participant row, as the decision needs it."""

    estado: str
    entrou_em: datetime
    saiu_em: datetime | None = None
    #: A timed pause: past this instant a ``pausado`` participant counts as ``ativo`` again.
    pausado_ate: datetime | None = None


@dataclass(frozen=True)
class ThreadView:
    """The thread, as the decision needs it."""

    #: The last LEAD message (``None`` when the lead never wrote).
    ultima_mensagem_lead_em: datetime | None = None
    #: Another agent (not the one deciding) is the ACTIVE participant.
    outro_agente_ativo: bool = False
    #: The lead asked to stop (``parar``) and has not opted in again: no agent talks to them.
    lead_opt_out: bool = False


@dataclass(frozen=True)
class Transicao:
    """A participant state change a decision implies (applied by :func:`aplicar_controles`)."""

    de: tuple[str, ...]
    para: str
    motivo: str
    ator_tipo: str = "sistema"


@dataclass(frozen=True)
class Decisao:
    status: str
    #: Append the lead's inbound message(s) to the shared thread.
    persistir_inbound: bool
    #: Run the model (the turn proceeds).
    executar_llm: bool
    #: Create the thread + the active participant first (``ligado`` + a lead never served).
    criar_thread: bool = False
    transicao: Transicao | None = None
    #: A reopened ``encerrado`` thread whose lead came back after >= 24 h (a new cycle).
    novo_ciclo: bool = False
    http_status: int = 200

    @property
    def normal(self) -> bool:
        return self.status == STATUS_NORMAL


def _recusa(status: str, *, persistir: bool, transicao: Transicao | None = None) -> Decisao:
    return Decisao(status=status, persistir_inbound=persistir, executar_llm=False, transicao=transicao)


def _ociosa(thread: ThreadView, participante: ParticipanteView, agora: datetime, dias: int) -> bool:
    """The drain clock: the thread's last LEAD message (the participant's entry when the lead
    never wrote) is ``dias`` days old or older."""
    desde = thread.ultima_mensagem_lead_em or participante.entrou_em
    return agora - desde >= timedelta(days=dias)


def decidir(
    modo: str | None,
    thread: ThreadView | None,
    participante: ParticipanteView | None,
    gatilho: str,
    agora: datetime,
    *,
    dreno_inatividade_dias: int = DRENO_DIAS_PADRAO,
) -> Decisao:
    """The §5.2 decision table (see the module docstring). Pure.

    ``modo`` not one of :data:`MODOS` (the control could not be read) -> 503
    ``controle_indisponivel``: fail closed, whatever the trigger. ``participante`` is the deciding
    agent's own row in ``thread`` (``None`` when it never took part).
    """
    if gatilho not in GATILHOS:
        raise ValueError(f"gatilho must be one of {GATILHOS}; got {gatilho!r}")
    if modo not in MODOS:
        return Decisao(
            status=STATUS_CONTROLE_INDISPONIVEL, persistir_inbound=False, executar_llm=False, http_status=503
        )

    # ── the lead withdrew consent: nobody answers, nobody follows up (an existing thread still records) ──
    if thread is not None and thread.lead_opt_out:
        return _recusa(
            STATUS_REENGAJAMENTO_IGNORADO if gatilho == "reengajamento" else STATUS_LEAD_OPT_OUT,
            persistir=gatilho == "mensagem",
        )

    # ── a timed pause that has run out: the participant is active again ──
    if (
        participante is not None and participante.estado == "pausado"
        and participante.pausado_ate is not None and agora >= participante.pausado_ate
    ):
        d = decidir(
            modo, thread, ParticipanteView("ativo", participante.entrou_em, participante.saiu_em),
            gatilho, agora, dreno_inatividade_dias=dreno_inatividade_dias,
        )
        if d.transicao is not None:  # e.g. the drain closes it: the row is still `pausado` in the database
            return replace(d, transicao=replace(d.transicao, de=("pausado",)))
        if d.executar_llm:
            return replace(d, transicao=Transicao(de=("pausado",), para="ativo", motivo="pausa_expirada"))
        return d

    # ── re-engagement: only an active participant, only while on / draining ──
    if gatilho == "reengajamento":
        if modo == "desligado" or thread is None or participante is None or participante.estado != "ativo":
            return _recusa(STATUS_REENGAJAMENTO_IGNORADO, persistir=False)
        if modo == "drenando" and _ociosa(thread, participante, agora, dreno_inatividade_dias):
            return _recusa(STATUS_REENGAJAMENTO_IGNORADO, persistir=False)
        return Decisao(status=STATUS_NORMAL, persistir_inbound=False, executar_llm=True)

    # ── a lead message ──
    if modo == "desligado":
        # Off replies to nobody. A thread that exists still receives the message (one context, Q5);
        # a lead never served is not stored.
        return _recusa(STATUS_AGENTE_DESLIGADO, persistir=thread is not None)

    if thread is None:
        if modo == "drenando":
            return _recusa(STATUS_NOVO_LEAD_RECUSADO, persistir=False)
        return Decisao(status=STATUS_NORMAL, persistir_inbound=True, executar_llm=True, criar_thread=True)

    if participante is None or participante.estado != "ativo":
        if thread.outro_agente_ativo:
            return _recusa(STATUS_CONVERSA_COM_OUTRO_AGENTE, persistir=True)

    if participante is None:
        if modo == "drenando":
            return _recusa(STATUS_NOVO_LEAD_RECUSADO, persistir=False)
        # The thread belongs to other agents that are done with it (the broker owns the lead).
        return _recusa(STATUS_CONVERSA_COM_OUTRO_RESPONSAVEL, persistir=True)

    estado = participante.estado
    if estado == "pausado":
        return _recusa(STATUS_CONVERSA_PAUSADA, persistir=True)
    if estado in ("concluido", "transferido"):
        return _recusa(STATUS_CONVERSA_COM_OUTRO_RESPONSAVEL, persistir=True)
    if estado == "encerrado":
        if modo == "drenando":
            return _recusa(STATUS_NOVO_LEAD_RECUSADO, persistir=True)
        novo_ciclo = participante.saiu_em is None or agora - participante.saiu_em >= CICLO_NOVO_APOS
        return Decisao(
            status=STATUS_NORMAL, persistir_inbound=True, executar_llm=True, novo_ciclo=novo_ciclo,
            transicao=Transicao(
                de=("encerrado",), para="ativo",
                motivo=_MOTIVO_NOVO_CICLO if novo_ciclo else _MOTIVO_LEAD_VOLTOU,
            ),
        )
    if estado == "ativo":
        if modo == "drenando" and _ociosa(thread, participante, agora, dreno_inatividade_dias):
            return _recusa(
                STATUS_NOVO_LEAD_RECUSADO, persistir=True,
                transicao=Transicao(de=("ativo",), para="encerrado", motivo=_MOTIVO_DRENO_INATIVO),
            )
        return Decisao(status=STATUS_NORMAL, persistir_inbound=True, executar_llm=True)
    raise ValueError(f"unknown participant estado {estado!r}")


# ── the service the turn route calls ────────────────────────────────────────


@dataclass(frozen=True)
class LeadIdentidade:
    """Who the lead is (the turn request's ``lead`` + ``contact``)."""

    #: SW ``julia_contatos.id`` — the authoritative lead identity.
    ref: str
    crm_lead_id: UUID | None = None
    #: ``{nome, telefone_e164}`` — stored on the lead_ref (personal data, 180-day retention).
    contato: dict[str, Any] | None = None


@dataclass(frozen=True)
class ControleResultado:
    decisao: Decisao
    modo: str
    #: The thread AFTER the decision was applied (created for a new lead). ``None`` when the
    #: lead has no thread (refused while off / draining).
    thread: ConversationRecord | None
    #: The deciding agent's participant row after the decision was applied.
    participante: ParticipanteRecord | None
    lead_ref: LeadRefRecord | None

    @property
    def status(self) -> str:
        return self.decisao.status

    @property
    def prosseguir(self) -> bool:
        """The turn proceeds (persist the inbound batch, run the model)."""
        return self.decisao.normal


_MAX_TENTATIVAS = 3


def aplicar_controles(
    *,
    org_id: UUID,
    agent_id: UUID,
    gatilho: str,
    channel: str,
    channel_ref: dict[str, Any],
    controles: Any,
    conversations: Any,
    threads: Any,
    lead: LeadIdentidade | None = None,
    contact: dict[str, Any] | None = None,
    version_id: UUID | None = None,
    messages: Any = None,
    agora: datetime | None = None,
    admitir_novo_lead: Callable[[], bool] | None = None,
) -> ControleResultado:
    """Read the controls, decide, and apply what the decision implies.

    The channel turn route calls this BEFORE persisting the inbound batch or calling the model
    (A-RT; for an existing thread, under the turn lock — the participant transitions are
    compare-and-set, so a call without the lock is safe too, just not serialised with the turn).
    The caller then:

    * ``resultado.status == "normal"`` -> persist the batch (``decisao.persistir_inbound``) and run
      the model;
    * any other status -> persist the batch iff ``decisao.persistir_inbound`` (into
      ``resultado.thread``; use :func:`app.channels.thread_service.anexar_mensagens`) and answer the
      status without a reply;
    * :class:`ControleIndisponivel` -> 503, nothing persisted, nothing sent.

    ``controles`` is an ``AgentControleStore``, ``conversations`` a ``ConversationStore`` (channel
    half), ``threads`` a ``ThreadStore``; ``messages`` (a ``MessageStore``) is only needed to stamp
    ``lead_ref_id`` on the messages of a thread linked lazily. ``admitir_novo_lead`` is the new-lead admission
    gate (guardrails B5, :mod:`app.channels.admissao`): consulted ONLY when the decision would open a thread for a
    lead never served; ``False`` -> ``novo_lead_limitado``, nothing stored. A gate that raises fails closed
    (:class:`ControleIndisponivel`). ``lead`` is the turn's ``lead``
    block: it creates / refreshes the ``lead_refs`` row and links a thread that has none yet.
    """
    agora = agora or utcnow()
    for _ in range(_MAX_TENTATIVAS):
        # 1. READ — fail closed: an unreadable control never becomes a reply.
        try:
            controle = controles.get(org_id, agent_id)
            thread = conversations.find_thread(org_id, channel, channel_ref)
            participantes = threads.list_participantes(org_id, thread.id) if thread is not None else []
            lead_atual = (
                threads.get_lead_ref(org_id, thread.lead_ref_id)
                if thread is not None and thread.lead_ref_id is not None else None
            )
        except Exception as exc:
            logger.exception(
                "agents.controles.read_failed org_id=%s agent_id=%s cause=%s", org_id, agent_id, type(exc).__name__
            )
            raise ControleIndisponivel() from exc

        propria = next((p for p in participantes if p.agent_id == agent_id), None)
        decisao = decidir(
            controle.modo,
            ThreadView(
                ultima_mensagem_lead_em=thread.ultima_mensagem_lead_em,
                outro_agente_ativo=any(p.agent_id != agent_id and p.estado == "ativo" for p in participantes),
                lead_opt_out=bool(lead_atual is not None and lead_atual.opt_out_ativo),
            ) if thread is not None else None,
            ParticipanteView(propria.estado, propria.entrou_em, propria.saiu_em, propria.pausado_ate)
            if propria is not None else None,
            gatilho,
            agora,
            dreno_inatividade_dias=controle.dreno_inatividade_dias,
        )
        if decisao.http_status == 503:
            raise ControleIndisponivel()
        if decisao.criar_thread and admitir_novo_lead is not None:
            try:
                admitido = admitir_novo_lead()
            except Exception as exc:
                logger.exception("agents.controles.admissao_failed org_id=%s cause=%s", org_id, type(exc).__name__)
                raise ControleIndisponivel() from exc
            if not admitido:
                return ControleResultado(
                    decisao=_recusa(STATUS_NOVO_LEAD_LIMITADO, persistir=False), modo=controle.modo,
                    thread=None, participante=None, lead_ref=None)

        # 2. APPLY.
        lead_ref = None
        if lead is not None and (decisao.criar_thread or thread is not None):
            lead_ref = threads.upsert_lead_ref(
                org_id, lead.ref, crm_lead_id=lead.crm_lead_id, contato=lead.contato
            )

        if decisao.criar_thread:
            thread = conversations.create_channel(
                org_id, agent_id, channel, channel_ref, contact, version_id=version_id,
                lead_ref_id=lead_ref.id if lead_ref is not None else None,
            )
            try:
                propria = threads.add_participante(
                    org_id, thread.id, agent_id, motivo=_MOTIVO_NOVO_LEAD, ator_tipo="sistema"
                )
            except OutroAgenteAtivo:
                # Two agents raced to open the same thread: re-read and let the table decide.
                logger.info("agents.controles.open_race org_id=%s agent_id=%s", org_id, agent_id)
                continue
        elif decisao.transicao is not None and thread is not None:
            moved = threads.transicionar(
                org_id, thread.id, agent_id, de=decisao.transicao.de, para=decisao.transicao.para,
                ator_tipo=decisao.transicao.ator_tipo, motivo=decisao.transicao.motivo,
            )
            if not moved:
                continue  # somebody else moved the participant first: re-read, re-decide
            propria = threads.get_participante(org_id, thread.id, agent_id)

        # A thread that predates the lead_refs (or whose link has not run yet) links lazily.
        if thread is not None and lead_ref is not None and thread.lead_ref_id is None:
            thread = conversations.link_lead_ref(org_id, thread.id, lead_ref.id)
            if messages is not None:
                messages.link_thread_lead(org_id, thread.id, lead_ref.id)

        return ControleResultado(
            decisao=decisao, modo=controle.modo, thread=thread, participante=propria, lead_ref=lead_ref
        )

    logger.error("agents.controles.state_race org_id=%s agent_id=%s", org_id, agent_id)
    raise ControleIndisponivel()
