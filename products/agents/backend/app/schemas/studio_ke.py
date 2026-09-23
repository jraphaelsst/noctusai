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

from pydantic import BaseModel, Field, field_validator, model_validator

from app.studio.models import (
    DOCUMENTS_BATCH_MAX,
    EVAL_RUN_BUDGET_USD_MAX,
    EVAL_RUN_MODEL_ALLOWLIST,
    LIMITS,
    RUN_CASE_IDS_MAX,
)
from noctusai_lib.api import StrictHttpModel

#: M3 — collection metadata is compiled into EVERY prompt of the agent (a
#: live, ungated prompt input), so it carries the tightest caps.
_COL_NOME = LIMITS["collection.nome"]
_COL_TAG = LIMITS["collection.tag"]
_COL_DESCRICAO = LIMITS["collection.descricao"]
_DOC_CONTEUDO = LIMITS["document.conteudo"]

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
    nome: str = Field(..., min_length=1, max_length=_COL_NOME)
    tag: str | None = Field(default=None, max_length=_COL_TAG)
    descricao: str = Field(default="", max_length=_COL_DESCRICAO)
    ordem: int = 0


class CollectionUpdateRequest(StrictHttpModel):
    nome: str | None = Field(default=None, max_length=_COL_NOME)
    tag: str | None = Field(default=None, max_length=_COL_TAG)
    descricao: str | None = Field(default=None, max_length=_COL_DESCRICAO)
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
    conteudo: str = Field(..., min_length=1, max_length=_DOC_CONTEUDO)
    resumo: str | None = None
    proveniencia: dict[str, Any] | None = None


class DocumentUpdateRequest(StrictHttpModel):
    titulo: str | None = None
    tipo: str | None = None
    resumo: str | None = None
    conteudo: str | None = Field(default=None, max_length=_DOC_CONTEUDO)
    proveniencia: dict[str, Any] | None = None
    ativo: bool | None = None
    motivo: str | None = None


class DocumentBatchItemIn(StrictHttpModel):
    """One document of a `documents:batch` call — same fields/caps as
    ``DocumentCreateRequest``, validated identically (no weaker path into
    the same table)."""

    slug: str = Field(..., min_length=1)
    titulo: str = Field(..., min_length=1)
    tipo: str
    conteudo: str = Field(..., min_length=1, max_length=_DOC_CONTEUDO)
    resumo: str | None = None
    proveniencia: dict[str, Any] | None = None


class DocumentBatchCreateRequest(StrictHttpModel):
    #: 1..100 (`DOCUMENTS_BATCH_MAX`) — 422 `too_short`/`too_long` beyond
    #: (Pydantic's own list-length error, never a bespoke 413: the body-size
    #: DoS backstop is the route's raised ``max_body_path_overrides`` cap,
    #: this is the item-COUNT cap).
    documentos: list[DocumentBatchItemIn] = Field(..., min_length=1, max_length=DOCUMENTS_BATCH_MAX)


class DocumentBatchItemResultOut(BaseModel):
    slug: str
    #: "criado" | "atualizado" | "inalterado" | "erro"
    status: str
    doc_id: UUID | None = None
    erro: str | None = None


class DocumentBatchResultOut(BaseModel):
    """Per-item results — ONE bad document in a call of 100 never loses the
    other 99 (a 4xx/5xx here would be an all-or-nothing failure)."""

    resultados: list[DocumentBatchItemResultOut]
    criados: int
    atualizados: int
    inalterados: int
    erros: int


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


class CriteriosOut(BaseModel):
    deve: list[str] = Field(default_factory=list)
    nao_deve: list[str] = Field(default_factory=list)


class VereditoOut(BaseModel):
    """One judged criterion of a result (contract §B2 ``veredito``)."""

    criterio: str
    tipo: str  # "deve" | "nao_deve"
    ok: bool
    motivo: str


class EvalCaseOut(BaseModel):
    id: UUID
    slug: str
    titulo: str
    entrada: str
    contexto: str | None
    criterios: CriteriosOut
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
    #: Additive (H1): ``True`` only for a run over every active case — the
    #: only kind the publish gate accepts. Subset runs are for iteration.
    completa: bool = False
    #: Contract §L (additive): ``None`` ⇒ the version's own model ran (the
    #: publish-gate-eligible shape); otherwise the cheaper-iteration
    #: override the runner used instead.
    modelo_geracao: str | None = None
    #: Contract §L (additive): the run's cost cap in USD.
    limite_usd: float | None = None
    #: Contract §L (additive): the run's accumulated cost (generator +
    #: judge, summed over every result) — ``None`` until the runner has
    #: written at least one result.
    custo_usd: float | None = None


class EvalRunListOut(BaseModel):
    items: list[EvalRunOut]


class EvalRunCreateRequest(StrictHttpModel):
    version_id: UUID
    #: Omitted ⇒ every active case (a COMPLETE run). A list is deduped and
    #: capped (L6) — and never satisfies the publish gate (H1). Mutually
    #: exclusive with ``repetir_falhas_de`` (422 ``case_ids_conflict``).
    case_ids: list[UUID] | None = Field(default=None, max_length=RUN_CASE_IDS_MAX)
    #: Contract §L: the cheaper-iteration model override — ``None`` ⇒ the
    #: version's own model. Typed ``str`` (not ``Literal``) — same
    #: `tipo`/`status`-style convention this module's header documents —
    #: validated against `EVAL_RUN_MODEL_ALLOWLIST` below (422
    #: `invalid_modelo_geracao`), intentionally NARROWER than
    #: `agent_versions.model`'s allowlist.
    modelo_geracao: str | None = None
    #: Contract §L: this run's cost cap in USD — omitted ⇒ the settings
    #: default (`STUDIO_EVAL_RUN_BUDGET_USD`, `app.config.settings.
    #: studio_eval_run_budget_usd`).
    limite_usd: float | None = Field(default=None, gt=0, le=EVAL_RUN_BUDGET_USD_MAX)
    #: Contract §L: rerun only the failures of a prior run of THIS agent —
    #: resolved server-side into ``case_ids`` (404 if the run doesn't
    #: belong to this org/agent). Mutually exclusive with ``case_ids``.
    repetir_falhas_de: UUID | None = None

    @field_validator("modelo_geracao")
    @classmethod
    def _modelo_geracao_allowlist(cls, value: str | None) -> str | None:
        if value is not None and value not in EVAL_RUN_MODEL_ALLOWLIST:
            raise ValueError(f"modelo_geracao must be one of {EVAL_RUN_MODEL_ALLOWLIST}")
        return value

    @model_validator(mode="after")
    def _case_ids_xor_repetir_falhas_de(self) -> "EvalRunCreateRequest":
        if self.case_ids is not None and self.repetir_falhas_de is not None:
            raise ValueError("case_ids and repetir_falhas_de are mutually exclusive")
        return self


class EvalResultOut(BaseModel):
    case_id: UUID
    case_slug: str
    case_titulo: str
    status: str
    score: float | None
    saida: str | None
    veredito: list[VereditoOut] | None
    notas_juiz: str | None
    duracao_ms: int | None
    #: Contract §L (additive): generator + judge cost of this case, summed.
    custo_usd: float | None = None
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    tokens_cache_leitura: int | None = None


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
    "DocumentBatchItemIn",
    "DocumentBatchCreateRequest",
    "DocumentBatchItemResultOut",
    "DocumentBatchResultOut",
    "RevisionOut",
    "RevisionListOut",
    "SearchItemOut",
    "SearchOut",
    "CriteriosModel",
    "CriteriosOut",
    "VereditoOut",
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
