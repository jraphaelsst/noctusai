"""Pydantic schemas — MCP tool I/O only.

Showcase DTOs (`ShowcaseImovel`, `ShowcaseUsuario`, `ShowcaseAgencia`,
`ShowcaseImovelDetalhes`) live in `noctusai_lib.integrations.vista`
(formalized 2026-05-03). This module keeps only the MCP-tool-specific
input/output schemas — one pair per tool descriptor. `Field(description=...)`
on every property so MCP introspection surfaces help text automatically
(per `KB § PATTERNS/mcp-tool-conventions.md` § 2).

Output models start minimal (`items: list[dict]`) per the convention doc;
tighten as call sites stabilize.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Tool I/O schemas ────────────────────────────────────────────────────


class ListImoveisInput(BaseModel):
    page: int = Field(1, ge=1, description="Page number (Vista paginates at quantidade=50 max).")
    page_size: int = Field(50, ge=1, le=50, description="Page size (Vista server-side cap is 50).")
    status: Optional[str] = Field(None, description="Vista Status filter (e.g. 'Venda', 'Aluguel', 'Venda e Aluguel'). Use vista.imoveis.list_filters to discover live values.")
    categoria: Optional[str] = Field(None, description="Vista Categoria filter (e.g. 'Casa', 'Apartamento', 'Terreno').")
    cidade: Optional[str] = Field(None, description="Vista Cidade filter. Note: tenant has casing duplicates (vista.md § 4.1).")
    bairro: Optional[str] = Field(None, description="Vista Bairro filter.")
    finalidade: Optional[str] = Field(None, description="Vista Finalidade filter (e.g. 'Residencial').")


class ListImoveisOutput(BaseModel):
    items: list[dict] = Field(default_factory=list, description="ShowcaseImovel-shaped objects.")
    pagination: dict = Field(default_factory=dict, description="{total, paginas, pagina, quantidade}.")
    probe_status: str = Field("live_probed", description="One of live_probed | doc_only | referenced.")


class GetImovelInput(BaseModel):
    codigo: str = Field(..., description="Vista primary id, e.g. 'CA2830'.")


class GetImovelOutput(BaseModel):
    item: Optional[dict] = Field(None, description="ShowcaseImovelDetalhes-shaped object, or null if not found.")
    probe_status: str = Field("live_probed", description="One of live_probed | doc_only | referenced.")


class ListImoveisFiltersOutput(BaseModel):
    filters: dict[str, list[str]] = Field(default_factory=dict, description="Enum values per field ({Status, Categoria, Cidade, Bairro}).")
    probe_status: str = Field("live_probed", description="One of live_probed | doc_only | referenced.")


class ListUsuariosOutput(BaseModel):
    items: list[dict] = Field(default_factory=list, description="ShowcaseUsuario-shaped objects.")
    probe_status: str = Field("live_probed", description="One of live_probed | doc_only | referenced.")


class ListAgenciasOutput(BaseModel):
    items: list[dict] = Field(default_factory=list, description="ShowcaseAgencia-shaped objects.")
    probe_status: str = Field("live_probed", description="One of live_probed | doc_only | referenced.")


class ListClientesOutput(BaseModel):
    """Permission-gated. Returns empty items + a typed_error when the tenant lacks permission."""
    items: list[dict] = Field(default_factory=list)
    typed_error: Optional[dict] = Field(None, description="{class, message, status} when 401/403 hits.")
    probe_status: str = Field("live_probed", description="One of live_probed | doc_only | referenced.")


class ListCorretoresOutput(BaseModel):
    """Same gating as ListClientesOutput."""
    items: list[dict] = Field(default_factory=list)
    typed_error: Optional[dict] = Field(None)
    probe_status: str = Field("live_probed", description="One of live_probed | doc_only | referenced.")


class ProbeOutput(BaseModel):
    probes: list[dict] = Field(default_factory=list, description="One row per PROBE_ENDPOINTS entry: {endpoint, status, http_status, latency_ms, expected_http_status, as_expected, note}. Read `as_expected` — NOT `status` — to decide whether a row needs attention: several endpoints answer a bare GET with 400/401/405 by design.")
    tenant_base_url: str = Field("", description="The base URL the probe was issued against.")
    configured: bool = Field(False, description="True iff VistaClient saw both base_url + api_key.")
    unexpected: list[str] = Field(default_factory=list, description="Endpoints whose http_status differed from the documented baseline — the only rows an operator must act on. Empty means the tenant matches vista.md § 4.")


class CalibratedFieldsOutput(BaseModel):
    """Reports the per-tenant field-set the calibration routine discovered.

    Phase 1 ships this as a passthrough of the hardcoded constants — the
    real calibration routine in `calibration.py` runs lazily on first
    real call and updates these on the fly.
    """
    imoveis_list: list[Any] = Field(default_factory=list)
    imoveis_detail: list[Any] = Field(default_factory=list)
    imoveis_conteudo: list[str] = Field(default_factory=list)
    usuarios: list[str] = Field(default_factory=list)
    agencias: list[str] = Field(default_factory=list)
    rejected: dict[str, list[str]] = Field(default_factory=dict, description="Per-endpoint list of fields probed and rejected during calibration.")
    calibrated_at: Optional[str] = Field(None, description="ISO timestamp of last calibration run; null if no probe has run.")


__all__ = [
    "ShowcaseImovel",
    "ShowcaseImovelDetalhes",
    "ShowcaseUsuario",
    "ShowcaseAgencia",
    "ListImoveisInput",
    "ListImoveisOutput",
    "GetImovelInput",
    "GetImovelOutput",
    "ListImoveisFiltersOutput",
    "ListUsuariosOutput",
    "ListAgenciasOutput",
    "ListClientesOutput",
    "ListCorretoresOutput",
    "ProbeOutput",
    "CalibratedFieldsOutput",
]
