"""The one DI seam for Core billing.

Every billing router takes `BillingContext` via `Depends(get_billing_context)`
and every scheduler job builds one with `build_billing_context()`. Tests
replace the whole context through `app.dependency_overrides` (routers) or
pass one in (jobs) — the Fake gateway, Fake inbox, Fake FX adapter, Fake
checkout and a fixed clock all enter here, so no test patches our code.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from noctusai_lib.domain.payments import EventInbox, make_event_inbox
from noctusai_lib.integrations.fx import FxRateAdapter, get_fx_rate_adapter
from noctusai_lib.integrations.payments import make_payment_gateway
from noctusai_lib.integrations.payments.checkout import HostedCheckout, make_hosted_checkout
from noctusai_lib.integrations.payments.protocol import PaymentGateway

from app.config import Settings, settings as default_settings
from app.database import get_admin_client
from app.services.billing_config import (
    ASAAS_BASE_URLS,
    BillingConfig,
    GatewayNotConfigured,
    build_config_store,
)

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class BillingContext:
    db: Any
    settings: Settings
    config: BillingConfig
    gateway_factory: Callable[[str, str], PaymentGateway]
    checkout_factory: Callable[[str, str], HostedCheckout]
    inbox: EventInbox
    fx: FxRateAdapter
    clock: Clock = utc_now

    def gateway(self, gateway: str, mode: str) -> PaymentGateway:
        return self.gateway_factory(gateway, mode)

    def checkout(self, gateway: str, mode: str) -> HostedCheckout:
        return self.checkout_factory(gateway, mode)

    def webhook_base_url(self) -> str:
        return (self.settings.public_api_base_url or self.settings.app_base_url).rstrip("/")


def _gateway_kwargs(config: BillingConfig, gateway: str, mode: str) -> dict:
    """Seed-factory kwargs for the key configured for (gateway, mode)."""
    if gateway == "stripe":
        key = config.get_secret("stripe", "secret_key", mode)
        if not key:
            raise GatewayNotConfigured(f"Stripe sem chave para o modo '{mode}'.")
        return {"provider": "stripe", "stripe_api_key": key}
    if gateway == "asaas":
        key = config.get_secret("asaas", "api_key", mode)
        if not key:
            raise GatewayNotConfigured(f"Asaas sem chave para o modo '{mode}'.")
        return {"provider": "asaas", "asaas_api_key": key, "asaas_base_url": ASAAS_BASE_URLS[mode]}
    raise GatewayNotConfigured(f"Gateway desconhecido: {gateway}")


def make_gateway_factory(config: BillingConfig) -> Callable[[str, str], PaymentGateway]:
    return lambda gateway, mode: make_payment_gateway(**_gateway_kwargs(config, gateway, mode))


def make_checkout_factory(config: BillingConfig) -> Callable[[str, str], HostedCheckout]:
    return lambda gateway, mode: make_hosted_checkout(**_gateway_kwargs(config, gateway, mode))


def build_billing_context(
    *, db: Optional[Any] = None, app_settings: Optional[Settings] = None
) -> BillingContext:
    """Production wiring."""
    db = db if db is not None else get_admin_client()
    cfg_settings = app_settings or default_settings
    config = BillingConfig(
        db,
        store_factory=lambda: build_config_store(db, cfg_settings.encryption_key),
        env_stripe_secret_key=cfg_settings.stripe_secret_key,
        env_stripe_webhook_secret=cfg_settings.stripe_webhook_secret,
    )
    return BillingContext(
        db=db,
        settings=cfg_settings,
        config=config,
        gateway_factory=make_gateway_factory(config),
        checkout_factory=make_checkout_factory(config),
        inbox=make_event_inbox(supabase_client=db, table_name="payment_events"),
        fx=get_fx_rate_adapter(live=True),
    )


def get_billing_context() -> BillingContext:
    """FastAPI dependency. Override in tests via `app.dependency_overrides`."""
    return build_billing_context()


__all__ = [
    "BillingContext",
    "Clock",
    "build_billing_context",
    "get_billing_context",
    "make_checkout_factory",
    "make_gateway_factory",
    "utc_now",
]
