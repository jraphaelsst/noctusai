"""Shared Fakes for the Core billing tests — every one enters through
`BillingContext` (the production DI seam), none patches our code.

`make_ctx()` returns a context over a `MockSupabaseClient` (schema-validated
against the migrations, so a wrong column name fails here as it would in
Postgres) plus the seed Fakes: `FakePaymentGateway` per gateway,
`FakeEventInbox`, `FakeFxRateAdapter`, `FakeAppConfigStore`,
`FakeHostedCheckout` + a settable clock.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from noctusai_lib.domain.payments import FakeEventInbox
from noctusai_lib.integrations.fx import FakeFxRateAdapter
from noctusai_lib.integrations.payments import FakePaymentGateway
from noctusai_lib.integrations.payments.checkout import FakeHostedCheckout
from noctusai_lib.integrations.payments.types import PaymentGatewayName
from noctusai_lib.security.app_config import FakeAppConfigStore

from app.config import Settings
from app.services.billing_config import BillingConfig, secret_key_name
from app.services.billing_context import BillingContext
from noctusai_lib.testing import MockSupabaseClient

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)

ORG_ID = "11111111-1111-1111-1111-111111111111"
OTHER_ORG_ID = "22222222-2222-2222-2222-222222222222"
PRODUCT_ID = "33333333-3333-3333-3333-333333333333"
PLAN_ID = "44444444-4444-4444-4444-444444444444"
PRICE_ID = "55555555-5555-5555-5555-555555555555"
ADMIN_USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OWNER_USER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
MEMBER_USER = "cccccccc-cccc-cccc-cccc-cccccccccccc"

STRIPE_WHSEC_TEST = "whsec_test_secret_value"
STRIPE_WHSEC_LIVE = "whsec_live_secret_value"
ASAAS_TOKEN_TEST = "asaas-test-token-0123456789"
ASAAS_TOKEN_LIVE = "asaas-live-token-0123456789"


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@dataclass
class Fakes:
    db: MockSupabaseClient
    clock: Clock
    gateways: dict[str, FakePaymentGateway]
    checkouts: dict[str, FakeHostedCheckout]
    inbox: FakeEventInbox
    fx: FakeFxRateAdapter
    store: FakeAppConfigStore
    gateway_requests: list[tuple[str, str]] = field(default_factory=list)


def default_secrets() -> dict[str, str]:
    return {
        secret_key_name("stripe", "secret_key", "test"): "sk_test_123",
        secret_key_name("stripe", "webhook_secret", "test"): STRIPE_WHSEC_TEST,
        secret_key_name("stripe", "secret_key", "live"): "sk_live_123",
        secret_key_name("stripe", "webhook_secret", "live"): STRIPE_WHSEC_LIVE,
        secret_key_name("asaas", "api_key", "test"): "$aact_hmlg_000000000000000000",
        secret_key_name("asaas", "webhook_token", "test"): ASAAS_TOKEN_TEST,
        secret_key_name("asaas", "api_key", "live"): "$aact_prod_000000000000000000",
        secret_key_name("asaas", "webhook_token", "live"): ASAAS_TOKEN_LIVE,
    }


def seed_catalog(db: MockSupabaseClient, *, trial_days: int = 7, grace_days: int = 5, audience: str = "any") -> None:
    db.set_table_data("products", [{"id": PRODUCT_ID, "slug": "social-wiring", "nome": "Social Wiring"}])
    db.set_table_data(
        "plans",
        [
            {
                "id": PLAN_ID, "nome": "Corretor", "slug": "corretor", "ativo": True,
                "product_id": PRODUCT_ID, "audience": audience, "trial_days": trial_days,
                "grace_days": grace_days, "price_monthly": 0, "price_yearly": 0,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        ],
    )
    db.set_table_data(
        "plan_prices",
        [
            {
                "id": PRICE_ID, "plan_id": PLAN_ID, "billing_cycle": "monthly", "currency": "BRL",
                "amount_cents": 9900, "stripe_price_id_test": "price_test123",
                "stripe_price_id_live": None, "ativo": True,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        ],
    )
    db.set_table_data(
        "organizations",
        [
            {"id": ORG_ID, "nome": "Imobiliária A", "slug": "comp_a", "org_type": "company"},
            {"id": OTHER_ORG_ID, "nome": "Corretor B", "slug": "indv_b", "org_type": "individual"},
        ],
    )


def seed_users(db: MockSupabaseClient) -> None:
    db.set_table_data(
        "noctus_users",
        [
            {"id": ADMIN_USER, "email": "admin@noctus.ai", "role": "admin", "org_role": "member", "org_id": OTHER_ORG_ID},
            {"id": OWNER_USER, "email": "owner@a.com", "role": "user", "org_role": "owner", "org_id": ORG_ID},
            {"id": MEMBER_USER, "email": "member@a.com", "role": "user", "org_role": "member", "org_id": ORG_ID},
        ],
    )


def make_ctx(
    *,
    automations: bool = True,
    mode: str = "test",
    stripe: bool = True,
    asaas: bool = True,
    secrets: Optional[dict[str, str]] = None,
    ptax: Optional[dict[date, Decimal]] = None,
    storage_price: Optional[str] = "0.021",
    db: Optional[MockSupabaseClient] = None,
    encryption: bool = True,
) -> tuple[BillingContext, Fakes]:
    db = db or MockSupabaseClient()
    flags = [
        {"key": "billing_automations_enabled", "value": "true" if automations else "false"},
        {"key": "billing_gateway_mode", "value": mode},
        {"key": "billing_stripe_enabled", "value": "true" if stripe else "false"},
        {"key": "billing_asaas_enabled", "value": "true" if asaas else "false"},
    ]
    if storage_price is not None:
        flags.append({"key": "storage_price_usd_per_gb_month", "value": storage_price})
    db.set_table_data("platform_settings", flags)

    store = FakeAppConfigStore()
    for key, value in (default_secrets() if secrets is None else secrets).items():
        store.put(key, value)

    def store_factory():
        if not encryption:
            from app.services.billing_config import EncryptionNotConfigured

            raise EncryptionNotConfigured("test: no ENCRYPTION_KEY")
        return store

    clock = Clock()
    stripe_gw = FakePaymentGateway()
    asaas_gw = FakePaymentGateway()
    asaas_gw.name = PaymentGatewayName.ASAAS
    gateways = {"stripe": stripe_gw, "asaas": asaas_gw}
    fakes = Fakes(
        db=db,
        clock=clock,
        gateways=gateways,
        checkouts={"stripe": FakeHostedCheckout(), "asaas": FakeHostedCheckout()},
        inbox=FakeEventInbox(),
        fx=FakeFxRateAdapter(bulletins=dict(ptax or {})),
        store=store,
    )
    config = BillingConfig(db, store_factory=store_factory, clock=clock)

    def gateway_factory(gateway: str, gateway_mode: str):
        fakes.gateway_requests.append((gateway, gateway_mode))
        return gateways[gateway]

    ctx = BillingContext(
        db=db,
        settings=Settings(app_base_url="https://core.example.com"),
        config=config,
        gateway_factory=gateway_factory,
        checkout_factory=lambda gateway, gateway_mode: fakes.checkouts[gateway],
        inbox=fakes.inbox,
        fx=fakes.fx,
        clock=clock,
    )
    return ctx, fakes


def managed_subscription(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "66666666-6666-6666-6666-666666666666",
        "org_id": ORG_ID,
        "plan_id": PLAN_ID,
        "plan_price_id": PRICE_ID,
        "status": "active",
        "gateway": "stripe",
        "gateway_mode": "test",
        "gateway_subscription_id": "sub_gw_1",
        "gateway_customer_id": "cus_gw_1",
        "billing_cycle": "monthly",
        "billing_method": "card",
        "currency": "BRL",
        "amount_cents": 9900,
        "automation_managed": True,
        "cancel_at_period_end": False,
        "metadata": {},
        "started_at": "2026-08-01T00:00:00+00:00",
        "created_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00",
        "current_period_end": "2026-10-01T00:00:00+00:00",
        "canceled_at": None,
        "past_due_since": None,
        "grace_ends_at": None,
        "trial_ends_at": None,
    }
    row.update(overrides)
    return row


def legacy_subscription(**overrides: Any) -> dict[str, Any]:
    row = managed_subscription(
        id="77777777-7777-7777-7777-777777777777",
        automation_managed=False,
        gateway=None,
        gateway_subscription_id=None,
        amount_cents=None,
        billing_cycle=None,
        currency=None,
    )
    row.update(overrides)
    return row


def sign_stripe(payload: bytes, secret: str) -> dict[str, str]:
    return {"stripe-signature": stripe_signature(payload, secret), "content-type": "application/json"}


def stripe_signature(payload: bytes, secret: str, *, timestamp: Optional[int] = None) -> str:
    ts = int(timestamp if timestamp is not None else time.time())
    signed = f"{ts}.".encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


_STRIPE_OBJECT_TYPES = {
    "checkout.session": "checkout.session",
    "customer.subscription": "subscription",
    "invoice": "invoice",
    "customer": "customer",
    "charge": "charge",
}


def stripe_event(event_id: str, event_type: str, obj: dict[str, Any], *, livemode: bool = False) -> bytes:
    """A payload shaped like a real Stripe event (the SDK requires `object`)."""
    prefix = event_type.rsplit(".", 1)[0]
    body = dict(obj)
    body.setdefault("object", _STRIPE_OBJECT_TYPES.get(prefix, prefix))
    return json.dumps(
        {
            "id": event_id,
            "object": "event",
            "api_version": "2025-03-31.basil",
            "created": int(NOW.timestamp()),
            "type": event_type,
            "livemode": livemode,
            "data": {"object": body},
        }
    ).encode()


def asaas_event(event_id: str, event_type: str, **body: Any) -> bytes:
    return json.dumps({"id": event_id, "event": event_type, **body}).encode()
