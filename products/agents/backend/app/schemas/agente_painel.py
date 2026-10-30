"""DTOs of the unified agent model + painel (agents-unified CONTRACT §2-§4). Response models are explicit
allowlists: the org-tier painel carries display fields only -- never an instruction, a rule or a tool description."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.agents import EstadoExternoOut

Origem = Literal["legado", "plataforma", "instancia", "org"]
Tier = Literal["membro", "org_admin", "plataforma"]


# ── GET /api/studio/modelo ──────────────────────────────────────────────────


class CampoModeloOut(BaseModel):
    chave: str
    rotulo: str
    tipo: Literal["texto", "numero", "booleano", "escolha", "lista", "objeto"]
    obrigatorio: bool
    max_length: int | None = None
    #: The limits a form needs to block what the create route would 422 (read from the Pydantic field).
    min_length: int | None = None
    pattern: str | None = None
    minimo: float | None = None
    minimo_exclusivo: float | None = None
    maximo: float | None = None
    #: The field's default (scalars only), so a form starts from what the server would use.
    padrao: str | float | bool | None = None
    opcoes: list[str] | None = None
    #: wizard fields only: ``plataforma`` (create body) | ``briefing`` (its ``briefing``)
    modelo: Literal["plataforma", "briefing"] | None = None


class SecaoModeloOut(BaseModel):
    id: str
    titulo: str
    grupo: Literal["painel", "conteudo", "operacao", "organizacao"]
    tier: Tier
    origens: list[Origem]
    area: str | None
    exige: list[str]


class AreaModeloOut(BaseModel):
    id: str
    titulo: str
    descricao: str
    ordem: int
    multiplas_linhas: bool
    campos: list[CampoModeloOut]
    enumeracao: dict[str, Any] | None
    secoes: list[str]


class PassoAssistenteOut(BaseModel):
    id: str
    titulo: str
    categoria: Literal["quem", "como", "o_que", "fechamento"]
    descricao: str
    ordem: int
    campos: list[CampoModeloOut]
    areas: list[str]
    nota: str | None


class AssistenteModeloOut(BaseModel):
    passos: list[PassoAssistenteOut]


class AgenteModeloOut(BaseModel):
    versao: int
    tier: Tier
    conteudo_modo: Literal["linhas"]
    origens: list[Origem]
    secoes: list[SecaoModeloOut]
    areas: list[AreaModeloOut]
    assistente: AssistenteModeloOut | None


# ── GET /api/agents/painel · /api/agents/{key}/painel ───────────────────────


class AgentePainelOut(BaseModel):
    """One agent card / page header. Display-level only, for any org member."""

    key: str
    nome: str
    descricao: str | None
    papel: str | None
    capacidades: list[str] = Field(default_factory=list)
    origem: Origem
    tipo: str
    runtime: str
    owner_product: str | None
    usa_canais: bool
    ativo: bool
    #: an external agent (One Chat): the owning product's live state, or ``aviso`` when unreachable/unconfigured
    estado_externo: EstadoExternoOut | None = None
    aviso: str | None = None
    #: the page sections THIS caller may open on THIS agent, in page order (``GET /api/studio/modelo`` titles them)
    secoes: list[str]
    #: the caller may switch it on/off through ``POST /api/agents/{key}/toggle`` (a legado agent, org admin)
    pode_alternar: bool


class AgentesPainelOut(BaseModel):
    items: list[AgentePainelOut]
    total: int


# ── GET /api/agents/{key}/painel/interno (superadmin, D31) ──────────────────


class AgenteInternoOut(BaseModel):
    key: str
    origem: Origem
    definition_scope: str
    conteudo_modo: str
    versao_ativa: int | None
    tem_rascunho: bool
    publicacao_limiar: float | None
    conteudo_status: dict[str, Any] | None
