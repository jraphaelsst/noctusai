"""`AgentsClient` -- social-wiring's client of the `agents` product's channel API.

Contract: products/social-wiring/projects/julia/specs/julia-agent-contract.md
  section 3.1  POST /api/channels/turns                 -> `run_turn`
  section 3.2  GET  /api/channels/agents/{key}/status   -> `agent_status`
  section 10.1 M5  deletion on request                  -> `delete_conversation_data`
Lais build contract (lais-build-contract.md) 2.1:
  (a) `contexto` rides in the turn request; (d) the response carries action objects
  (`JuliaAction`); (e) POST /api/channels/conversations/{id}/resumo -> `resumo`;
  (f) PUT /api/channels/ferramentas-token -> `put_ferramentas_token`.
Owner 2026-10-19: POST /api/channels/agents/{key}/decisoes/{chave} -> `decidir` (a choice decided by the rule the
  owner keeps in the agent's prompt section `decisao-<chave>`; `regra_padrao` applies while that section is absent).

Fake + Real + factory (KB § PATTERNS/backend/seed-fake-real-adapter.md):
  * `AgentsClient`      -- the Protocol the lead path depends on;
  * `FakeAgentsClient`  -- scripted replies, deterministic, records every call;
  * `HttpAgentsClient`  -- the real one, base URL + per-org token;
  * `make_agents_client`-- the pure factory (token/base_url/dev decision in, client out).

Every row of the section 3.1 error table maps to ONE typed exception below, so
the lead path decides what to do from the TYPE, never from a status code or a
message string. The lead never sees any of this (L2): errors end in "no reply".

Deletion wire (shipped by A2): DELETE /api/channels/conversations, JSON body, 204.

Julia v2 (products/agents/projects/julia-v2/CONTRACT.md section 8): Julia is HOSTED in agents and SW consumes her
through this client ONLY. The turn request carries the lead identity + the closed `contexto.estado` data (never
prompt text); the response carries the thread id, the participant state, the computed qualification and typed actions;
the shared-thread API (append without a turn, per-conversation pause, hand-offs, consent, LGPD delete-by-lead, the
controls read, the computed qualification) is here too. SW NEVER gates on a cached copy of any of it (fail closed).
The wire is validated against `products/agents/backend/contracts/channels.v2.json` in
`tests/services/test_agents_contract_v2.py` once agents publishes it.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol, Sequence, Union, runtime_checkable

import httpx
from noctusai_lib.integrations.agents import (  # shared taxonomy + transport live in the seed (KB § INTEGRATIONS/agents-org-specs.md)
    DEFAULT_RETRY_AFTER_S,
    DEFAULT_TIMEOUT_S,
    AgentNotFound,
    AgentsBadRequest,
    AgentsClientError,
    AgentsHttpTransport,
    AgentsNotConfigured,
    AgentsTimeout,
    AgentsTokenInvalid,
    AgentsUpstreamError,
)
from noctusai_lib.integrations.agents import error_code as _error_code
from noctusai_lib.integrations.agents import need as _need
from noctusai_lib.integrations.agents import opt_str as _opt_str
from noctusai_lib.integrations.agents import retry_after as _retry_after
from noctusai_lib.primitives.not_configured import IntegrationNotConfigured
from urllib.parse import quote

logger = logging.getLogger(__name__)


#: Hard shape limits of section 3.1 -- the lead path trims to these BEFORE the call.
MAX_BATCH_MESSAGES = 20
MAX_MESSAGE_CHARS = 2000  # agents' MESSAGE_MAX_CHARS (GUARDRAILS B5): it truncates, SW trims first so the cut is SW's and visible


# ── wire types ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class TurnMessage:
    texto: str
    provider_message_id: str
    at: datetime
    #: Media the lead sent, STRUCTURED (GUARDRAILS B2): `{tipo: audio|imagem|video|documento, texto_extraido <= 2000, legenda?}`.
    #: The extraction NEVER rides inside `texto` (a typed "[Audio transcrito] ..." is just lead text). `texto` may be empty when
    #: `midia` is set. None = a plain text message.
    midia: Optional[dict[str, Any]] = None


#: `gatilho` of a turn: a lead message, or a re-engagement the SW timers fire (no lead message).
GATILHO_MENSAGEM = "mensagem"
GATILHO_REENGAJAMENTO = "reengajamento"
GATILHOS = (GATILHO_MENSAGEM, GATILHO_REENGAJAMENTO)


@dataclass(frozen=True)
class TurnRequest:
    agent_key: str
    connection_id: str
    chat_id: str
    messages: tuple[TurnMessage, ...]
    phone_e164: Optional[str] = None
    display_name: Optional[str] = None
    channel: str = "whatsapp"
    #: The per-turn DATA context SW renders (`julia_contexto_service.montar`): `hash`, `agora`, `fuso`, `estado`
    #: (closed, typed -- agents owns the schema; the re-engagement flavour rides in it) and `capacidades`. NEVER prompt
    #: text. None = key omitted.
    contexto: Optional[dict[str, Any]] = None
    #: julia-v2: the lead identity. `lead_ref` = `julia_contatos.id` (SW is authoritative); `crm_lead_id` = `leads.id`
    #: once the CRM lead exists.
    lead_ref: Optional[str] = None
    crm_lead_id: Optional[str] = None
    #: `mensagem` (>= 1 message) or `reengajamento` (no lead message; needs a `contexto`, whose `estado.reengajamento`
    #: names the flow).
    gatilho: str = GATILHO_MENSAGEM

    def to_wire(self) -> dict[str, Any]:
        wire = self._base_wire()
        if self.lead_ref:
            wire["lead"] = {"ref": self.lead_ref, "crm_lead_id": self.crm_lead_id}
        if self.contexto is not None:
            wire["contexto"] = self.contexto
        return wire

    def _base_wire(self) -> dict[str, Any]:
        wire: dict[str, Any] = {
            "agent_key": self.agent_key,
            "channel": self.channel,
            "channel_ref": {"connection_id": self.connection_id, "chat_id": self.chat_id},
            "contact": {"phone_e164": self.phone_e164, "display_name": self.display_name},
            "gatilho": self.gatilho,
            "messages": [
                _mensagem_wire(m)
                for m in self.messages
            ],
        }
        return wire


def _mensagem_wire(m: "TurnMessage") -> dict[str, Any]:
    out: dict[str, Any] = {"texto": m.texto, "provider_message_id": m.provider_message_id, "at": m.at.isoformat()}
    if m.midia:
        out["midia"] = dict(m.midia)
    return out


@dataclass(frozen=True)
class HandoffAction:
    motivo: str
    type: str = "handoff"
    #: The typed reason code (agents enum, labels live in agents' DB). None from an older agents build.
    motivo_codigo: Optional[str] = None
    seq: int = 0


@dataclass(frozen=True)
class JuliaAction:
    """One of the non-handoff action shapes of the turn response (`lead_pronto`, `intencao_visita`, `captacao`,
    `encerrar`, `consentimento_credito`, ...). `payload` is the action object minus `type`/`seq`. An UNKNOWN type is
    kept (not dropped): the apply service answers it with an `acao_sem_handler` event so a newer agents build never
    loses data silently."""

    type: str
    seq: int
    payload: dict[str, Any] = field(default_factory=dict)


Action = Union[HandoffAction, JuliaAction]

#: The `status` values of a turn response (julia-v2 section 8.1 + the controls decision table, section 5.2).
STATUS_RESPONDEU = ("respondido", "silencio", "handoff", "encerrado", "concluido")
#: Nothing is sent to the lead and no action is applied: agents decided NOT to serve this message.
STATUS_SEM_ATENDIMENTO = (
    "agente_desligado", "novo_lead_recusado", "conversa_pausada", "conversa_com_outro_responsavel",
    "conversa_com_outro_agente", "controle_indisponivel", "lead_opt_out", "reengajamento_ignorado", "limite_atingido",
    "limite_taxa", "novo_lead_limitado", "loop_detectado",
)
#: The not-served statuses that mean "a LIMIT stopped a real person": never silence -- SW routes each to a human
#: (`julia_lead_turn_service._encaminhar_limite`). `limite_taxa` = per-lead rate limit; `novo_lead_limitado` = the
#: per-agent new-lead admission cap (agents stored NOTHING, thread null); `loop_detectado` = a flood/echo loop (agents
#: paused the participant and handed off `seguranca`).
STATUS_LIMITE_PARA_HUMANO = ("limite_taxa", "novo_lead_limitado", "loop_detectado")
STATUS_TURNO = STATUS_RESPONDEU + STATUS_SEM_ATENDIMENTO

#: Who triggered a lead-level opt-out (agents' `origem`): the agent itself on the lead's request, a human operator,
#: or an integration (the default when SW does not say).
ORIGENS_OPT_OUT = ("agente", "operador", "integracao")
ORIGEM_OPT_OUT_PADRAO = "integracao"
OPT_OUT_MOTIVO_MAX = 500
OPT_OUT_MENSAGEM_MAX = 1000
#: `encerrar.motivo` agents sends when the lead asked to stop being contacted; with `lead_opt_out: true` it means
#: agents ALREADY recorded the opt-out (SW must not call opt-out again, and stops every follow-up of that lead).
MOTIVO_ENCERRAR_PEDIU_PARAR = "lead_pediu_parar"


@dataclass(frozen=True)
class QualificacaoResumo:
    """`qualificacao` of a turn response: the stage/score agents COMPUTED (never judged). `estagios` is the ordered
    list of the pinned standard's stage keys when agents sends it (an older build does not)."""

    versao: Optional[str] = None
    estagio: Optional[str] = None
    score: Optional[int] = None
    faltando: tuple[str, ...] = ()
    estagios: tuple[str, ...] = ()


@dataclass(frozen=True)
class TurnResult:
    conversation_id: str
    partes: tuple[str, ...]
    status: str  # one of `STATUS_TURNO`
    actions: tuple[Action, ...] = ()
    custo_usd: Optional[float] = None
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None
    #: julia-v2: the shared lead thread (== `conversation_id`, an alias for one release); None when agents stored
    #: nothing (a lead it refused to serve).
    thread_id: Optional[str] = None
    #: The Julia participant state after the turn: ativo | pausado | concluido | encerrado | transferido.
    participante_estado: Optional[str] = None
    qualificacao: Optional[QualificacaoResumo] = None
    #: Conformance violations agents recorded for this turn (`{regra, politica}` only).
    conformidade: tuple[dict[str, Any], ...] = ()

    @property
    def handoff(self) -> Optional[HandoffAction]:
        return next((a for a in self.actions if isinstance(a, HandoffAction)), None)

    @property
    def julia_actions(self) -> tuple[JuliaAction, ...]:
        """The non-handoff actions, in `seq` order (ties keep arrival order)."""
        return tuple(sorted((a for a in self.actions if isinstance(a, JuliaAction)), key=lambda a: a.seq))

    @property
    def thread(self) -> Optional[str]:
        return self.thread_id or self.conversation_id or None

    @property
    def atendeu(self) -> bool:
        """True when agents served the turn (a reply, a deliberate silence, or a terminal action)."""
        return self.status in STATUS_RESPONDEU


@dataclass(frozen=True)
class AgentStatus:
    agent_key: str
    nome: str
    ativo: bool
    versao_ativa: Optional[int]
    provider: Optional[str]
    model: Optional[str]
    llm_configurado: bool
    #: julia-v2 section 8.2: the controls summary (None from an older agents build).
    modo: Optional[str] = None
    aceita_novos_leads: Optional[bool] = None
    threads_abertas: Optional[int] = None
    conteudo_completo: Optional[bool] = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "agent_key": self.agent_key,
            "nome": self.nome,
            "ativo": self.ativo,
            "versao_ativa": self.versao_ativa,
            "provider": self.provider,
            "model": self.model,
            "llm_configurado": self.llm_configurado,
        }
        # the controls summary is shown only when this agents build sends it (an older one does not)
        for k in ("modo", "aceita_novos_leads", "threads_abertas", "conteudo_completo"):
            if getattr(self, k) is not None:
                out[k] = getattr(self, k)
        return out


@dataclass(frozen=True)
class AgentUso:
    """`GET /api/channels/uso?mes=YYYY-MM`: the org's channel turns + cost for the month and
    its per-day cost cap (the Painel "Consumo do plano")."""

    turnos: int
    custo_usd: float
    limite_diario_usd: float


@dataclass(frozen=True)
class DeletionRequest:
    agent_key: str
    connection_id: str
    chat_id: str


@dataclass(frozen=True)
class DeletionResult:
    """`deleted` is False when agents had nothing for that chat (not an error)."""

    deleted: bool
    messages_deleted: int = 0


@dataclass(frozen=True)
class ResumoRequest:
    """The window to summarise (julia-v2: the resumo is NARRATIVE only; the criteria come from agents' records)."""

    perguntas: tuple[dict[str, Any], ...] = ()  # legacy, no longer sent
    desde: Optional[datetime] = None

    def to_wire(self) -> dict[str, Any]:
        return {"desde": self.desde.isoformat() if self.desde else None}


@dataclass(frozen=True)
class ResumoResult:
    resumo: str
    slots: dict[str, str] = field(default_factory=dict)  # legacy: v2 resumo carries no slots
    operacao: Optional[str] = None
    intencoes: tuple[str, ...] = ()
    #: DISPLAY-ONLY (`desfecho_sugerido`): SW never acts on it.
    desfecho: str = "em_andamento"
    custo_usd: Optional[float] = None
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None


@dataclass(frozen=True)
class DecisaoRequest:
    """julia-v2 D13: the rule lives in agents' DB (`agent_version_decisoes`); SW sends the options and the data ONLY."""

    opcoes: tuple[str, ...]
    dados: dict[str, Any] = field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        return {"opcoes": list(self.opcoes), "dados": dict(self.dados)}


@dataclass(frozen=True)
class DecisaoResult:
    escolha: str
    motivo: str = ""
    #: `versao` = the published version's rule decided; `padrao_da_versao` = the option flagged `padrao` in the row.
    regra: str = "versao"
    custo_usd: Optional[float] = None


# ── the shared thread, hand-offs, consent, controls, qualification (julia-v2 section 8.2) ────────────────
@dataclass(frozen=True)
class ParticipanteInfo:
    agent_key: str
    estado: str
    agent_nome: Optional[str] = None
    pausado_ate: Optional[str] = None
    motivo: Optional[str] = None


@dataclass(frozen=True)
class HandoffRecord:
    """The hand-off note agents recorded (profile + atendimento summary + MASKED identity). `identificacao_mascarada`
    holds masked fields only -- the raw documents never leave agents' encrypted identity store."""

    id: str
    thread_id: str
    de_agent_key: str
    para: dict[str, Any]
    motivo_codigo: str
    resumo: str
    perfil: dict[str, Any] = field(default_factory=dict)
    identificacao_completa: bool = False
    identificacao_mascarada: dict[str, Any] = field(default_factory=dict)
    perguntas_abertas: tuple[Any, ...] = ()
    compromissos: tuple[Any, ...] = ()
    lead_ref: Optional[str] = None
    aceito_em: Optional[str] = None
    aceito_por: Optional[str] = None


@dataclass(frozen=True)
class ThreadInfo:
    thread_id: str
    channel: str = "whatsapp"
    lead_ref: Optional[str] = None
    participantes: tuple[ParticipanteInfo, ...] = ()
    ultimo_turno_em: Optional[str] = None
    ultima_mensagem_lead_em: Optional[str] = None
    opt_out_em: Optional[str] = None
    reengajamento_suprimido: bool = False
    reengajamento_suprimido_motivo: Optional[str] = None
    ultimo_handoff: Optional[HandoffRecord] = None

    def estado_de(self, agent_key: str) -> Optional[str]:
        return next((p.estado for p in self.participantes if p.agent_key == agent_key), None)

    def pausado(self, agent_key: str, agora: Optional[datetime] = None) -> bool:
        """Is `agent_key` paused RIGHT NOW? A timed pause (`pausado_ate`) that already ran out counts as active, exactly as
        agents decides it."""
        for p in self.participantes:
            if p.agent_key != agent_key or p.estado != "pausado":
                continue
            if not p.pausado_ate:
                return True
            try:
                ate = datetime.fromisoformat(p.pausado_ate.replace("Z", "+00:00"))
            except ValueError:
                return True
            if ate.tzinfo is None:
                ate = ate.replace(tzinfo=timezone.utc)
            return (agora or datetime.now(timezone.utc)) < ate
        return False


@dataclass(frozen=True)
class AppendResult:
    message_id: Optional[str]
    #: True when the `provider_message_id` was already in agents' ledger (a retry): nothing appended.
    duplicado: bool = False


@dataclass(frozen=True)
class ConsentInfo:
    lead_ref: str
    opt_in_em: Optional[str] = None
    opt_in_origem: Optional[str] = None
    opt_out_em: Optional[str] = None
    opt_out_ativo: bool = False
    participantes_encerrados: int = 0
    #: The id of the opt-out EVENT agents recorded (who/why/how); None from an older agents build or for opt-in.
    evento_id: Optional[str] = None
    #: The WHY of the active opt-out (the GET carries the event object); what an operator is shown before writing.
    opt_out_motivo: Optional[str] = None
    opt_out_origem: Optional[str] = None


#: `tipo` of an opt-out history record: the lead asked to stop / an authorised human put the lead back.
TIPOS_OPT_OUT_EVENTO = ("opt_out", "reativacao")
NOTIFICACAO_STATUS = ("pendente", "enviada", "falhou")
REATIVACAO_MOTIVO_MAX = 500


@dataclass(frozen=True)
class OptOutEvento:
    """One record of agents' lead opt-out history (`GET /api/channels/opt-outs`): WHO/WHY/WHEN of an opt-out or of a
    reactivation, and whether the org admins' in-app notice reached them."""

    id: str
    tipo: str
    lead_ref: str
    em: Optional[str] = None
    lead_nome: Optional[str] = None
    lead_telefone: Optional[str] = None
    thread_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_key: Optional[str] = None
    agent_nome: Optional[str] = None
    ator_user_id: Optional[str] = None
    origem: Optional[str] = None
    motivo: Optional[str] = None
    mensagem_lead: Optional[str] = None
    participantes_encerrados: int = 0
    notificacao_status: str = "pendente"
    notificacao_erro: Optional[str] = None
    notificado_em: Optional[str] = None


@dataclass(frozen=True)
class OptOutPagina:
    items: tuple[OptOutEvento, ...] = ()
    next_cursor: Optional[str] = None


@dataclass(frozen=True)
class ReativacaoResult:
    consent: ConsentInfo
    evento: Optional[OptOutEvento] = None


@dataclass(frozen=True)
class ControleInfo:
    agent_key: str
    modo: str  # ligado | drenando | desligado
    aceita_novos_leads: bool
    dreno_inatividade_dias: int = 7
    threads_abertas: int = 0
    drenagem: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QualificacaoEstado:
    """`GET /api/channels/leads/{ref}/qualificacao`: the full computed state (stage, score, recorded values). Never
    weights, rule bodies or identity values."""

    lead_ref: str
    estagio: Optional[str]
    score: Optional[int]
    valores: dict[str, Any] = field(default_factory=dict)
    faltando: tuple[str, ...] = ()
    pode_ofertar: bool = False
    pode_concluir: bool = False
    scores: dict[str, int] = field(default_factory=dict)
    eventos_imovel: tuple[dict[str, Any], ...] = ()
    estagios: tuple[str, ...] = ()
    versao_id: Optional[str] = None
    hash: Optional[str] = None


@dataclass(frozen=True)
class EstagioInfo:
    """One qualification stage as agents reports it (`GET /api/channels/agents/{key}/qualificacao/estagios`):
    `ordem` is the comparable position ("stage >= estagio_minimo" uses it); `conclusivo` marks a stage that may
    conclude. Labels are the org's own words (a DB row on the agents side), never a rule or a prompt."""

    chave: str
    rotulo: str
    ordem: int
    conclusivo: bool = False


# ── typed errors (one per row of the section 3.1 error table) ───────────────


class ConversationNotFound(AgentsClientError):
    """404 conversation_not_found / thread_not_found (the `resumo` and thread routes)."""


class ThreadNotFound(ConversationNotFound):
    """404 thread_not_found: agents has no thread for that id / channel ref / lead (not an error to the caller)."""


class HandoffNotFound(AgentsClientError):
    """404 handoff_not_found."""


class LeadDesconhecido(AgentsClientError):
    """`GET /api/channels/leads/{ref}/consentimento` 404 `lead_desconhecido`: agents has never seen the lead (the
    opt-out POST always registers the lead, so an unknown lead has never opted out)."""


class SemOptOutAtivo(AgentsClientError):
    """409 `sem_opt_out_ativo`: the lead has no active opt-out to lift."""


class OptOutEventoNotFound(AgentsClientError):
    """404 on `POST /opt-outs/{id}/notificar`: agents has no such opt-out record."""


class ParticipanteNotFound(AgentsClientError):
    """404 participante_not_found: the agent does not take part in the thread."""


class LeadSemQualificacao(AgentsClientError):
    """404 lead_sem_qualificacao / lead_sem_identificacao: nothing recorded for the lead yet."""


class TransicaoInvalida(AgentsClientError):
    """409 transicao_invalida / outro_agente_ativo: the requested participant state is not reachable."""


class AgentUnavailable(AgentsClientError):
    """409 agent_inactive / no_active_version / prompt_too_large / conteudo_incompleto."""


class ControleIndisponivel(AgentsClientError):
    """503 controle_indisponivel: agents could not read its own control. FAIL CLOSED: nothing is sent."""


class TurnInProgress(AgentsClientError):
    """409 turn_in_progress -- SW re-queues the batch once after 5 s."""


class IdempotencyConflict(AgentsClientError):
    """409 on a replayed provider_message_id with different text (M2). A bug on our side."""




class LlmNotConfigured(AgentsClientError, IntegrationNotConfigured):
    """424 llm_not_configured -- no org key for the provider."""


class CapacityExceeded(AgentsClientError):
    """429 capacidade -- slots full / org budget exhausted; honours Retry-After."""

    def __init__(self, message: str = "", *, code: Optional[str] = None, retry_after: int = DEFAULT_RETRY_AFTER_S):
        super().__init__(message, code=code)
        self.retry_after = retry_after






# ── Protocol ────────────────────────────────────────────────────────────────
@runtime_checkable
class AgentsClient(Protocol):
    async def run_turn(self, req: TurnRequest) -> TurnResult: ...

    async def agent_status(self, agent_key: str) -> AgentStatus: ...

    async def delete_conversation_data(self, req: DeletionRequest) -> DeletionResult: ...

    async def apagar_lead(self, lead_ref: str) -> None: ...

    async def resumo(self, conversation_id: str, req: ResumoRequest) -> ResumoResult: ...

    async def decidir(self, agent_key: str, chave: str, req: DecisaoRequest) -> DecisaoResult: ...

    async def put_ferramentas_token(self, token: str) -> None: ...

    async def uso(self, mes: str) -> AgentUso: ...

    # ── the shared thread (julia-v2 section 8.2) ──
    async def buscar_thread(
        self, *, connection_id: Optional[str] = None, chat_id: Optional[str] = None, lead_ref: Optional[str] = None,
        channel: str = "whatsapp",
    ) -> Optional[ThreadInfo]: ...

    async def obter_thread(self, thread_id: str) -> ThreadInfo: ...

    async def anexar_mensagem(
        self, thread_id: str, *, role: str, texto: str, provider_message_id: str, at: Optional[datetime] = None,
        autor_user_id: Optional[str] = None, autor: Optional[dict[str, Any]] = None,
    ) -> AppendResult: ...

    async def set_participante(
        self, thread_id: str, agent_key: str, *, estado: str, ator_user_id: str, motivo: Optional[str] = None,
        ate: Optional[datetime] = None,
    ) -> ParticipanteInfo: ...

    async def listar_handoffs(self, thread_id: str) -> tuple[HandoffRecord, ...]: ...

    async def obter_handoff(self, handoff_id: str) -> HandoffRecord: ...

    async def aceitar_handoff(self, handoff_id: str, user_id: str) -> HandoffRecord: ...

    async def opt_in(self, lead_ref: str, *, origem: str, em: Optional[datetime] = None) -> ConsentInfo: ...

    async def opt_out(
        self, lead_ref: str, *, em: Optional[datetime] = None, origem: str = ORIGEM_OPT_OUT_PADRAO,
        motivo: Optional[str] = None, mensagem_lead: Optional[str] = None, ator_user_id: Optional[str] = None,
    ) -> ConsentInfo: ...

    async def consentimento(self, lead_ref: str) -> Optional[ConsentInfo]: ...

    async def listar_opt_outs(
        self, *, limit: int = 50, cursor: Optional[str] = None, lead_ref: Optional[str] = None,
    ) -> OptOutPagina: ...

    async def renotificar_opt_out(self, evento_id: str, *, ator_user_id: str) -> OptOutEvento: ...

    async def reativar_lead(self, lead_ref: str, *, motivo: str, ator_user_id: str) -> ReativacaoResult: ...

    async def controle(self, agent_key: str) -> ControleInfo: ...

    async def estagios(self, agent_key: str) -> tuple[EstagioInfo, ...]: ...

    async def qualificacao(self, lead_ref: str) -> Optional[QualificacaoEstado]: ...

    async def identificacao_mascarada(self, lead_ref: str) -> Optional[dict[str, Any]]: ...

    async def feedback_mensagem(
        self, message_id: str, *, nota: str, user_id: str, comentario: Optional[str] = None,
    ) -> None: ...


# ── Fake ────────────────────────────────────────────────────────────────────
ScriptedReply = Union[TurnResult, AgentsClientError, Callable[[TurnRequest], TurnResult]]

_NAMESPACE = uuid.UUID("5f0e3b0a-7c1d-4a52-9d55-3a0c1b5a8f10")

#: The standard v1 stage order the Fake reports (julia-v2 CONTRACT 4.3) -- a TEST fixture of the agents side, not a rule
#: SW applies: the real order comes from agents' response.
FAKE_ESTAGIOS = ("novo", "em_conversa", "perfil_basico", "qualificado_frio", "qualificado", "pronto_para_corretor")


class FakeAgentsClient:
    """Scripted, deterministic, records every call. Follows julia-v2 CONTRACT section 8.

    `script` is consumed one entry per `run_turn`: a `TurnResult` is returned, an
    `AgentsClientError` is raised, a callable is called with the request. When the
    script is exhausted the default reply is returned. A replayed set of
    `provider_message_id`s returns the stored result without consuming the script
    (agents' idempotency, section 3.1 side effect 1).

    It also keeps a small in-memory THREAD per chat (participant state, appended messages, hand-offs, consent), so the
    per-conversation toggle / append-without-reply / consent paths can be asserted end to end."""

    DEFAULT_PARTES = ("Prazer! Você procura comprar ou alugar?",)

    def __init__(
        self,
        script: Sequence[ScriptedReply] = (),
        *,
        status: Optional[AgentStatus] = None,
        status_error: Optional[AgentsClientError] = None,
        default_partes: Sequence[str] = DEFAULT_PARTES,
        resumo_script: Sequence[Union[ResumoResult, AgentsClientError]] = (),
        decisao_script: Sequence[Union[DecisaoResult, AgentsClientError]] = (),
        ferramentas_token_error: Optional[AgentsClientError] = None,
        uso: Union[AgentUso, AgentsClientError, None] = None,
        handoffs: Sequence[HandoffRecord] = (),
        controle: Union[ControleInfo, AgentsClientError, None] = None,
        qualificacoes: Optional[dict[str, QualificacaoEstado]] = None,
        errors: Optional[dict[str, AgentsClientError]] = None,
        estagios: Optional[Sequence[EstagioInfo]] = None,
    ):
        self._estagios = tuple(estagios) if estagios is not None else tuple(
            EstagioInfo(chave=c, rotulo=c.replace("_", " ").capitalize(), ordem=i * 10, conclusivo=i >= len(FAKE_ESTAGIOS) - 2)
            for i, c in enumerate(FAKE_ESTAGIOS)
        )
        self.estagios_calls: list[str] = []
        self._uso = uso
        self.uso_calls: list[str] = []
        self._script = list(script)
        self._resumo_script = list(resumo_script)
        self._decisao_script = list(decisao_script)
        self.decisoes: list[tuple[str, str, DecisaoRequest]] = []
        self._ferramentas_token_error = ferramentas_token_error
        self._status = status
        self._status_error = status_error
        self._default_partes = tuple(default_partes)
        self._replays: dict[tuple[str, ...], TurnResult] = {}
        self.turns: list[TurnRequest] = []
        self.identificacoes: dict[str, dict[str, Any]] = {}  # lead_ref -> the MASKED identity agents holds (empty = nothing registered)
        self.status_calls: list[str] = []
        self.deletions: list[DeletionRequest] = []
        self.resumos: list[tuple[str, ResumoRequest]] = []
        self.ferramentas_tokens: list[str] = []
        # julia-v2 thread state
        self.handoffs: list[HandoffRecord] = list(handoffs)
        self._controle = controle
        self.qualificacoes: dict[str, QualificacaoEstado] = dict(qualificacoes or {})
        #: Method name -> an error raised on every call of it (e.g. `{"set_participante": AgentsTimeout()}`).
        self.errors: dict[str, AgentsClientError] = dict(errors or {})
        self.participantes: dict[tuple[str, str], str] = {}  # (thread_id, agent_key) -> estado
        self.appended: list[dict[str, Any]] = []  # every accepted append (dedup by provider_message_id)
        self._appended_ids: dict[str, str] = {}
        self.participante_calls: list[dict[str, Any]] = []
        self.handoff_aceites: list[tuple[str, str]] = []
        self.opt_ins: list[tuple[str, str]] = []
        self.opt_outs: list[str] = []
        self.opt_out_calls: list[dict[str, Any]] = []  # every opt_out call, with the validated body it would send
        self.leads_com_opt_out: set[str] = set()  # a later opt-in lifts it (agents' rule)
        self.consentimentos: dict[str, ConsentInfo] = {}  # leads agents has seen via opt_in/opt_out (others: unknown)
        self.lead_threads: dict[str, str] = {}  # lead_ref -> thread_id for leads that have a thread but no recorded turn
        self.opt_out_eventos: list[OptOutEvento] = []  # the history agents keeps (newest last; reads reverse it)
        self.reativacoes: list[dict[str, Any]] = []
        self.renotificacoes: list[tuple[str, str]] = []
        self.leads_apagados: list[str] = []
        self.thread_reads: list[str] = []
        self.feedbacks: list[dict[str, Any]] = []

    def _maybe_fail(self, method: str) -> None:
        if method in self.errors:
            raise self.errors[method]

    @staticmethod
    def conversation_id_for(req: TurnRequest) -> str:
        return str(uuid.uuid5(_NAMESPACE, f"{req.agent_key}|{req.connection_id}|{req.chat_id}"))

    @staticmethod
    def thread_id_for(connection_id: str, chat_id: str) -> str:
        return str(uuid.uuid5(_NAMESPACE, f"julia|{connection_id}|{chat_id}"))

    async def run_turn(self, req: TurnRequest) -> TurnResult:
        self.turns.append(req)
        ids = tuple(m.provider_message_id for m in req.messages)
        if ids in self._replays:
            return self._replays[ids]
        if self._script:
            nxt = self._script.pop(0)
            if isinstance(nxt, AgentsClientError):
                raise nxt
            result = nxt(req) if callable(nxt) and not isinstance(nxt, TurnResult) else nxt
        else:
            tid = self.conversation_id_for(req)
            result = TurnResult(
                conversation_id=tid,
                thread_id=tid,
                partes=self._default_partes,
                status="respondido",
                participante_estado="ativo",
                custo_usd=0.0,
                tokens_entrada=0,
                tokens_saida=0,
            )
        if result.thread:
            self.participantes.setdefault((result.thread, req.agent_key), result.participante_estado or "ativo")
        self._replays[ids] = result
        return result

    async def agent_status(self, agent_key: str) -> AgentStatus:
        self.status_calls.append(agent_key)
        if self._status_error is not None:
            raise self._status_error
        return self._status or AgentStatus(
            agent_key=agent_key, nome="Julia", ativo=True, versao_ativa=1,
            provider="openai", model="gpt-5-mini", llm_configurado=True,
            modo="ligado", aceita_novos_leads=True, threads_abertas=0, conteudo_completo=True,
        )

    async def delete_conversation_data(self, req: DeletionRequest) -> DeletionResult:
        self.deletions.append(req)
        had = any(
            t.connection_id == req.connection_id and t.chat_id == req.chat_id and t.agent_key == req.agent_key
            for t in self.turns
        )
        return DeletionResult(deleted=had, messages_deleted=2 * len(self.turns) if had else 0)

    async def apagar_lead(self, lead_ref: str) -> None:
        self._maybe_fail("apagar_lead")
        self.leads_apagados.append(lead_ref)  # idempotent by construction: 204 whether or not it existed

    async def resumo(self, conversation_id: str, req: ResumoRequest) -> ResumoResult:
        self.resumos.append((conversation_id, req))
        if self._resumo_script:
            nxt = self._resumo_script.pop(0)
            if isinstance(nxt, AgentsClientError):
                raise nxt
            return nxt
        return ResumoResult(resumo="Resumo de teste da conversa.", desfecho="em_andamento", custo_usd=0.0,
                            tokens_entrada=0, tokens_saida=0)

    async def decidir(self, agent_key: str, chave: str, req: DecisaoRequest) -> DecisaoResult:
        """Scripted; with no script, the FIRST option (deterministic) as the version's flagged default."""
        self.decisoes.append((agent_key, chave, req))
        if self._decisao_script:
            nxt = self._decisao_script.pop(0)
            if isinstance(nxt, AgentsClientError):
                raise nxt
            return nxt
        return DecisaoResult(escolha=req.opcoes[0], motivo="decisão de teste", regra="padrao_da_versao", custo_usd=0.0)

    async def uso(self, mes: str) -> AgentUso:
        self.uso_calls.append(mes)
        if isinstance(self._uso, AgentsClientError):
            raise self._uso
        return self._uso or AgentUso(turnos=0, custo_usd=0.0, limite_diario_usd=5.0)

    async def put_ferramentas_token(self, token: str) -> None:
        if self._ferramentas_token_error is not None:
            raise self._ferramentas_token_error
        self.ferramentas_tokens.append(token)

    # ── the shared thread ──
    def _info(self, thread_id: str, lead_ref: Optional[str] = None) -> ThreadInfo:
        parts = tuple(
            ParticipanteInfo(agent_key=k, estado=e) for (t, k), e in self.participantes.items() if t == thread_id
        )
        if lead_ref is None:
            lead_ref = next((x.lead_ref for x in reversed(self.turns) if x.lead_ref and self.conversation_id_for(x) == thread_id), None)
        suprimido = lead_ref is not None and lead_ref in self.leads_com_opt_out
        return ThreadInfo(
            thread_id=thread_id, lead_ref=lead_ref, participantes=parts,
            reengajamento_suprimido=suprimido, reengajamento_suprimido_motivo="opt_out" if suprimido else None,
            ultimo_handoff=next((h for h in reversed(self.handoffs) if h.thread_id == thread_id), None),
        )

    def seed_lead_thread(self, lead_ref: str) -> str:
        """Test seam: the lead already has a thread in agents (reads by `lead_ref` find it); returns its id."""
        tid = str(uuid.uuid5(_NAMESPACE, f"lead-thread|{lead_ref}"))
        self.lead_threads[lead_ref] = tid
        return tid

    async def buscar_thread(
        self, *, connection_id: Optional[str] = None, chat_id: Optional[str] = None, lead_ref: Optional[str] = None,
        channel: str = "whatsapp",
    ) -> Optional[ThreadInfo]:
        self._maybe_fail("buscar_thread")
        self.thread_reads.append(f"{connection_id}|{chat_id}|{lead_ref}")
        if connection_id and chat_id:
            tid = self.thread_id_for(connection_id, chat_id)
            if any(t == tid for (t, _k) in self.participantes) or any(
                (x.connection_id, x.chat_id) == (connection_id, chat_id) for x in self.turns
            ):
                return self._info(tid)
            return None
        if lead_ref:
            for x in reversed(self.turns):
                if x.lead_ref == lead_ref:
                    return self._info(self.conversation_id_for(x), lead_ref)
            if lead_ref in self.lead_threads:
                return self._info(self.lead_threads[lead_ref], lead_ref)
        return None

    async def obter_thread(self, thread_id: str) -> ThreadInfo:
        self._maybe_fail("obter_thread")
        self.thread_reads.append(thread_id)
        if not any(t == thread_id for (t, _k) in self.participantes):
            raise ThreadNotFound("thread not found", code="thread_not_found")
        return self._info(thread_id)

    async def anexar_mensagem(
        self, thread_id: str, *, role: str, texto: str, provider_message_id: str, at: Optional[datetime] = None,
        autor_user_id: Optional[str] = None, autor: Optional[dict[str, Any]] = None,
    ) -> AppendResult:
        self._maybe_fail("anexar_mensagem")
        if role == "humano" and not autor_user_id:
            raise AgentsBadRequest("autor_user_id required", code="invalid_field")
        if role != "humano" and (autor or autor_user_id):
            # the lead turn / lead append route rejects `autor` (agents' provenance slice): only the staff append may carry it
            raise AgentsBadRequest("autor only on a humano append", code="invalid_field")
        if provider_message_id in self._appended_ids:
            return AppendResult(message_id=None, duplicado=True)
        mid = str(uuid.uuid5(_NAMESPACE, f"msg|{thread_id}|{provider_message_id}"))
        self._appended_ids[provider_message_id] = mid
        self.appended.append({
            "thread_id": thread_id, "role": role, "texto": texto, "provider_message_id": provider_message_id,
            "autor_user_id": autor_user_id, "autor": autor, "at": at,
        })
        return AppendResult(message_id=mid, duplicado=False)

    async def set_participante(
        self, thread_id: str, agent_key: str, *, estado: str, ator_user_id: str, motivo: Optional[str] = None,
        ate: Optional[datetime] = None,
    ) -> ParticipanteInfo:
        self._maybe_fail("set_participante")
        self.participante_calls.append({
            "thread_id": thread_id, "agent_key": agent_key, "estado": estado, "ator_user_id": ator_user_id,
            "motivo": motivo, "ate": ate,
        })
        atual = self.participantes.get((thread_id, agent_key))
        if atual is None:
            raise ParticipanteNotFound("not a participant", code="participante_not_found")
        if atual in ("concluido", "encerrado", "transferido"):
            raise TransicaoInvalida(f"{atual} -> {estado}", code="transicao_invalida")
        self.participantes[(thread_id, agent_key)] = estado
        return ParticipanteInfo(agent_key=agent_key, estado=estado, pausado_ate=ate.isoformat() if ate else None,
                                motivo=motivo)

    async def listar_handoffs(self, thread_id: str) -> tuple[HandoffRecord, ...]:
        self._maybe_fail("listar_handoffs")
        return tuple(h for h in self.handoffs if h.thread_id == thread_id)

    async def obter_handoff(self, handoff_id: str) -> HandoffRecord:
        self._maybe_fail("obter_handoff")
        for h in self.handoffs:
            if h.id == handoff_id:
                return h
        raise HandoffNotFound("handoff not found", code="handoff_not_found")

    async def aceitar_handoff(self, handoff_id: str, user_id: str) -> HandoffRecord:
        self._maybe_fail("aceitar_handoff")
        h = await self.obter_handoff(handoff_id)
        self.handoff_aceites.append((handoff_id, user_id))
        return h

    async def opt_in(self, lead_ref: str, *, origem: str, em: Optional[datetime] = None) -> ConsentInfo:
        self._maybe_fail("opt_in")
        self.opt_ins.append((lead_ref, origem))
        self.leads_com_opt_out.discard(lead_ref)
        anterior = self.consentimentos.get(lead_ref)
        info = ConsentInfo(
            lead_ref=lead_ref, opt_in_origem=origem, opt_in_em=(em or datetime.now()).isoformat(),
            opt_out_em=anterior.opt_out_em if anterior else None, opt_out_ativo=False,
            evento_id=anterior.evento_id if anterior else None,
        )
        self.consentimentos[lead_ref] = info
        return info

    async def opt_out(
        self, lead_ref: str, *, em: Optional[datetime] = None, origem: str = ORIGEM_OPT_OUT_PADRAO,
        motivo: Optional[str] = None, mensagem_lead: Optional[str] = None, ator_user_id: Optional[str] = None,
    ) -> ConsentInfo:
        self._maybe_fail("opt_out")
        body = opt_out_body(em=em, origem=origem, motivo=motivo, mensagem_lead=mensagem_lead, ator_user_id=ator_user_id)
        self.opt_outs.append(lead_ref)
        self.opt_out_calls.append({"lead_ref": lead_ref, **body})
        self.leads_com_opt_out.add(lead_ref)
        for k in list(self.participantes):
            self.participantes[k] = "encerrado"
        anterior = self.consentimentos.get(lead_ref)
        quando = (em or datetime.now()).isoformat()
        evento_id = str(uuid.uuid5(_NAMESPACE, f"opt-out|{lead_ref}|{len(self.opt_out_calls)}"))
        info = ConsentInfo(
            lead_ref=lead_ref, opt_in_em=anterior.opt_in_em if anterior else None,
            opt_in_origem=anterior.opt_in_origem if anterior else None,
            opt_out_em=quando, opt_out_ativo=True, evento_id=evento_id, opt_out_motivo=motivo, opt_out_origem=origem,
        )
        self.consentimentos[lead_ref] = info
        self.opt_out_eventos.append(OptOutEvento(
            id=evento_id, tipo="opt_out", lead_ref=lead_ref, em=quando, ator_user_id=ator_user_id, origem=origem,
            motivo=motivo, mensagem_lead=mensagem_lead, thread_id=self.lead_threads.get(lead_ref),
        ))
        return info

    async def consentimento(self, lead_ref: str) -> Optional[ConsentInfo]:
        self._maybe_fail("consentimento")
        return self.consentimentos.get(lead_ref)

    async def listar_opt_outs(
        self, *, limit: int = 50, cursor: Optional[str] = None, lead_ref: Optional[str] = None,
    ) -> OptOutPagina:
        self._maybe_fail("listar_opt_outs")
        if not 1 <= limit <= 100:
            raise ValueError("listar_opt_outs limit must be 1..100")
        itens = [e for e in reversed(self.opt_out_eventos) if lead_ref is None or e.lead_ref == lead_ref]
        inicio = int(cursor) if cursor else 0
        pagina = itens[inicio:inicio + limit]
        proximo = str(inicio + limit) if inicio + limit < len(itens) else None
        return OptOutPagina(items=tuple(pagina), next_cursor=proximo)

    async def renotificar_opt_out(self, evento_id: str, *, ator_user_id: str) -> OptOutEvento:
        self._maybe_fail("renotificar_opt_out")
        self.renotificacoes.append((evento_id, str(ator_user_id)))
        for i, e in enumerate(self.opt_out_eventos):
            if e.id == evento_id:
                novo = replace(e, notificacao_status="enviada", notificacao_erro=None, notificado_em=datetime.now().isoformat())
                self.opt_out_eventos[i] = novo
                return novo
        raise OptOutEventoNotFound("opt-out record not found", code="evento_not_found")

    async def reativar_lead(self, lead_ref: str, *, motivo: str, ator_user_id: str) -> ReativacaoResult:
        self._maybe_fail("reativar_lead")
        motivo = reativacao_motivo(motivo)
        atual = self.consentimentos.get(lead_ref)
        if atual is None:
            raise LeadDesconhecido("agents has never seen the lead", code="lead_desconhecido")
        if not atual.opt_out_ativo:
            raise SemOptOutAtivo("the lead has no active opt-out", code="sem_opt_out_ativo")
        self.reativacoes.append({"lead_ref": lead_ref, "motivo": motivo, "ator_user_id": str(ator_user_id)})
        self.leads_com_opt_out.discard(lead_ref)
        info = replace(atual, opt_out_ativo=False, participantes_encerrados=0)
        self.consentimentos[lead_ref] = info
        evento = OptOutEvento(
            id=str(uuid.uuid5(_NAMESPACE, f"reativacao|{lead_ref}|{len(self.reativacoes)}")), tipo="reativacao",
            lead_ref=lead_ref, em=datetime.now().isoformat(), ator_user_id=str(ator_user_id), origem="operador", motivo=motivo,
        )
        self.opt_out_eventos.append(evento)
        return ReativacaoResult(consent=info, evento=evento)

    async def controle(self, agent_key: str) -> ControleInfo:
        self._maybe_fail("controle")
        if isinstance(self._controle, AgentsClientError):
            raise self._controle
        return self._controle or ControleInfo(agent_key=agent_key, modo="ligado", aceita_novos_leads=True)

    async def estagios(self, agent_key: str) -> tuple[EstagioInfo, ...]:
        self._maybe_fail("estagios")
        self.estagios_calls.append(agent_key)
        return tuple(sorted(self._estagios, key=lambda e: (e.ordem, e.chave)))

    async def qualificacao(self, lead_ref: str) -> Optional[QualificacaoEstado]:
        self._maybe_fail("qualificacao")
        return self.qualificacoes.get(lead_ref)

    async def identificacao_mascarada(self, lead_ref: str) -> Optional[dict[str, Any]]:
        self._maybe_fail("identificacao_mascarada")
        return self.identificacoes.get(lead_ref)

    async def feedback_mensagem(
        self, message_id: str, *, nota: str, user_id: str, comentario: Optional[str] = None,
    ) -> None:
        self._maybe_fail("feedback_mensagem")
        self.feedbacks.append({"message_id": message_id, "nota": nota, "user_id": user_id, "comentario": comentario})


# ── Real ────────────────────────────────────────────────────────────────────


def _raise_for_agents_status(response: httpx.Response) -> None:
    """Section 3.1 error table -> typed exception. 2xx returns."""
    status = response.status_code
    if status < 400:
        return
    code = _error_code(response)
    if status in (401, 403):
        raise AgentsTokenInvalid(f"agents refused the token ({status})", code=code)
    if status == 404:
        if code == "agent_not_found":
            raise AgentNotFound("agent not found", code=code)
        if code == "thread_not_found":
            raise ThreadNotFound("thread not found", code=code)
        if code == "conversation_not_found":
            raise ConversationNotFound("conversation not found", code=code)
        if code == "handoff_not_found":
            raise HandoffNotFound("handoff not found", code=code)
        if code == "lead_desconhecido":
            raise LeadDesconhecido("agents has never seen the lead", code=code)
        if code == "participante_not_found":
            raise ParticipanteNotFound("participant not found", code=code)
        if code in ("evento_not_found", "evento_nao_encontrado", "opt_out_evento_not_found"):
            raise OptOutEventoNotFound("opt-out record not found", code=code)
        if code in ("lead_sem_qualificacao", "lead_sem_identificacao"):
            raise LeadSemQualificacao("nothing recorded for the lead", code=code)
        raise AgentsUpstreamError("agents answered 404", code=code)
    if status == 409:
        if code == "sem_opt_out_ativo":
            raise SemOptOutAtivo("the lead has no active opt-out", code=code)
        if code == "turn_in_progress":
            raise TurnInProgress("turn in progress", code=code)
        if code in ("agent_inactive", "no_active_version", "prompt_too_large", "conteudo_incompleto"):
            raise AgentUnavailable(code, code=code)
        if code in ("transicao_invalida", "outro_agente_ativo"):
            raise TransicaoInvalida(code, code=code)
        raise IdempotencyConflict(f"agents answered 409 ({code})", code=code)
    if status == 422:
        raise AgentsBadRequest("agents rejected the request shape", code=code)
    if status == 424:
        raise LlmNotConfigured("llm not configured for the org", code=code or "llm_not_configured")
    if status == 429:
        raise CapacityExceeded("agents at capacity", code=code or "capacidade", retry_after=_retry_after(response))
    if status == 503 and code == "controle_indisponivel":
        raise ControleIndisponivel("agents could not read its control", code=code)
    raise AgentsUpstreamError(f"agents answered {status}", code=code)




def parse_qualificacao_resumo(raw: Any) -> Optional[QualificacaoResumo]:
    if not isinstance(raw, dict):
        return None
    score = raw.get("score")
    faltando = raw.get("faltando")
    # A-RT2 names it `estagios_ordem`; older builds sent nothing (kept optional)
    estagios = raw.get("estagios_ordem", raw.get("estagios"))
    return QualificacaoResumo(
        versao=_opt_str(raw, "versao"),
        estagio=_opt_str(raw, "estagio"),
        score=score if isinstance(score, int) and not isinstance(score, bool) else None,
        faltando=tuple(str(f) for f in faltando if isinstance(f, str)) if isinstance(faltando, list) else (),
        estagios=tuple(str(e) for e in estagios if isinstance(e, str)) if isinstance(estagios, list) else (),
    )


def parse_turn_result(body: Any) -> TurnResult:
    """Strict parse of the julia-v2 section 8.1 200 body -- a malformed reply is an upstream fault (no reply sent),
    never a half-trusted result. A status that is not in the contract is a fault too: a newer agents build must not make
    SW guess whether to send."""
    if not isinstance(body, dict):
        raise AgentsUpstreamError("malformed agents response: body")
    status = _need(body, "status", str)
    if status not in STATUS_TURNO:
        raise AgentsUpstreamError("malformed agents response: status")
    thread_id = _opt_str(body, "thread_id")
    conversation_id = _opt_str(body, "conversation_id") or thread_id or ""
    if status in STATUS_RESPONDEU and not conversation_id:
        raise AgentsUpstreamError("malformed agents response: conversation_id")
    reply = body.get("reply") if isinstance(body.get("reply"), dict) else {}
    partes = reply.get("partes", [])
    if not isinstance(partes, list) or not all(isinstance(p, str) for p in partes):
        raise AgentsUpstreamError("malformed agents response: reply.partes")
    if status in STATUS_RESPONDEU and "partes" not in reply:
        raise AgentsUpstreamError("malformed agents response: reply")
    actions_raw = body.get("actions", [])
    if not isinstance(actions_raw, list):
        raise AgentsUpstreamError("malformed agents response: actions")
    actions: list[Action] = []
    for idx, a in enumerate(actions_raw):
        if not isinstance(a, dict) or not isinstance(a.get("type"), str) or not a.get("type"):
            # the TYPE only: an action carries lead slot values, which must never reach a log line
            logger.warning("agents returned a malformed action (kind=%s)", type(a).__name__)
            continue
        seq = a.get("seq")
        seq = seq if isinstance(seq, int) and not isinstance(seq, bool) else idx
        if a["type"] == "handoff":
            actions.append(HandoffAction(
                motivo=str(a.get("motivo") or "")[:280], motivo_codigo=_opt_str(a, "motivo_codigo"), seq=seq,
            ))
            continue
        # A non-handoff action; an unknown type is kept so the apply service can report `acao_sem_handler`.
        actions.append(JuliaAction(
            type=a["type"], seq=seq, payload={k: v for k, v in a.items() if k not in ("type", "seq")},
        ))
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    participante = body.get("participante") if isinstance(body.get("participante"), dict) else {}
    conformidade = body.get("conformidade") if isinstance(body.get("conformidade"), dict) else {}
    violacoes = conformidade.get("violacoes") if isinstance(conformidade.get("violacoes"), list) else []
    return TurnResult(
        conversation_id=conversation_id,
        thread_id=thread_id or conversation_id or None,
        partes=tuple(p for p in partes if p.strip()),
        status=status,
        actions=tuple(actions),
        custo_usd=usage.get("custo_usd"),
        tokens_entrada=usage.get("tokens_entrada"),
        tokens_saida=usage.get("tokens_saida"),
        participante_estado=_opt_str(participante, "estado"),
        qualificacao=parse_qualificacao_resumo(body.get("qualificacao")),
        conformidade=tuple(
            {"regra": str(v.get("regra")), "politica": str(v.get("politica"))} for v in violacoes if isinstance(v, dict)
        ),
    )


def parse_resumo_result(body: Any) -> ResumoResult:
    """Strict parse of the resumo 200 body (julia-v2: `{resumo, desfecho_sugerido}`, narrative only; a pre-v2 build also
    sends slots/operacao/intencoes); a malformed one is an upstream fault."""
    resumo = _need(body, "resumo", str)
    slots_raw = body.get("slots") if isinstance(body.get("slots"), dict) else {}
    intencoes = body.get("intencoes") if isinstance(body.get("intencoes"), list) else []
    desfecho = _opt_str(body, "desfecho_sugerido") or _opt_str(body, "desfecho") or "em_andamento"
    operacao = body.get("operacao")
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    return ResumoResult(
        resumo=resumo,
        slots={str(k): str(v) for k, v in slots_raw.items() if v is not None},
        operacao=operacao if isinstance(operacao, str) else None,
        intencoes=tuple(str(i) for i in intencoes if isinstance(i, str)),
        desfecho=desfecho,
        custo_usd=usage.get("custo_usd"),
        tokens_entrada=usage.get("tokens_entrada"),
        tokens_saida=usage.get("tokens_saida"),
    )


def parse_decisao_result(body: Any, opcoes: Sequence[str]) -> DecisaoResult:
    """Strict parse; an `escolha` outside what we offered is an upstream fault, never used."""
    escolha = _need(body, "escolha", str)
    if escolha not in opcoes:
        raise AgentsUpstreamError("agents chose an option that was not offered")
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    regra = body.get("regra")
    return DecisaoResult(
        escolha=escolha,
        motivo=body.get("motivo") if isinstance(body.get("motivo"), str) else "",
        regra=regra if regra in ("versao", "padrao_da_versao") else "versao",
        custo_usd=usage.get("custo_usd"),
    )


def parse_uso(body: Any) -> AgentUso:
    turnos = _need(body, "turnos", int)
    custo = _need(body, "custo_usd", (int, float))
    limite = _need(body, "limite_diario_usd", (int, float))
    return AgentUso(turnos=int(turnos), custo_usd=float(custo), limite_diario_usd=float(limite))


def parse_agent_status(body: Any) -> AgentStatus:
    aceita = body.get("aceita_novos_leads")
    abertas = body.get("threads_abertas")
    completo = body.get("conteudo_completo")
    return AgentStatus(
        agent_key=_need(body, "agent_key", str),
        nome=_need(body, "nome", str),
        ativo=bool(_need(body, "ativo", bool)),
        versao_ativa=body.get("versao_ativa") if isinstance(body.get("versao_ativa"), int) else None,
        provider=body.get("provider") if isinstance(body.get("provider"), str) else None,
        model=body.get("model") if isinstance(body.get("model"), str) else None,
        llm_configurado=bool(_need(body, "llm_configurado", bool)),
        modo=_opt_str(body, "modo"),
        aceita_novos_leads=aceita if isinstance(aceita, bool) else None,
        threads_abertas=abertas if isinstance(abertas, int) and not isinstance(abertas, bool) else None,
        conteudo_completo=completo if isinstance(completo, bool) else None,
    )


def parse_participante(raw: Any) -> ParticipanteInfo:
    return ParticipanteInfo(
        agent_key=_need(raw, "agent_key", str),
        estado=_need(raw, "estado", str),
        agent_nome=_opt_str(raw, "agent_nome"),
        pausado_ate=_opt_str(raw, "pausado_ate"),
        motivo=_opt_str(raw, "motivo"),
    )


def parse_handoff(raw: Any) -> HandoffRecord:
    return HandoffRecord(
        id=_need(raw, "id", str),
        thread_id=_need(raw, "thread_id", str),
        lead_ref=_opt_str(raw, "lead_ref"),
        de_agent_key=_opt_str(raw, "de_agent_key") or "",
        para=dict(raw["para"]) if isinstance(raw.get("para"), dict) else {},
        motivo_codigo=_opt_str(raw, "motivo_codigo") or "",
        resumo=raw.get("resumo") if isinstance(raw.get("resumo"), str) else "",
        perfil=dict(raw["perfil"]) if isinstance(raw.get("perfil"), dict) else {},
        identificacao_completa=bool(raw.get("identificacao_completa")),
        identificacao_mascarada=dict(raw["identificacao_mascarada"]) if isinstance(raw.get("identificacao_mascarada"), dict) else {},
        perguntas_abertas=tuple(raw["perguntas_abertas"]) if isinstance(raw.get("perguntas_abertas"), list) else (),
        compromissos=tuple(raw["compromissos"]) if isinstance(raw.get("compromissos"), list) else (),
        aceito_em=_opt_str(raw, "aceito_em"),
        aceito_por=_opt_str(raw, "aceito_por"),
    )


def parse_thread(body: Any) -> ThreadInfo:
    partes = _need(body, "participantes", list)
    ultimo = body.get("ultimo_handoff")
    return ThreadInfo(
        thread_id=_need(body, "thread_id", str),
        channel=_opt_str(body, "channel") or "whatsapp",
        lead_ref=_opt_str(body, "lead_ref"),
        participantes=tuple(parse_participante(p) for p in partes),
        ultimo_turno_em=_opt_str(body, "ultimo_turno_em"),
        ultima_mensagem_lead_em=_opt_str(body, "ultima_mensagem_lead_em"),
        opt_out_em=_opt_str(body, "opt_out_em"),
        reengajamento_suprimido=bool(body.get("reengajamento_suprimido")),
        reengajamento_suprimido_motivo=_opt_str(body, "reengajamento_suprimido_motivo"),
        ultimo_handoff=parse_handoff(ultimo) if isinstance(ultimo, dict) else None,
    )


def opt_out_body(
    *, em: Optional[datetime], origem: str, motivo: Optional[str], mensagem_lead: Optional[str],
    ator_user_id: Optional[str],
) -> dict[str, Any]:
    """The validated opt-out request body (shared by the Real and the Fake so a test cannot pass what prod refuses).
    `origem` is always sent; the optional fields only when given."""
    if origem not in ORIGENS_OPT_OUT:
        raise ValueError(f"opt_out origem must be one of {ORIGENS_OPT_OUT}, got {origem!r}")
    if motivo is not None and len(motivo) > OPT_OUT_MOTIVO_MAX:
        raise ValueError(f"opt_out motivo is capped at {OPT_OUT_MOTIVO_MAX} chars")
    if mensagem_lead is not None and len(mensagem_lead) > OPT_OUT_MENSAGEM_MAX:
        raise ValueError(f"opt_out mensagem_lead is capped at {OPT_OUT_MENSAGEM_MAX} chars")
    body: dict[str, Any] = {"origem": origem}
    if em is not None:
        body["em"] = em.isoformat()
    if motivo is not None:
        body["motivo"] = motivo
    if mensagem_lead is not None:
        body["mensagem_lead"] = mensagem_lead
    if ator_user_id is not None:
        body["ator_user_id"] = str(ator_user_id)
    return body


def reativacao_motivo(motivo: Optional[str]) -> str:
    """The required reactivation reason (1..500 chars, shared by the Real and the Fake)."""
    limpo = (motivo or "").strip()
    if not limpo or len(limpo) > REATIVACAO_MOTIVO_MAX:
        raise ValueError(f"reativacao motivo is required and capped at {REATIVACAO_MOTIVO_MAX} chars")
    return limpo


def parse_opt_out_evento(raw: Any) -> OptOutEvento:
    if not isinstance(raw, dict):
        raise AgentsUpstreamError("agents returned a malformed opt-out record")
    encerrados = raw.get("participantes_encerrados")
    return OptOutEvento(
        id=_need(raw, "id", str), tipo=_need(raw, "tipo", str), lead_ref=_need(raw, "lead_ref", str),
        em=_opt_str(raw, "em"), lead_nome=_opt_str(raw, "lead_nome"), lead_telefone=_opt_str(raw, "lead_telefone"),
        thread_id=_opt_str(raw, "thread_id"), agent_id=_opt_str(raw, "agent_id"), agent_key=_opt_str(raw, "agent_key"),
        agent_nome=_opt_str(raw, "agent_nome"), ator_user_id=_opt_str(raw, "ator_user_id"), origem=_opt_str(raw, "origem"),
        motivo=_opt_str(raw, "motivo"), mensagem_lead=_opt_str(raw, "mensagem_lead"),
        participantes_encerrados=encerrados if isinstance(encerrados, int) and not isinstance(encerrados, bool) else 0,
        notificacao_status=_opt_str(raw, "notificacao_status") or "pendente",
        notificacao_erro=_opt_str(raw, "notificacao_erro"), notificado_em=_opt_str(raw, "notificado_em"),
    )


def parse_opt_out_pagina(body: Any) -> OptOutPagina:
    itens = _need(body, "items", list)
    return OptOutPagina(items=tuple(parse_opt_out_evento(i) for i in itens), next_cursor=_opt_str(body, "next_cursor"))


def parse_reativacao(body: Any) -> ReativacaoResult:
    evento = body.get("evento")
    return ReativacaoResult(consent=parse_consent(body), evento=parse_opt_out_evento(evento) if isinstance(evento, dict) else None)


def parse_consent(body: Any) -> ConsentInfo:
    encerrados = body.get("participantes_encerrados")
    evento = body.get("opt_out_evento")  # the GET carries the event object; the POST carries `evento_id`
    return ConsentInfo(
        lead_ref=_need(body, "lead_ref", str),
        opt_in_em=_opt_str(body, "opt_in_em"),
        opt_in_origem=_opt_str(body, "opt_in_origem"),
        opt_out_em=_opt_str(body, "opt_out_em"),
        opt_out_ativo=bool(body.get("opt_out_ativo")),
        participantes_encerrados=encerrados if isinstance(encerrados, int) and not isinstance(encerrados, bool) else 0,
        evento_id=_opt_str(body, "evento_id") or _opt_str(evento if isinstance(evento, dict) else {}, "id"),
        opt_out_motivo=_opt_str(evento if isinstance(evento, dict) else {}, "motivo"),
        opt_out_origem=_opt_str(evento if isinstance(evento, dict) else {}, "origem"),
    )


def parse_controle(body: Any) -> ControleInfo:
    dias = body.get("dreno_inatividade_dias")
    abertas = body.get("threads_abertas")
    return ControleInfo(
        agent_key=_need(body, "agent_key", str),
        modo=_need(body, "modo", str),
        aceita_novos_leads=bool(_need(body, "aceita_novos_leads", bool)),
        dreno_inatividade_dias=dias if isinstance(dias, int) and not isinstance(dias, bool) else 7,
        threads_abertas=abertas if isinstance(abertas, int) and not isinstance(abertas, bool) else 0,
        drenagem=dict(body["drenagem"]) if isinstance(body.get("drenagem"), dict) else {},
    )


def parse_estagios(body: Any) -> tuple[EstagioInfo, ...]:
    itens = body.get("data") if isinstance(body, dict) else body
    if not isinstance(itens, list):
        raise AgentsUpstreamError("agents returned a malformed stage list")
    out: list[EstagioInfo] = []
    for i in itens:
        ordem = i.get("ordem") if isinstance(i, dict) else None
        if not isinstance(i, dict) or not isinstance(i.get("chave"), str) or not isinstance(ordem, int) or isinstance(ordem, bool):
            raise AgentsUpstreamError("agents returned a malformed stage list")
        out.append(EstagioInfo(chave=i["chave"], rotulo=str(i.get("rotulo") or i["chave"]), ordem=ordem,
                               conclusivo=bool(i.get("conclusivo"))))
    return tuple(sorted(out, key=lambda e: (e.ordem, e.chave)))


def parse_qualificacao_estado(body: Any) -> QualificacaoEstado:
    score = body.get("score")
    faltando = body.get("faltando")
    eventos = body.get("eventos_imovel")
    estagios = body.get("estagios")
    scores = body.get("scores") if isinstance(body.get("scores"), dict) else {}
    return QualificacaoEstado(
        lead_ref=_need(body, "lead_ref", str),
        estagio=_opt_str(body, "estagio"),
        score=score if isinstance(score, int) and not isinstance(score, bool) else None,
        valores=dict(body["valores"]) if isinstance(body.get("valores"), dict) else {},
        faltando=tuple(str(f) for f in faltando if isinstance(f, str)) if isinstance(faltando, list) else (),
        pode_ofertar=bool(body.get("pode_ofertar")),
        pode_concluir=bool(body.get("pode_concluir")),
        scores={str(k): int(v) for k, v in scores.items() if isinstance(v, int) and not isinstance(v, bool)},
        eventos_imovel=tuple(e for e in eventos if isinstance(e, dict)) if isinstance(eventos, list) else (),
        estagios=tuple(str(e) for e in estagios if isinstance(e, str)) if isinstance(estagios, list) else (),
        versao_id=_opt_str(body, "versao_id"),
        hash=_opt_str(body, "hash"),
    )


class HttpAgentsClient(AgentsHttpTransport):
    """The real client. `base_url` = `resolve_product_url("agents")`; `token` is the
    org's `pk_...` channel token (sent as a bearer). The token is never logged.
    Transport (httpx, timeout/network mapping) is the seed's `AgentsHttpTransport`; the status table is ours."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        if not base_url:
            raise ValueError("HttpAgentsClient needs a base_url")
        if not token:
            raise ValueError("HttpAgentsClient needs a token")
        super().__init__(base_url, token, timeout=timeout, transport=transport, raise_for_status=_raise_for_agents_status)

    async def run_turn(self, req: TurnRequest) -> TurnResult:
        return parse_turn_result(await self._send("POST", "/api/channels/turns", json=req.to_wire()))

    async def agent_status(self, agent_key: str) -> AgentStatus:
        return parse_agent_status(await self._send("GET", f"/api/channels/agents/{quote(agent_key, safe='')}/status"))

    async def delete_conversation_data(self, req: DeletionRequest) -> DeletionResult:
        """`DELETE /api/channels/conversations` (A2): 204 empty, also when nothing exists;
        409 `turn_in_progress` while a turn runs (raised as `TurnInProgress`)."""
        # 404 is tolerated too (an older agents build): nothing stored = already gone.
        body = await self._send(
            "DELETE",
            "/api/channels/conversations",
            json={
                "agent_key": req.agent_key,
                "channel": "whatsapp",
                "channel_ref": {"connection_id": req.connection_id, "chat_id": req.chat_id},
            },
            ok_statuses=(404,),
        )
        # A 204 carries no body, so "was something deleted" is not knowable; the 2xx
        # itself is the guarantee that nothing remains.
        if isinstance(body, dict) and "deleted" in body:
            return DeletionResult(deleted=bool(body["deleted"]))
        return DeletionResult(deleted=body is not None)

    async def apagar_lead(self, lead_ref: str) -> None:
        """`DELETE /api/channels/leads/{ref}` (LGPD delete-by-lead across every agent): 204, idempotent; 409
        `turn_in_progress` while a turn runs (raised as `TurnInProgress`)."""
        await self._send("DELETE", f"/api/channels/leads/{quote(lead_ref, safe='')}")

    async def uso(self, mes: str) -> AgentUso:
        """`GET /api/channels/uso?mes=YYYY-MM` (Julia w9 Painel)."""
        return parse_uso(await self._send("GET", f"/api/channels/uso?mes={quote(mes, safe='')}"))

    async def resumo(self, conversation_id: str, req: ResumoRequest) -> ResumoResult:
        """`POST /api/channels/threads/{id}/resumo` (julia-v2 section 8.2): narrative only."""
        body = await self._send(
            "POST", f"/api/channels/threads/{quote(conversation_id, safe='')}/resumo", json=req.to_wire()
        )
        return parse_resumo_result(body)

    async def decidir(self, agent_key: str, chave: str, req: DecisaoRequest) -> DecisaoResult:
        """`POST /api/channels/agents/{key}/decisoes/{chave}` (julia-v2 D13): the rule is agents' DB row."""
        body = await self._send(
            "POST", f"/api/channels/agents/{quote(agent_key, safe='')}/decisoes/{quote(chave, safe='')}",
            json=req.to_wire(),
        )
        return parse_decisao_result(body, req.opcoes)

    async def put_ferramentas_token(self, token: str) -> None:
        """`PUT /api/channels/ferramentas-token` (contract 2.1(f)); auth = the org's channel
        token (this client's own bearer). 204 on success."""
        if not token:
            raise ValueError("put_ferramentas_token needs a token")
        await self._send("PUT", "/api/channels/ferramentas-token", json={"token": token})

    # ── the shared thread (julia-v2 section 8.2) ──
    async def buscar_thread(
        self, *, connection_id: Optional[str] = None, chat_id: Optional[str] = None, lead_ref: Optional[str] = None,
        channel: str = "whatsapp",
    ) -> Optional[ThreadInfo]:
        """`GET /api/channels/threads?channel=&connection_id=&chat_id=` OR `?lead_ref=`. None when agents has no thread
        (a lead it never served is never stored)."""
        by_channel = bool(connection_id and chat_id)
        if by_channel == bool(lead_ref):
            raise ValueError("buscar_thread needs connection_id+chat_id OR lead_ref")
        params = {"channel": channel, "connection_id": connection_id, "chat_id": chat_id} if by_channel else {"lead_ref": lead_ref}
        try:
            return parse_thread(await self._send("GET", "/api/channels/threads", params=params))
        except ThreadNotFound:
            return None

    async def obter_thread(self, thread_id: str) -> ThreadInfo:
        """`GET /api/channels/threads/{id}`: the participants + their states. This is the ONLY source of the
        per-conversation toggle state SW shows."""
        return parse_thread(await self._send("GET", f"/api/channels/threads/{quote(thread_id, safe='')}"))

    async def anexar_mensagem(
        self, thread_id: str, *, role: str, texto: str, provider_message_id: str, at: Optional[datetime] = None,
        autor_user_id: Optional[str] = None, autor: Optional[dict[str, Any]] = None,
    ) -> AppendResult:
        """`POST /api/channels/threads/{id}/mensagens`: append WITHOUT a turn (a human attendant's message, or a lead
        message agents will not answer). Idempotent by `provider_message_id`. `autor` (`{nome, papel}`, the staff list's name and
        role) is accepted ONLY with `role="humano"` -- agents' lead routes reject it (provenance cannot be claimed by a lead)."""
        if role not in ("user", "humano"):
            raise ValueError("role is 'user' or 'humano'")
        if autor is not None and role != "humano":
            raise ValueError("autor only with role='humano'")
        body: dict[str, Any] = {"role": role, "texto": texto, "provider_message_id": provider_message_id}
        if at is not None:
            body["at"] = at.isoformat()
        if autor_user_id is not None:
            body["autor_user_id"] = str(autor_user_id)
        if autor is not None:
            body["autor"] = {"nome": str(autor.get("nome") or "")[:120], "papel": str(autor.get("papel") or "")}
        out = await self._send("POST", f"/api/channels/threads/{quote(thread_id, safe='')}/mensagens", json=body)
        return AppendResult(message_id=_opt_str(out, "message_id"), duplicado=bool(out.get("duplicado")))

    async def set_participante(
        self, thread_id: str, agent_key: str, *, estado: str, ator_user_id: str, motivo: Optional[str] = None,
        ate: Optional[datetime] = None,
    ) -> ParticipanteInfo:
        """`PATCH /api/channels/threads/{id}/participantes/{agent_key}`: the per-conversation pause / resume. The actor
        is recorded by agents (participant event + audit log)."""
        if estado not in ("pausado", "ativo"):
            raise ValueError("estado is 'pausado' or 'ativo'")
        body: dict[str, Any] = {"estado": estado, "ator_user_id": str(ator_user_id)}
        if motivo:
            body["motivo"] = motivo[:300]
        if ate is not None:
            body["ate"] = ate.isoformat()
        out = await self._send(
            "PATCH", f"/api/channels/threads/{quote(thread_id, safe='')}/participantes/{quote(agent_key, safe='')}",
            json=body,
        )
        return parse_participante(out)

    async def listar_handoffs(self, thread_id: str) -> tuple[HandoffRecord, ...]:
        out = await self._send("GET", f"/api/channels/threads/{quote(thread_id, safe='')}/handoffs")
        if not isinstance(out, list):
            raise AgentsUpstreamError("malformed agents response: handoffs")
        return tuple(parse_handoff(h) for h in out if isinstance(h, dict))

    async def obter_handoff(self, handoff_id: str) -> HandoffRecord:
        return parse_handoff(await self._send("GET", f"/api/channels/handoffs/{quote(handoff_id, safe='')}"))

    async def aceitar_handoff(self, handoff_id: str, user_id: str) -> HandoffRecord:
        """`POST /api/channels/handoffs/{id}/aceite`: the human operator took it (the first acceptance wins)."""
        return parse_handoff(await self._send(
            "POST", f"/api/channels/handoffs/{quote(handoff_id, safe='')}/aceite", json={"user_id": str(user_id)},
        ))

    async def opt_in(self, lead_ref: str, *, origem: str, em: Optional[datetime] = None) -> ConsentInfo:
        body: dict[str, Any] = {"origem": origem}
        if em is not None:
            body["em"] = em.isoformat()
        return parse_consent(await self._send("PUT", f"/api/channels/leads/{quote(lead_ref, safe='')}/opt-in", json=body))

    async def opt_out(
        self, lead_ref: str, *, em: Optional[datetime] = None, origem: str = ORIGEM_OPT_OUT_PADRAO,
        motivo: Optional[str] = None, mensagem_lead: Optional[str] = None, ator_user_id: Optional[str] = None,
    ) -> ConsentInfo:
        """`POST /api/channels/leads/{ref}/opt-out`: ends every agent's participation for the lead and records WHO/WHY
        (agents notifies the org admins itself -- SW sends no second notification for the same event)."""
        body = opt_out_body(em=em, origem=origem, motivo=motivo, mensagem_lead=mensagem_lead, ator_user_id=ator_user_id)
        return parse_consent(await self._send("POST", f"/api/channels/leads/{quote(lead_ref, safe='')}/opt-out", json=body))

    async def consentimento(self, lead_ref: str) -> Optional[ConsentInfo]:
        """`GET /api/channels/leads/{ref}/consentimento`: the lead-level consent state, independent of any thread.
        None = agents has never seen the lead (404 `lead_desconhecido`), i.e. it never opted out; any other failure
        raises."""
        try:
            return parse_consent(await self._send("GET", f"/api/channels/leads/{quote(lead_ref, safe='')}/consentimento"))
        except LeadDesconhecido:
            return None

    async def listar_opt_outs(
        self, *, limit: int = 50, cursor: Optional[str] = None, lead_ref: Optional[str] = None,
    ) -> OptOutPagina:
        """`GET /api/channels/opt-outs`: the opt-out + reactivation history of the org's leads, newest first."""
        if not 1 <= limit <= 100:
            raise ValueError("listar_opt_outs limit must be 1..100")
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if lead_ref:
            params["lead_ref"] = lead_ref
        return parse_opt_out_pagina(await self._send("GET", "/api/channels/opt-outs", params=params))

    async def renotificar_opt_out(self, evento_id: str, *, ator_user_id: str) -> OptOutEvento:
        """`POST /api/channels/opt-outs/{id}/notificar`: send the admins' in-app notice of that record again."""
        return parse_opt_out_evento(await self._send(
            "POST", f"/api/channels/opt-outs/{quote(evento_id, safe='')}/notificar", json={"ator_user_id": str(ator_user_id)},
        ))

    async def reativar_lead(self, lead_ref: str, *, motivo: str, ator_user_id: str) -> ReativacaoResult:
        """`POST /api/channels/leads/{ref}/reativar`: lift the lead's active opt-out (409 `sem_opt_out_ativo` when
        there is none, 404 `lead_desconhecido` for an unknown lead)."""
        body = {"ator_user_id": str(ator_user_id), "motivo": reativacao_motivo(motivo)}
        return parse_reativacao(await self._send("POST", f"/api/channels/leads/{quote(lead_ref, safe='')}/reativar", json=body))

    async def controle(self, agent_key: str) -> ControleInfo:
        """`GET /api/channels/agents/{key}/controle`: read-only for SW (mode + drain progress). SW never decides the
        mode and never gates on a cached copy of this -- the turn endpoint decides."""
        return parse_controle(await self._send("GET", f"/api/channels/agents/{quote(agent_key, safe='')}/controle"))

    async def estagios(self, agent_key: str) -> tuple[EstagioInfo, ...]:
        """`GET /api/channels/agents/{key}/qualificacao/estagios` -> `[{chave, rotulo, ordem, conclusivo}]` (a bare
        list or `{"data": [...]}`), sorted by `ordem`. Read-only for SW."""
        body = await self._send("GET", f"/api/channels/agents/{quote(agent_key, safe='')}/qualificacao/estagios")
        return parse_estagios(body)

    async def qualificacao(self, lead_ref: str) -> Optional[QualificacaoEstado]:
        """`GET /api/channels/leads/{ref}/qualificacao`: the full computed state. None = nothing recorded yet."""
        try:
            return parse_qualificacao_estado(
                await self._send("GET", f"/api/channels/leads/{quote(lead_ref, safe='')}/qualificacao")
            )
        except LeadSemQualificacao:
            return None

    async def identificacao_mascarada(self, lead_ref: str) -> Optional[dict[str, Any]]:
        """`GET /api/channels/leads/{ref}/identificacao`: MASKED identity fields only. None = nothing recorded."""
        try:
            out = await self._send("GET", f"/api/channels/leads/{quote(lead_ref, safe='')}/identificacao")
        except LeadSemQualificacao:
            return None
        return out if isinstance(out, dict) else None

    async def feedback_mensagem(
        self, message_id: str, *, nota: str, user_id: str, comentario: Optional[str] = None,
    ) -> None:
        """`POST /api/channels/messages/{id}/feedback`: like / dislike forwarded from SW (the agent's learning signal)."""
        if nota not in ("like", "dislike"):
            raise ValueError("nota is 'like' or 'dislike'")
        body: dict[str, Any] = {"nota": nota, "user_id": str(user_id), "origem": "sw"}
        if comentario:
            body["comentario"] = comentario[:1000]
        await self._send("POST", f"/api/channels/messages/{quote(message_id, safe='')}/feedback", json=body)


# ── factory ─────────────────────────────────────────────────────────────────
def make_agents_client(
    *,
    token: Optional[str],
    base_url: Optional[str],
    allow_fake: bool,
) -> Optional[AgentsClient]:
    """Pure factory. Token + URL present -> the real client. Otherwise the Fake when
    `allow_fake` (dev), else `None` -- the caller reports "nao configurado" and sends
    no reply (prod: a lead is never answered by a scripted fake)."""
    if token and base_url:
        return HttpAgentsClient(base_url, token)
    if allow_fake:
        logger.warning("agents token/base_url missing: using FakeAgentsClient (dev only)")
        return FakeAgentsClient()
    return None


__all__ = [
    "Action", "AgentNotFound", "AgentStatus", "AgentUnavailable", "AgentUso", "AgentsBadRequest", "AgentsClient",
    "AgentsClientError", "AgentsNotConfigured", "AgentsTimeout", "AgentsTokenInvalid", "AgentsUpstreamError",
    "AppendResult", "CapacityExceeded", "ConsentInfo", "ControleIndisponivel", "ControleInfo", "ConversationNotFound",
    "DecisaoRequest", "DecisaoResult", "DeletionRequest", "DeletionResult", "EstagioInfo", "FAKE_ESTAGIOS", "FakeAgentsClient",
    "GATILHOS", "GATILHO_MENSAGEM", "GATILHO_REENGAJAMENTO", "HandoffAction", "HandoffNotFound", "HandoffRecord",
    "HttpAgentsClient", "IdempotencyConflict", "JuliaAction", "LeadDesconhecido", "LeadSemQualificacao", "LlmNotConfigured",
    "MAX_BATCH_MESSAGES", "MAX_MESSAGE_CHARS", "ParticipanteInfo", "ParticipanteNotFound", "QualificacaoEstado",
    "QualificacaoResumo", "ResumoRequest", "ResumoResult", "STATUS_RESPONDEU", "STATUS_SEM_ATENDIMENTO", "STATUS_LIMITE_PARA_HUMANO",
    "STATUS_TURNO", "ThreadInfo", "ThreadNotFound", "TransicaoInvalida", "TurnInProgress",
    "TurnMessage", "TurnRequest", "TurnResult", "make_agents_client", "parse_agent_status", "parse_consent",
    "parse_controle", "parse_decisao_result", "parse_estagios", "parse_handoff", "parse_qualificacao_estado", "parse_resumo_result",
    "parse_thread", "parse_turn_result", "parse_uso",
    "MOTIVO_ENCERRAR_PEDIU_PARAR", "ORIGENS_OPT_OUT", "ORIGEM_OPT_OUT_PADRAO", "OPT_OUT_MENSAGEM_MAX", "OPT_OUT_MOTIVO_MAX",
    "opt_out_body", "NOTIFICACAO_STATUS", "OptOutEvento", "OptOutEventoNotFound", "OptOutPagina", "REATIVACAO_MOTIVO_MAX",
    "ReativacaoResult", "SemOptOutAtivo", "TIPOS_OPT_OUT_EVENTO", "parse_opt_out_evento", "parse_opt_out_pagina",
    "parse_reativacao", "reativacao_motivo",
]
