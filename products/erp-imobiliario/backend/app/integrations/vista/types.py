"""Vista showcase DTOs — the shape ERP exposes to its frontend.

These are NoctusAI-side DTOs, not Vista's raw shape. The normalizer module
(`normalizers.py`) is the seam that converts Vista payloads into these.

The future migration phase will reuse these DTOs as the field-mapping
contract between Vista and ERP's canonical tables.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ShowcaseImovel(BaseModel):
    codigo: str = Field(..., description="Vista primary id, e.g. 'CA2830'")
    titulo: Optional[str] = None
    categoria: Optional[str] = None
    finalidade: Optional[str] = None
    status: Optional[str] = None
    cidade: Optional[str] = None
    bairro: Optional[str] = None
    endereco: Optional[str] = None
    cep: Optional[str] = None
    estado: Optional[str] = None
    valor_venda: Optional[float] = None
    valor_locacao: Optional[float] = None
    area_total: Optional[float] = None
    area_privativa: Optional[float] = None
    area_construida: Optional[float] = None
    dormitorios: Optional[int] = None
    suites: Optional[int] = None
    vagas: Optional[int] = None
    banheiros: Optional[int] = None
    foto_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    data_atualizacao: Optional[str] = None
    corretor_nome: Optional[str] = None
    raw: dict = Field(default_factory=dict, description="Vista raw payload — for debug & migration prep")


class ShowcaseImovelDetalhes(BaseModel):
    codigo: str
    base: ShowcaseImovel
    caracteristicas: dict = Field(default_factory=dict)
    raw: dict = Field(default_factory=dict)


class ShowcaseUsuario(BaseModel):
    codigo: str
    nome: Optional[str] = None
    email: Optional[str] = None
    setor: Optional[str] = None
    foto_url: Optional[str] = None
    raw: dict = Field(default_factory=dict)


class ShowcaseAgencia(BaseModel):
    codigo: str
    nome: Optional[str] = None
    endereco: Optional[str] = None
    cidade: Optional[str] = None
    bairro: Optional[str] = None
    site: Optional[str] = None
    raw: dict = Field(default_factory=dict)


class ShowcasePagination(BaseModel):
    pagina: int = 1
    quantidade: int = 0
    total: Optional[int] = None
    paginas: Optional[int] = None


class ShowcaseEnvelope(BaseModel):
    """Standard envelope returned by every /api/vista-showcase/{tab} endpoint."""

    source: str = "vista"
    tab: str
    live: bool = True
    fetched_at: str
    pagination: Optional[ShowcasePagination] = None
    items: list[Any] = Field(default_factory=list)
    raw_available: bool = True
    warnings: list[str] = Field(default_factory=list)


class ShowcaseTabStatus(BaseModel):
    """Reported by GET /api/vista-showcase/tabs.

    Drives the frontend's sub-tab nav — including 'Permissão pendente'
    placeholders for 401 endpoints and 'Não disponível neste tenant' for
    404 endpoints.
    """

    tab: str
    label: str
    status: str  # "live" | "permission_denied" | "not_found" | "not_configured" | "doc_only"
    endpoint: str
    note: Optional[str] = None


class ShowcaseDiagnostic(BaseModel):
    tenant_base_url: str
    configured: bool
    probes: list[dict] = Field(default_factory=list)
