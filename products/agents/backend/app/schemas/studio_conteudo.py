"""Pydantic schemas for the Julia v2 content API (CONTRACT §2.4, §2.6).

Request bodies are :class:`~noctusai_lib.api.StrictHttpModel` (``extra="forbid"`` → 422). The
write routes are REPLACE-SET (the body is the whole set for that table of the draft), exactly like
``PUT .../draft/sections``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.studio.models import LIMITS, SPEC_TIPOS
from noctusai_lib.api import StrictHttpModel

CHAVE_TEXTO_PATTERN = r"^[a-z0-9]+(\.[a-z0-9_]+)+$"
FERRAMENTA_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"
DECISAO_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
SPEC_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"


# ── inputs ──────────────────────────────────────────────────────────────────


class TextoIn(StrictHttpModel):
    chave: str = Field(..., pattern=CHAVE_TEXTO_PATTERN, max_length=120)
    conteudo: str = Field(default="", max_length=LIMITS["texto.conteudo"])


class TextosReplaceRequest(StrictHttpModel):
    itens: list[TextoIn]
    #: Optimistic lock: the draft's ``compiled_hash`` as the caller last read it. A different current hash
    #: (someone else wrote in between) answers 409 ``conflito_de_versao``. ``null`` = no check.
    expected_hash: str | None = Field(default=None, max_length=128)


class FerramentaIn(StrictHttpModel):
    ferramenta: str = Field(..., pattern=FERRAMENTA_PATTERN)
    ativo: bool = True
    descricao: str = Field(..., min_length=1, max_length=LIMITS["ferramenta.descricao"])
    parametros: dict[str, str] = Field(default_factory=dict)
    obrigatoria_skill: str | None = Field(default=None, max_length=64)


class FerramentasReplaceRequest(StrictHttpModel):
    itens: list[FerramentaIn]
    #: Optimistic lock: the draft's ``compiled_hash`` as the caller last read it. A different current hash
    #: (someone else wrote in between) answers 409 ``conflito_de_versao``. ``null`` = no check.
    expected_hash: str | None = Field(default=None, max_length=128)


class OpcaoIn(StrictHttpModel):
    valor: str = Field(..., min_length=1, max_length=120)
    rotulo: str = Field(..., max_length=200)
    padrao: bool = False


class DecisaoIn(StrictHttpModel):
    chave: str = Field(..., pattern=DECISAO_PATTERN, max_length=80)
    titulo: str = Field(..., min_length=1, max_length=200)
    regra: str = Field(default="", max_length=LIMITS["decisao.regra"])
    opcoes: list[OpcaoIn] = Field(default_factory=list)


class DecisoesReplaceRequest(StrictHttpModel):
    itens: list[DecisaoIn]
    #: Optimistic lock: the draft's ``compiled_hash`` as the caller last read it. A different current hash
    #: (someone else wrote in between) answers 409 ``conflito_de_versao``. ``null`` = no check.
    expected_hash: str | None = Field(default=None, max_length=128)


class SpecDefIn(StrictHttpModel):
    chave: str = Field(..., pattern=SPEC_PATTERN)
    rotulo: str = Field(..., min_length=1, max_length=200)
    descricao: str = Field(default="", max_length=LIMITS["spec.descricao"])
    tipo: str = Field(default="texto")
    obrigatoria: bool = True
    exemplo: str | None = Field(default=None, max_length=LIMITS["spec.exemplo"])

    @field_validator("tipo")
    @classmethod
    def _tipo(cls, v: str) -> str:
        if v not in SPEC_TIPOS:
            raise ValueError(f"tipo must be one of {SPEC_TIPOS}")
        return v


class SpecsReplaceRequest(StrictHttpModel):
    itens: list[SpecDefIn]
    #: Optimistic lock: the draft's ``compiled_hash`` as the caller last read it. A different current hash
    #: (someone else wrote in between) answers 409 ``conflito_de_versao``. ``null`` = no check.
    expected_hash: str | None = Field(default=None, max_length=128)


class OrgSpecsUpdateRequest(StrictHttpModel):
    """``valores``: ``{chave: valor}``; a blank value clears the spec. Keys must be declared by the
    definition (the active or the draft version)."""

    valores: dict[str, str]


class PlataformaTextosRequest(StrictHttpModel):
    itens: dict[str, str]


# NOTE: ``PlataformaAgentCreateRequest`` / ``PlataformaAgentUpdateRequest`` / ``PlataformaAgentOut`` live in
# ``app.schemas.studio_plataforma`` (they embed the generation schemas, which import this module).

# ── outputs ─────────────────────────────────────────────────────────────────


class TextoOut(BaseModel):
    id: UUID
    chave: str
    conteudo: str


class FerramentaOut(BaseModel):
    id: UUID
    ferramenta: str
    ativo: bool
    descricao: str
    parametros: dict[str, Any]
    obrigatoria_skill: str | None


class DecisaoOut(BaseModel):
    id: UUID
    chave: str
    titulo: str
    regra: str
    opcoes: list[dict[str, Any]]


class SpecDefOut(BaseModel):
    id: UUID
    chave: str
    rotulo: str
    descricao: str
    tipo: str
    obrigatoria: bool
    exemplo: str | None


class TextosOut(BaseModel):
    version_id: UUID
    itens: list[TextoOut]


class FerramentasOut(BaseModel):
    version_id: UUID
    itens: list[FerramentaOut]


class DecisoesOut(BaseModel):
    version_id: UUID
    itens: list[DecisaoOut]


class SpecsOut(BaseModel):
    version_id: UUID
    itens: list[SpecDefOut]


class OrgSpecValorOut(BaseModel):
    chave: str
    valor: str
    updated_at: datetime | None = None


class OrgSpecsOut(BaseModel):
    """The org's view: what the definition asks for, what the org filled, what is still missing."""

    agent_key: str
    #: The definition version the declarations come from (``null`` = nothing published/drafted yet).
    version_id: UUID | None
    versao: int | None
    declaradas: list[SpecDefOut]
    valores: list[OrgSpecValorOut]
    faltando: list[str]


class OrgStatusOut(BaseModel):
    agent_key: str
    completo: bool
    sem_versao: bool
    specs_faltando: list[str]


class ConteudoPayloadOut(BaseModel):
    """CONTRACT §2.3 "Compilado": everything the model receives for a version, attributed to rows."""

    version_id: UUID
    hash: str
    texto: str
    tokens_estimados: int
    manifest: list[dict[str, Any]]
    avisos: list[dict[str, Any]]
    textos: list[TextoOut]
    ferramentas: list[FerramentaOut]
    decisoes: list[DecisaoOut]
    specs: list[SpecDefOut]
    ponto_cache: int = 0


class CompiladoOrgOut(BaseModel):
    """The definition compiled FOR this org (``{{org.x}}`` replaced) — nothing hidden."""

    version_id: UUID
    versao: int
    hash: str
    texto: str
    tokens_estimados: int
    manifest: list[dict[str, Any]]
    avisos: list[dict[str, Any]]
    specs_faltando: list[str]
    completo: bool
    ponto_cache: int = 0


class PlataformaTextoOut(BaseModel):
    chave: str
    conteudo: str
    updated_at: datetime


class PlataformaTextosOut(BaseModel):
    itens: list[PlataformaTextoOut]


class ContentTokenCreateRequest(StrictHttpModel):
    label: str = Field(..., min_length=1, max_length=120)
    #: Days until expiry (1..365); omitted = 30; an explicit ``null`` = never expires.
    expira_em_dias: int | None = Field(30, ge=1, le=365)
    #: Also grant ``studio:agent-delete`` (the token may then DELETE agents). Default off.
    permitir_exclusao: bool = False


class ContentTokenOut(BaseModel):
    id: UUID
    token: str
    prefix: str
    expires_at: datetime | None = None  # None = never expires
    scopes: list[str]


class ContentTokenInfoOut(BaseModel):
    """One content token, NEVER the secret (only the display prefix)."""

    id: UUID
    label: str
    prefix: str
    scopes: list[str]
    created_at: datetime | None = None
    created_by: UUID | None = None
    expires_at: datetime | None = None  # None = never expires
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    status: Literal["ativo", "expirado", "revogado"]


class ContentTokensOut(BaseModel):
    itens: list[ContentTokenInfoOut]
