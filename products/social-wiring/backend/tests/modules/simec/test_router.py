"""/api/simec/... — auth boundary (strict 401), org + provider scoping, the
config layer lifecycle (admin-gated, validated, versioned, history), and
readouts computed end-to-end through the seed calculator and persisted.

DI seams only (``app.dependency_overrides``): ``get_current_user_org``
(session), ``get_simec_repository`` / ``get_ig_repository_for_simec``
(repositories over an in-memory PostgREST double), ``get_simec_service``
(the real service with the Fake source and a fixed "today"),
``get_admin_gate`` (owner/admin decision).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.domain.content_performance import load_default_config

from app.modules.instagram.repository import IgInsightsRepository
from app.modules.instagram.sync_service import TZ_BR
from app.modules.simec.repository import SimecRepository
from app.modules.simec.service import SimecService
from app.modules.simec.sources import FakeInstagramSource, demo_instagram_rows
from tests.modules.instagram.fakes import FakeSupabase

ORG_A = "00000000-0000-4000-8000-00000000000a"
ORG_B = "00000000-0000-4000-8000-00000000000b"
ACC = "00000000-0000-4000-8000-0000000000a1"
ACC_META = "00000000-0000-4000-8000-0000000000a2"
ACC_B = "00000000-0000-4000-8000-0000000000b1"
USER = "00000000-0000-4000-8000-0000000000u1".replace("u", "f")
TODAY = date(2026, 10, 19)
RID = "00000000-0000-4000-8000-0000000000d1"

PATHS = [
    ("get", "/api/simec/accounts", None),
    ("get", "/api/simec/config/defaults", None),
    ("get", "/api/simec/config", None),
    ("put", "/api/simec/config/org", {"overrides": {}}),
    ("put", f"/api/simec/accounts/{ACC}/config", {"overrides": {}}),
    ("post", f"/api/simec/accounts/{ACC}/readouts", {}),
    ("get", f"/api/simec/accounts/{ACC}/readouts", None),
    ("get", f"/api/simec/accounts/{ACC}/readouts/latest", None),
    ("get", f"/api/simec/readouts/{RID}", None),
]


def _acct(id_, org, provider="instagram"):
    return {"id": id_, "org_id": org, "provider": provider, "status": "validated",
            "marca_id": None, "account_label": "monica",
            "metadata": {"channel_title": "monica", "scopes": ["instagram_business_manage_insights"]},
            "channel_info": {"username": "monicatangerino"}, "last_synced_at": None,
            "created_at": "2026-10-01T00:00:00+00:00"}


@pytest.fixture
def sb():
    s = FakeSupabase()
    s.tables["integration_accounts"] = [_acct(ACC, ORG_A), _acct(ACC_META, ORG_A, "meta"), _acct(ACC_B, ORG_B)]
    return s


@pytest.fixture
def admin():
    return {"is_admin": True}


@pytest.fixture
def client(sb, admin):
    from app.main import app
    from app.modules.simec.router import (
        get_admin_gate,
        get_ig_repository_for_simec,
        get_simec_repository,
        get_simec_service,
    )

    def gate(auth, request, context):
        if not admin["is_admin"]:
            raise HTTPException(403, f"{context} restrito a administradores.")

    app.dependency_overrides[get_simec_repository] = lambda: SimecRepository(sb)
    app.dependency_overrides[get_ig_repository_for_simec] = lambda: IgInsightsRepository(sb)
    app.dependency_overrides[get_simec_service] = lambda: SimecService(
        SimecRepository(sb), FakeInstagramSource(default=demo_instagram_rows), today=lambda: TODAY)
    app.dependency_overrides[get_admin_gate] = lambda: gate
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _login(org=ORG_A):
    from app.dependencies import get_current_user_org
    from app.main import app

    app.dependency_overrides[get_current_user_org] = lambda: (SimpleNamespace(id=USER), "tok", org)


def _call(client, method, path, body=None):
    if body is None:
        return getattr(client, method)(path)
    return getattr(client, method)(path, json=body)


class TestAuthBoundary:
    @pytest.mark.parametrize("method,path,body", PATHS)
    def test_no_session_is_strict_401(self, client, method, path, body):
        assert _call(client, method, path, body).status_code == 401


class TestScoping:
    @pytest.mark.parametrize("method,path,body", [p for p in PATHS if ACC in p[1]])
    def test_other_orgs_account_is_404(self, client, method, path, body):
        _login(ORG_B)
        assert _call(client, method, path, body).status_code == 404

    def test_non_instagram_account_is_404(self, client):
        _login()
        assert client.post(f"/api/simec/accounts/{ACC_META}/readouts", json={}).status_code == 404

    def test_malformed_account_id_is_400(self, client):
        _login()
        assert client.get("/api/simec/accounts/not-a-uuid/readouts").status_code == 400


class TestAccounts:
    def test_lists_only_this_orgs_instagram_accounts(self, client):
        _login()
        r = client.get("/api/simec/accounts")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["metrics_source"] == "fake"
        assert [a["account_id"] for a in body["accounts"]] == [ACC]
        a = body["accounts"][0]
        assert a["username"] == "monicatangerino" and a["insights_scope_granted"] is True
        assert a["latest_readout"] is None

    def test_org_without_connection_is_empty_not_error(self, client, sb):
        sb.tables["integration_accounts"] = []
        _login()
        assert client.get("/api/simec/accounts").json()["accounts"] == []


class TestConfig:
    def test_defaults(self, client):
        _login()
        body = client.get("/api/simec/config/defaults").json()
        cfg = load_default_config("instagram")
        assert body["version"] == cfg.version and body["fingerprint"] == cfg.fingerprint
        assert body["config"]["windows"]["7d"] == {"label": "7 dias", "min_days": 7, "max_days": 10}

    def test_tiktok_is_not_served_yet(self, client):
        _login()
        assert client.get("/api/simec/config/defaults?platform=tiktok").status_code == 422

    def test_org_then_profile_layers(self, client, sb):
        _login()
        r = client.put("/api/simec/config/org", json={"overrides": {"baseline": {"min_posts": 8}}})
        assert r.status_code == 200, r.text
        assert r.json()["version"] == "instagram-defaults-1.0.0+org.v1"
        r = client.put("/api/simec/config/org", json={"overrides": {"baseline": {"min_posts": 9}}})
        assert r.json()["version"] == "instagram-defaults-1.0.0+org.v2"
        r = client.put(f"/api/simec/accounts/{ACC}/config",
                       json={"overrides": {"windows": {"7d": {"max_days": 12}}}})
        assert r.status_code == 200, r.text
        body = client.get(f"/api/simec/config?account_id={ACC}").json()
        assert body["version"] == "instagram-defaults-1.0.0+org.v2+perfil.v1"
        assert body["config"]["baseline"]["min_posts"] == 9
        assert body["config"]["windows"]["7d"]["max_days"] == 12
        assert body["layers"]["org"]["version"] == 2
        assert body["layers"]["account"]["overrides"] == {"windows": {"7d": {"max_days": 12}}}
        # org-only view does not carry the profile layer
        assert client.get("/api/simec/config").json()["version"] == "instagram-defaults-1.0.0+org.v2"
        hist = sb.tables["simec_config_historico"]
        assert [(h["version"], h["changed_by"]) for h in hist] == [(1, USER), (2, USER), (1, USER)]

    def test_non_admin_cannot_write(self, client, admin, sb):
        _login()
        admin["is_admin"] = False
        r = client.put("/api/simec/config/org", json={"overrides": {"baseline": {"min_posts": 8}}})
        assert r.status_code == 403
        assert "simec_configs" not in sb.tables or sb.tables["simec_configs"] == []

    @pytest.mark.parametrize("overrides", [
        {"windows": {"7d": {"min_days": 11}}},
        {"alerts": {"x": {"indicator": "reach", "method": "zscore", "threshold": 2}}},
        {"version": "mine"},
    ])
    def test_invalid_overrides_are_422_and_not_stored(self, client, sb, overrides):
        _login()
        r = client.put("/api/simec/config/org", json={"overrides": overrides})
        assert r.status_code == 422, r.text
        assert not sb.tables.get("simec_configs")

    def test_unknown_body_field_is_422(self, client):
        _login()
        assert client.put("/api/simec/config/org", json={"overrides": {}, "x": 1}).status_code == 422


class TestReadouts:
    def test_latest_is_null_before_any(self, client):
        _login()
        r = client.get(f"/api/simec/accounts/{ACC}/readouts/latest")
        assert r.status_code == 200 and r.json() == {"readout": None}

    def test_compute_store_and_read_back(self, client, sb):
        _login()
        r = client.post(f"/api/simec/accounts/{ACC}/readouts", json={"cadence": "mensal"})
        assert r.status_code == 201, r.text
        ro = r.json()
        cfg = load_default_config("instagram")
        assert ro["source"] == "fake"
        assert ro["config_version"] == cfg.version and ro["config_fingerprint"] == cfg.fingerprint
        assert (ro["period_start"], ro["period_end"]) == ("2026-09-20", "2026-10-19")
        assert ro["history_start"] == "2026-06-22"
        assert set(ro["panel"]) == {"72h", "7d", "30d", "atual"}
        assert ro["panel"]["7d"]["media_views_3s"]["status"] == "nao_disponivel"
        assert ro["panel"]["7d"]["conteudos_validos"]["value"] >= 1
        assert ro["readings"] and all(x["status"] for x in ro["readings"])
        assert {x["window"] for x in ro["readings"]} <= {"72h", "7d", "30d", "atual"}
        assert ro["baselines"] and "fired" in ro["alerts"] and "not_evaluated" in ro["alerts"]
        assert len(sb.tables["simec_readouts"]) == 1
        assert len(sb.tables["simec_leituras"]) == len(ro["readings"])
        assert all(x["org_id"] == ORG_A for x in sb.tables["simec_leituras"])

        latest = client.get(f"/api/simec/accounts/{ACC}/readouts/latest").json()["readout"]
        assert latest["id"] == ro["id"] and latest["panel"] == ro["panel"]
        assert client.get(f"/api/simec/readouts/{ro['id']}").json()["id"] == ro["id"]
        items = client.get(f"/api/simec/accounts/{ACC}/readouts").json()["items"]
        assert [i["id"] for i in items] == [ro["id"]]
        acc = client.get("/api/simec/accounts").json()["accounts"][0]
        assert acc["latest_readout"]["id"] == ro["id"]

        _login(ORG_B)
        assert client.get(f"/api/simec/readouts/{ro['id']}").status_code == 404

    def test_profile_layer_is_stamped_on_the_readout(self, client):
        _login()
        client.put(f"/api/simec/accounts/{ACC}/config", json={"overrides": {"baseline": {"min_posts": 3}}})
        ro = client.post(f"/api/simec/accounts/{ACC}/readouts", json={}).json()
        assert ro["config_version"] == "instagram-defaults-1.0.0+perfil.v1"
        assert ro["config"]["baseline"]["min_posts"] == 3

    def test_explicit_period(self, client):
        _login()
        r = client.post(f"/api/simec/accounts/{ACC}/readouts",
                        json={"period_start": "2026-09-01", "period_end": "2026-09-30"})
        assert r.status_code == 201, r.text
        assert r.json()["period_start"] == "2026-09-01"

    @pytest.mark.parametrize("body", [
        {"period_start": "2026-09-30", "period_end": "2026-09-01"},
        {"period_start": "2026-09-01"},
        {"period_start": "2024-01-01", "period_end": "2026-01-01"},
        {"cadence": "diario"},
        {"bogus": 1},
    ])
    def test_bad_requests_are_422(self, client, body):
        _login()
        assert client.post(f"/api/simec/accounts/{ACC}/readouts", json=body).status_code == 422

    def test_unknown_readout_is_404(self, client):
        _login()
        assert client.get(f"/api/simec/readouts/{RID}").status_code == 404


class TestWiring:
    def test_register_shape(self):
        from app.main import ModuleRegistration
        from app.modules.simec import register

        reg = register()
        assert isinstance(reg, ModuleRegistration)
        assert [r.prefix for r in reg.routers] == ["/api/simec"]

    def test_mounted_in_the_app(self):
        from app.main import app

        paths = {getattr(r, "path", "") for r in app.routes}
        assert "/api/simec/accounts/{account_id}/readouts" in paths

    def test_misconfigured_source_is_503_not_a_silent_fallback(self, sb):
        from app.dependencies import get_current_user_org
        from app.main import app
        from app.modules.simec.router import (
            get_ig_repository_for_simec,
            get_simec_repository,
            get_simec_source_kind,
        )

        app.dependency_overrides[get_simec_repository] = lambda: SimecRepository(sb)
        app.dependency_overrides[get_ig_repository_for_simec] = lambda: IgInsightsRepository(sb)
        app.dependency_overrides[get_current_user_org] = lambda: (SimpleNamespace(id=USER), "t", ORG_A)
        app.dependency_overrides[get_simec_source_kind] = lambda: "metricool"
        try:
            r = TestClient(app, raise_server_exceptions=False).get("/api/simec/accounts")
            assert r.status_code == 503
        finally:
            app.dependency_overrides.clear()

    def test_default_source_is_the_real_instagram_one(self, sb):
        from app.modules.simec.router import get_simec_service, get_simec_source_kind

        assert get_simec_source_kind() == "instagram"
        svc = get_simec_service(SimecRepository(sb), IgInsightsRepository(sb), "instagram")
        assert svc.source_name == "instagram_snapshots"
