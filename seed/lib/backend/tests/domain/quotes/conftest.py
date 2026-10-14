"""Shared harness for the quotes organ suite.

The mock PostgREST client validates EVERY column the code touches against the schema EMITTED BY `quotes_migration`
(plus the real `parties_migration` / `items_migration` output the quotes reference), through the mock's own
`set_cache_for_tests` seam -- a column the services write that the generator forgot fails HERE, not in prod.
DB-side rules (unique indexes, CHECKs, triggers, the atomic number RPC) are proven on a REAL Postgres in
`test_quotes_on_real_postgres.py`; here Python's job is covered: org scoping, auth, validation, state machine,
the public surface. Nothing is monkeypatched: db / sender / handler / adapters are the factories' own DI seams.

`QuotesDb` is a test DOUBLE of the client (a subclass), not a patch of our code: its only extension is `rpc()` for
the number sequence (the mock's own `rpc()` is canned data), counting per org exactly like the SQL function.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.items import ItemsConfig, items_migration
from noctusai_lib.domain.parties import PartiesConfig, parties_migration
from noctusai_lib.domain.quotes import (
    FakeQuoteAcceptHandler,
    QuotesConfig,
    QuotesContext,
    make_quotes_public_router,
    make_quotes_router,
    quotes_migration,
)
from noctusai_lib.domain.quotes._common import Scope
from noctusai_lib.integrations.docx_render import FakeDocxRenderAdapter
from noctusai_lib.integrations.email.fake_adapter import FakeEmailSender
from noctusai_lib.integrations.signature import FakeSignatureAdapter
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
SCHEMA = "quox"
SECRET = "test-link-secret-0123456789"
VALID_CPF = "52998224725"

CFG = QuotesConfig(schema=SCHEMA)


class QuotesDb(MockSupabaseClient):
    """The mock client + a per-org number sequence on `rpc(<prefix>next_number)` (mirrors the SQL function)."""

    def __init__(self, *a: Any, **k: Any) -> None:
        super().__init__(*a, **k)
        self._numbers: dict[str, int] = {}

    def rpc(self, name, params=None):
        if name == CFG.rpc("next_number"):
            org = str((params or {}).get("p_org"))
            self._numbers[org] = self._numbers.get(org, 0) + 1
            self.rpc_calls.append((name, dict(params or {})))
            return type("R", (), {"execute": lambda _self: type("Resp", (), {"data": self._numbers[org]})()})()
        return super().rpc(name, params)


@pytest.fixture
def quotes_schema_cache():
    base = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
    sql = "\n".join(
        [
            parties_migration(PartiesConfig(schema=SCHEMA), SCHEMA),
            items_migration(ItemsConfig(schema=SCHEMA)),
            quotes_migration(CFG, SCHEMA),
        ]
    )
    _schema_cache.set_cache_for_tests({**base, **parse_sql(sql, source_label="quotes_migration")})
    yield
    _schema_cache.set_cache_for_tests(base)


def make_db() -> QuotesDb:
    return QuotesDb(validate_schema=True, schema=SCHEMA)


@pytest.fixture
def db(quotes_schema_cache) -> QuotesDb:
    return make_db()


@pytest.fixture
def s(db) -> Scope:
    return Scope(db, CFG, ORG_A)


@pytest.fixture
def s_b(db) -> Scope:
    """Org B on the SAME database -- for isolation tests."""
    return Scope(db, CFG, ORG_B)


def seed_party(db, org: str = ORG_A, **over: Any) -> dict:
    row = {
        "id": over.pop("id", None) or _uuid(), "org_id": org, "kind": "PF", "legal_name": "Ana Souza", "email": "ana@cliente.com",
        "phones": [], "address": {}, "is_active": True, **over,
    }
    db.table("pty_parties").insert(row).execute()
    return row


def seed_item(db, org: str = ORG_A, **over: Any) -> dict:
    row = {
        "id": over.pop("id", None) or _uuid(), "org_id": org, "sku": over.pop("sku", None) or f"SKU{_uuid()[:6]}", "name": "Cadeira",
        "item_type": "goods", "unit": "UN", "price_cents": 15000, "is_active": True, **over,
    }
    db.table("itm_items").insert(row).execute()
    return row


def _uuid() -> str:
    from uuid import uuid4

    return str(uuid4())


def line(**over: Any) -> dict:
    return {"description": "Serviço de instalação", "kind": "service", "qty": "2", "unit_price_cents": 10000, **over}


def docx_template_bytes(body: str = "Orçamento {{ number }} - {{ party_name }} - {{ total }}") -> bytes:
    """A real (tiny) Word template -- what a tenant would upload."""
    import io

    from docx import Document

    doc = Document()
    doc.add_paragraph(body)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def tomorrow() -> date:
    return date.today() + timedelta(days=3)


# ─── HTTP harness ────────────────────────────────────────────────────────────


def _auth(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    role = authorization.split(" ", 1)[1]
    return {"org_id": ORG_B if role.startswith("org-b") else ORG_A, "user_id": USER_ID, "admin": role in ("admin", "org-b-admin")}


def _admin(auth: dict = Depends(_auth)) -> dict:
    if not auth["admin"]:
        raise HTTPException(status_code=403, detail="Admin only")
    return auth


def _resolve(auth: dict, db: Any) -> QuotesContext:
    return QuotesContext(db=db, org_id=auth["org_id"], user_id=auth["user_id"], is_admin=auth["admin"])


@dataclass
class Harness:
    db: QuotesDb
    app: FastAPI
    client: TestClient
    handler: FakeQuoteAcceptHandler
    email: FakeEmailSender
    signature: FakeSignatureAdapter
    limited: list

    def staff(self, role: str = "user") -> dict:
        return {"Authorization": f"Bearer {role}"}

    @property
    def admin(self) -> dict:
        return self.staff("admin")


def build_harness(*, docx: bool = True, signature: bool = True, secret: Optional[str] = SECRET, with_limiter: bool = True) -> Harness:
    db = make_db()
    handler, email, sig = FakeQuoteAcceptHandler(), FakeEmailSender(), FakeSignatureAdapter()
    limited: list = []

    def rate_limit(limit: str):
        def deco(fn):
            limited.append((fn.__name__, limit))
            return fn
        return deco

    docx_adapter = FakeDocxRenderAdapter()
    staff = make_quotes_router(
        CFG, _auth, _admin, resolve_context=_resolve, get_db=lambda: db, get_handler=lambda: handler,
        get_email=lambda: email, get_link_secret=(lambda: secret) if secret else None,
        accept_url=lambda token: f"https://app.test/orcamento/{token}", issuer=lambda org: {"name": "Acme Ltda"},
        get_signature=(lambda: sig) if signature else None,
        docx_template=(lambda ctx: docx_template_bytes()) if docx else None, get_docx_adapter=lambda: docx_adapter,
    )
    public = make_quotes_public_router(
        CFG, get_db=lambda: db, get_link_secret=lambda: secret or "", get_handler=lambda: handler,
        issuer=lambda org: {"name": "Acme Ltda"}, rate_limit=rate_limit if with_limiter else None,
    )
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(staff)
    app.include_router(public)
    return Harness(db, app, TestClient(app), handler, email, sig, limited)


@pytest.fixture
def h(quotes_schema_cache) -> Harness:
    return build_harness()
