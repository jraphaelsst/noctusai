"""Pydantic schemas for the Agent Studio definitions API (contract §D1, §D2).

Request bodies are :class:`~noctusai_lib.api.StrictHttpModel` (``extra=
"forbid"`` → 422 on an unknown field, §D intro). Response models are plain
``BaseModel`` (consumers ignore unknown response fields). PATCH bodies are
read with ``model_dump(exclude_unset=True)`` so an omitted field is "leave
as is" and an explicit ``null`` is "clear" where the column is nullable.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.studio.models import (
    LIMITS,
    OVERRIDE_REASON_MIN_CHARS,
    PUBLICACAO_LIMIAR_MIN,
    SKILL_FILES_BATCH_MAX,
    override_reason_ok,
)
from noctusai_lib.api import StrictHttpModel

#: 012 slug CHECK (agent key, section chave, skill nome, client slug).
SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
#: 012 skill-file caminho CHECK (the `..` exclusion is validated separately).
CAMINHO_PATTERN = r"^[a-z0-9][a-z0-9._/-]*$"

EntryTipo = Literal[
    "marca", "publico", "posicionamento", "trava", "decisao", "aprendizado", "evidencia", "nota"
]
EntryStatus = Literal["ativo", "arquivado"]


# ── agents ──────────────────────────────────────────────────────────────────


class StudioAgentCreateRequest(StrictHttpModel):
    key: str = Field(..., min_length=1, max_length=64, pattern=SLUG_PATTERN)
    nome: str = Field(..., min_length=1)
    descricao: str | None = None


class StudioAgentUpdateRequest(StrictHttpModel):
    nome: str | None = Field(default=None, min_length=1)
    descricao: str | None = None
    ativo: bool | None = None
    #: H2 floor — the DB CHECK ``agents_publicacao_limiar_floor`` mirrors it.
    publicacao_limiar: float | None = Field(default=None, ge=PUBLICACAO_LIMIAR_MIN, le=1)


class AgentSummaryOut(BaseModel):
    id: UUID
    key: str
    nome: str
    descricao: str | None
    definition_mode: str
    ativo: bool
    publicacao_limiar: float
    versao_ativa: int | None
    tem_rascunho: bool


class AgentListOut(BaseModel):
    items: list[AgentSummaryOut]


class VersionSummaryOut(BaseModel):
    id: UUID
    versao: int
    status: str
    notas: str | None
    model: str
    created_at: datetime
    published_at: datetime | None
    compiled_hash: str | None
    eval_score: float | None


class AgentDetailOut(AgentSummaryOut):
    versoes: list[VersionSummaryOut]


# ── versions ────────────────────────────────────────────────────────────────


class SectionOut(BaseModel):
    id: UUID
    chave: str
    titulo: str
    ordem: int
    conteudo: str
    ativo: bool


class SkillFileMetaOut(BaseModel):
    id: UUID
    caminho: str
    titulo: str | None
    chars: int


class SkillFileOut(BaseModel):
    id: UUID
    caminho: str
    titulo: str | None
    conteudo: str


class SkillOut(BaseModel):
    id: UUID
    nome: str
    descricao: str
    corpo: str
    ordem: int
    ativo: bool
    arquivos: list[SkillFileMetaOut]


class VersionDetailOut(VersionSummaryOut):
    effort: str
    max_turns: int
    idioma: str
    tool_policy: dict[str, Any]
    based_on_version_id: UUID | None
    published_by: UUID | None
    publish_override_reason: str | None
    eval_run_id: UUID | None
    secoes: list[SectionOut]
    skills: list[SkillOut]
    #: Additive (H2): the threshold in force when the version was published
    #: (``None`` on a draft). ``eval_score`` on a published version is the
    #: gating run's score snapshotted at publish (``None`` for an override).
    limiar_aplicado: float | None = None


class DraftCreateRequest(StrictHttpModel):
    from_version_id: UUID | None = None


class ToolPolicyIn(StrictHttpModel):
    web_search: bool
    knowledge: bool


class DraftUpdateRequest(StrictHttpModel):
    notas: str | None = None
    model: str | None = None
    effort: str | None = None
    max_turns: int | None = None
    idioma: str | None = Field(default=None, min_length=1)
    tool_policy: ToolPolicyIn | None = None


class SectionIn(StrictHttpModel):
    id: UUID | None = None
    chave: str = Field(..., min_length=1, pattern=SLUG_PATTERN)
    titulo: str = Field(..., min_length=1)
    ordem: int
    conteudo: str = Field(..., max_length=LIMITS["section.conteudo"])
    ativo: bool


class SectionsReplaceRequest(StrictHttpModel):
    secoes: list[SectionIn]


class SkillCreateRequest(StrictHttpModel):
    nome: str = Field(..., min_length=1, max_length=64, pattern=SLUG_PATTERN)
    descricao: str = Field(..., min_length=1, max_length=1024)
    corpo: str = Field(..., max_length=LIMITS["skill.corpo"])
    ordem: int = 0
    ativo: bool = True


class SkillUpdateRequest(StrictHttpModel):
    nome: str | None = Field(default=None, min_length=1, max_length=64, pattern=SLUG_PATTERN)
    descricao: str | None = Field(default=None, min_length=1, max_length=1024)
    corpo: str | None = Field(default=None, max_length=LIMITS["skill.corpo"])
    ordem: int | None = None
    ativo: bool | None = None


class SkillFileUpsertRequest(StrictHttpModel):
    caminho: str = Field(..., min_length=1, max_length=255, pattern=CAMINHO_PATTERN)
    titulo: str | None = None
    conteudo: str = Field(..., max_length=LIMITS["skill_file.conteudo"])

    @field_validator("caminho")
    @classmethod
    def _no_parent_segments(cls, v: str) -> str:
        # 012 CHECK `caminho !~ '\.\.'` — refuse at the boundary, not at the DB.
        if ".." in v:
            raise ValueError("caminho must not contain '..'")
        return v


class SkillFileBatchItemIn(StrictHttpModel):
    """One file of a `files:batch` call — same fields/caps/path-traversal
    guard as ``SkillFileUpsertRequest`` (no weaker validation path)."""

    caminho: str = Field(..., min_length=1, max_length=255, pattern=CAMINHO_PATTERN)
    titulo: str | None = None
    conteudo: str = Field(..., max_length=LIMITS["skill_file.conteudo"])

    @field_validator("caminho")
    @classmethod
    def _no_parent_segments(cls, v: str) -> str:
        if ".." in v:
            raise ValueError("caminho must not contain '..'")
        return v


class SkillFilesBatchUpsertRequest(StrictHttpModel):
    #: 1..50 (`SKILL_FILES_BATCH_MAX`).
    arquivos: list[SkillFileBatchItemIn] = Field(..., min_length=1, max_length=SKILL_FILES_BATCH_MAX)


class SkillFileBatchItemResultOut(BaseModel):
    caminho: str
    #: "criado" | "atualizado" | "erro"
    status: str
    id: UUID | None = None
    titulo: str | None = None
    chars: int | None = None
    erro: str | None = None


class SkillFilesBatchResultOut(BaseModel):
    resultados: list[SkillFileBatchItemResultOut]
    criados: int
    atualizados: int
    erros: int


class PublishRequest(StrictHttpModel):
    notas: str | None = None
    #: §H4 / L1: the gate cannot be bypassed without a reason of at least
    #: 20 NON-whitespace characters. Stored stripped; the DB CHECK
    #: ``agent_versions_override_reason_len`` is the backstop.
    override_reason: str | None = None

    @field_validator("override_reason")
    @classmethod
    def _real_reason(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not override_reason_ok(v):
            raise ValueError(
                f"override_reason needs at least {OVERRIDE_REASON_MIN_CHARS} non-whitespace characters"
            )
        return v


# ── compile / diff / prompts ────────────────────────────────────────────────


class AvisoOut(BaseModel):
    codigo: str
    mensagem: str
    bloqueante: bool


class CompiledOut(BaseModel):
    texto: str
    hash: str
    tokens_estimados: int
    manifest: list[dict[str, Any]]
    sob_demanda: list[dict[str, Any]]
    avisos: list[AvisoOut]
    version_id: UUID
    client_id: UUID | None


class DiffSideOut(BaseModel):
    version_id: UUID
    hash: str


class DiffSectionOut(BaseModel):
    chave: str
    estado: Literal["igual", "alterada", "nova", "removida"]


class DiffSkillOut(BaseModel):
    nome: str
    estado: Literal["igual", "alterada", "nova", "removida"]


class DiffConfigOut(BaseModel):
    campo: str
    a: Any
    b: Any


class DiffOut(BaseModel):
    a: DiffSideOut
    b: DiffSideOut
    texto_a: str
    texto_b: str
    secoes: list[DiffSectionOut]
    skills: list[DiffSkillOut]
    configuracoes: list[DiffConfigOut]


class PromptByHashOut(BaseModel):
    hash: str
    texto: str
    manifest: list[dict[str, Any]]
    version_id: UUID
    client_id: UUID | None
    created_at: datetime


# ── clients (§D2) ───────────────────────────────────────────────────────────


class ClientEntryOut(BaseModel):
    id: UUID
    tipo: str
    titulo: str
    conteudo: str
    status: str
    created_at: datetime


class ClientOut(BaseModel):
    id: UUID
    slug: str
    nome: str
    resumo: str
    ativo: bool
    entradas: list[ClientEntryOut]


class ClientSummaryOut(BaseModel):
    id: UUID
    slug: str
    nome: str
    resumo: str
    ativo: bool
    total_entradas: int


class ClientListOut(BaseModel):
    items: list[ClientSummaryOut]


class ClientCreateRequest(StrictHttpModel):
    slug: str = Field(..., min_length=1, max_length=64, pattern=SLUG_PATTERN)
    nome: str = Field(..., min_length=1)
    #: M3: the client brain is a live, ungated prompt input — capped.
    resumo: str = Field(default="", max_length=LIMITS["client.resumo"])
    ativo: bool = True


class ClientUpdateRequest(StrictHttpModel):
    slug: str | None = Field(default=None, min_length=1, max_length=64, pattern=SLUG_PATTERN)
    nome: str | None = Field(default=None, min_length=1)
    resumo: str | None = Field(default=None, max_length=LIMITS["client.resumo"])
    ativo: bool | None = None


class ClientEntryCreateRequest(StrictHttpModel):
    tipo: EntryTipo
    titulo: str = Field(..., min_length=1, max_length=LIMITS["entry.titulo"])
    conteudo: str = Field(default="", max_length=LIMITS["entry.conteudo"])
    status: EntryStatus = "ativo"


class ClientEntryUpdateRequest(StrictHttpModel):
    tipo: EntryTipo | None = None
    titulo: str | None = Field(default=None, min_length=1, max_length=LIMITS["entry.titulo"])
    conteudo: str | None = Field(default=None, max_length=LIMITS["entry.conteudo"])
    status: EntryStatus | None = None
