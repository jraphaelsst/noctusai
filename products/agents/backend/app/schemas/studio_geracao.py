"""Pydantic schemas of the AI draft generation API (S3a; ``app.routers.studio_geracoes_router``).

Request bodies are :class:`~noctusai_lib.api.StrictHttpModel` (``extra="forbid"`` -> 422). The per-area MODEL
OUTPUT schemas (what the generator must answer with) live here too: they are BE-owned, validated by the SAME
item models the draft routers validate their bodies with (``FerramentaIn`` / ``DecisaoIn`` / ``SpecDefIn`` /
``SectionIn``), so a generated row can never be one the manual route would refuse.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.studio import SLUG_PATTERN
from app.schemas.studio_conteudo import CHAVE_TEXTO_PATTERN, DecisaoIn, FerramentaIn, SpecDefIn
from app.studio.models import LIMITS
from noctusai_lib.api import StrictHttpModel

Area = Literal["secoes", "textos", "ferramentas", "decisoes", "specs", "skills", "configuracoes"]
GeracaoStatus = Literal["pendente", "executando", "concluida", "parcial", "falhou", "cancelada"]
AreaStatus = Literal["pendente", "executando", "concluida", "falhou", "pulado", "cancelada"]
Canal = Literal["whatsapp", "web", "interno"]

LIMITE_USD_PADRAO = 5.0


class Briefing(StrictHttpModel):
    # ``title`` = the pt-BR label forms show (`app.studio.modelo` serves it as ``rotulo``).
    nome: str = Field(..., min_length=1, max_length=80, title="Nome")
    objetivo: str = Field(..., min_length=10, max_length=600, title="Objetivo")
    publico: str = Field(..., min_length=3, max_length=300, title="Público atendido")
    canal: Canal = Field(..., title="Canal principal")
    idioma: str = Field(default="pt-BR", min_length=2, max_length=20, title="Idioma")
    tom_de_voz: str | None = Field(default=None, max_length=300, title="Tom de voz")
    limites: str | None = Field(default=None, max_length=1000, title="Limites")
    exemplos: str | None = Field(default=None, max_length=4000, title="Exemplos")


class GeracaoCreateRequest(StrictHttpModel):
    briefing: Briefing
    areas: list[Area] | None = None
    forcar: bool = False
    limite_usd: float = Field(default=LIMITE_USD_PADRAO, gt=0, le=LIMITE_USD_PADRAO)


class RepetirRequest(StrictHttpModel):
    forcar: bool = False


# ── outputs ─────────────────────────────────────────────────────────────────


class ItemGeradoOut(BaseModel):
    chave: str
    estado: Literal["gerado", "editado"]


class AreaOut(BaseModel):
    area: Area
    status: AreaStatus
    erro: str | None
    custo_usd: float
    itens_escritos: int
    itens: list[ItemGeradoOut]
    lacunas: list[str]
    concluido_em: datetime | None


class GeracaoOut(BaseModel):
    id: UUID
    agent_key: str
    status: GeracaoStatus
    versao_gerador: int | None
    modelo: str
    briefing: Briefing
    custo_usd: float
    limite_usd: float
    criado_em: datetime
    iniciado_em: datetime | None
    concluido_em: datetime | None
    erro: str | None
    areas: list[AreaOut]


class GeracoesOut(BaseModel):
    items: list[GeracaoOut]


# ── model output (validated, BE-owned) ──────────────────────────────────────


class _Saida(BaseModel):
    """The generator's JSON answers: unknown top-level keys are ignored (models add noise); every KNOWN field is
    typed and capped. ``lacunas`` = needs the generator could not cover (reported to the author, never invented)."""

    model_config = ConfigDict(extra="ignore")
    lacunas: list[str] = Field(default_factory=list, max_length=50)


class Plano(_Saida):
    persona: str = Field(default="", max_length=2000)
    objetivos: list[str] = Field(default_factory=list, max_length=12)
    #: per-area guidance carried into that area's call (keys: Area names)
    diretrizes: dict[str, str] = Field(default_factory=dict)


class SecaoGerada(BaseModel):
    model_config = ConfigDict(extra="ignore")
    chave: str = Field(..., min_length=1, max_length=64, pattern=SLUG_PATTERN)
    titulo: str = Field(..., min_length=1, max_length=200)
    conteudo: str = Field(..., max_length=LIMITS["section.conteudo"])
    ordem: int | None = None
    ativo: bool = True


class SaidaSecoes(_Saida):
    secoes: list[SecaoGerada] = Field(..., min_length=1, max_length=40)


class TextoGerado(BaseModel):
    model_config = ConfigDict(extra="ignore")
    chave: str = Field(..., pattern=CHAVE_TEXTO_PATTERN, max_length=120)
    conteudo: str = Field(..., max_length=LIMITS["texto.conteudo"])


class SaidaTextos(_Saida):
    textos: list[TextoGerado] = Field(..., min_length=1, max_length=400)


class SaidaFerramentas(_Saida):
    ferramentas: list[FerramentaIn] = Field(..., max_length=60)


class SaidaDecisoes(_Saida):
    decisoes: list[DecisaoIn] = Field(..., max_length=40)


class SaidaSpecs(_Saida):
    specs: list[SpecDefIn] = Field(..., max_length=40)


class SkillEscolhida(BaseModel):
    model_config = ConfigDict(extra="ignore")
    chave: str = Field(..., max_length=64, pattern=SLUG_PATTERN)
    obrigatoria_para: list[str] = Field(default_factory=list, max_length=32)
    racional: str = Field(..., min_length=1, max_length=600)


class SaidaSkills(_Saida):
    skills: list[SkillEscolhida] = Field(..., max_length=30)


class SaidaConfiguracoes(_Saida):
    provider: str | None = None
    model: str | None = None
    effort: str | None = None
    max_turns: int | None = Field(default=None, ge=1, le=200)
    idioma: str | None = Field(default=None, max_length=20)
    tool_policy: dict[str, Any] | None = None
    notas: str | None = Field(default=None, max_length=LIMITS.get("version.notas", 2000))


#: Area -> the model with its output schema (``model_json_schema()`` is handed to the generator as DATA).
SAIDAS: dict[str, type[_Saida]] = {
    "secoes": SaidaSecoes, "textos": SaidaTextos, "ferramentas": SaidaFerramentas, "decisoes": SaidaDecisoes,
    "specs": SaidaSpecs, "skills": SaidaSkills, "configuracoes": SaidaConfiguracoes,
}
