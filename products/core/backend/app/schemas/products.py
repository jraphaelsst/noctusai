"""Request/response schemas for `app.routers.products`."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class ProductCreate(StrictHttpModel):
    nome: str
    slug: str
    descricao: Optional[str] = None
    # A product must ship a REAL icon — required and non-empty. The value must
    # render as an actual icon, never bare text: a lucide-react name registered
    # in core/frontend/src/lib/product-icon.tsx `ICONS` (e.g. "Building2") or an
    # emoji. Enforced repo-wide by the `check_product_icon_registered` keeper.
    icone: str = Field(min_length=1)
    url_base: str  # e.g. http://localhost:8080 or https://erp.noctus.ai
    cor: Optional[str] = "#6366f1"  # brand color
    logout_behavior: Optional[str] = "redirect"  # 'redirect' or 'signout'


class ProductUpdate(StrictHttpModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    # Optional on update, but if supplied it must be non-empty (same icon rule).
    icone: Optional[str] = Field(default=None, min_length=1)
    url_base: Optional[str] = None
    cor: Optional[str] = None
    ativo: Optional[bool] = None
    logout_behavior: Optional[str] = None  # 'redirect' or 'signout'
