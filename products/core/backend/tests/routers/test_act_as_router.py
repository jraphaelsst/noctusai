"""Round 2 — superadmin act-as-org endpoints (``/api/admin/orgs``, ``/api/admin/act-as*``).

Fixtures (tests/conftest.py): ``client`` = authenticated NON-admin (get_current_admin
403s), ``admin_client`` = superadmin, ``unauth_client`` = no token (401). Every
denial is a strict ``== 403`` / ``== 401``.
"""
from __future__ import annotations

import pytest

ORG = "11111111-1111-1111-1111-111111111111"
PRODUCT = {"id": "p-1", "slug": "igig", "nome": "IgIg", "url_base": "http://localhost:5190", "ativo": True}


def _seed_licensed(sb, *, licensed: bool = True):
    sb.set_table_data("organizations", [{"id": ORG, "nome": "Imob X", "slug": "imob-x"}])
    sb.set_table_data("products", [PRODUCT])
    sb.set_table_data(
        "licenses",
        [{"id": "l-1", "org_id": ORG, "product_id": "p-1", "status": "active", "fim": None}] if licensed else [],
    )
    sb.set_table_data("act_as_sessions", [])


ADMIN_ENDPOINTS = [
    ("get", "/api/admin/orgs", None),
    ("post", "/api/admin/act-as", {"org_id": ORG, "product_slug": "igig"}),
    ("delete", "/api/admin/act-as/current", None),
    ("get", "/api/admin/act-as/history", None),
]


class TestAuthBoundary:
    @pytest.mark.parametrize("method,url,body", ADMIN_ENDPOINTS)
    def test_unauthenticated_is_401(self, unauth_client, method, url, body):
        resp = getattr(unauth_client, method)(url, **({"json": body} if body else {}))
        assert resp.status_code == 401

    @pytest.mark.parametrize("method,url,body", ADMIN_ENDPOINTS)
    def test_non_admin_is_403(self, client, method, url, body):
        resp = getattr(client, method)(url, **({"json": body} if body else {}))
        assert resp.status_code == 403

    def test_non_admin_cannot_start_a_session(self, client):
        _seed_licensed(client.mock_supabase)
        client.post("/api/admin/act-as", json={"org_id": ORG, "product_slug": "igig"})
        assert client.mock_supabase.table("act_as_sessions").inserted_payloads == []


class TestStart:
    def test_unlicensed_target_is_403_org_sem_licenca(self, admin_client):
        _seed_licensed(admin_client.mock_supabase, licensed=False)
        resp = admin_client.post("/api/admin/act-as", json={"org_id": ORG, "product_slug": "igig"})
        assert resp.status_code == 403
        assert resp.json()["code"] == "org_sem_licenca"
        assert admin_client.mock_supabase.table("act_as_sessions").inserted_payloads == []

    def test_licensed_target_starts_and_mints_sso_redirect(self, admin_client):
        _seed_licensed(admin_client.mock_supabase)
        resp = admin_client.post(
            "/api/admin/act-as", json={"org_id": ORG, "product_slug": "igig", "reason": "suporte"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["session_id"]
        assert "/sso?token=" in body["redirect_url"]
        [row] = admin_client.mock_supabase.table("act_as_sessions").inserted_payloads
        assert row["target_org_id"] == ORG
        assert row["entry_product_slug"] == "igig"
        assert row["reason"] == "suporte"

    def test_unknown_org_is_404(self, admin_client):
        _seed_licensed(admin_client.mock_supabase)
        admin_client.mock_supabase.set_table_data("organizations", [])
        resp = admin_client.post("/api/admin/act-as", json={"org_id": ORG, "product_slug": "igig"})
        assert resp.status_code == 404

    def test_unknown_field_is_422(self, admin_client):
        resp = admin_client.post(
            "/api/admin/act-as", json={"org_id": ORG, "product_slug": "igig", "nope": 1}
        )
        assert resp.status_code == 422


class TestEndAndHistory:
    def test_end_without_live_session_is_ended_false(self, admin_client):
        admin_client.mock_supabase.set_table_data("act_as_sessions", [])
        resp = admin_client.delete("/api/admin/act-as/current")
        assert resp.status_code == 200
        assert resp.json() == {"ended": False}

    def test_history_envelope_and_order(self, admin_client):
        sb = admin_client.mock_supabase
        sb.set_table_data("act_as_sessions", [{
            "id": "s-1", "superadmin_id": "admin-user-456", "target_org_id": ORG,
            "entry_product_slug": "igig", "reason": None,
            "started_at": "2026-10-06T10:00:00+00:00", "ended_at": None, "ended_by": None,
        }])
        sb.set_table_data("noctus_users", [{"id": "admin-user-456", "email": "admin@example.com"}])
        sb.set_table_data("organizations", [{"id": ORG, "nome": "Imob X"}])
        resp = admin_client.get("/api/admin/act-as/history?limit=10")
        assert resp.status_code == 200
        [item] = resp.json()["items"]
        assert item == {
            "session_id": "s-1", "superadmin_email": "admin@example.com",
            "target_org_id": ORG, "target_org_nome": "Imob X",
            "entry_product_slug": "igig", "reason": None,
            "started_at": "2026-10-06T10:00:00+00:00", "ended_at": None, "ended_by": None,
        }


class TestOrgsList:
    def test_orgs_shape_with_licensed_products(self, admin_client):
        sb = admin_client.mock_supabase
        _seed_licensed(sb)
        sb.set_table_data("noctus_users", [{"id": "u1", "email": "dono@x.com", "org_id": ORG, "org_role": "owner"}])
        resp = admin_client.get("/api/admin/orgs")
        assert resp.status_code == 200, resp.text
        [org] = resp.json()
        assert org["id"] == ORG and org["nome"] == "Imob X" and org["slug"] == "imob-x"
        assert org["owner_email"] == "dono@x.com"
        assert [p["slug"] for p in org["licensed_products"]] == ["igig"]
        assert set(org["licensed_products"][0]) == {"slug", "nome", "url_base"}

    def test_expired_license_is_not_listed(self, admin_client):
        sb = admin_client.mock_supabase
        _seed_licensed(sb)
        sb.set_table_data("licenses", [
            {"id": "l-1", "org_id": ORG, "product_id": "p-1", "status": "active", "fim": "2020-01-01T00:00:00+00:00"}
        ])
        sb.set_table_data("noctus_users", [])
        [org] = admin_client.get("/api/admin/orgs").json()
        assert org["licensed_products"] == []


class TestLogoutEndsSession:
    def test_logout_ends_live_session(self, client):
        from app.services import act_as_service  # noqa: F401
        sb = client.mock_supabase
        sb.set_table_data("act_as_sessions", [{"id": "s-1", "superadmin_id": "test-user-123", "ended_at": None}])
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 200
        updates = sb.table("act_as_sessions").updated_payloads
        assert updates and updates[-1]["ended_by"] == "logout"


class TestLifecycle:
    """start -> (replaced) -> exit -> logout, on the real service + mock DB."""

    def test_start_ends_previous_live_session_as_replaced(self, admin_client):
        sb = admin_client.mock_supabase
        _seed_licensed(sb)
        admin_client.post("/api/admin/act-as", json={"org_id": ORG, "product_slug": "igig"})
        updates = sb.table("act_as_sessions").updated_payloads
        assert updates and updates[0]["ended_by"] == "replaced"
        assert len(sb.table("act_as_sessions").inserted_payloads) == 1

    def test_exit_ends_live_session_as_exit_and_audits(self, admin_client):
        sb = admin_client.mock_supabase
        sb.set_table_data("act_as_sessions", [
            {"id": "s-1", "superadmin_id": "admin-user-456", "target_org_id": ORG, "ended_at": None}
        ])
        resp = admin_client.delete("/api/admin/act-as/current")
        assert resp.status_code == 200
        assert resp.json() == {"ended": True}
        assert sb.table("act_as_sessions").updated_payloads[-1]["ended_by"] == "exit"

    def test_invalid_ended_by_is_refused(self):
        from app.services import act_as_service

        with pytest.raises(ValueError):
            act_as_service.end_live_session("u", "timeout")
