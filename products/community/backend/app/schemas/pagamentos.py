"""Schemas for the `pagamentos` domain (contract §Manager+member views,
amendment A16 — admin-only) and the `plano_gateway_refs` sub-resource
(contract §Gateway refs).

`GatewayRef*` lives here, not in `schemas/planos.py` — module 2's owned
scope is disjoint from `planos.py` / `planos_service.py` (untouched by
this slice); `plano_gateway_refs` is its own table with its own service
(`app/services/gateway_refs_service.py`), only nested under the
`/api/planos/{plano_id}/gateway-refs` URL path for discoverability.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PAGAMENTO_ESTADOS = ("pendente", "pago", "falhou", "estornado")
GATEWAYS = ("stripe", "asaas")


class Pagamento(BaseModel):
    """Response body — `admin`-only (amendment A16/P3: `moderador` never
    sees this shape, on any route)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    membro_id: UUID
    membro_nome: Optional[str] = None
    assinatura_id: Optional[UUID] = None
    gateway: str
    cobranca_externa_id: str
    valor_centavos: int
    metodo: str
    estado: str
    pago_em: Optional[datetime] = None
    vencimento: Optional[datetime] = None
    url_fatura: Optional[str] = None
    pix_payload: Optional[str] = None
    pix_imagem_base64: Optional[str] = None
    created_at: datetime


class GatewayRefUpsert(BaseModel):
    """Request body for `PUT /api/planos/{plano_id}/gateway-refs/{gateway}`."""

    model_config = ConfigDict(extra="forbid")

    ref_externo: str = Field(..., min_length=1, max_length=500)


class GatewayRef(BaseModel):
    """Response body — contract's `GatewayRef` shape."""

    model_config = ConfigDict(from_attributes=True)

    plano_id: UUID
    gateway: str
    ref_externo: str
    updated_at: datetime


class GatewayRefListResponse(BaseModel):
    """Paginated-envelope shape for `GET /api/planos/{plano_id}/gateway-refs`
    (no actual pagination — a plano has at most 2 refs, one per gateway)."""

    items: list[GatewayRef]
    total: int


# ── PUBLIC tier listing (amendment A17) ───────────────────────────────
#
# Lives here (not `schemas/planos.py`, outside module 2's owned scope)
# for the same reason `GatewayRef*` does — `PlanoPublico` is DERIVED
# from `planos` joined with `plano_gateway_refs`, both module 2 concerns.


class Beneficios(BaseModel):
    """The boolean-only projection of `entitlements` — amendment A17.
    `conteudo_ids` / `grupos_whatsapp` (internal ids) are NEVER
    serialized publicly; this model has no fields for them at all."""

    model_config = ConfigDict(extra="forbid")

    feed: bool = False
    forum: bool = False
    chat: bool = False
    eventos: bool = False


class PlanoPublico(BaseModel):
    """Response body for `GET /api/planos/publicos` (PUBLIC, amendment
    A17) — deliberately NARROWER than `schemas.planos.Plano`.
    `ref_externo` / any gateway reference, `membros_ativos`, `ativo`,
    `ordem`, and timestamps are never serialized here (this model simply
    has no such fields)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    descricao: Optional[str] = None
    preco_centavos: int
    ciclo: str
    beneficios: Beneficios
    metodos_disponiveis: list[str]


class PlanoPublicoListResponse(BaseModel):
    items: list[PlanoPublico]
    total: int
