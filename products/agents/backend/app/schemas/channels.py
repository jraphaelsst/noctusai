"""Schemas of the channel turn API (Lais contract §3.1 / §3.2 / §4).

Request bodies are :class:`~noctusai_lib.api.StrictHttpModel` (``extra="forbid"``
→ 422 on an unknown field). The caps are the §10.1 M4 flood limits: a batch is
1..20 messages, each 1..8000 characters, 16 000 characters in total — enforced
here, BEFORE any model call or write.
"""
from __future__ import annotations

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
    "ACAO_NAMES",
    "CONTEXTO_MAX_CHARS",
    "FERRAMENTA_NAMES",
    "ActionArgs",
    "CaptacaoActionOut",
    "ContextoCredito",
    "ConsentimentoCreditoActionOut",
    "ChannelActionOut",
    "ChannelAgentStatusOut",
    "ChannelContexto",
    "ChannelContact",
    "ChannelDeleteRequest",
    "ChannelInboundMessage",
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
    "ContextoEstado",
    "ContextoPergunta",
    "DefinirOperacaoActionOut",
    "EncerrarActionOut",
    "HandoffActionOut",
    "PedidoVisitaActionOut",
    "QualificarLeadActionOut",
    "SalvarSlotsActionOut",
]

BATCH_MAX_MESSAGES = 20
MESSAGE_MAX_CHARS = 8000
BATCH_MAX_CHARS = 16_000

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


class ChannelInboundMessage(StrictHttpModel):
    texto: str = Field(..., min_length=1, max_length=MESSAGE_MAX_CHARS)
    provider_message_id: str = Field(..., min_length=1, max_length=256)
    at: datetime

    @field_validator("texto")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("texto must not be blank")
        return v


#: The whole `contexto` (as JSON) may not exceed this many characters (§2.1(a)).
CONTEXTO_MAX_CHARS = 80_000
_CONTEXTO_TOO_BIG = "contexto_grande"

Operacao = Literal["compra", "aluguel"]
FerramentaName = Literal["buscar_imoveis", "detalhes_imovel", "horarios_visita", "consultar_empreendimento"]
AcaoName = Literal[
    "salvar_slots", "definir_operacao", "qualificar_lead", "pedido_visita", "captacao", "encerrar", "consentimento_credito", "handoff"
]
FERRAMENTA_NAMES: tuple[str, ...] = (
    "buscar_imoveis", "detalhes_imovel", "horarios_visita", "consultar_empreendimento",
)
ACAO_NAMES: tuple[str, ...] = (
    "salvar_slots", "definir_operacao", "qualificar_lead", "pedido_visita", "captacao", "encerrar", "consentimento_credito", "handoff",
)


class ContextoPergunta(StrictHttpModel):
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


class ContextoEstado(StrictHttpModel):
    slots: dict[str, str] = Field(default_factory=dict)
    operacao: Literal["compra", "aluguel", "administracao"] | None = None
    interacao_id: UUID
    encerrado: bool
    credito: ContextoCredito | None = None


class ChannelContexto(StrictHttpModel):
    """SW-rendered per-turn context (§2.1(a)); ``extra="forbid"`` at every level."""

    hash: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    conhecimento_md: str = Field(default="", max_length=60_000)
    perguntas: list[ContextoPergunta] = Field(default_factory=list, max_length=8)
    estado: ContextoEstado
    ferramentas: list[FerramentaName] = Field(default_factory=list)
    acoes: list[AcaoName] = Field(default_factory=list)
    agora: datetime
    fuso: Literal["America/Sao_Paulo"]

    @model_validator(mode="after")
    def _size_cap(self) -> "ChannelContexto":
        if len(self.model_dump_json()) > CONTEXTO_MAX_CHARS:
            raise ValueError(_CONTEXTO_TOO_BIG)
        return self


class ChannelTurnRequest(StrictHttpModel):
    agent_key: str = Field(..., min_length=1, max_length=64)
    channel: Channel
    channel_ref: ChannelRef
    contact: ChannelContact = Field(default_factory=ChannelContact)
    messages: list[ChannelInboundMessage] = Field(..., min_length=1, max_length=BATCH_MAX_MESSAGES)
    #: Lais F-AG (§2.1(a)): optional; absent = page-0 behaviour.
    contexto: ChannelContexto | None = None

    @model_validator(mode="after")
    def _batch_caps(self) -> "ChannelTurnRequest":
        total = sum(len(m.texto) for m in self.messages)
        if total > BATCH_MAX_CHARS:
            raise ValueError(f"the batch holds {total} characters; the maximum is {BATCH_MAX_CHARS}")
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
    motivo: str


class SalvarSlotsActionOut(_ActionOut):
    type: Literal["salvar_slots"]
    slots: dict[str, str]


class DefinirOperacaoActionOut(_ActionOut):
    type: Literal["definir_operacao"]
    operacao: Literal["compra", "aluguel", "administracao", "atualizacao"]


class QualificarLeadActionOut(_ActionOut):
    type: Literal["qualificar_lead"]
    motivo: str


class PedidoVisitaActionOut(_ActionOut):
    type: Literal["pedido_visita"]
    codigo_imovel: str | None = None
    inicio: datetime
    fim: datetime
    cpf: str | None = None


class CaptacaoActionOut(_ActionOut):
    type: Literal["captacao"]
    descricao: str
    endereco: str | None = None
    operacao: Literal["venda", "aluguel"] | None = None


class EncerrarActionOut(_ActionOut):
    type: Literal["encerrar"]
    motivo: Literal["lead_encerrou", "sem_interesse", "invalido", "outro"]


class ConsentimentoCreditoActionOut(_ActionOut):
    type: Literal["consentimento_credito"]
    aceito: bool


#: Discriminated union on ``type`` (§2.1(d)).
ChannelActionOut = Annotated[
    Union[
        HandoffActionOut, SalvarSlotsActionOut, DefinirOperacaoActionOut, QualificarLeadActionOut,
        PedidoVisitaActionOut, CaptacaoActionOut, EncerrarActionOut, ConsentimentoCreditoActionOut,
    ],
    Field(discriminator="type"),
]

#: Model-facing argument schemas of the action tools (strict: the model's
#: arguments are validated BEFORE anything is recorded).
ActionArgs = {
    "salvar_slots": SalvarSlotsActionOut,
    "definir_operacao": DefinirOperacaoActionOut,
    "qualificar_lead": QualificarLeadActionOut,
    "pedido_visita": PedidoVisitaActionOut,
    "captacao": CaptacaoActionOut,
    "encerrar": EncerrarActionOut,
    "consentimento_credito": ConsentimentoCreditoActionOut,
}


class ChannelUsageOut(BaseModel):
    custo_usd: float | None = None
    tokens_entrada: int | None = None
    tokens_saida: int | None = None


class ChannelTurnResponse(BaseModel):
    conversation_id: UUID
    reply: ChannelReplyOut
    actions: list[ChannelActionOut]
    status: Literal["respondido", "silencio", "handoff", "encerrado"]
    usage: ChannelUsageOut


class ChannelAgentStatusOut(BaseModel):
    agent_key: str
    nome: str
    ativo: bool
    versao_ativa: int | None
    provider: str | None
    model: str | None
    llm_configurado: bool


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
    """``POST /api/channels/conversations/{id}/resumo`` (§2.1(e))."""

    perguntas: list[ContextoPergunta] = Field(default_factory=list, max_length=8)
    desde: datetime | None = None


class ChannelResumoUsageOut(BaseModel):
    custo_usd: float | None = None
    tokens_entrada: int | None = None
    tokens_saida: int | None = None


class ChannelResumoResponse(BaseModel):
    resumo: str
    slots: dict[str, str]
    operacao: str | None = None
    intencoes: list[Literal["encerrar", "captacao", "cobranca_atendimento", "parceria", "visita", "reclamacao"]]
    desfecho: Literal["qualificado", "frio", "captacao", "invalido", "em_andamento"]
    usage: ChannelResumoUsageOut


#: A decision key: the agent's prompt section ``decisao-<chave>`` holds its rule.
DECISAO_CHAVE_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
_OPCAO_PATTERN = r"^[a-z0-9_]{1,40}$"
DecisaoValor = Union[str, int, float, bool, None]


class ChannelDecisaoRequest(StrictHttpModel):
    """``POST /api/channels/agents/{agent_key}/decisoes/{chave}``: pick ONE of
    ``opcoes`` for ``dados`` by the rule the owner wrote in the agent's prompt
    section ``decisao-<chave>``; ``regra_padrao`` (the caller's built-in rule)
    applies only while the published version has no such section."""

    opcoes: list[Annotated[str, Field(pattern=_OPCAO_PATTERN)]] = Field(..., min_length=2, max_length=10)
    dados: dict[Annotated[str, Field(max_length=60)], DecisaoValor] = Field(default_factory=dict, max_length=30)
    regra_padrao: str = Field(..., min_length=1, max_length=2000)

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
    #: ``secao`` = the owner's prompt section decided; ``padrao`` = the caller's ``regra_padrao``.
    regra: Literal["secao", "padrao"]
    usage: ChannelResumoUsageOut


class ChannelToolsTokenRequest(StrictHttpModel):
    """``PUT /api/channels/ferramentas-token`` (§2.1(f))."""

    token: str = Field(..., min_length=8, max_length=4096)
