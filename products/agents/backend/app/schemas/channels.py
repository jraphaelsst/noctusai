"""Schemas of the channel turn API (Lais contract §3.1 / §3.2 / §4; Julia v2 CONTRACT §8).

Request bodies are :class:`~noctusai_lib.api.StrictHttpModel` (``extra="forbid"``
→ 422 on an unknown field). The caps are the §10.1 M4 flood limits: a batch is
1..20 messages, each 1..8000 characters, 16 000 characters in total — enforced
here, BEFORE any model call or write.

**Turn v2** (Julia v2): ``lead`` identifies the lead (SW ``julia_contatos.id``), ``gatilho`` says why the
turn runs (``mensagem`` / ``reengajamento``) and ``contexto.estado`` carries the closed, typed operational
facts SW owns -- the attendant, the re-engagement flavour, the campaign property, the credit state. The v1
shape (no ``lead``/``gatilho``; ``contexto.perguntas|ferramentas|acoes|conhecimento_md``,
``estado.slots|operacao``) is still ACCEPTED for one release and ignored where v2 replaced it: the response
is v2 either way. The JSON Schema of the request/response is generated to
``products/agents/backend/contracts/channels.v2.json`` (drift-tested) -- SW validates against that file.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from noctusai_lib.api import StrictHttpModel

__all__ = [
    "ChannelUsoOut",
    "BATCH_MAX_CHARS",
    "BATCH_MAX_MESSAGES",
    "MESSAGE_MAX_CHARS",
    "CONTEXTO_MAX_CHARS",
    "CaptacaoActionOut",
    "ContextoCapacidades",
    "ContextoCredito",
    "ContextoOrigem",
    "ConsentimentoCreditoActionOut",
    "SolicitacaoTitularActionOut",
    "ChannelActionOut",
    "ChannelAgentStatusOut",
    "ChannelContexto",
    "ChannelContact",
    "ChannelDeleteRequest",
    "ChannelInboundMessage",
    "ChannelMidia",
    "ChannelLead",
    "ChannelRef",
    "ChannelReplyOut",
    "ChannelTokenCreateRequest",
    "ChannelTokenOut",
    "ChannelTurnRequest",
    "ChannelTurnResponse",
    "ChannelUsageOut",
    "ChannelResumoRequest",
    "ChannelResumoResponse",
    "ChannelResumoUsageOut",
    "ChannelToolsTokenRequest",
    "ConformidadeOut",
    "ContextoEstado",
    "ContextoPergunta",
    "EncerrarActionOut",
    "HandoffActionOut",
    "IntencaoVisitaActionOut",
    "LeadProntoActionOut",
    "ParticipanteOut",
    "QualificacaoOut",
    "EstagioOut",
    "ViolacaoOut",
]

BATCH_MAX_MESSAGES = 20
#: Input caps (guardrails B5). A lead is NEVER answered 422 for writing too much: an oversized message / batch is
#: truncated to the cap and the turn proceeds (the cut is the abuse bound; SW trims to the same numbers upstream).
MESSAGE_MAX_CHARS = 2000
BATCH_MAX_CHARS = 6000

#: Channels the turn API accepts (page 0: WhatsApp via WAHA / Cloud API).
Channel = Literal["whatsapp"]


class ChannelRef(StrictHttpModel):
    """The conversation identity within a channel: the connection (the number)
    and the chat on it. Unique per org + agent."""

    connection_id: UUID
    chat_id: str = Field(..., min_length=1, max_length=256)

    def canonical(self) -> dict[str, str]:
        return {"connection_id": str(self.connection_id), "chat_id": self.chat_id}


class ChannelContact(StrictHttpModel):
    """Display metadata only. NEVER put into a prompt (§10.1 M3)."""

    phone_e164: str | None = Field(default=None, max_length=32)
    display_name: str | None = Field(default=None, max_length=200)


MIDIA_TEXTO_MAX = 2000
MIDIA_LEGENDA_MAX = 1000


class ChannelMidia(StrictHttpModel):
    """The media a lead message carried, sent as DATA beside the text (guardrails B2): what SW extracted from it
    (transcription, OCR, a description) is never merged into ``texto`` with an in-band prefix, so typed text and
    media-derived text cannot be mistaken for each other."""

    tipo: Literal["audio", "imagem", "video", "documento"]
    texto_extraido: str = Field(default="", max_length=MIDIA_TEXTO_MAX)
    legenda: str | None = Field(default=None, max_length=MIDIA_LEGENDA_MAX)

    def canonical(self) -> dict[str, str]:
        return {k: v for k, v in (("tipo", self.tipo), ("texto_extraido", self.texto_extraido), ("legenda", self.legenda)) if v}


class ChannelInboundMessage(StrictHttpModel):
    """One message the LEAD sent. There is deliberately no author field: whatever arrives on this route is the lead
    speaking, whatever the text claims. Staff lines have their own route (``/api/channels/threads/{id}/mensagens``)."""

    #: Truncated (never rejected) at :data:`MESSAGE_MAX_CHARS`; may be empty ONLY when ``midia`` is present.
    texto: str = Field(default="")
    provider_message_id: str = Field(..., min_length=1, max_length=256)
    at: datetime
    #: Backward compatible: absent = the old ``texto``-only shape.
    midia: ChannelMidia | None = None
    #: ``True`` when ``texto`` was cut to the size cap (here, or by the batch cap). The turn tells the model, in DB
    #: wording (``historico.rotulo_truncado``), that this message is incomplete. Set by the truncation, not trusted
    #: from the sender: a sent ``true`` only adds the label.
    truncado: bool = False

    @model_validator(mode="after")
    def _not_blank(self) -> "ChannelInboundMessage":
        if not self.texto.strip() and self.midia is None:
            raise ValueError("texto must not be blank")
        if len(self.texto) > MESSAGE_MAX_CHARS:
            self.texto = self.texto[:MESSAGE_MAX_CHARS]
            self.truncado = True
        return self

    def assinatura(self) -> str:
        """What the idempotency ledger hashes: the text alone for a text-only message (unchanged hash for every
        message stored before ``midia`` existed), the text plus the media object otherwise."""
        if self.midia is None:
            return self.texto
        return self.texto + "\x1f" + json.dumps(self.midia.canonical(), ensure_ascii=False, sort_keys=True)

    def falas_do_lead(self) -> list[str]:
        """The texts the turn's detectors read as the lead's: the typed text and an AUDIO's transcription (spoken by
        the lead), plus any other media text for the injection / extraction signals only via :meth:`textos_de_entrada`."""
        out = [self.texto] if self.texto.strip() else []
        if self.midia is not None and self.midia.tipo == "audio" and self.midia.texto_extraido.strip():
            out.append(self.midia.texto_extraido)
        return out

    def textos_de_entrada(self) -> list[str]:
        """Every text that came in with the message (typed, extracted, caption): what the input-side tripwires scan."""
        out = [self.texto] if self.texto.strip() else []
        if self.midia is not None:
            out += [t for t in (self.midia.texto_extraido, self.midia.legenda) if t and t.strip()]
        return out


#: The whole `contexto` (as JSON) may not exceed this many characters (§2.1(a)).
CONTEXTO_MAX_CHARS = 80_000
_CONTEXTO_TOO_BIG = "contexto_grande"

Operacao = Literal["compra", "aluguel"]
#: v1 vocabularies, ACCEPTED (and ignored) on a v1-shaped request for one release.
_FerramentaV1 = Literal["buscar_imoveis", "detalhes_imovel", "horarios_visita", "consultar_empreendimento"]
_AcaoV1 = Literal[
    "salvar_slots", "definir_operacao", "qualificar_lead", "pedido_visita", "captacao", "encerrar",
    "consentimento_credito", "handoff",
]


class ContextoPergunta(StrictHttpModel):
    """v1 only (the essential questions): ignored by turn v2 -- the qualification standard replaced them."""

    chave: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=300)
    dica: str | None = Field(default=None, max_length=600)
    categoria: str = Field(..., min_length=1, max_length=64)
    qualificatoria: bool
    operacao: Operacao | None = None


class ContextoCredito(StrictHttpModel):
    """Wave 13: the credit-analysis state of an aluguel lead. ``consentimento`` is ``None`` until the
    lead answered; the model asks ONCE (before the visit) and records the answer with
    ``consentimento_credito``. Absent from ``estado`` when the org does not use the analysis."""

    ativo: bool
    consentimento: bool | None = None


class ContextoOrigem(StrictHttpModel):
    """Where the lead came from: the campaign property Julia opens the offer with."""

    canal_origem: str | None = Field(default=None, max_length=64)
    codigo_imovel_campanha: str | None = Field(default=None, max_length=64)


class ContextoEstado(StrictHttpModel):
    """The operational state SW owns, closed and typed (no free-form keys: an unknown one is a 422).

    ``atendente_nome`` and the re-engagement flavour (``reengajamento`` / ``reescrever`` / ``texto_base`` /
    ``tentativa``) used to be stripped by SW because agents forbade them (NOC-REMEDIATE
    [julia-v2-reengajamento-contexto], closed here): they are now fields, rendered by DB texts."""

    #: v1 (recorded slots / operation): accepted, ignored -- the dossier is the qualification state.
    slots: dict[str, str] = Field(default_factory=dict)
    operacao: Literal["compra", "aluguel", "administracao"] | None = None
    interacao_id: UUID
    encerrado: bool
    credito: ContextoCredito | None = None
    #: The human attendant who owns the chat (a fact for the model, never a command).
    atendente_nome: str | None = Field(default=None, min_length=1, max_length=120)
    #: A re-engagement turn: the flow that triggered it (matches the turn's ``gatilho``).
    reengajamento: Literal["minutos", "horas", "regua"] | None = None
    #: The template text of a regua attempt (``reescrever``: put it in the agent's voice, same facts).
    reescrever: bool = False
    texto_base: str | None = Field(default=None, min_length=1, max_length=2000)
    tentativa: int | None = Field(default=None, ge=1, le=100)
    origem: ContextoOrigem | None = None


class ContextoCapacidades(StrictHttpModel):
    """What SW can do right now (not what the model must): ``ferramentas_sw=False`` withholds the CRM tools."""

    ferramentas_sw: bool = True


class ChannelContexto(StrictHttpModel):
    """SW-rendered per-turn context (§2.1(a)); ``extra="forbid"`` at every level."""

    hash: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    #: v1 (knowledge moved to the org specs; essential questions to the standard; tool/action lists to
    #: the agent version's tool rows): accepted, ignored.
    conhecimento_md: str = Field(default="", max_length=60_000)
    perguntas: list[ContextoPergunta] = Field(default_factory=list, max_length=8)
    ferramentas: list[_FerramentaV1] = Field(default_factory=list)
    acoes: list[_AcaoV1] = Field(default_factory=list)
    estado: ContextoEstado
    capacidades: ContextoCapacidades = Field(default_factory=ContextoCapacidades)
    agora: datetime
    fuso: Literal["America/Sao_Paulo"]

    @model_validator(mode="after")
    def _size_cap(self) -> "ChannelContexto":
        if len(self.model_dump_json()) > CONTEXTO_MAX_CHARS:
            raise ValueError(_CONTEXTO_TOO_BIG)
        return self


class ChannelLead(StrictHttpModel):
    """Who the lead is: SW ``julia_contatos.id`` is authoritative (the agents ``lead_refs.ref_externa``)."""

    ref: str = Field(..., min_length=1, max_length=256)
    crm_lead_id: UUID | None = None


def _truncar_lote(messages: list[ChannelInboundMessage]) -> list[ChannelInboundMessage]:
    """Keep the batch within :data:`BATCH_MAX_CHARS`: the earliest messages keep their text, the later ones are cut to
    what is left (at least one character each, so every ``provider_message_id`` still answers idempotently)."""
    if sum(len(m.texto) for m in messages) <= BATCH_MAX_CHARS:
        return messages
    out: list[ChannelInboundMessage] = []
    restante = BATCH_MAX_CHARS
    for i, m in enumerate(messages):
        reservado = len(messages) - i - 1  # one character for each message still to come
        permitido = max(1, min(len(m.texto), restante - reservado))
        out.append(m if permitido >= len(m.texto) else m.model_copy(update={"texto": m.texto[:permitido], "truncado": True}))
        restante -= permitido
    return out


class ChannelTurnRequest(StrictHttpModel):
    agent_key: str = Field(..., min_length=1, max_length=64)
    channel: Channel
    channel_ref: ChannelRef
    contact: ChannelContact = Field(default_factory=ChannelContact)
    #: v2: the lead. A v1-shaped request without it is keyed by its ``channel_ref`` (one release).
    lead: ChannelLead | None = None
    #: Why the turn runs. A ``reengajamento`` turn has no new lead message (``messages`` may be empty).
    gatilho: Literal["mensagem", "reengajamento"] = "mensagem"
    messages: list[ChannelInboundMessage] = Field(default_factory=list, max_length=BATCH_MAX_MESSAGES)
    #: Lais F-AG (§2.1(a)): optional; absent = page-0 behaviour.
    contexto: ChannelContexto | None = None

    @model_validator(mode="after")
    def _batch_caps(self) -> "ChannelTurnRequest":
        if self.gatilho == "mensagem" and not self.messages:
            raise ValueError("a message turn needs at least one message")
        if self.gatilho == "reengajamento" and self.contexto is None:
            raise ValueError("a re-engagement turn needs contexto")
        self.messages = _truncar_lote(self.messages)
        ids = [m.provider_message_id for m in self.messages]
        if len(set(ids)) != len(ids):
            raise ValueError("provider_message_id must be unique within a batch")
        return self


class ChannelReplyOut(BaseModel):
    partes: list[str]


class _ActionOut(BaseModel):
    #: Order of the action within the turn (1-based). Default 0 only so a reply
    #: stored by a pre-F-AG turn still replays.
    seq: int = Field(default=0, ge=0)


class HandoffActionOut(_ActionOut):
    type: Literal["handoff"]
    #: Typed reason (the code is an enum in the tool schema; its label is a DB row).
    motivo_codigo: str
    motivo: str


class LeadProntoActionOut(_ActionOut):
    """``concluir_qualificacao`` took effect (code-gated on a ``conclusivo`` computed stage)."""

    type: Literal["lead_pronto"]
    estagio: str
    score: int
    valores: dict[str, Any]
    imoveis_gostou: list[str]
    intencoes_visita: list[str]


class IntencaoVisitaActionOut(_ActionOut):
    """The lead wants to visit property ``codigo``. Nothing is scheduled (D11)."""

    type: Literal["intencao_visita"]
    codigo: str
    preferencia_horario: str | None = None


class CaptacaoActionOut(_ActionOut):
    type: Literal["captacao"]
    descricao: str
    endereco: str | None = None
    operacao: Literal["venda", "aluguel"] | None = None


class EncerrarActionOut(_ActionOut):
    type: Literal["encerrar"]
    motivo: Literal["lead_encerrou", "sem_interesse", "invalido", "outro", "lead_pediu_parar"]
    #: The lead asked to stop: a lead-level opt-out was recorded (every agent stops, the owner was notified).
    lead_opt_out: bool = False


class ConsentimentoCreditoActionOut(_ActionOut):
    type: Literal["consentimento_credito"]
    aceito: bool
    #: The lead's own words (from the turn's batch) that answer the consent question: SW stores a hash + the
    #: message id as the evidence of the decision.
    trecho: str | None = None


class SolicitacaoTitularActionOut(_ActionOut):
    """A data-subject request was recorded on SW's side (``registrar_solicitacao_titular``) and the lead handed to a
    person (``handoff`` with ``motivo_codigo="direito_titular"`` rides next to it). Nothing was erased."""

    type: Literal["solicitacao_titular"]
    tipo: Literal[
        "confirmacao", "acesso", "correcao", "eliminacao", "portabilidade", "revogacao_consentimento", "oposicao",
        "info_compartilhamento", "outro",
    ]
    id: str
    prazo_em: str | None = None


#: Discriminated union on ``type`` (§2.1(d)).
ChannelActionOut = Annotated[
    Union[
        HandoffActionOut, LeadProntoActionOut, IntencaoVisitaActionOut, CaptacaoActionOut, EncerrarActionOut,
        ConsentimentoCreditoActionOut, SolicitacaoTitularActionOut,
    ],
    Field(discriminator="type"),
]


class ChannelUsageOut(BaseModel):
    custo_usd: float | None = None
    tokens_entrada: int | None = None
    tokens_saida: int | None = None


class ParticipanteOut(BaseModel):
    agent_key: str
    estado: Literal["ativo", "pausado", "concluido", "encerrado", "transferido"]


class QualificacaoOut(BaseModel):
    """The computed state after the turn (SW mirrors it; it never acts on a model's say-so)."""

    versao: str | None = None
    estagio: str
    score: int
    faltando: list[str]
    #: The pinned standard's stage KEYS in order (low to high), so a consumer can read ``estagio_minimo`` as
    #: "this stage or beyond" without holding a copy of the standard. Keys only.
    estagios_ordem: list[str] = Field(default_factory=list)


class EstagioOut(BaseModel):
    """One stage of the pinned standard as a consumer may see it: label and order only -- never the rule,
    points or the description (platform IP, CONTRACT 0.4)."""

    chave: str
    rotulo: str
    ordem: int
    conclusivo: bool


class ViolacaoOut(BaseModel):
    regra: str
    politica: Literal["registrar", "bloquear", "sinal"]
    bloqueada: bool = False


class ConformidadeOut(BaseModel):
    violacoes: list[ViolacaoOut] = Field(default_factory=list)


#: The turn's outcome. ``respondido`` / ``silencio`` / ``handoff`` / ``encerrado`` / ``concluido`` are turns
#: the model ran; every other value is a control or limit that answered WITHOUT running it (nothing is sent).
TurnStatus = Literal[
    "respondido", "silencio", "handoff", "encerrado", "concluido",
    "agente_desligado", "novo_lead_recusado", "conversa_pausada", "conversa_com_outro_responsavel",
    "conversa_com_outro_agente", "reengajamento_ignorado", "lead_opt_out", "limite_atingido",
    # abuse protection (guardrails B5): SW routes each to a human, never to silence
    "limite_taxa", "novo_lead_limitado", "loop_detectado",
]


class ChannelTurnResponse(BaseModel):
    #: ``None`` only when a brand-new lead was refused (nothing was stored).
    thread_id: UUID | None = None
    #: Alias of ``thread_id`` for one release.
    conversation_id: UUID | None = None
    status: TurnStatus
    reply: ChannelReplyOut
    actions: list[ChannelActionOut]
    participante: ParticipanteOut | None = None
    qualificacao: QualificacaoOut | None = None
    conformidade: ConformidadeOut = Field(default_factory=ConformidadeOut)
    usage: ChannelUsageOut = Field(default_factory=ChannelUsageOut)


class ChannelAgentStatusOut(BaseModel):
    agent_key: str
    nome: str
    #: Kept for one release; ``modo`` is the control.
    ativo: bool
    versao_ativa: int | None
    provider: str | None
    model: str | None
    llm_configurado: bool
    modo: Literal["ligado", "drenando", "desligado"] = "desligado"
    aceita_novos_leads: bool = False
    threads_abertas: int = 0
    #: Every required text/spec is filled: a turn would not answer 409 ``conteudo_incompleto``.
    conteudo_completo: bool = False


class ChannelUsoOut(BaseModel):
    """``GET /api/channels/uso`` — the org's channel usage for one month."""

    turnos: int
    custo_usd: float
    limite_diario_usd: float


class ChannelDeleteRequest(StrictHttpModel):
    """``DELETE /api/channels/conversations`` — deletion on request (LGPD)."""

    agent_key: str = Field(..., min_length=1, max_length=64)
    channel: Channel
    channel_ref: ChannelRef


class ChannelTokenCreateRequest(StrictHttpModel):
    product: Literal["social-wiring"]
    label: str = Field(..., min_length=1, max_length=120)


class ChannelTokenOut(BaseModel):
    """Returned ONCE at mint. ``token`` is never retrievable again."""

    id: UUID
    token: str
    prefix: str
    expires_at: datetime
    scopes: list[str]


class ChannelResumoRequest(StrictHttpModel):
    """``POST /api/channels/threads/{id}/resumo`` (also ``/conversations/{id}/resumo``): a narrative only --
    the criteria come from the qualification records, never from this call."""

    #: v1 (essential questions): accepted, ignored.
    perguntas: list[ContextoPergunta] = Field(default_factory=list, max_length=8)
    desde: datetime | None = None


class ChannelResumoUsageOut(BaseModel):
    custo_usd: float | None = None
    tokens_entrada: int | None = None
    tokens_saida: int | None = None


class ChannelResumoResponse(BaseModel):
    resumo: str
    #: Display only -- SW never acts on it (the computed stage does).
    desfecho_sugerido: Literal["qualificado", "frio", "captacao", "invalido", "em_andamento"]
    usage: ChannelResumoUsageOut


#: A decision key: the agent version's ``agent_version_decisoes.chave``.
DECISAO_CHAVE_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
_OPCAO_PATTERN = r"^[a-z0-9_]{1,40}$"
DecisaoValor = Union[str, int, float, bool, None]


class ChannelDecisaoRequest(StrictHttpModel):
    """``POST /api/channels/agents/{agent_key}/decisoes/{chave}``: pick ONE of ``opcoes`` for ``dados`` by the
    rule of the agent version's decision row (``agent_version_decisoes``). No rule travels with the call."""

    opcoes: list[Annotated[str, Field(pattern=_OPCAO_PATTERN)]] = Field(..., min_length=2, max_length=10)
    dados: dict[Annotated[str, Field(max_length=60)], DecisaoValor] = Field(default_factory=dict, max_length=30)
    #: v1 (the caller's built-in rule): accepted, ignored -- the rule is the version's, and the fallback
    #: is the option the row flags ``padrao`` (D13).
    regra_padrao: str | None = Field(default=None, max_length=2000)

    @field_validator("opcoes")
    @classmethod
    def _opcoes_unicas(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("opcoes repetidas")
        return v

    @field_validator("dados")
    @classmethod
    def _dados_curtos(cls, v: dict[str, Any]) -> dict[str, Any]:
        if any(isinstance(x, str) and len(x) > 500 for x in v.values()):
            raise ValueError("valor de dados acima de 500 caracteres")
        return v


class ChannelDecisaoResponse(BaseModel):
    escolha: str
    motivo: str
    #: ``versao`` = the model decided by the version's rule; ``padrao_da_versao`` = the row's ``padrao``
    #: option answered (no rule written, or the model could not decide).
    regra: Literal["versao", "padrao_da_versao"]
    usage: ChannelResumoUsageOut


class ChannelToolsTokenRequest(StrictHttpModel):
    """``PUT /api/channels/ferramentas-token`` (§2.1(f))."""

    token: str = Field(..., min_length=8, max_length=4096)
