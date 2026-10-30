"""/api/brand (CONTRACT org-brand-identity §3–§4).

Everything runs through the real seams: the router, ``BrandService``, the seed
``FakeJobRepository`` + jobs ``Worker``, the seed fake storage, the seed LLM
client with the seed ``FakeProvider`` registered under a provider name, and the
product ``FakeBrandRepo`` (the org_brand_identities migration's invariants). The runtime is handed to
the router through ``dependency_overrides`` — nothing of ours is patched.
"""
from __future__ import annotations

import asyncio
import base64
import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from noctusai_lib.domain.jobs import make_job_repository
from noctusai_lib.integrations.llm import LLMConfig, configure_llm, register
from noctusai_lib.integrations.llm.client import _reset_for_testing
from noctusai_lib.integrations.llm.providers import FakeProvider
from noctusai_lib.integrations.storage import make_storage_backend
from noctusai_lib.testing import MockSupabaseClient

from app.routers import brand as router_module
from app.services.brand import tokens as T
from app.services.brand.repository import FakeBrandRepo
from app.services.brand.service import BUCKET, BrandService
from app.services.brand.wiring import AllowAll, BrandRuntime, build_worker, get_runtime

ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"
ORG_PLATFORM = "99999999-9999-9999-9999-999999999999"
OWNER_A, MEMBER_A, OWNER_B, STAFF = "a0000000-0000-0000-0000-00000000000a", "a0000000-0000-0000-0000-00000000000b", \
    "b0000000-0000-0000-0000-00000000000a", "c0000000-0000-0000-0000-00000000000c"
SESSION = "5e550000-0000-0000-0000-000000000001"

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF = b"%PDF-1.7\n" + b"y" * 64
WOFF2 = b"wOF2" + b"\x00" * 32
GOOD_ANSWER = json.dumps({
    "tokens": {"schema": T.SCHEMA_ID, "light": {"primary": "20 80% 45%", "background": "40 30% 98%"},
               "fonts": {"heading": {"family": "Lora", "weights": [600], "source": "google"}}},
    "brand_book": "# Marca\nAzul e laranja.",
    "voice": {"tone": "acolhedor", "vocabulary": ["lar"], "do": ["falar simples"], "dont": ["jargão"]},
})


def _jwt(sub: str, session_id: str) -> str:
    def b64(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'none'})}.{b64({'sub': sub, 'session_id': session_id, 'aal': 'aal2'})}.sig"


TOKENS = {"tok-owner-a": OWNER_A, "tok-member-a": MEMBER_A, "tok-owner-b": OWNER_B,
          _jwt(STAFF, SESSION): STAFF}


class Env:
    def __init__(self, *, chat_responses=None, chat_usage=None, authenticate=None):
        self.repo = FakeBrandRepo()
        self.platform = self.repo.seed_platform(T.platform_tokens())
        self.jobs = make_job_repository(use_fake=True)
        self.storage = make_storage_backend(kind="fake")
        core = MockSupabaseClient()
        core.set_table_data("noctus_users", [
            {"id": OWNER_A, "org_id": ORG_A, "org_role": "owner", "role": "user", "organizations": {"is_platform": False}},
            {"id": MEMBER_A, "org_id": ORG_A, "org_role": "member", "role": "user", "organizations": {"is_platform": False}},
            {"id": OWNER_B, "org_id": ORG_B, "org_role": "owner", "role": "user", "organizations": {"is_platform": False}},
            {"id": STAFF, "org_id": ORG_PLATFORM, "org_role": "owner", "role": "admin", "organizations": {"is_platform": True}},
        ])
        core.set_table_data("org_memberships", [
            {"id": "m1", "user_id": OWNER_A, "org_id": ORG_A, "org_role": "owner", "status": "active"},
            {"id": "m2", "user_id": MEMBER_A, "org_id": ORG_A, "org_role": "member", "status": "active"},
            {"id": "m3", "user_id": MEMBER_A, "org_id": ORG_B, "org_role": "member", "status": "active"},
            {"id": "m4", "user_id": OWNER_B, "org_id": ORG_B, "org_role": "owner", "status": "active"},
        ])
        core.set_table_data("platform_org_selections", [])
        self.core = core

        async def permission(user_id, org_id, slug):
            assert slug == "settings:manage"
            if user_id == MEMBER_A:
                raise HTTPException(status_code=403, detail="Sem permissão")

        async def fake_auth(authorization, request):
            token = (authorization or "").removeprefix("Bearer ")
            if not authorization or not authorization.startswith("Bearer ") or token not in TOKENS:
                raise HTTPException(status_code=401, detail="Token ausente")
            return SimpleNamespace(id=TOKENS[token]), token

        configure_llm(LLMConfig(key_provider=lambda *_a, **_k: "test-key"))
        self.fake_llm = FakeProvider(chat_responses=chat_responses or [GOOD_ANSWER],
                                     chat_usage=chat_usage, usage_provider="anthropic" if chat_usage else None)
        provider = f"fake-brand-{uuid.uuid4().hex[:6]}"
        register(provider, lambda: self.fake_llm)

        self.service = BrandService(
            repo=self.repo, storage=self.storage, jobs=self.jobs,
            get_core_client=lambda: self.core, require_permission=permission,
            llm_provider=provider,
        )
        self.runtime = BrandRuntime(service=self.service, authenticate=authenticate or fake_auth,
                                    ingest_limit=AllowAll())
        self.worker = build_worker(self.service)
        app = FastAPI()
        app.include_router(router_module.router)
        app.dependency_overrides[get_runtime] = lambda: self.runtime
        self.client = TestClient(app)

    def h(self, token="tok-owner-a", **extra):
        return {"Authorization": f"Bearer {token}", **extra}

    def ingest(self, files=None, descriptions=None, token="tok-owner-a"):
        files = files or [("files", ("manual.pdf", PDF, "application/pdf")),
                          ("files", ("logo.png", PNG, "image/png")),
                          ("files", ("Lora-Regular.woff2", WOFF2, "font/woff2"))]
        data = {"descriptions": json.dumps(descriptions)} if descriptions else {}
        return self.client.post("/api/brand/identities/ingest", headers=self.h(token), files=files, data=data)

    def work(self) -> bool:
        return asyncio.run(self.worker.run_once())

    def ingested(self, **kw) -> str:
        r = self.ingest(**kw)
        assert r.status_code == 202, r.text
        assert self.work()
        return r.json()["identity_id"]


@pytest.fixture(autouse=True)
def _llm_reset():
    yield
    _reset_for_testing()


ROUTES = [
    ("get", "/api/brand/current"), ("get", "/api/brand/identities"),
    ("get", f"/api/brand/identities/{uuid.uuid4()}"), ("post", "/api/brand/identities/ingest"),
    ("get", "/api/brand/jobs/fake-job-1"), ("patch", f"/api/brand/identities/{uuid.uuid4()}"),
    ("post", f"/api/brand/identities/{uuid.uuid4()}/activate"),
    ("post", f"/api/brand/identities/{uuid.uuid4()}/assets"),
]


class TestAuth:
    @pytest.mark.parametrize("method,path", ROUTES)
    def test_unauthenticated_is_strict_401(self, method, path):
        env = Env()
        assert getattr(env.client, method)(path).status_code == 401
        assert getattr(env.client, method)(path, headers={"Authorization": "Bearer nope"}).status_code == 401

    def test_401_before_body_validation(self):
        env = Env()
        r = env.client.patch(f"/api/brand/identities/{uuid.uuid4()}", content=b"{not json")
        assert r.status_code == 401

    @pytest.mark.parametrize("method,path", ROUTES)
    def test_seed_auth_dependency_without_header_is_401(self, method, path):
        from app.dependencies import get_current_user

        async def seed_auth(authorization, request):
            return await get_current_user(authorization, request)

        env = Env(authenticate=seed_auth)
        assert getattr(env.client, method)(path).status_code == 401

    def test_management_requires_settings_manage(self):
        env = Env()
        assert env.client.get("/api/brand/identities", headers=env.h("tok-member-a")).status_code == 403
        assert env.ingest(token="tok-member-a").status_code == 403


class TestCurrent:
    def test_no_identity_serves_the_platform_row(self):
        env = Env()
        r = env.client.get("/api/brand/current", headers=env.h())
        assert r.status_code == 200
        body = r.json()
        assert body["source"] == "platform" and body["identity_id"] == env.platform["id"]
        assert body["tokens"]["light"] == T.platform_tokens()["light"]
        assert not {"voice", "brand_book"} & set(body) and "source_files" not in body
        assert r.headers["ETag"]
        again = env.client.get("/api/brand/current", headers=env.h(**{"If-None-Match": r.headers["ETag"]}))
        assert again.status_code == 304

    def test_active_org_identity_is_served_with_signed_urls_and_no_voice(self):
        env = Env()
        iid = env.ingested()
        assert env.client.post(f"/api/brand/identities/{iid}/activate", headers=env.h()).status_code == 200
        body = env.client.get("/api/brand/current", headers=env.h()).json()
        assert body["source"] == "org" and body["identity_id"] == iid and body["version"] == 1
        assert body["tokens"]["light"]["primary"] == "20 80% 45%"
        assert body["assets"]["logo_light"].startswith(f"fake://storage/{BUCKET}/{ORG_A}/")
        assert body["assets"]["fonts"][0]["family"] == "Lora"
        assert "voice" not in json.dumps(body) and "acolhedor" not in json.dumps(body)
        # org B still gets the platform
        assert env.client.get("/api/brand/current", headers=env.h("tok-owner-b")).json()["source"] == "platform"

    def test_acting_header_honoured_only_for_an_entitled_org(self):
        env = Env()
        h = {"X-Noctus-Acting-Org": ORG_B}
        assert env.client.get("/api/brand/current", headers=env.h("tok-member-a", **h)).json()["org_id"] == ORG_B
        r = env.client.get("/api/brand/current", headers=env.h("tok-owner-a", **h))
        assert r.status_code == 409 and r.json()["detail"]["code"] == "org_selection_changed"
        assert env.client.get("/api/brand/current",
                              headers=env.h("tok-owner-a", **{"X-Noctus-Acting-Org": "garbage"})).status_code == 409

    def test_staff_needs_a_live_selection_bound_to_this_login(self):
        env = Env()
        staff = _jwt(STAFF, SESSION)
        h = env.h(staff, **{"X-Noctus-Acting-Org": ORG_A})
        assert env.client.get("/api/brand/current", headers=h).status_code == 409
        env.core.set_table_data("platform_org_selections", [
            {"id": "s1", "user_id": STAFF, "target_org_id": ORG_A, "auth_session_id": "other-login", "ended_at": None}])
        assert env.client.get("/api/brand/current", headers=h).status_code == 409
        env.core.set_table_data("platform_org_selections", [
            {"id": "s1", "user_id": STAFF, "target_org_id": ORG_A, "auth_session_id": SESSION, "ended_at": None}])
        assert env.client.get("/api/brand/current", headers=h).json()["org_id"] == ORG_A

    def test_management_routes_refuse_a_pin_to_another_org(self):
        env = Env()
        r = env.client.get("/api/brand/identities", headers=env.h(**{"X-Noctus-Acting-Org": ORG_B}))
        assert r.status_code == 409


class TestIngestion:
    def test_ingest_to_done_with_seed_llm_fake(self):
        env = Env(chat_usage=[(1200, 800)])
        r = env.ingest(descriptions={"logo.png": "logo principal"})
        assert r.status_code == 202
        job_id, iid = r.json()["job_id"], r.json()["identity_id"]
        assert env.client.get(f"/api/brand/jobs/{job_id}", headers=env.h()).json()["status"] == "queued"
        assert env.work()
        status = env.client.get(f"/api/brand/jobs/{job_id}", headers=env.h()).json()
        assert status == {"job_id": job_id, "status": "done", "identity_id": iid}
        row = env.client.get(f"/api/brand/identities/{iid}", headers=env.h()).json()["data"]
        assert row["status"] == "draft" and row["voice"]["tone"] == "acolhedor"
        assert row["brand_book"].startswith("# Marca")
        assert row["validation"]["dark_derived"] is True
        assert "light.card" in row["validation"]["filled_from_default"]
        assert row["assets"]["logo_light"].endswith("/source/01.png")
        ext = row["source"]["extraction"]
        assert ext["model"] == "claude-sonnet-5-5" and ext["usage"]["prompt_tokens"] == 1200
        # the call itself: PDF as a native document block, uploads fenced as data
        call = env.fake_llm.calls[0]
        assert call["model"] == "claude-sonnet-5-5"
        system, user = call["messages"]
        assert "UNTRUSTED DATA" in system["content"]
        kinds = [b["type"] for b in user["content"]]
        assert "document" in kinds
        doc = next(b for b in user["content"] if b["type"] == "document")
        assert doc["source"]["media_type"] == "application/pdf" and base64.b64decode(doc["source"]["data"]) == PDF
        assert any("logo principal" in b.get("text", "") and "<brand-data-" in b.get("text", "") for b in user["content"])

    def test_unparseable_answer_fails_with_reason(self):
        env = Env(chat_responses=["sorry, here is some prose"])
        r = env.ingest()
        env.work()
        status = env.client.get(f"/api/brand/jobs/{r.json()['job_id']}", headers=env.h()).json()
        assert status["status"] == "failed" and status["error"]["code"] == "resposta_invalida"
        row = env.client.get(f"/api/brand/identities/{r.json()['identity_id']}", headers=env.h()).json()["data"]
        assert row["status"] == "failed"

    def test_injected_css_from_the_model_never_lands(self):
        evil = json.dumps({"tokens": {"light": {"primary": "0 0% 0%; } body { background: url(//x) }",
                                                "accent": "200 50% 50%"},
                                      "fonts": {"body": {"family": "x'}*{", "weights": [400], "source": "google"}}},
                           "brand_book": "", "voice": {}})
        env = Env(chat_responses=[evil])
        iid = env.ingested()
        row = env.client.get(f"/api/brand/identities/{iid}", headers=env.h()).json()["data"]
        assert row["tokens"]["light"]["primary"] == T.platform_tokens()["light"]["primary"]
        assert row["tokens"]["light"]["accent"] == "200 50% 50%" and row["tokens"]["fonts"] == {}
        assert row["validation"]["refused"]

    def test_no_document_fails_named(self):
        env = Env()
        r = env.ingest(files=[("files", ("logo.png", PNG, "image/png"))])
        env.work()
        assert env.client.get(f"/api/brand/jobs/{r.json()['job_id']}", headers=env.h()).json()["error"]["code"] == "sem_documento"

    @pytest.mark.parametrize("files,codigo", [
        ([("files", ("logo.svg", b"<svg/>", "image/svg+xml"))], "svg_recusado"),
        ([("files", ("logo.png", PDF, "image/png"))], "conteudo_invalido"),
        ([("files", (f"{i}.png", PNG, "image/png")) for i in range(11)], "arquivos_demais"),
    ])
    def test_upload_refusals(self, files, codigo):
        env = Env()
        r = env.ingest(files=files)
        assert r.status_code == 422 and r.json()["detail"]["code"] == codigo

    def test_no_files_is_422_after_auth(self):
        env = Env()
        r = env.client.post("/api/brand/identities/ingest", headers=env.h())
        assert r.status_code == 422 and r.json()["detail"]["code"] == "sem_arquivos"

    def test_rate_limited_per_org(self):
        env = Env()

        class Deny:
            def allow(self, org_id):
                return False

        env.runtime.ingest_limit = Deny()
        assert env.ingest().status_code == 429


class TestIsolationAndEdits:
    def test_cross_org_ids_are_404(self):
        env = Env()
        r = env.ingest()
        iid, job_id = r.json()["identity_id"], r.json()["job_id"]
        env.work()
        b = env.h("tok-owner-b")
        assert env.client.get(f"/api/brand/identities/{iid}", headers=b).status_code == 404
        assert env.client.get(f"/api/brand/jobs/{job_id}", headers=b).status_code == 404
        assert env.client.patch(f"/api/brand/identities/{iid}", headers=b, json={"brand_book": "x"}).status_code == 404
        assert env.client.post(f"/api/brand/identities/{iid}/activate", headers=b).status_code == 404
        assert env.client.post(f"/api/brand/identities/{iid}/assets", headers=b,
                               files={"file": ("logo.png", PNG, "image/png")}, data={"slot": "logo_dark"}).status_code == 404
        assert env.client.get("/api/brand/identities/not-a-uuid", headers=env.h()).status_code == 404
        assert env.client.get(f"/api/brand/identities/{env.platform['id']}", headers=env.h()).status_code == 404

    def test_patch_is_strict(self):
        env = Env()
        iid = env.ingested()
        url = f"/api/brand/identities/{iid}"
        r = env.client.patch(url, headers=env.h(), json={"tokens": {"light": {"primary": "red"}}})
        assert r.status_code == 422 and r.json()["detail"]["code"] == "tokens_invalidos"
        assert env.client.patch(url, headers=env.h(), json={"unknown": 1}).status_code == 422
        ok = env.client.patch(url, headers=env.h(), json={"tokens": {"light": {"accent": "100 40% 40%"}, "dark": None},
                                                          "voice": {"tone": "sério"}})
        assert ok.status_code == 200
        data = ok.json()["data"]
        assert data["tokens"]["light"]["accent"] == "100 40% 40%" and data["tokens"]["light"]["primary"] == "20 80% 45%"
        assert data["validation"]["dark_derived"] is True and data["voice"]["tone"] == "sério"

    def test_activate_archives_previous_and_rollback(self):
        env = Env(chat_responses=[GOOD_ANSWER, GOOD_ANSWER])
        v1, v2 = env.ingested(), env.ingested()
        assert env.client.post(f"/api/brand/identities/{v1}/activate", headers=env.h()).json()["data"]["status"] == "active"
        assert env.client.post(f"/api/brand/identities/{v2}/activate", headers=env.h()).status_code == 200
        listing = {r["id"]: r for r in env.client.get("/api/brand/identities", headers=env.h()).json()["data"]}
        assert listing[v1]["status"] == "archived" and listing[v2]["status"] == "active"
        assert all("voice" not in r for r in listing.values())
        assert env.client.post(f"/api/brand/identities/{v1}/activate", headers=env.h()).status_code == 200  # rollback
        assert env.client.get("/api/brand/current", headers=env.h()).json()["identity_id"] == v1
        # archived/active are not editable
        assert env.client.patch(f"/api/brand/identities/{v2}", headers=env.h(), json={"brand_book": "x"}).status_code == 409

    def test_failed_and_in_flight_drafts_cannot_be_activated(self):
        env = Env(chat_responses=["nope"])
        r = env.ingest()
        iid = r.json()["identity_id"]
        assert env.client.post(f"/api/brand/identities/{iid}/activate", headers=env.h()).status_code == 409  # queued
        env.work()
        assert env.client.post(f"/api/brand/identities/{iid}/activate", headers=env.h()).status_code == 409  # failed

    def test_asset_upload(self):
        env = Env()
        iid = env.ingested()
        url = f"/api/brand/identities/{iid}/assets"
        ok = env.client.post(url, headers=env.h(), files={"file": ("x.png", PNG, "image/png")}, data={"slot": "logo_dark"})
        assert ok.status_code == 200 and "/assets/logo_dark-" in ok.json()["data"]["assets"]["logo_dark"]
        svg = env.client.post(url, headers=env.h(), files={"file": ("x.svg", b"<svg/>", "image/svg+xml")},
                              data={"slot": "logo_dark"})
        assert svg.status_code == 422 and svg.json()["detail"]["code"] == "svg_recusado"
        assert env.client.post(url, headers=env.h(), files={"file": ("x.png", PNG, "image/png")},
                               data={"slot": "font"}).status_code == 422
        assert env.client.post(url, headers=env.h(), files={"file": ("x.png", PNG, "image/png")},
                               data={"slot": "banner"}).status_code == 422
        font = env.client.post(url, headers=env.h(), files={"file": ("Inter.woff2", WOFF2, "font/woff2")},
                               data={"slot": "font", "family": "Inter"})
        assert font.status_code == 200 and font.json()["data"]["assets"]["fonts"][-1]["family"] == "Inter"


def test_body_limits_cover_the_upload_routes():
    from noctusai_lib.api.middleware import path_is_covered_by_overrides, to_wildcard_pattern

    for route in router_module.router.routes:
        if "ingest" in route.path or route.path.endswith("/assets"):
            assert path_is_covered_by_overrides(to_wildcard_pattern(route.path), router_module.BODY_LIMITS)


def test_main_wires_the_brand_body_limits():
    from app.main import app as core_app

    mw = next(m for m in core_app.user_middleware if m.cls.__name__ == "MaxBodySizeMiddleware")
    overrides = mw.kwargs["path_overrides"]
    for path, limit in router_module.BODY_LIMITS.items():
        assert overrides.get(path) == limit
