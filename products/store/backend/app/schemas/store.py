"""HTTP-boundary shapes for the store API (contract §2 / §3).

Inbound models are `StrictHttpModel` (`extra="forbid"`): an unknown field is
a 422, never a silently dropped write. Settings validation lives HERE (one
place) — price 100..1_000_000, 1–8 items, guarantee 0..30, bio <= 600.
"""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

MAX_ITEMS = 8


class SettingsItem(StrictHttpModel):
    label: str = Field(min_length=1, max_length=200)
    anchor_cents: int = Field(ge=0, le=100_000_000)


class SettingsAuthor(StrictHttpModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(default="", max_length=120)
    bio: str = Field(default="", max_length=600)
    has_photo: bool = False


class LandingSettings(StrictHttpModel):
    product_name: str = Field(min_length=1, max_length=200)
    price_cents: int = Field(ge=100, le=1_000_000)
    items: list[SettingsItem] = Field(min_length=1, max_length=MAX_ITEMS)
    guarantee_days: int = Field(ge=0, le=30)
    author: SettingsAuthor
    checkout_enabled: bool = True


class SettingsUpdate(StrictHttpModel):
    data: LandingSettings
    expected_version: int = Field(ge=0)


class CheckoutIn(StrictHttpModel):
    """Loosely typed on purpose (plain `str`): CPF/email get a dedicated 422
    with a pt-BR message from the service, not Pydantic's default shape."""

    nome: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=254)
    cpf: str = Field(max_length=32)


class CheckoutOut(StrictHttpModel):
    checkout_url: str
    pedido_token: str


class PedidoPublicOut(StrictHttpModel):
    status: str
    produto: str
    email_mascarado: str
    download_url: Optional[str] = None


class KitInfoOut(StrictHttpModel):
    exists: bool
    size: Optional[int] = None
    updated_at: Optional[str] = None
