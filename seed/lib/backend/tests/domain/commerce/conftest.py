"""Shared harness for the commerce organ suite.

The mock PostgREST client validates EVERY column the code touches against the
schema EMITTED BY `commerce_migration` (injected through the mock's own
`set_cache_for_tests` seam), so a column the services write that the generator
forgot fails here, not in prod. Nothing is monkeypatched: db, storage, gateway,
mailer, licence checker and inbox are the factories' own DI seams.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.commerce import (
    CommerceConfig,
    CommerceContext,
    FakeCheckoutGateway,
    commerce_migration,
    commerce_staff_router,
    commerce_webhook_router,
    make_fulfillment_registry,
    storefront_router,
)
from noctusai_lib.domain.commerce.fulfillment import FulfillmentRegistry
from noctusai_lib.domain.licensing import FakeLicenseChecker
from noctusai_lib.domain.payments import FakeEventInbox
from noctusai_lib.integrations.cnpj_registry import FakeCnpjRegistryLookup
from noctusai_lib.integrations.email import FakeEmailSender
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.primitives.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from noctusai_lib.testing import _schema_cache
from noctusai_lib.testing.migration_parser import parse_sql
from noctusai_lib.testing.mocks import MockSupabaseClient

ORG_A = "5b0e8f7a-1c2d-4e3f-9a8b-7c6d5e4f3a2b"
ORG_B = "9c8d7e6f-5a4b-4c3d-8e2f-1a0b9c8d7e6f"
USER_ID = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
SCHEMA = "commerce"
HOST_A = "loja-a.test"
HOST_B = "loja-b.test"
AUTH = {"Authorization": "Bearer test-token"}
VALID_CNPJ = "11222333000181"  # check digits valid
VALID_CPF = "52998224725"  # check digits valid
SECRET = "test-link-secret"

CFG = CommerceConfig(schema=SCHEMA)


def run(coro):
    """Drive a coroutine to completion (the suite does not depend on an asyncio pytest plugin)."""
    return asyncio.run(coro)


@pytest.fixture
def commerce_schema_cache():
    """Extend the mock's migration-derived schema map with the organ's template output
    (restored, not reset, afterwards: a reset would re-parse every product's migrations)."""
    base = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
    generated = parse_sql(commerce_migration(CFG, SCHEMA), source_label="commerce_migration")
    _schema_cache.set_cache_for_tests({**base, **generated})
    yield
    _schema_cache.set_cache_for_tests(base)


def make_db() -> MockSupabaseClient:
    return MockSupabaseClient(validate_schema=True, schema=SCHEMA)


@pytest.fixture
def db(commerce_schema_cache) -> MockSupabaseClient:
    return make_db()


def _auth(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    role = authorization.split(" ", 1)[1]
    return {"org_id": ORG_B if role == "org-b" else ORG_A, "user_id": USER_ID, "admin": role == "admin"}


def _resolve(auth: dict, db: Any) -> CommerceContext:
    return CommerceContext(db=db, org_id=auth["org_id"], user_id=auth["user_id"])


@dataclass
class Harness:
    db: MockSupabaseClient
    storage: FakeStorageBackend
    gateway: FakeCheckoutGateway
    mailer: FakeEmailSender
    checker: FakeLicenseChecker
    inbox: FakeEventInbox
    cnpj: FakeCnpjRegistryLookup
    fulfillment: FulfillmentRegistry
    app: FastAPI
    client: TestClient
    limited: list[str] = field(default_factory=list)

    def staff(self, role: str = "user") -> dict:
        return {"Authorization": f"Bearer {role}"}

    def shop(self, host: str = HOST_A, **extra: str) -> dict:
        return {"host": host, **extra}

    def seed_host(self, org: str = ORG_A, host: str = HOST_A) -> None:
        rows = self.db.table("commerce_storefront_hosts").select("*").execute().data or []
        self.db.set_table_data(
            "commerce_storefront_hosts",
            [*rows, {"hostname": host, "org_id": org, "is_primary": True, "created_at": "2026-01-01T00:00:00+00:00"}],
        )


def build_harness(*, rate_limit: Any = None) -> Harness:
    db = make_db()
    storage = FakeStorageBackend()
    gateway = FakeCheckoutGateway(webhook_secret="hook-token")
    mailer = FakeEmailSender()
    checker = FakeLicenseChecker(allow_all=True)
    inbox = FakeEventInbox()
    cnpj = FakeCnpjRegistryLookup()
    fulfillment = make_fulfillment_registry()
    limited: list[str] = []

    def rl(limit: str):
        def deco(fn):
            limited.append(limit)
            return fn

        return deco

    staff = commerce_staff_router(
        CFG,
        auth_dependency=_auth,
        resolve_context=_resolve,
        get_db=lambda: db,
        get_storage=lambda: storage,
        get_cnpj_lookup=lambda: cnpj,
        is_platform_admin=lambda auth: auth["admin"],
    )
    shop = storefront_router(
        CFG,
        get_db=lambda: db,
        get_storage=lambda: storage,
        get_gateway=lambda: gateway,
        get_email=lambda: mailer,
        get_license_checker=lambda: checker,
        get_link_secret=lambda: SECRET,
        rate_limit=rate_limit if rate_limit is not None else rl,
    )
    hook = commerce_webhook_router(
        CFG,
        get_db=lambda: db,
        get_gateway=lambda: gateway,
        get_event_inbox=lambda: inbox,
        get_fulfillment=lambda: fulfillment,
        rate_limit=rl,
    )
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(staff)
    app.include_router(shop)
    app.include_router(hook)
    return Harness(db, storage, gateway, mailer, checker, inbox, cnpj, fulfillment, app, TestClient(app), limited)


@pytest.fixture
def h(commerce_schema_cache) -> Harness:
    return build_harness()


# ── domain seeding through the services themselves ──────────────────────────


def seed_profile(db: Any, org: str = ORG_A, **over: Any) -> dict:
    from noctusai_lib.domain.commerce import profile

    data = {
        "legal_name": "Loja Teste LTDA",
        "trade_name": "Loja Teste",
        "cnpj": VALID_CNPJ,
        "tax_regime": "simples",
        "tax_treatment": {},
        "locale": "pt-BR",
        "currency": "BRL",
        "brand_tokens": {"primary": "#112233"},
        "address": {"city": "São Paulo"},
        "contact_email": "contato@loja.test",
        "contact_phone": "11999999999",
        **over,
    }
    return profile.put_profile(db, org, USER_ID, data, expected_version=0, is_platform_admin=True)


def seed_product(
    db: Any,
    org: str = ORG_A,
    *,
    title: str = "Ebook",
    product_type: str = "digital",
    price_cents: int = 4700,
    publish: bool = True,
    **over: Any,
) -> tuple[dict, dict]:
    from noctusai_lib.domain.commerce import catalog

    product = catalog.create_product(db, org, {"title": title, "product_type": product_type, **over})
    offer = catalog.create_offer(db, org, product["id"], {"name": "Padrão", "price_cents": price_cents})
    if publish:
        product = catalog.set_product_status(db, org, product["id"], "published")
    return product, offer


def checkout_body(offer_id: str, **over: Any) -> dict:
    body = {
        "items": [{"offer_id": offer_id, "qty": 1}],
        "coupon": None,
        "buyer": {"name": "Ana Souza", "email": "Ana@Example.com", "doc": VALID_CPF, "phone": "11988887777"},
        "address": {"city": "Santos"},
        "payment_method": "pix",
        "consents": {
            "terms_version": CFG.terms_version,
            "privacy_version": CFG.privacy_version,
            "marketing": False,
            "immediate_delivery_waiver": True,
        },
    }
    body.update(over)
    return body
