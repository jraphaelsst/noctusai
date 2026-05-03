"""Vista showcase DTOs — Pydantic models the normalizers produce.

These are the platform-canonical Vista shapes: both `mcp/vista/` (MCP tool
output) and ERP showcase router/service consume them.

MCP-tool-specific I/O schemas (`ListImoveisInput`, `ListImoveisOutput`,
`GetImovelInput`, etc.) live in `mcp/vista/types.py` — not here — because
they're MCP-server-specific (one Pydantic model per tool descriptor) and
have no consumer outside that server.

See `KB § INTEGRATIONS/vista.md § 5.2` for the full normalizer
field-mapping contract these DTOs back.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ShowcaseImovel(BaseModel):
    codigo: str = Field(..., description="Vista primary id, e.g. 'CA2830' or 'ONE10006'")
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
    raw: dict = Field(default_factory=dict, description="Vista raw payload — preserved for debug + future migration phase")


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


__all__ = [
    "ShowcaseImovel",
    "ShowcaseImovelDetalhes",
    "ShowcaseUsuario",
    "ShowcaseAgencia",
]
