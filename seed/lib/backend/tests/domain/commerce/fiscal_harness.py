"""Support for the fiscal/invoice suites (slice B2): schema cache, A1 generator, seeded org, runtime.

Imported (not a conftest) so it never collides with the organ conftest. Nothing is monkeypatched:
db, storage, mailer, jobs, inbox and the invoice provider are the factories' own DI seams.
"""
from __future__ import annotations

import asyncio
import datetime
from dataclasses import dataclass
from typing import Any, Optional

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from noctusai_lib.domain.commerce import CommerceConfig, commerce_migration
from noctusai_lib.domain.commerce.fiscal_sql import commerce_fiscal_migration
from noctusai_lib.domain.commerce.invoices import InvoiceRuntime
from noctusai_lib.domain.jobs import FakeJobRepository
from noctusai_lib.domain.payments import FakeEventInbox
from noctusai_lib.integrations.email import FakeEmailSender
from noctusai_lib.integrations.invoices import FakeInvoiceProvider
from noctusai_lib.integrations.invoices.certificate import OID_ICP_BRASIL_CNPJ
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.testing import _schema_cache
from noctusai_lib.testing.migration_parser import parse_sql
from noctusai_lib.testing.mocks import MockSupabaseClient

from .conftest import ORG_A, ORG_B, SCHEMA, USER_ID, VALID_CNPJ, VALID_CPF, seed_product, seed_profile

CFG = CommerceConfig(schema=SCHEMA)
PFX_PASSWORD = "s3nha-do-pfx-XYZ"


def run(coro):
    return asyncio.run(coro)


def _der_utf8(text: str) -> bytes:
    raw = text.encode()
    return bytes([0x0C, len(raw)]) + raw


def build_pfx(*, cnpj: Optional[str] = VALID_CNPJ, password: str = PFX_PASSWORD, days: int = 365) -> tuple[bytes, datetime.datetime]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "LOJA TESTE LTDA")])
    now = datetime.datetime.now(datetime.timezone.utc)
    not_after = (now + datetime.timedelta(days=days)).replace(microsecond=0)
    builder = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(not_after)
    )
    if cnpj:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.OtherName(OID_ICP_BRASIL_CNPJ, _der_utf8(cnpj))]), critical=False)
    cert = builder.sign(key, hashes.SHA256())
    pfx = pkcs12.serialize_key_and_certificates(b"t", key, cert, None, serialization.BestAvailableEncryption(password.encode()))
    return pfx, not_after


@pytest.fixture(scope="session")
def pfx_ok() -> tuple[bytes, datetime.datetime]:
    return build_pfx()


@pytest.fixture
def fiscal_schema_cache():
    base = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
    merged = {t: set(c) for t, c in base.items()}
    for sql, label in ((commerce_migration(CFG, SCHEMA), "commerce_migration"), (commerce_fiscal_migration(CFG, SCHEMA), "commerce_fiscal_migration")):
        for table, cols in parse_sql(sql, source_label=label).items():
            merged.setdefault(table, set()).update(cols)  # ALTER ... ADD COLUMN yields only the new columns
    _schema_cache.set_cache_for_tests(merged)
    yield
    _schema_cache.set_cache_for_tests(base)


@dataclass
class FH:
    db: MockSupabaseClient
    provider: FakeInvoiceProvider
    storage: FakeStorageBackend
    mailer: FakeEmailSender
    jobs: FakeJobRepository
    inbox: FakeEventInbox

    def runtime(self) -> InvoiceRuntime:
        return InvoiceRuntime(CFG, lambda org: self.provider, self.storage, self.mailer)


@pytest.fixture
def fh(fiscal_schema_cache) -> FH:
    return FH(
        MockSupabaseClient(validate_schema=True, schema=SCHEMA),
        FakeInvoiceProvider(), FakeStorageBackend(), FakeEmailSender(), FakeJobRepository(), FakeEventInbox(),
    )


def seed_paid_order(fh: FH, org: str = ORG_A, *, product_type: str = "service", status: str = "paid", discount: int = 0, doc: Optional[str] = VALID_CPF) -> dict:
    """A paid order with one line of `product_type`, written straight to the tables."""
    product, offer = seed_product(fh.db, org, product_type=product_type, price_cents=10000)
    cust = {"id": f"c0000000-0000-4000-8000-{abs(hash((org, product_type, status))) % 10**12:012d}", "org_id": org,
            "email": "ana@example.com", "name": "Ana Souza", "doc": doc, "phone": None, "address": {"city": "Santos"}}
    fh.db.set_table_data("commerce_customers", [*(fh.db.table("commerce_customers").select("*").execute().data or []), cust])
    order_id = f"d0000000-0000-4000-8000-{len(fh.db.table('commerce_orders').select('*').execute().data or []) + 1:012d}"
    order = {"id": order_id, "org_id": org, "token": f"tok-{order_id}", "customer_id": cust["id"], "status": status,
             "subtotal_cents": 10000, "discount_cents": discount, "total_cents": 10000 - discount, "currency": "BRL",
             "payment_method": "pix", "gateway": "asaas", "paid_at": "2026-10-10T12:00:00+00:00",
             "buyer_doc": doc, "buyer_name": "Ana Souza", "platform_fee_cents": 0,
             "created_at": "2026-10-10T11:00:00+00:00", "updated_at": "2026-10-10T12:00:00+00:00"}
    fh.db.set_table_data("commerce_orders", [*(fh.db.table("commerce_orders").select("*").execute().data or []), order])
    item = {"id": f"e0000000-0000-4000-8000-{order_id[-12:]}", "org_id": org, "order_id": order_id, "product_id": product["id"],
            "offer_id": offer["id"], "title_snapshot": "Consultoria", "product_type": product_type,
            "fulfillment_type": "none", "unit_price_cents": 10000, "qty": 1, "total_cents": 10000}
    fh.db.set_table_data("commerce_order_items", [*(fh.db.table("commerce_order_items").select("*").execute().data or []), item])
    return order


def seed_fiscal_org(fh: FH, org: str = ORG_A, *, regime: str = "simples", treatment: Optional[dict] = None, auto: bool = True, company: bool = True, cert: bool = True, **over: Any) -> dict:
    """Profile + (optionally) a registered company + a valid certificate, via the real services."""
    from noctusai_lib.domain.commerce import fiscal as fiscal_svc

    seed_profile(fh.db, org, tax_regime=regime, tax_treatment=treatment or {"service": "service_nfse", "physical": "goods_nfe", "digital": "rights_receipt"}, **over)
    if company:
        fiscal_svc.update_fiscal(fh.db, org, USER_ID, {"municipio_ibge": "3548500"}, expected_version=1, provider=fh.provider)
    if cert:
        pfx, _ = build_pfx()
        fiscal_svc.upload_certificate(fh.db, org, pfx=pfx, password=PFX_PASSWORD, provider=fh.provider)
    if auto:
        v = fiscal_svc.get_fiscal(fh.db, org)["version"]
        fiscal_svc.update_fiscal(fh.db, org, USER_ID, {"auto_issue_invoices": True}, expected_version=v, provider=fh.provider)
    return fiscal_svc.get_fiscal(fh.db, org)
