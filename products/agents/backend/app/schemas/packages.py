"""Pydantic schemas for the Agent Packages routes (contract §G2, §H2, §I).

Request bodies are :class:`~noctusai_lib.api.StrictHttpModel` (``extra=
"forbid"`` → 422 on an unknown field, Studio §D intro). Responses are plain
``BaseModel``.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from noctusai_lib.api import StrictHttpModel

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
SEMVER_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$"

#: ``projeto-<slug>`` must fit the 64-char collection slug (8 + 56).
PROJECT_SLUG_MAX = 56
#: §G2 — whole-call size cap and per-file skip threshold.
SOURCES_MAX_BYTES = 25 * 1024 * 1024
SOURCE_FILE_MAX_BYTES = 200 * 1024
SOURCES_MAX_FILES = 5000
#: §H2 — one push carries at most this many rows.
LEARNINGS_MAX_ROWS = 500


# ── §I — package serving ────────────────────────────────────────────────────


class PackageVersionOut(BaseModel):
    versao: str
    sha: str | None
    status: str
    published_at: datetime | None
    tem_arvore: bool


class PackageVersionsOut(BaseModel):
    key: str
    items: list[PackageVersionOut]


class PackageFileOut(BaseModel):
    path: str
    conteudo: str


class PackageOut(BaseModel):
    files: list[PackageFileOut]
    package: dict[str, Any]


# ── §G2 — project sources ───────────────────────────────────────────────────


class SourceItem(StrictHttpModel):
    path: str = Field(..., min_length=1, max_length=500)
    sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    tipo: Literal["doc", "codigo", "quadro"]
    conteudo: str

    @field_validator("path")
    @classmethod
    def _clean_path(cls, v: str) -> str:
        parts = v.split("/")
        if v.startswith("/") or "\\" in v or "\x00" in v or any(p in ("", ".", "..") for p in parts):
            raise ValueError("path must be a clean relative posix path")
        return v


class SourcesBody(StrictHttpModel):
    """The object form of the manifest (``{"fontes": [...]}``); the bare
    array is accepted too — the contract writes the body as ``[{...}]``."""

    fontes: list[SourceItem] = Field(..., max_length=SOURCES_MAX_FILES)
    #: Fingerprints (first 16 hex of sha256 of the matched text) of scanner hits a HUMAN
    #: acknowledged as not-a-secret in the consumer's agents.lock.json (`project.nao_segredos`).
    #: Exact-token exemption only — the scan rules are never relaxed (CONTRACT agent-packages §J2).
    nao_segredos: list[str] = Field(default_factory=list, max_length=500)

    @field_validator("nao_segredos")
    @classmethod
    def _fingerprints(cls, v: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[0-9a-f]{16}", f) for f in v):
            raise ValueError("nao_segredos entries must be 16 lowercase hex chars")
        return v


def acknowledged_fingerprints(body: "SourcesBody | list[SourceItem]") -> frozenset[str]:
    return frozenset(body.nao_segredos) if isinstance(body, SourcesBody) else frozenset()


def manifest_items(body: "SourcesBody | list[SourceItem]") -> list[SourceItem]:
    items = body.fontes if isinstance(body, SourcesBody) else body
    seen: set[str] = set()
    for it in items:
        if it.path in seen:
            raise ValueError(f"duplicate path in manifest: {it.path!r}")
        seen.add(it.path)
    return items


class SourceSkipOut(BaseModel):
    path: str
    motivo: str


class SourcesSyncOut(BaseModel):
    projeto: str
    colecao_id: UUID
    colecao_slug: str
    total: int
    criados: int
    atualizados: int
    inalterados: int
    removidos: int
    ignorados: list[SourceSkipOut]
    avisos: list[str]
    sources_sha: str


class ProjectOut(BaseModel):
    slug: str
    colecao_id: UUID | None
    total_fontes: int
    ultima_sincronizacao: datetime | None
    sources_sha: str


class ProjectListOut(BaseModel):
    items: list[ProjectOut]


# ── §H2 — learnings ─────────────────────────────────────────────────────────

_TIPOS = ("pitfall", "armadilha", "practice", "pratica", "prática", "decision", "decisao", "decisão")
_ROW_STATUSES = ("new", "novo", "absorbed", "absorvido", "promoted", "promovido")


class LearningRowIn(StrictHttpModel):
    data: str = Field(..., min_length=1, max_length=40)
    tipo: str
    texto: str = Field(..., min_length=1, max_length=8000)
    evidencia: str = Field(default="", max_length=4000)
    status: str = "novo"
    #: Optional integrity check — must equal the §H1 row identity when sent.
    row_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("tipo", "status")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()

    @model_validator(mode="after")
    def _allowlists(self) -> "LearningRowIn":
        if self.tipo not in _TIPOS:
            raise ValueError(f"tipo must be one of {list(_TIPOS)}")
        if self.status not in _ROW_STATUSES:
            raise ValueError(f"status must be one of {list(_ROW_STATUSES)}")
        return self


class LearningsPushIn(StrictHttpModel):
    project_slug: str = Field(..., min_length=1, max_length=PROJECT_SLUG_MAX, pattern=SLUG_PATTERN)
    rows: list[LearningRowIn] = Field(..., min_length=1, max_length=LEARNINGS_MAX_ROWS)


class LearningNewOut(BaseModel):
    id: UUID
    row_sha: str


class LearningsPushOut(BaseModel):
    recebidas: int
    novas: int
    duplicadas: int
    novos: list[LearningNewOut]


class LearningOut(BaseModel):
    id: UUID
    project_slug: str
    row_sha: str
    data: str
    tipo: str
    texto: str
    evidencia: str
    row_status: str
    status: str
    nota: str | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    created_at: datetime


class LearningListOut(BaseModel):
    items: list[LearningOut]


class LearningReviewIn(StrictHttpModel):
    status: Literal["aceito", "descartado"]
    # CONTRACT agent-packages §H2: a review always carries a note (enforced here, not only in the UI).
    nota: str = Field(min_length=3, max_length=2000, pattern=r"\S")
