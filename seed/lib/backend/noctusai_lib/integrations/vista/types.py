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


class ShowcaseCliente(BaseModel):
    """One CRM client, LIST view — deliberately the minimised projection.

    🔴 The demographic categories this tenant also exposes (`DataNascimento`,
    `Sexo`, `EstadoCivil`, `Profissao`) are NOT on this model, and that is the
    point: a 42,960-row list is the worst place to carry a demographic profile,
    and the ERP renders one page of it per admin click. They live on
    :class:`ShowcaseClienteDetalhes` instead, reachable only by opening a
    single named record — one deliberate act, one audit row.

    Minimisation by CONSTRUCTION, not by convention: the list endpoint cannot
    leak a birth date because there is nowhere on this type to put one. A
    future edit that wants those fields in the list has to change the type,
    which is exactly the moment the decision should be re-made.

    No `raw` passthrough either, unlike the imóvel/usuário/agência DTOs. Those
    carry the untouched Vista payload "for debug + future migration"; there is
    no clientes migration, and an unstructured copy of personal data is the
    thing minimisation argues against most. The envelope reports
    `raw_available=False` so the UI never offers a payload dump for this tab.

    Field set confirmed live 2026-08-21 — KB § INTEGRATIONS/vista.md § 4.2.
    """

    codigo: str = Field(..., description="Vista primary id for the client")
    nome: Optional[str] = None
    celular: Optional[str] = None
    status: Optional[str] = None
    data_cadastro: Optional[str] = None
    corretor_nome: Optional[str] = None
    interesse: Optional[str] = None


class ShowcaseClienteDetalhes(BaseModel):
    """One CRM client, DETAIL view — the list projection PLUS the demographics.

    Everything special-category-adjacent this tenant returns lands here and
    nowhere else. Reached only via `/clientes/detalhes` for one named `codigo`.
    """

    codigo: str
    base: ShowcaseCliente
    data_nascimento: Optional[str] = None
    sexo: Optional[str] = None
    estado_civil: Optional[str] = None
    profissao: Optional[str] = None


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
    "ShowcaseCliente",
    "ShowcaseClienteDetalhes",
    "ShowcaseUsuario",
    "ShowcaseAgencia",
]
