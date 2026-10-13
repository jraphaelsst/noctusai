"""`CommerceConfig` — everything that differs between two commerce products.

The mechanics (catalog, checkout, order machine, webhook, privacy) are identical
for every market product; only these knobs differ. Table names are NOT here on
purpose: the `commerce_*` names are part of the wire/DB contract
(`projects/commerce-seed-p3/CONTRACT.md §2`) and the frontend organ + the
host product's parity test pin them. A knob that renamed a table would let two
products drift into two organs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

DEFAULT_WITHDRAWAL_TEXT = (
    "Direito de arrependimento: em compras feitas fora do estabelecimento (internet), "
    "você pode desistir da compra em até 7 (sete) dias corridos, contados da assinatura "
    "do contrato ou do recebimento do produto ou serviço (art. 49 do Código de Defesa do "
    "Consumidor). Para produtos digitais de entrega imediata, o direito de arrependimento "
    "é exercido nos termos informados no momento da compra."
)


@dataclass(frozen=True)
class CommerceConfig:
    """One commerce product's knobs.

    Attributes:
        schema: the product's Postgres schema (also the PostgREST schema the
            router's `get_db` client is scoped to).
        bucket: PRIVATE storage bucket for product media; keys are
            `<org_id>/products/<product_id>/<media_id>.<ext>`.
        license_product_slug: `products.slug` the storefront license check uses
            (an org without an active license for it is a 404, not a 403).
        storefront_rate_limit / checkout_rate_limit / webhook_rate_limit:
            slowapi limit strings applied through the host-supplied
            `rate_limit` decorator factory (see `storefront_router`).
        terms_version / privacy_version: the legal-text versions the checkout
            requires the buyer to have accepted (a stale page => `aceite_obrigatorio`).
        withdrawal_text: the right-of-withdrawal disclosure the storefront serves.
        platform_wallet_credential: `resolve_credential` key (PLATFORM tier) of
            noc's Asaas wallet id for the fee split (D27).
        asaas_api_key_name / asaas_webhook_token_name: per-org credential names.
        order_expiry_hours: how long a pending order's charge stays payable.
        *_path_template: frontend paths the redirect/e-mail links point to.
        link_ttl_minutes: lifetime of an e-mailed access / verification link.
        signed_url_ttl_seconds: lifetime of a media signed URL.
        org_id_expr: SQL expression the authenticated own-org policies compare to.
    """

    schema: str
    bucket: str = "commerce-media"
    license_product_slug: str = "commerce"
    storefront_rate_limit: str = "120/minute"
    checkout_rate_limit: str = "10/minute"
    webhook_rate_limit: str = "300/minute"
    terms_version: str = "1.0"
    privacy_version: str = "1.0"
    withdrawal_text: str = DEFAULT_WITHDRAWAL_TEXT
    platform_wallet_credential: str = "asaas_platform_wallet_id"
    asaas_api_key_name: str = "asaas_api_key"
    asaas_webhook_token_name: str = "asaas_webhook_token"
    order_expiry_hours: int = 72
    order_path_template: str = "/pedido/{token}"
    my_orders_path_template: str = "/minhas-compras?token={token}"
    privacy_verify_path_template: str = "/privacidade/verificar?token={token}"
    link_ttl_minutes: int = 60
    signed_url_ttl_seconds: int = 3600
    org_id_expr: str = "public.current_org_id()"

    def __post_init__(self) -> None:
        if not _IDENT.match(self.schema or ""):
            raise ValueError(f"CommerceConfig.schema must be a bare lowercase identifier, got {self.schema!r}")
        if not _BUCKET.match(self.bucket or ""):
            raise ValueError(f"CommerceConfig.bucket must be a bucket id, got {self.bucket!r}")
        for name in ("storefront_rate_limit", "checkout_rate_limit", "webhook_rate_limit"):
            if not getattr(self, name).strip():
                raise ValueError(f"CommerceConfig.{name} must be a non-empty limit string")
        if self.order_expiry_hours < 1 or self.link_ttl_minutes < 1 or self.signed_url_ttl_seconds < 1:
            raise ValueError("CommerceConfig durations must be >= 1")
        for name in ("order_path_template", "my_orders_path_template", "privacy_verify_path_template"):
            if "{token}" not in getattr(self, name):
                raise ValueError(f"CommerceConfig.{name} must contain '{{token}}'")


@dataclass(frozen=True)
class CommerceContext:
    """What every staff handler needs, resolved by the host's `resolve_context`."""

    db: Any
    org_id: str
    user_id: str


__all__ = ["CommerceConfig", "CommerceContext", "DEFAULT_WITHDRAWAL_TEXT"]
