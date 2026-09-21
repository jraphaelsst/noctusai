"""Pydantic schemas for Agent Studio's knowledge + evals API (contract
§D3/§D4, slice BE-KE).

Request bodies are :class:`~noctusai_lib.api.StrictHttpModel` (``extra=
"forbid"`` -> 422 on an unknown field, contract §0/§H "Strictness").
Response models are plain ``BaseModel`` — consumers must ignore unknown
response fields (same contract as ``app/schemas/agents.py``).

``tipo``/``status``/`op` fields are typed ``str`` here, not ``Literal``
— the store raises ``ValueError`` for a value outside its CHECK-constraint
allowlist, mapped to 422 at the router (same shape as
``app/schemas/agents.py``'s `model`/`effort`, see `persona_router.py`'s
docstring). Duplicating the allowlist as a second `Literal` here would
just be a second place to keep in sync with the DB CHECK.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from noctusai_lib.api import StrictHttpModel

# ── Knowledge — collections (§D3) ───────────────────────────────────────


class CollectionOut(BaseModel):
    id: UUID
    slug: str
    nome: str
    tag: str | None
    descricao: str
    ordem: int
    total_documentos: int


class CollectionListOut(BaseModel):
    colecoes: list[CollectionOut]


class CollectionCreateRequest(StrictHttpModel):
    slug: str = Field(..., min_length=1)
    nome: str = Field(..., min_length=1)
    tag: str | None = None
    descricao: str = ""
    ordem: int = 0


class CollectionUpdateRequest(StrictHttpModel):
    nome: str | None = None
    tag: str | None = None
    descricao: str | None = None
    ordem: int | None = None


# ── Knowledge — documents (§D3) ─────────────────────────────────────────


class DocumentListItemOut(BaseModel):
    id: UUID
    slug: str
    titulo: str
    tipo: str
    resumo: str | None
    chars: int
    ativo: bool
    updated_at: datetime


class DocumentListOut(BaseModel):
    items: list[DocumentListItemOut]
    total: int


class DocumentOut(BaseModel):
    id: UUID
    collection_id: UUID
    slug: str
    titulo: str
    tipo: str
    resumo: str | None
    conteudo: str
    proveniencia: dict[str, Any]
    ativo: bool
    chars: int
    updated_at: datetime


class DocumentCreateRequest(StrictHttpModel):
    slug: str = Field(..., min_length=1)
    titulo: str = Field(..., min_length=1)
    tipo: str
    conteudo: str = Field(..., min_length=1)
    resumo: str | None = None
    proveniencia: dict[str, Any] | None = None


class DocumentUpdateRequest(StrictHttpModel):
    titulo: str | None = None
    tipo: str | None = None
    resumo: str | None = None
    conteudo: str | None = None
    proveniencia: dict[str, Any] | None = None
    ativo: bool | None = None
    motivo: str | None = None


class RevisionOut(BaseModel):
    id: UUID
    op: str
    motivo: str | None
    author_id: UUID | None
    created_at: datetime


class RevisionListOut(BaseModel):
    items: list[RevisionOut]


class SearchItemOut(BaseModel):
    doc_id: UUID
    slug: str
    titulo: str
    colecao: str
    tag: str | None
    tipo: str
    trecho: str
    rank: float


class SearchOut(BaseModel):
    items: list[SearchItemOut]


# ── Evals — cases (§D4) ─────────────────────────────────────────────────


class CriteriosModel(StrictHttpModel):
    deve: list[str] = Field(default_factory=list)
    nao_deve: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _at_least_one(self) -> "CriteriosModel":
        if len(self.deve) + len(self.nao_deve) < 1:
            raise ValueError("criterios must contain at least one item across deve/nao_deve")
        return self


class EvalCaseOut(BaseModel):
    id: UUID
    slug: str
    titulo: str
    entrada: str
    contexto: str | None
    criterios: dict[str, list[str]]
    rubrica: str | None
    tags: list[str]
    ativo: bool


class EvalCaseListOut(BaseModel):
    items: list[EvalCaseOut]


class EvalCaseCreateRequest(StrictHttpModel):
    slug: str = Field(..., min_length=1)
    titulo: str = Field(..., min_length=1)
    entrada: str = Field(..., min_length=1)
    criterios: CriteriosModel
    contexto: str | None = None
    rubrica: str | None = None
    tags: list[str] = Field(default_factory=list)
    ativo: bool = True


class EvalCaseUpdateRequest(StrictHttpModel):
    titulo: str | None = None
    entrada: str | None = None
    contexto: str | None = None
    criterios: CriteriosModel | None = None
    rubrica: str | None = None
    tags: list[str] | None = None
    ativo: bool | None = None


# ── Evals — runs (§D4) ──────────────────────────────────────────────────


class EvalRunOut(BaseModel):
    id: UUID
    version_id: UUID
    compiled_hash: str
    status: str
    total: int
    aprovados: int
    score: float | None
    limiar: float
    started_at: datetime | None
    finished_at: datetime | None
    erro: str | None


class EvalRunListOut(BaseModel):
    items: list[EvalRunOut]


class EvalRunCreateRequest(StrictHttpModel):
    version_id: UUID
    case_ids: list[UUID] | None = None


class EvalResultOut(BaseModel):
    case_id: UUID
    case_slug: str
    case_titulo: str
    status: str
    score: float | None
    saida: str | None
    veredito: Any | None
    notas_juiz: str | None
    duracao_ms: int | None


class EvalRunDetailOut(EvalRunOut):
    resultados: list[EvalResultOut]


__all__ = [
    "CollectionOut",
    "CollectionListOut",
    "CollectionCreateRequest",
    "CollectionUpdateRequest",
    "DocumentListItemOut",
    "DocumentListOut",
    "DocumentOut",
    "DocumentCreateRequest",
    "DocumentUpdateRequest",
    "RevisionOut",
    "RevisionListOut",
    "SearchItemOut",
    "SearchOut",
    "CriteriosModel",
    "EvalCaseOut",
    "EvalCaseListOut",
    "EvalCaseCreateRequest",
    "EvalCaseUpdateRequest",
    "EvalRunOut",
    "EvalRunListOut",
    "EvalRunCreateRequest",
    "EvalResultOut",
    "EvalRunDetailOut",
]
