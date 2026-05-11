"""Request/response schemas for `app.routers.products`."""
from __future__ import annotations

from typing import Optional

from noctusai_lib.api import StrictHttpModel


class ProductCreate(StrictHttpModel):
    nome: str
    slug: str
    descricao: Optional[str] = None
    icone: Optional[str] = None
    url_base: str  # e.g. http://localhost:8080 or https://erp.noctus.ai
    cor: Optional[str] = "#6366f1"  # brand color
    logout_behavior: Optional[str] = "redirect"  # 'redirect' or 'signout'


class ProductUpdate(StrictHttpModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    icone: Optional[str] = None
    url_base: Optional[str] = None
    cor: Optional[str] = None
    ativo: Optional[bool] = None
    logout_behavior: Optional[str] = None  # 'redirect' or 'signout'
