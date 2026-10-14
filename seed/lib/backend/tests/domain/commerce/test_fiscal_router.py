"""Fiscal + invoice-webhook routers over TestClient: authz matrix, envelopes, certificate upload, webhook 5-pin."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from noctusai_lib.domain.commerce import CommerceContext
from noctusai_lib.domain.commerce import invoices as inv
from noctusai_lib.domain.commerce.fiscal_router import (
    CERTIFICATE_UPLOAD_MAX_BYTES,
    commerce_fiscal_router,
    commerce_invoice_webhook_router,
)
from noctusai_lib.domain.jobs import Worker
from noctusai_lib.domain.commerce.fiscal_types import CUTOVER_PHRASE, ROLLBACK_PHRASE
from noctusai_lib.integrations.invoices import WEBHOOK_TOKEN_HEADER, InvoiceKind
from noctusai_lib.primitives.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

from .conftest import ORG_A, ORG_B, USER_ID, VALID_CNPJ
from .fiscal_harness import CFG, FH, PFX_PASSWORD, build_pfx, fh, fiscal_schema_cache, run, seed_fiscal_org, seed_paid_order  # noqa: F401

UUID0 = "11111111-1111-1111-1111-111111111111"
HOOK_TOKEN = "hook-secret-ORG-A"


def _auth(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    role = authorization.split(" ", 1)[1]
    return {"org_id": ORG_B if role.startswith("org-b") else ORG_A, "user_id": USER_ID,
            "admin": role in ("admin", "org-b-admin"), "platform": role == "platform"}


def _platform(auth: dict = Depends(_auth)) -> dict:
    if not auth["platform"]:
        raise HTTPException(status_code=403, detail={"detail": "Restrito a administradores da plataforma", "code": "platform_admin_required"})
    return auth


def _admin(auth: dict = Depends(_auth)) -> dict:
    if not auth["admin"]:
        raise HTTPException(status_code=403, detail={"detail": "Restrito a administradores da organizacao", "code": "org_admin_required"})
    return auth


@dataclass
class App:
    client: TestClient
    fh: FH
    limited: list[str]
    provider_builds: list[str]


def build_app(fh: FH, *, platform: bool = False) -> App:
    limiter = Limiter(key_func=get_remote_address)
    limited: list[str] = []
    builds: list[str] = []

    def rl(limit: str):
        real = limiter.limit(limit)

        def deco(fn):
            limited.append(limit)
            return real(fn)

        return deco

    def make_provider(org: str):
        builds.append(org)
        return fh.provider

    staff = commerce_fiscal_router(
        CFG, auth_dependency=_auth, admin_dependency=_admin,
        resolve_context=lambda auth, db: CommerceContext(db=db, org_id=auth["org_id"], user_id=auth["user_id"]),
        get_db=lambda: fh.db, get_storage=lambda: fh.storage, get_jobs=lambda: fh.jobs, make_provider=make_provider,
        platform_admin_dependency=_platform if platform else None,
    )
    hook = commerce_invoice_webhook_router(
        CFG, get_db=lambda: fh.db, get_storage=lambda: fh.storage, get_event_inbox=lambda: fh.inbox,
        make_provider=make_provider,
        get_webhook_token=lambda org: HOOK_TOKEN if org == ORG_A else None,  # ORG_B: unset => fail-closed
        get_jobs=lambda: fh.jobs, get_mailer=lambda: fh.mailer, rate_limit=rl,
    )
    api = FastAPI()
    api.state.limiter = limiter
    api.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    api.add_exception_handler(AppException, app_exception_handler)
    api.add_exception_handler(HTTPException, http_exception_handler)
    api.add_exception_handler(ValidationError, validation_exception_handler)
    api.include_router(staff)
    api.include_router(hook)
    return App(TestClient(api), fh, limited, builds)


@pytest.fixture
def app(fh) -> App:
    return build_app(fh)


@pytest.fixture
def papp(fh) -> App:
    return build_app(fh, platform=True)


STAFF, ADMIN, OTHER = {"Authorization": "Bearer user"}, {"Authorization": "Bearer admin"}, {"Authorization": "Bearer org-b"}

ROUTES = [
    ("GET", "/api/commerce/fiscal", False), ("PUT", "/api/commerce/fiscal", True),
    ("POST", "/api/commerce/fiscal/certificate", True), ("POST", "/api/commerce/fiscal/nfse-cutover", True),
    ("POST", "/api/commerce/fiscal/nfse-cutover/rollback", True),
    ("GET", f"/api/commerce/orders/{UUID0}/invoices", False), ("POST", f"/api/commerce/orders/{UUID0}/invoices", True),
    ("POST", f"/api/commerce/invoices/{UUID0}/cancel", True), ("GET", f"/api/commerce/invoices/{UUID0}/documents/pdf", False),
]


@pytest.mark.parametrize("method,path,_admin_only", ROUTES)
def test_unauthenticated_is_strictly_401(app, method, path, _admin_only):
    assert app.client.request(method, path).status_code == 401  # strict ==, never `in (401, 4xx)`


@pytest.mark.parametrize("method,path,admin_only", [r for r in ROUTES if r[2]])
def test_staff_write_is_strictly_403(app, method, path, admin_only):
    assert app.client.request(method, path, headers=STAFF).status_code == 403


def test_route_inventory_is_exactly_the_contract(app):
    mounted = {(m, r.path) for r in app.client.app.routes if r.path.startswith("/api/commerce") for m in r.methods - {"HEAD", "OPTIONS"}}
    norm = lambda p: re.sub(r"[0-9a-f]{8}-[0-9a-f-]{27}|\{[^}]+\}|/documents/pdf$", lambda m: "/documents/X" if m.group(0).endswith("pdf") else "X", p)  # noqa: E731
    assert {(m, norm(p)) for m, p in mounted} == {(m, norm(p)) for m, p, _ in ROUTES}


class TestFiscalRoutes:
    def test_get_before_profile_is_null_staff_can_read(self, app):
        assert app.client.get("/api/commerce/fiscal", headers=STAFF).json() == {"data": None}

    def test_put_regime_rule_and_version_envelopes(self, app):
        seed_fiscal_org(app.fh, auto=False, cert=False, company=False, regime="simples")
        r = app.client.put("/api/commerce/fiscal", json={"expected_version": 1, "nfse_mode": "municipal"}, headers=ADMIN)
        assert r.status_code == 422 and r.json()["error"]["code"] == "nfse_nacional_obrigatorio"
        r = app.client.put("/api/commerce/fiscal", json={"expected_version": 1, "inscricao_municipal": "12", "municipio_ibge": "3548500"}, headers=ADMIN)
        assert r.status_code == 200 and r.json()["data"]["version"] == 2
        assert not any("token" in k for k in r.json()["data"])
        r = app.client.put("/api/commerce/fiscal", json={"expected_version": 1}, headers=ADMIN)
        assert r.status_code == 409 and r.json()["error"]["code"] == "versao_conflitante"

    def test_put_rejects_unknown_keys(self, app):
        assert app.client.put("/api/commerce/fiscal", json={"expected_version": 0, "company_token": "x"}, headers=ADMIN).status_code == 422

    def test_other_org_sees_nothing(self, app):
        seed_fiscal_org(app.fh, auto=False)
        assert app.client.get("/api/commerce/fiscal", headers=OTHER).json() == {"data": None}

    def test_cutover_and_rollback_endpoints(self, app):
        seed_fiscal_org(app.fh, regime="lucro_presumido", auto=False)
        bad = app.client.post("/api/commerce/fiscal/nfse-cutover", json={"confirm": "sim"}, headers=ADMIN)
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "confirmacao_invalida"
        ok = app.client.post("/api/commerce/fiscal/nfse-cutover", json={"confirm": CUTOVER_PHRASE}, headers=ADMIN)
        assert ok.status_code == 200 and ok.json()["data"]["nfse_mode"] == "nacional" and ok.json()["data"]["can_rollback"]
        back = app.client.post("/api/commerce/fiscal/nfse-cutover/rollback", json={"confirm": ROLLBACK_PHRASE}, headers=ADMIN)
        assert back.status_code == 200 and back.json()["data"]["nfse_mode"] == "municipal"
        again = app.client.post("/api/commerce/fiscal/nfse-cutover/rollback", json={"confirm": ROLLBACK_PHRASE}, headers=ADMIN)
        assert again.status_code == 409 and again.json()["error"]["code"] == "janela_rollback_encerrada"


class TestCertificateRoute:
    def _post(self, app, pfx: bytes, password: str = PFX_PASSWORD, headers=ADMIN):
        return app.client.post("/api/commerce/fiscal/certificate", files={"file": ("a1.pfx", pfx)}, data={"password": password}, headers=headers)

    def test_happy_path_returns_only_expiry_and_cnpj(self, app):
        seed_fiscal_org(app.fh, cert=False, auto=False)
        pfx, _ = build_pfx()
        r = self._post(app, pfx)
        assert r.status_code == 200 and set(r.json()["data"]) == {"certificate_valid_until", "certificate_cnpj"}
        assert r.json()["data"]["certificate_cnpj"] == VALID_CNPJ
        assert PFX_PASSWORD not in r.text

    def test_mismatch_invalid_and_oversize_are_422_generic(self, app, caplog):
        seed_fiscal_org(app.fh, cert=False, auto=False)
        caplog.set_level(logging.DEBUG)
        other, _ = build_pfx(cnpj="12345678000190")
        assert self._post(app, other).json()["error"]["code"] == "certificado_cnpj_divergente"
        for body, pw in ((b"junk", PFX_PASSWORD), (b"\x00" * (64 * 1024 + 1), PFX_PASSWORD), (build_pfx()[0], "x" * 129), (build_pfx()[0], "wrong")):
            r = self._post(app, body, pw)
            assert r.status_code == 422 and r.json()["error"]["code"] == "certificado_invalido"
        assert PFX_PASSWORD not in caplog.text and "wrong" not in caplog.text.replace("wrong-", "")

    def test_staff_cannot_upload(self, app):
        assert self._post(app, b"x", headers=STAFF).status_code == 403

    def test_documented_body_ceiling_covers_the_64kb_cap(self):
        assert CERTIFICATE_UPLOAD_MAX_BYTES > 64 * 1024


class TestInvoiceRoutes:
    def test_list_issue_cancel_and_documents(self, app):
        seed_fiscal_org(app.fh, auto=False)
        order = seed_paid_order(app.fh)
        base = f"/api/commerce/orders/{order['id']}/invoices"
        assert app.client.get(base, headers=STAFF).json() == {"data": []}
        r = app.client.post(base, json={"kind": "nfse"}, headers=ADMIN)
        assert r.status_code == 201 and r.json()["data"]["status"] == "processing"
        iid = r.json()["data"]["id"]
        assert app.client.post(base, json={"kind": "nfse"}, headers=ADMIN).json()["error"]["code"] == "nota_ja_emitida"
        assert app.client.post(base, json={"kind": "xx"}, headers=ADMIN).status_code == 422
        for _ in range(3):
            run(Worker(app.fh.jobs, worker_id="w", handlers=_handlers(app.fh), retry_policy=inv.INVOICE_RETRY_POLICY).run_once())
        listed = app.client.get(base, headers=STAFF).json()["data"]
        assert [i["status"] for i in listed] == ["authorized"]
        doc = app.client.get(f"/api/commerce/invoices/{iid}/documents/pdf", headers=STAFF)
        assert doc.status_code == 200 and doc.json()["data"]["url"] and 0 < doc.json()["data"]["expires_in"] <= 600
        assert app.client.get(f"/api/commerce/invoices/{iid}/documents/exe", headers=STAFF).status_code == 422
        short = app.client.post(f"/api/commerce/invoices/{iid}/cancel", json={"reason": "curto"}, headers=ADMIN)
        assert short.status_code == 422 and short.json()["error"]["code"] == "justificativa_curta"
        ok = app.client.post(f"/api/commerce/invoices/{iid}/cancel", json={"reason": "Pedido estornado integralmente"}, headers=ADMIN)
        assert ok.status_code == 200 and ok.json()["data"]["cancel_requested_at"]

    def test_foreign_order_and_invoice_are_404(self, app):
        seed_fiscal_org(app.fh, auto=False)
        order = seed_paid_order(app.fh)
        assert app.client.get(f"/api/commerce/orders/{order['id']}/invoices", headers=OTHER).status_code == 404
        (row,) = inv.register_invoices(app.fh.db, ORG_A, order)
        assert app.client.get(f"/api/commerce/invoices/{row['id']}/documents/pdf", headers=OTHER).status_code == 404
        assert app.client.post(f"/api/commerce/invoices/{row['id']}/cancel", json={"reason": "x" * 20}, headers={"Authorization": "Bearer org-b-admin"}).status_code == 404


class TestInvoiceWebhook:
    def _setup(self, app, **kw):
        seed_fiscal_org(app.fh, **kw)
        order = seed_paid_order(app.fh)
        (row,) = inv.register_invoices(app.fh.db, ORG_A, order)
        return order, row

    def _post(self, app, org, body: Any, token: Optional[str] = HOOK_TOKEN, provider="fake", raw: Optional[bytes] = None):
        headers = {WEBHOOK_TOKEN_HEADER: token} if token is not None else {}
        data = raw if raw is not None else json.dumps(body).encode()
        return app.client.post(f"/api/webhooks/invoices/{provider}/{org}", content=data, headers=headers)

    def test_auth_matrix(self, app):
        _, row = self._setup(app)
        body = {"ref": row["ref"], "status": "authorized"}
        assert self._post(app, ORG_A, body, token=None).status_code == 401
        assert self._post(app, ORG_A, body, token="wrong").status_code == 401
        assert self._post(app, ORG_A, body, token=HOOK_TOKEN[:-1]).status_code == 401
        assert self._post(app, ORG_B, body, token=HOOK_TOKEN).status_code == 401  # org B has no token: fail-closed
        assert self._post(app, ORG_B, body, token="").status_code == 401
        assert inv.get_invoice(app.fh.db, ORG_A, row["id"])["status"] == "processing"  # nothing moved on any refusal

    def test_token_in_query_string_is_not_accepted(self, app):
        _, row = self._setup(app)
        r = app.client.post(f"/api/webhooks/invoices/fake/{ORG_A}?token={HOOK_TOKEN}", json={"ref": row["ref"]})
        assert r.status_code == 401

    def test_unknown_provider_path_is_404_and_bad_body_is_400(self, app):
        self._setup(app)
        assert self._post(app, ORG_A, {"ref": "x"}, provider="otherpay").status_code == 401  # authed, but not this org's provider
        assert self._post(app, ORG_A, None, raw=b"not json").status_code == 400
        assert self._post(app, ORG_A, {"no_ref": 1}).status_code == 400
        assert self._post(app, ORG_A, {"ref": "../../etc"}).status_code == 400

    def test_body_is_never_trusted_only_get_is(self, app):
        _, row = self._setup(app)
        app.fh.provider._auto_authorize = False
        app.fh.provider.issue(_req(app, row))
        # the provider still says PROCESSING; the body lies "authorized" + urls
        lie = {"ref": row["ref"], "status": "authorized", "caminho_xml_nota_fiscal": "https://evil.test/x.xml", "numero": "666"}
        r = self._post(app, ORG_A, lie)
        assert r.status_code == 200 and r.json()["outcome"] == "processed"
        after = inv.get_invoice(app.fh.db, ORG_A, row["id"])
        assert after["status"] == "processing" and after.get("number") is None and after.get("xml_path") is None

    def test_provider_truth_authorizes_and_copies(self, app):
        _, row = self._setup(app)
        app.fh.provider.issue(_req(app, row))
        r = self._post(app, ORG_A, {"ref": row["ref"], "status": "authorized"})
        assert r.json() == {"received": True, "outcome": "processed"}
        after = inv.get_invoice(app.fh.db, ORG_A, row["id"])
        assert after["status"] == "authorized" and after["pdf_path"] and after["number"]

    def test_replay_is_deduplicated_by_ref_and_status(self, app):
        _, row = self._setup(app)
        app.fh.provider.issue(_req(app, row))
        body = {"ref": row["ref"], "status": "authorized"}
        assert self._post(app, ORG_A, body).json()["outcome"] == "processed"
        assert self._post(app, ORG_A, body).json()["outcome"] == "duplicate"
        assert self._post(app, ORG_A, {"ref": row["ref"], "status": "cancelled"}).json()["outcome"] == "processed"  # new status = new key

    def test_cross_org_ref_is_refused_without_a_state_change(self, app):
        # a ref that belongs to ORG_B delivered (with ORG_A's valid token) to ORG_A's endpoint
        seed_fiscal_org(app.fh, ORG_B, auto=False)
        order_b = seed_paid_order(app.fh, ORG_B)
        (row_b,) = inv.register_invoices(app.fh.db, ORG_B, order_b)
        r = self._post(app, ORG_A, {"ref": row_b["ref"], "status": "authorized"})
        assert r.status_code == 200 and r.json()["outcome"] == "ignored"
        assert inv.get_invoice(app.fh.db, ORG_B, row_b["id"])["status"] == "processing"
        assert self._post(app, ORG_A, {"ref": "zzzzzzzz-unknown-nfse-1"}).json()["outcome"] == "ignored"

    def test_provider_read_failure_is_502_and_releases_the_inbox_claim(self, app):
        _, row = self._setup(app)  # the Fake has no such document => get() raises InvoiceNotFound
        body = {"ref": row["ref"], "status": "authorized"}
        assert self._post(app, ORG_A, body).status_code == 502
        app.fh.provider.issue(_req(app, row))
        assert self._post(app, ORG_A, body).json()["outcome"] == "processed"  # the retry was not swallowed as a duplicate

    def test_real_slowapi_limiter_wraps_the_webhook(self, app):
        assert app.limited == [CFG.webhook_rate_limit]
        self._setup(app)
        assert self._post(app, ORG_A, {"ref": "a"}, token="x").status_code == 401  # the wrapped route still resolves its types


def _handlers(fh: FH):
    return inv.make_invoice_job_handlers(
        CFG, get_db=lambda: fh.db, make_provider=lambda org: fh.provider, get_storage=lambda: fh.storage,
        get_jobs=lambda: fh.jobs, get_mailer=lambda: fh.mailer,
    )


def _req(app: App, row: dict):
    order = app.fh.db.table("commerce_orders").select("*").eq("id", row["order_id"]).execute().data[0]
    profile = inv.get_profile(app.fh.db, ORG_A)
    return inv.build_request(app.fh.db, ORG_A, order, row, profile, profile["invoice_company_ref"])


class TestWebhookPreAuthUniformity:
    """Item 1: nothing is built / read for an unauthenticated caller, and every refusal looks identical."""

    def test_every_pre_auth_failure_is_the_same_401_and_builds_no_provider(self, app):
        _, row = TestInvoiceWebhook()._setup(app)
        body = {"ref": row["ref"], "status": "authorized"}
        poster = TestInvoiceWebhook()._post
        unknown_org = "00000000-0000-4000-8000-000000000000"
        refusals = [
            poster(app, unknown_org, body),                       # unknown org
            poster(app, ORG_B, body),                             # org with the token unset (fail-closed)
            poster(app, ORG_A, body, token="wrong"),              # wrong token
            poster(app, ORG_A, body, token=None),                 # no token
            poster(app, ORG_A, body, token="wrong", provider="otherpay"),  # unknown provider, bad token
        ]
        assert {r.status_code for r in refusals} == {401}
        assert len({r.text for r in refusals}) == 1  # byte-identical bodies: no oracle
        assert app.provider_builds == []              # the provider was never even constructed

    def test_authenticated_unknown_provider_is_the_same_401(self, app):
        _, row = TestInvoiceWebhook()._setup(app)
        r = TestInvoiceWebhook()._post(app, ORG_A, {"ref": row["ref"]}, provider="otherpay")
        assert r.status_code == 401 and r.json()["error"]["code"] == "assinatura_invalida"


class TestPlatformAdminWrites:
    """Item 2: contract 0 -- a platform admin acting on another org, real actor recorded."""

    PLATFORM = {"Authorization": "Bearer platform"}

    def test_without_the_dependency_behaviour_is_unchanged(self, app):
        seed_fiscal_org(app.fh, auto=False, cert=False, company=False)
        assert app.client.put("/api/commerce/fiscal", json={"expected_version": 1}, headers=self.PLATFORM).status_code == 403

    def test_platform_admin_may_write_and_the_ledger_names_the_real_actor(self, papp):
        seed_fiscal_org(papp.fh, auto=False, cert=False, company=False)
        r = papp.client.put("/api/commerce/fiscal", json={"expected_version": 1, "inscricao_municipal": "77"}, headers=self.PLATFORM)
        assert r.status_code == 200 and r.json()["data"]["version"] == 2
        ledger = [v for v in papp.fh.db.table("commerce_store_profile_versions").select("*").eq("org_id", ORG_A).execute().data if v["version"] == 2][0]
        assert ledger["changed_by"] == USER_ID and ledger["snapshot"]["acted_by_platform_admin"] is True

    def test_org_admin_is_not_marked_as_platform(self, papp):
        seed_fiscal_org(papp.fh, auto=False, cert=False, company=False)
        papp.client.put("/api/commerce/fiscal", json={"expected_version": 1, "inscricao_municipal": "77"}, headers=ADMIN)
        ledger = [v for v in papp.fh.db.table("commerce_store_profile_versions").select("*").eq("org_id", ORG_A).execute().data if v["version"] == 2][0]
        assert "acted_by_platform_admin" not in ledger["snapshot"]

    def test_plain_staff_is_still_403_and_unauthenticated_still_401(self, papp):
        assert papp.client.put("/api/commerce/fiscal", json={"expected_version": 1}, headers=STAFF).status_code == 403
        assert papp.client.put("/api/commerce/fiscal", json={"expected_version": 1}).status_code == 401
        assert papp.client.post("/api/commerce/fiscal/nfse-cutover", json={"confirm": "x"}).status_code == 401

    def test_cutover_by_platform_admin_is_recorded_as_such(self, papp):
        seed_fiscal_org(papp.fh, regime="lucro_presumido", auto=False)
        r = papp.client.post("/api/commerce/fiscal/nfse-cutover", json={"confirm": CUTOVER_PHRASE}, headers=self.PLATFORM)
        assert r.status_code == 200 and r.json()["data"]["nfse_cutover"]["via"] == "platform_admin"
        assert r.json()["data"]["nfse_cutover"]["approved_by"] == USER_ID
