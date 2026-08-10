"""Request/response schemas for `app.routers.products`."""
from __future__ import annotations

from typing import Literal, Optional

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
    # `icone` / `url_base` stay on the API because the SYSTEM manipulates them
    # (scaffolder, url-roster tooling) — the admin edit modal deliberately does
    # not expose them, alongside the immutable slug.
    icone: Optional[str] = Field(default=None, min_length=1)
    url_base: Optional[str] = None
    cor: Optional[str] = None
    logout_behavior: Optional[str] = None  # 'redirect' or 'signout'

    # NOTE: `ativo` and `deploy_scope` are DELIBERATELY absent.
    #
    # Both carry transition RULES (an inactive product can never be live; a
    # reactivated product always lands in dev). A generic PATCH cannot express
    # those — it would let a caller set `ativo=false` while `deploy_scope`
    # stayed 'live', which the DB CHECK would then reject as an opaque 500.
    # Routing them through /activation and /deploy-scope keeps ONE code path
    # that owns the rules and returns honest 4xx errors.


class ProductActivation(StrictHttpModel):
    """Body for `POST /api/products/{id}/activation` — the STATUS axis.

    Deactivating demotes `deploy_scope` to 'dev' in the same write (a live
    product cannot be deactivated in place). Reactivating always lands in
    'dev'; promoting back to 'live' is a separate, explicit human action.
    """

    ativo: bool


class ProductDeployScope(StrictHttpModel):
    """Body for `POST /api/products/{id}/deploy-scope` — the SCOPE axis.

    'live' → worked in prod (dev-validate, then promote).
    'dev'  → worked in dev only; never reaches prod.
    Refused with 409 when the product is inactive.
    """

    deploy_scope: Literal["live", "dev"]
