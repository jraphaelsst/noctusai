"""Shared harness for the commerce organ suite.

The mock PostgREST client validates EVERY column the code touches against the
schema EMITTED BY `commerce_migration` (injected through the mock's own
`set_cache_for_tests` seam), so a column the services write that the generator
forgot fails here, not in prod. Nothing is monkeypatched: db, storage, gateway,
mailer, licence checker and inbox are the factories' own DI seams.

Rate limiting is a REAL slowapi `Limiter` on every rate-limited router (storefront +
webhook), always -- a standing guard, not one regression test: a real
`limiter.limit` wraps the handler from another module, and a router whose string
annotations do not survive that wrapping 500s in prod while a pass-through
decorator stays green (slice B's bug). `Harness.limited` still records each limit
string the routers asked for. Each harness gets its own in-memory Limiter, so no
test inherits another's counters.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from noctusai_lib.domain.commerce import (
    CommerceConfig,
    commerce_money_migration,
    CommerceContext,
    FakeCheckoutGateway,
    commerce_migration,
    commerce_staff_router,
    commerce_webhook_router,
    make_fulfillment_registry,
    storefront_router,
)
from noctusai_lib.domain.commerce.fulfillment import FulfillmentRegistry
from noctusai_lib.domain.commerce.erp_sql import commerce_erp_migration
from noctusai_lib.domain.finance.booking import FakeFinanceBooking
from noctusai_lib.domain.items import ItemsConfig, items_migration
from noctusai_lib.domain.parties import PartiesConfig, parties_migration
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
from noctusai_lib.testing.migration_parser import parse_check_sql, parse_default_sql, parse_sql
from noctusai_lib.testing.mocks import MockSupabaseClient

from ..money_rpc import RpcMockClient

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
    """Extend the mock's migration-derived maps (columns, CHECKs, DEFAULTs) with the organ's template output:
    the base migration PLUS the P4 money delta (restored, not reset, afterwards: a reset would re-parse every
    product's migrations). Hosts apply the delta in a new migration (wave 3); until then the mock must still
    judge writes against the schema the generators emit."""
    base = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
    base_checks, base_defaults = _schema_cache._CHECK_CACHE, _schema_cache._DEFAULTS_CACHE
    # + the ERP link delta (item_id / channel / source_ref) and the parties / items tables it and the quote handlers touch.
    sql = "\n".join(
        [
            commerce_migration(CFG, SCHEMA),
            commerce_money_migration(CFG, SCHEMA),
            commerce_erp_migration(CFG, SCHEMA),
            parties_migration(PartiesConfig(schema=SCHEMA), SCHEMA),
            items_migration(ItemsConfig(schema=SCHEMA)),
        ]
    )
    generated = parse_sql(sql, source_label="commerce_migration+money")
    merged: dict[str, set[str]] = {t: set(c) for t, c in base.items()}
    for table, cols in generated.items():
        merged.setdefault(table, set()).update(cols)
    _schema_cache.set_cache_for_tests(merged)
    checks = parse_check_sql(sql)
    defaults = parse_default_sql(sql)
    _schema_cache.get_check_map()
    existing_checks = {
        t: {c.name: c.body for c in compiled} for t, compiled in (_schema_cache._CHECK_CACHE or {}).items()
    }
    for table, named in checks.items():
        existing_checks.setdefault(table, {}).update(named)
    _schema_cache.set_checks_for_tests(
        existing_checks, {t: set(c) for t, c in (_schema_cache._DEFAULTS_CACHE or {}).items()} | {t: set(c) for t, c in defaults.items()}
    )
    yield
    _schema_cache.set_cache_for_tests(base)
    _schema_cache._CHECK_CACHE, _schema_cache._DEFAULTS_CACHE = base_checks, base_defaults


def make_db() -> MockSupabaseClient:
    return RpcMockClient(validate_schema=True, schema=SCHEMA)


@pytest.fixture
def db(commerce_schema_cache) -> MockSupabaseClient:
    return make_db()


def _auth(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    role = authorization.split(" ", 1)[1]
    return {"org_id": ORG_B if role == "org-b" else ORG_A, "user_id": USER_ID, "admin": role == "admin"}


def _org_admin(authorization: Optional[str] = Header(None)) -> dict:
    """The harness's org-admin gate: 401 unauthenticated, 403 plain staff (the real one is `require_org_admin`)."""
    auth = _auth(authorization)
    role = (authorization or "").split(" ", 1)[1]
    if role not in ("orgadmin", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return auth


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
    limiter: Limiter
    limited: list[str] = field(default_factory=list)
    finance: Any = None

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


def build_harness() -> Harness:
    db = make_db()
    storage = FakeStorageBackend()
    gateway = FakeCheckoutGateway(webhook_secret="hook-token")
    mailer = FakeEmailSender()
    checker = FakeLicenseChecker(allow_all=True)
    inbox = FakeEventInbox()
    cnpj = FakeCnpjRegistryLookup()
    fulfillment = make_fulfillment_registry()
    finance = FakeFinanceBooking()
    limited: list[str] = []
    limiter = Limiter(key_func=get_remote_address)

    def rl(limit: str):
        real = limiter.limit(limit)

        def deco(fn):
            limited.append(limit)
            return real(fn)

        return deco

    staff = commerce_staff_router(
        CFG,
        auth_dependency=_auth,
        resolve_context=_resolve,
        get_db=lambda: db,
        get_storage=lambda: storage,
        get_cnpj_lookup=lambda: cnpj,
        is_platform_admin=lambda auth: auth["admin"],
        admin_dependency=_org_admin,
        get_gateway=lambda: gateway,
        get_finance=lambda: finance,
        get_fulfillment=lambda: fulfillment,
        get_email=lambda: mailer,
    )
    shop = storefront_router(
        CFG,
        get_db=lambda: db,
        get_storage=lambda: storage,
        get_gateway=lambda: gateway,
        get_email=lambda: mailer,
        get_license_checker=lambda: checker,
        get_link_secret=lambda: SECRET,
        rate_limit=rl,
    )
    hook = commerce_webhook_router(
        CFG,
        get_db=lambda: db,
        get_gateway=lambda: gateway,
        get_event_inbox=lambda: inbox,
        get_fulfillment=lambda: fulfillment,
        get_finance=lambda: finance,
        get_email=lambda: mailer,
        rate_limit=rl,
    )
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(staff)
    app.include_router(shop)
    app.include_router(hook)
    return Harness(db, storage, gateway, mailer, checker, inbox, cnpj, fulfillment, app, TestClient(app), limiter, limited, finance)


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


# ── P4 money helpers ────────────────────────────────────────────────────────


def place_order(db: Any, gateway: Any, *, org: str = ORG_A, **body: Any) -> dict:
    """Seed a store + product, run a real checkout, mirror the charge into the fake gateway; returns the order row."""
    from noctusai_lib.domain.commerce.checkout import create_checkout

    seed_profile(db, org)
    _, offer = seed_product(db, org, price_cents=body.pop("price_cents", 10000))
    create_checkout(db, org, CFG, gateway, checkout_body(offer["id"], **body), order_url_for=lambda t: f"https://x.test/pedido/{t}")
    gateway.sync_charges()
    rows = db.table("commerce_orders").select("*").eq("org_id", org).execute().data
    return rows[-1]


def pay(gateway: Any, order: dict, *, confirmed_only: bool = False, fee_cents: int = 0) -> Any:
    """Make the fake gateway read the order's CURRENT charge as paid (optionally with a gateway fee)."""
    from dataclasses import replace

    from noctusai_lib.integrations.payments.types import Money

    charge = gateway.charges.mark_paid(order["gateway_charge_id"], confirmed_only=confirmed_only)
    if fee_cents:
        charge = gateway.charges.charges[charge.id_at_gateway] = replace(
            charge, fee=Money(fee_cents), net=Money(charge.amount.amount_cents - fee_cents)
        )
    return charge


def money_deps(gateway: Any, **over: Any) -> Any:
    from noctusai_lib.domain.commerce import MoneyDeps

    return MoneyDeps(cfg=CFG, gateway=gateway, **over)
