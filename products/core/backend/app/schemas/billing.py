"""Request/response schemas for `app.routers.billing`."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class CheckoutRequest(StrictHttpModel):
    plan_id: str = Field(..., description="UUID do plano desejado")
    billing_cycle: str = Field(
        default="monthly",
        pattern="^(monthly|yearly)$",
        description="Ciclo de cobranca: monthly ou yearly",
    )
    success_url: Optional[str] = Field(
        default=None,
        description="URL de redirecionamento apos pagamento bem-sucedido",
    )
    cancel_url: Optional[str] = Field(
        default=None,
        description="URL de redirecionamento se o usuario cancelar o checkout",
    )


class PortalRequest(StrictHttpModel):
    return_url: Optional[str] = Field(
        default=None,
        description="URL de retorno apos sair do portal Stripe",
    )


class CancelRequest(StrictHttpModel):
    at_period_end: bool = Field(
        default=True,
        description="Se True, cancela ao final do periodo atual. Se False, cancela imediatamente.",
    )
