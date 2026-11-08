"""`ModuleSpec` / `create_product_app(modules=...)` / per-org enablement guard / platform-admin write API / page-key contract."""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.api.auth.session.types import AuthContext
from noctusai_lib.domain.module_enablement import (
    MODULE_GROUP_KEYS,
    FakeModuleEnablementStore,
    ModuleEnablement,
    SupabaseModuleEnablementStore,
    create_org_modules_admin_router,
    module_enablement_migration,
)
from noctusai_seed.modules import ModuleSpec, PageSpec, module_manifest, mount_modules, validate_modules
from noctusai_seed.organs import ORGAN_REGISTRY, MountedOrgan, organ_guard_probes, organ_migration_sql

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "lib" / "backend" / "tests" / "fixtures" / "module_manifest.json"
FE_NAV = ROOT / "lib" / "frontend" / "src" / "design-system" / "components" / "nav-groups.ts"

ORG_ON, ORG_OFF, ORG_ADMIN_USER = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222", "u-admin"


async def _auth(authorization: str | None = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="no auth")
    org = ORG_OFF if authorization == "off" else ORG_ON
    return (SimpleNamespace(id="u1"), "tok", org)


def _organ(name: str = "leads", path: str = "/api/leads") -> MountedOrgan:
    r = APIRouter()

    @r.get(path)
    async def _list(base: Any = Depends(_auth)):
        return {"ok": True}

    return MountedOrgan(name=name, routers=(r,))


def _spec(**kw) -> ModuleSpec:
    return ModuleSpec(key="crm", organs=(_organ(),), pages=(PageSpec("crm/leads", "/crm/leads", "Leads"),),
                      permissions={"crm.write": "admin"}, **kw)


def _client(spec: ModuleSpec, store: FakeModuleEnablementStore) -> TestClient:
    enablement = ModuleEnablement(store, [spec.enablement_key], ttl_s=0)
    mounted = mount_modules([spec], enablement=enablement, auth_dependency=_auth)
    app = FastAPI()
    for router, deps in mounted.guarded:
        app.include_router(router, dependencies=list(deps))
    for router in mounted.open_routers:
        app.include_router(router)
    return TestClient(app)


# -- guard + endpoint --------------------------------------------------------------------------------------------


def test_default_all_on_and_strict_401():
    c = _client(_spec(), FakeModuleEnablementStore())
    assert c.get("/api/leads").status_code == 401
    assert c.get("/api/modules").status_code == 401
    assert c.get("/api/leads", headers={"authorization": "on"}).status_code == 200


def test_disabled_module_refuses_403_with_stable_code():
    store = FakeModuleEnablementStore(rows={(ORG_OFF, "crm"): False})
    c = _client(_spec(), store)
    r = c.get("/api/leads", headers={"authorization": "off"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "module_disabled"
    assert c.get("/api/leads", headers={"authorization": "on"}).status_code == 200


def test_unauthenticated_call_to_disabled_module_is_401_not_403():
    store = FakeModuleEnablementStore(rows={(ORG_OFF, "crm"): False})
    assert _client(_spec(), store).get("/api/leads").status_code == 401


def test_enablement_outage_is_503_never_all_on():
    store = FakeModuleEnablementStore(unavailable=True)
    c = _client(_spec(), store)
    assert c.get("/api/leads", headers={"authorization": "on"}).status_code == 503
    assert c.get("/api/modules", headers={"authorization": "on"}).status_code == 503


def test_modules_endpoint_reports_enabled_per_org():
    store = FakeModuleEnablementStore(rows={(ORG_OFF, "crm"): False})
    c = _client(_spec(), store)
    on = c.get("/api/modules", headers={"authorization": "on"}).json()["modules"][0]
    off = c.get("/api/modules", headers={"authorization": "off"}).json()["modules"][0]
    assert on == {"key": "crm", "enablement_key": "crm", "enabled": True, "permissions": {"crm.write": "admin"}}
    assert off["enabled"] is False


def test_license_key_is_the_enablement_key():
    store = FakeModuleEnablementStore(rows={(ORG_OFF, "crm-pro"): False})
    c = _client(_spec(license_key="crm-pro"), store)
    assert c.get("/api/leads", headers={"authorization": "off"}).status_code == 403
    assert c.get("/api/leads", headers={"authorization": "on"}).status_code == 200


def test_public_routers_are_not_guarded():
    pub = APIRouter()

    @pub.get("/p/quote")
    async def _q():
        return {"public": True}

    spec = ModuleSpec(key="crm", public_routers=(pub,))
    c = _client(spec, FakeModuleEnablementStore(rows={(ORG_OFF, "crm"): False}))
    assert c.get("/p/quote").status_code == 200


# -- create_product_app(modules=) --------------------------------------------------------------------------------


class _S:
    """Minimal settings shape (mirrors test_serve_spa)."""

    cors_origins = "http://localhost:3000"
    cors_origins_list = ["http://localhost:3000"]
    debug = True
    is_production = False
    sentry_dsn = None
    product_slug = "test"
    supabase_url = "http://localhost:54321"
    supabase_anon_key = "anon"
    supabase_service_role_key = "service"
    consent_gating = False
    llm_usage_tracking = False
    redis_url = None


def _cpa(**kw):
    from noctusai_seed import create_product_app

    return create_product_app(name="Test", schema="test", settings=_S(), version="9.9.9", **kw)


def test_create_product_app_requires_auth_dependency_with_modules():
    with pytest.raises(ValueError, match="module_auth_dependency"):
        _cpa(modules=[_spec()])


def test_create_product_app_mounts_modules_and_default_is_unchanged():
    plain = _cpa()
    assert not any(getattr(r, "path", "") == "/api/modules" for r in plain.routes)
    app = _cpa(modules=[_spec()], module_auth_dependency=_auth)
    paths = {getattr(r, "path", "") for r in app.routes}
    assert {"/api/leads", "/api/modules"} <= paths
    c = TestClient(app)
    assert c.get("/api/leads").status_code == 401
    assert c.get("/api/leads", headers={"authorization": "on"}).status_code == 200  # Fake store under pytest = all ON


# -- spec validation -----------------------------------------------------------------------------------------------


def test_spec_validation():
    with pytest.raises(ValueError, match="canonical"):
        ModuleSpec(key="nope")
    with pytest.raises(ValueError, match="duplicate page keys"):
        ModuleSpec(key="crm", pages=(PageSpec("a", "/a", "A"), PageSpec("a", "/b", "B")))
    with pytest.raises(ValueError, match="status"):
        PageSpec("a", "/a", "A", status="x")
    with pytest.raises(ValueError, match="level"):
        ModuleSpec(key="crm", permissions={"p": "root"})
    with pytest.raises(ValueError, match="one module"):
        validate_modules([ModuleSpec(key="crm", pages=(PageSpec("a", "/a", "A"),)), ModuleSpec(key="erp", pages=(PageSpec("a", "/b", "A"),))])
    with pytest.raises(ValueError, match="share enablement key"):
        validate_modules([ModuleSpec(key="crm", license_key="x"), ModuleSpec(key="erp", license_key="x")])


def test_conflicting_body_overrides_are_refused():
    a = MountedOrgan(name="a", routers=(), max_body_path_overrides={"/x": 1})
    b = MountedOrgan(name="b", routers=(), max_body_path_overrides={"/x": 2})
    en = ModuleEnablement(FakeModuleEnablementStore(), ["crm", "erp"])
    with pytest.raises(ValueError, match="conflicting"):
        mount_modules([ModuleSpec(key="crm", organs=(a,)), ModuleSpec(key="erp", organs=(b,))], enablement=en, auth_dependency=_auth)


# -- platform-admin write API ----------------------------------------------------------------------------------------


class _Q:
    def __init__(self, rows): self._rows = rows
    def select(self, *_a): return self
    def eq(self, col, val): self._rows = [r for r in self._rows if str(r.get(col)) == str(val)]; return self
    def limit(self, _n): return self
    def execute(self): return SimpleNamespace(data=self._rows)


class _Core:
    def __init__(self):
        self.t = {"noctus_users": [{"id": ORG_ADMIN_USER, "role": "admin"}, {"id": "u-org-admin", "role": "user"}],
                  "organizations": [{"id": ORG_ON}]}
    def table(self, n): return _Q(list(self.t[n]))
    def from_(self, n): return self.table(n)


def _admin_client():
    core, store = _Core(), FakeModuleEnablementStore()
    en = ModuleEnablement(store, MODULE_GROUP_KEYS, ttl_s=0)

    async def get_auth_context(authorization: str | None = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401, detail="no auth")
        return AuthContext(org_id=ORG_ON, caller_kind="user", user_id=authorization, scopes=[], raw_token="t", api_token_id=None)

    app = FastAPI()
    app.include_router(create_org_modules_admin_router(get_auth_context=get_auth_context, get_core_client=lambda: core, enablement=en))
    return TestClient(app), store


def test_admin_api_strict_401_and_403():
    c, store = _admin_client()
    for method, path, kw in (("get", f"/api/platform/org-modules/{ORG_ON}", {}),
                             ("put", f"/api/platform/org-modules/{ORG_ON}/crm", {"json": {"enabled": False}})):
        assert getattr(c, method)(path, **kw).status_code == 401, path
        r = getattr(c, method)(path, headers={"authorization": "u-org-admin"}, **kw)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "platform_admin_required", path
    assert store.writes == []


def test_admin_api_toggle_roundtrip():
    c, store = _admin_client()
    h = {"authorization": ORG_ADMIN_USER}
    got = c.get(f"/api/platform/org-modules/{ORG_ON}", headers=h).json()
    assert [m["key"] for m in got["modules"]] == list(MODULE_GROUP_KEYS) and all(m["enabled"] for m in got["modules"])
    r = c.put(f"/api/platform/org-modules/{ORG_ON}/crm", headers=h, json={"enabled": False})
    assert r.status_code == 200 and r.json() == {"key": "crm", "enabled": False}
    assert store.writes == [(ORG_ON, "crm", False, ORG_ADMIN_USER)]
    after = {m["key"]: m["enabled"] for m in c.get(f"/api/platform/org-modules/{ORG_ON}", headers=h).json()["modules"]}
    assert after["crm"] is False and after["erp"] is True


def test_admin_api_validation():
    c, _ = _admin_client()
    h = {"authorization": ORG_ADMIN_USER}
    assert c.put(f"/api/platform/org-modules/{ORG_ON}/bogus", headers=h, json={"enabled": True}).status_code == 422
    assert c.put("/api/platform/org-modules/not-a-uuid/crm", headers=h, json={"enabled": True}).status_code == 422
    r = c.put(f"/api/platform/org-modules/{ORG_OFF}/crm", headers=h, json={"enabled": True})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "org_not_found"
    assert c.put(f"/api/platform/org-modules/{ORG_ON}/crm", headers=h, json={"enabled": True, "x": 1}).status_code == 422


# -- Real store over a PostgREST-shaped client ---------------------------------------------------------------------------


def test_supabase_store_reads_and_upserts():
    calls: list[Any] = []

    class T:
        def select(self, *_): return self
        def eq(self, *_): return self
        def upsert(self, row, on_conflict=None): calls.append((row, on_conflict)); return self
        def execute(self): return SimpleNamespace(data=[{"module_key": "crm", "enabled": False}])

    class C:
        def table(self, n): assert n == "org_modules"; return T()

    s = SupabaseModuleEnablementStore(lambda: C())
    assert s.explicit(ORG_ON) == {"crm": False}
    s.set_enabled(ORG_ON, "erp", True, updated_by="u")
    assert calls == [({"org_id": ORG_ON, "module_key": "erp", "enabled": True, "updated_by": "u"}, "org_id,module_key")]


# -- migration + organ registry ----------------------------------------------------------------------------------------


def test_migration_is_service_only_and_registered():
    sql = module_enablement_migration("public")
    assert "tier:platform" in sql and "REVOKE ALL ON public.org_modules FROM PUBLIC, anon, authenticated" in sql
    assert "GRANT SELECT" not in sql and "TO authenticated" not in sql
    assert organ_migration_sql("module_enablement", "public") == sql
    assert sql.splitlines()[0] == ORGAN_REGISTRY["module_enablement"].migration_header
    assert organ_guard_probes("module_enablement", "public") == ()
    # one platform table: the schema argument (a rendering product's) never moves it out of `public`
    assert module_enablement_migration("erp") == sql


# -- page-key contract ---------------------------------------------------------------------------------------------------


def test_backend_modules_match_the_shared_manifest_fixture():
    specs = [
        ModuleSpec(key="crm", pages=(
            PageSpec("crm/leads", "/crm/leads", "Leads"), PageSpec("crm/funil", "/crm/funil", "Funil"),
            PageSpec("crm/relatorios", "/crm/relatorios", "Relatórios", status="desenvolvimento"))),
        ModuleSpec(key="erp", license_key="erp-financeiro", pages=(PageSpec("erp/financeiro", "/erp/financeiro", "Financeiro"),)),
    ]
    assert module_manifest(specs) == json.loads(FIXTURE.read_text())


def test_group_keys_match_frontend_module_group_order():
    ts = FE_NAV.read_text()
    block = re.search(r"MODULE_GROUP_ORDER = \[(.*?)\] as const", ts, re.S).group(1)
    assert tuple(re.findall(r'"([^"]+)"', block)) == MODULE_GROUP_KEYS
