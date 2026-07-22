"""Pydantic schemas for the Leads module — mirrors
``leads-module-PROJECT.md`` §5.3 field-for-field. The TypeScript types the
frontend engineer builds against are copied verbatim from that section;
these models are the backend side of the SAME contract. Do not rename /
retype a field here without updating that doc first (frontend is building
against it in parallel).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.api import StrictHttpModel
from pydantic import BaseModel, ConfigDict, Field


# ─── shared nested refs (joined) ───────────────────────────────────────

class SourceRef(BaseModel):
    id: UUID
    slug: str
    label: str
    cor: Optional[str] = None


class CorretorRef(BaseModel):
    id: UUID
    nome: str
    cor: Optional[str] = None


# ─── Lead ───────────────────────────────────────────────────────────────

class LeadOut(BaseModel):
    id: UUID
    org_id: UUID
    data_entrada: date
    ano: int
    mes: int
    codigo_raw: Optional[str] = None
    codigo_imovel: Optional[str] = None
    empreendimento: Optional[str] = None
    regiao: Optional[str] = None
    origem_id: Optional[UUID] = None
    origem_raw: Optional[str] = None
    origem: Optional[SourceRef] = None
    tipo_lead: str = "desconhecido"
    cliente_nome: Optional[str] = None
    contato: Optional[str] = None
    contato_tipo: Optional[str] = None
    corretor_id: Optional[UUID] = None
    corretor_raw: Optional[str] = None
    corretor: Optional[CorretorRef] = None
    anuncio_tier: Optional[str] = None
    status: Optional[str] = None
    observacoes: Optional[str] = None
    follow_up_data: Optional[date] = None
    follow_up_nota: Optional[str] = None
    needs_review: bool = False
    source_sheet: Optional[str] = None
    source_row: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class LeadCreate(StrictHttpModel):
    """POST /api/leads body — manual entry. Server assigns id/org_id/
    created_at/needs_review defaults; source_sheet/source_row/
    import_batch_id are importer-only (not settable via this endpoint —
    a manually-created lead always has source_sheet=NULL, matching the
    fact-table's idempotency-key exemption, §4)."""

    data_entrada: date
    codigo_raw: Optional[str] = None
    codigo_imovel: Optional[str] = None
    empreendimento: Optional[str] = None
    regiao: Optional[str] = None
    origem_id: Optional[UUID] = None
    tipo_lead: str = "desconhecido"
    cliente_nome: Optional[str] = None
    contato: Optional[str] = None
    contato_tipo: Optional[str] = None
    corretor_id: Optional[UUID] = None
    anuncio_tier: Optional[str] = None
    status: Optional[str] = None
    observacoes: Optional[str] = None
    follow_up_data: Optional[date] = None
    follow_up_nota: Optional[str] = None


class LeadUpdate(StrictHttpModel):
    """PATCH /api/leads/{id} body — all fields optional (partial update)."""

    data_entrada: Optional[date] = None
    codigo_raw: Optional[str] = None
    codigo_imovel: Optional[str] = None
    empreendimento: Optional[str] = None
    regiao: Optional[str] = None
    origem_id: Optional[UUID] = None
    tipo_lead: Optional[str] = None
    cliente_nome: Optional[str] = None
    contato: Optional[str] = None
    contato_tipo: Optional[str] = None
    corretor_id: Optional[UUID] = None
    anuncio_tier: Optional[str] = None
    status: Optional[str] = None
    observacoes: Optional[str] = None
    follow_up_data: Optional[date] = None
    follow_up_nota: Optional[str] = None
    needs_review: Optional[bool] = None


# ─── analytics: summary ─────────────────────────────────────────────────

class PeriodoOut(BaseModel):
    de: Optional[str] = None
    ate: Optional[str] = None


class ComparativoOut(BaseModel):
    total_anterior: int
    variacao_pct: Optional[float] = None


class TopOrigemOut(BaseModel):
    id: UUID
    label: str
    total: int
    share_pct: float


class TopCorretorOut(BaseModel):
    id: UUID
    nome: str
    total: int


class LeadsSummaryOut(BaseModel):
    total: int
    novos: int
    retornos: int
    origens_ativas: int
    corretores_ativos: int
    empreendimentos: int
    needs_review: int
    periodo: PeriodoOut
    comparativo: Optional[ComparativoOut] = None
    media_diaria: float
    top_origem: Optional[TopOrigemOut] = None
    top_corretor: Optional[TopCorretorOut] = None


# ─── analytics: timeseries ──────────────────────────────────────────────

class TimeseriesPointOut(BaseModel):
    bucket: str
    label: str
    total: int
    series: Optional[dict[str, int]] = None


class SeriesMetaOut(BaseModel):
    key: str
    label: str
    cor: Optional[str] = None


class TimeseriesOut(BaseModel):
    grain: str
    split: Optional[str] = None
    series_meta: list[SeriesMetaOut] = Field(default_factory=list)
    points: list[TimeseriesPointOut] = Field(default_factory=list)


# ─── analytics: by-dimension ─────────────────────────────────────────────

class DimensionBucketOut(BaseModel):
    key: str
    label: str
    cor: Optional[str] = None
    total: int
    share_pct: float
    novos: int
    retornos: int
    variacao_pct: Optional[float] = None


class ByDimensionOut(BaseModel):
    dim: str
    total: int
    buckets: list[DimensionBucketOut] = Field(default_factory=list)


# ─── analytics: heatmap ──────────────────────────────────────────────────

class HeatmapOut(BaseModel):
    anos: list[int]
    cells: dict[str, list[Optional[int]]]
    max: int


# ─── facets ───────────────────────────────────────────────────────────────

class FacetItem(BaseModel):
    value: str
    count: int


class FacetsOut(BaseModel):
    empreendimentos: list[FacetItem] = Field(default_factory=list)
    regioes: list[FacetItem] = Field(default_factory=list)
    anos: list[int] = Field(default_factory=list)


# ─── sources ──────────────────────────────────────────────────────────────

class LeadSourceOut(BaseModel):
    id: UUID
    org_id: UUID
    slug: str
    label: str
    categoria: str
    cor: Optional[str] = None
    ativo: bool
    ordem: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class LeadSourceCreate(StrictHttpModel):
    slug: str
    label: str
    categoria: str = "outro"
    cor: Optional[str] = None
    ativo: bool = True
    ordem: int = 0


class LeadSourceUpdate(StrictHttpModel):
    label: Optional[str] = None
    categoria: Optional[str] = None
    cor: Optional[str] = None
    ativo: Optional[bool] = None
    ordem: Optional[int] = None


class LeadSourceAliasOut(BaseModel):
    id: UUID
    org_id: UUID
    alias: str
    alias_norm: str
    source_id: UUID
    origem: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadSourceAliasCreate(StrictHttpModel):
    alias: str
    source_id: UUID


class UnmappedOrigemOut(BaseModel):
    alias: str
    count: int


# ─── corretores ───────────────────────────────────────────────────────────

class LeadCorretorOut(BaseModel):
    id: UUID
    org_id: UUID
    nome: str
    nome_norm: str
    cor: Optional[str] = None
    ativo: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    lead_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class LeadCorretorCreate(StrictHttpModel):
    nome: str
    cor: Optional[str] = None
    ativo: bool = True


class LeadCorretorUpdate(StrictHttpModel):
    nome: Optional[str] = None
    cor: Optional[str] = None
    ativo: Optional[bool] = None


class LeadCorretorAliasOut(BaseModel):
    id: UUID
    org_id: UUID
    alias: str
    alias_norm: str
    corretor_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadCorretorAliasCreate(StrictHttpModel):
    alias: str
    corretor_id: UUID


# ─── import ────────────────────────────────────────────────────────────────

class ImportBatchOut(BaseModel):
    id: UUID
    filename: str
    sheets: int
    rows_read: int
    rows_inserted: int
    rows_updated: int
    rows_skipped: int
    rows_flagged: int
    status: str
    erro: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ImportPreviewOut(BaseModel):
    filename: str
    sheets: list[str] = Field(default_factory=list)
    rows_read: int
    rows_new: int
    rows_existing: int
    rows_skipped: int
    unmapped_origens: list[UnmappedOrigemOut] = Field(default_factory=list)
    unmapped_corretores: list[UnmappedOrigemOut] = Field(default_factory=list)
    sample: list[LeadOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


__all__ = [
    "SourceRef",
    "CorretorRef",
    "LeadOut",
    "LeadCreate",
    "LeadUpdate",
    "PeriodoOut",
    "ComparativoOut",
    "TopOrigemOut",
    "TopCorretorOut",
    "LeadsSummaryOut",
    "TimeseriesPointOut",
    "SeriesMetaOut",
    "TimeseriesOut",
    "DimensionBucketOut",
    "ByDimensionOut",
    "HeatmapOut",
    "FacetItem",
    "FacetsOut",
    "LeadSourceOut",
    "LeadSourceCreate",
    "LeadSourceUpdate",
    "LeadSourceAliasOut",
    "LeadSourceAliasCreate",
    "UnmappedOrigemOut",
    "LeadCorretorOut",
    "LeadCorretorCreate",
    "LeadCorretorUpdate",
    "LeadCorretorAliasOut",
    "LeadCorretorAliasCreate",
    "ImportBatchOut",
    "ImportPreviewOut",
]
