"""
Pydantic schemas for the AdConnect catalog domain.

Schema source-of-truth: `migrations/001_adconnect.sql` (the single fresh-start
migration — KB § PATTERNS/database-rls.md § Single 001 migration convention).
The shapes here are wire-format (request/response) contracts; they mirror
the SQL columns 1:1 (snake_case throughout).

Tables covered (Phase 2):
  • adconnect.categorias
  • adconnect.products
  • adconnect.precos_distribuidor
  • adconnect.promos

Distributor read-side schema is included here too (Phase 2 routers expose
list/get; Phase 1 distributor CRUD is Engineer A's territory).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Categorias
# ---------------------------------------------------------------------------


class CategoriaIn(BaseModel):
    """Payload for creating/updating a category."""

    nome: str = Field(min_length=1, max_length=128)
    descricao: Optional[str] = None
    ordem: int = 0
    ativa: bool = True


class CategoriaOut(BaseModel):
    """Read-side category row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    nome: str
    descricao: Optional[str] = None
    ordem: int = 0
    ativa: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


class ProductIn(BaseModel):
    """Payload for creating/updating a product."""

    sku: str = Field(min_length=1, max_length=64)
    nome: str = Field(min_length=1, max_length=255)
    descricao: Optional[str] = None
    categoria_id: Optional[UUID] = None
    base_price: Decimal = Field(ge=0)
    in_stock: bool = True
    estoque_quantidade: Optional[int] = None
    fotos: list[str] = Field(default_factory=list)
    ativo: bool = True


class ProductOut(BaseModel):
    """Read-side product row.

    The `effective_price` field is populated by the service layer when the
    caller is a distributor user — it carries the per-distributor preferential
    price (or `base_price` when no preferential row exists). Brand admins
    always see `effective_price = base_price`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    sku: str
    nome: str
    descricao: Optional[str] = None
    categoria_id: Optional[UUID] = None
    base_price: Decimal = Decimal("0")
    in_stock: bool = True
    estoque_quantidade: Optional[int] = None
    fotos: list[str] = Field(default_factory=list)
    ativo: bool = True
    effective_price: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Per-distributor preferential pricing
# ---------------------------------------------------------------------------


class PrecoDistribuidorIn(BaseModel):
    """Payload for setting a per-distributor preferential price."""

    product_id: UUID
    distributor_id: UUID
    preferential_price: Decimal = Field(ge=0)
    valido_de: Optional[datetime] = None
    valido_ate: Optional[datetime] = None


class PrecoDistribuidorOut(BaseModel):
    """Read-side preferential price row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    distributor_id: UUID
    preferential_price: Decimal
    valido_de: Optional[datetime] = None
    valido_ate: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Promos
# ---------------------------------------------------------------------------


class PromoIn(BaseModel):
    """Payload for creating/updating a promotional rule.

    Per the `adconnect.promos` CHECK constraint, exactly one of
    `desconto_percentual` or `desconto_valor` must be set.
    """

    nome: str = Field(min_length=1, max_length=255)
    descricao: Optional[str] = None
    desconto_percentual: Optional[Decimal] = Field(default=None, ge=0, le=100)
    desconto_valor: Optional[Decimal] = Field(default=None, ge=0)
    valido_de: datetime
    valido_ate: datetime
    ativa: bool = True
    aplicavel_categorias: list[UUID] = Field(default_factory=list)
    aplicavel_produtos: list[UUID] = Field(default_factory=list)
    aplicavel_distribuidores: list[UUID] = Field(default_factory=list)


class PromoOut(BaseModel):
    """Read-side promo row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    nome: str
    descricao: Optional[str] = None
    desconto_percentual: Optional[Decimal] = None
    desconto_valor: Optional[Decimal] = None
    valido_de: datetime
    valido_ate: datetime
    ativa: bool = True
    aplicavel_categorias: list[UUID] = Field(default_factory=list)
    aplicavel_produtos: list[UUID] = Field(default_factory=list)
    aplicavel_distribuidores: list[UUID] = Field(default_factory=list)
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Distributor schemas (read-side only for Phase 2 — Phase 1 owns full CRUD).
# ---------------------------------------------------------------------------


class DistributorOut(BaseModel):
    """Read-side distributor row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    cnpj: str
    nome: str
    endereco_logradouro: Optional[str] = None
    endereco_numero: Optional[str] = None
    endereco_complemento: Optional[str] = None
    endereco_bairro: Optional[str] = None
    endereco_cidade: Optional[str] = None
    endereco_uf: Optional[str] = None
    endereco_cep: Optional[str] = None
    contato_nome: Optional[str] = None
    contato_email: Optional[str] = None
    contato_telefone: Optional[str] = None
    status: str = "ativo"
    tier: str = "STARTER"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


__all__ = [
    "CategoriaIn",
    "CategoriaOut",
    "ProductIn",
    "ProductOut",
    "PrecoDistribuidorIn",
    "PrecoDistribuidorOut",
    "PromoIn",
    "PromoOut",
    "DistributorOut",
]
