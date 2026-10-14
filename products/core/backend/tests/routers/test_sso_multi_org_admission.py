"""Multi-org S4: SSO ADMISSION looks at every ACTIVE non-customer membership, not just the
profile (last-active) org. The real ``create_sso_token`` runs -- the minted token is decoded to
prove WHICH org admitted the user and with WHICH role. Denial reasons are unchanged."""
from __future__ import annotations

import jwt
import pytest

from app.config import settings
from noctusai_lib.api.auth import SSO_AUDIENCE, SSO_ISSUER

USER = "test-user-123"


def _seed(mock_sb, *, memberships, licensed_orgs, aceita_clientes=False, profile_org="org-1", ativo=True):
    mock_sb.set_table_data("noctus_users", {
        "id": USER, "org_id": profile_org, "role": "user", "email": "test@example.com"})
    mock_sb.set_table_data("org_memberships", [
        {"user_id": USER, "org_id": org, "org_role": role, "status": status, "updated_at": upd}
        for (org, role, status, upd) in memberships
    ])
    mock_sb.set_table_data("products", {
        "id": "prod-1", "slug": "social-wiring", "url_base": "http://localhost:8080",
        "aceita_clientes": aceita_clientes, "ativo": ativo, "deploy_scope": "live"})
    mock_sb.set_table_data("licenses", [
        {"id": f"l-{o}", "status": "active", "fim": None, "org_id": o, "product_id": "prod-1"}
        for o in licensed_orgs
    ])


def _claims(resp):
    return jwt.decode(resp.json()["sso_token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm],
                      audience=SSO_AUDIENCE, issuer=SSO_ISSUER)


class TestAdmissionViaAnyActiveMembership:
    def test_admitted_through_a_non_profile_membership_and_the_token_names_that_org(self, client):
        # profile (last-active) org-1 is NOT licensed; the user is an owner of org-2, which is
        _seed(client.mock_supabase,
              memberships=[("org-1", "viewer", "active", "2026-01-02"), ("org-2", "owner", "active", "2026-01-01")],
              licensed_orgs=["org-2"])
        resp = client.post("/api/sso/token", json={"product_slug": "social-wiring"})
        assert resp.status_code == 200, resp.text
        claims = _claims(resp)
        assert claims["org_id"] == "org-2"
        assert claims["org_role"] == "owner"  # the role IN the admitting org, not the profile's

    def test_the_profile_org_wins_when_it_is_licensed_too(self, client):
        _seed(client.mock_supabase,
              memberships=[("org-1", "member", "active", "2026-01-01"), ("org-2", "owner", "active", "2026-02-01")],
              licensed_orgs=["org-1", "org-2"])
        resp = client.post("/api/sso/token", json={"product_slug": "social-wiring"})
        assert _claims(resp)["org_id"] == "org-1"

    def test_launch_admits_the_same_way(self, client):
        _seed(client.mock_supabase,
              memberships=[("org-1", "viewer", "active", "2026-01-02"), ("org-2", "owner", "active", "2026-01-01")],
              licensed_orgs=["org-2"])
        resp = client.get("/api/sso/launch/social-wiring", follow_redirects=False)
        assert resp.status_code == 302

    def test_an_ended_or_suspended_membership_does_not_admit(self, client):
        _seed(client.mock_supabase,
              memberships=[("org-1", "viewer", "active", "2026-01-02"),
                           ("org-2", "owner", "removed", "2026-01-03"),
                           ("org-3", "owner", "suspended", "2026-01-04")],
              licensed_orgs=["org-2", "org-3"])
        resp = client.post("/api/sso/token", json={"product_slug": "social-wiring"})
        assert resp.status_code == 403
        assert resp.json()["error"]["message"] == "Organização não tem acesso a este produto"

    def test_a_customer_role_membership_never_admits_to_a_staff_only_product(self, client):
        _seed(client.mock_supabase,
              memberships=[("org-1", "viewer", "active", "2026-01-02"), ("org-2", "membro", "active", "2026-01-01")],
              licensed_orgs=["org-2"], aceita_clientes=False)
        resp = client.post("/api/sso/token", json={"product_slug": "social-wiring"})
        assert resp.status_code == 403  # org-2 is licensed but the role there is a customer's

    def test_only_customer_memberships_keeps_the_customer_refusal(self, client):
        _seed(client.mock_supabase, memberships=[("org-1", "membro", "active", "2026-01-01")],
              licensed_orgs=["org-1"], aceita_clientes=False)
        resp = client.post("/api/sso/token", json={"product_slug": "social-wiring"})
        assert resp.status_code == 403
        assert resp.json()["error"]["message"] == "Área restrita à equipe."

    def test_no_licensed_org_keeps_the_license_denial_on_both_routes(self, client):
        _seed(client.mock_supabase,
              memberships=[("org-1", "owner", "active", "2026-01-01"), ("org-2", "owner", "active", "2026-01-02")],
              licensed_orgs=[])
        tok = client.post("/api/sso/token", json={"product_slug": "social-wiring"})
        assert tok.status_code == 403
        assert tok.json()["error"]["message"] == "Organização não tem acesso a este produto"
        launch = client.get("/api/sso/launch/social-wiring", follow_redirects=False)
        assert launch.status_code == 403
        assert launch.json()["error"]["message"] == "Sem acesso a este produto"

    def test_an_inactive_product_stays_unlaunchable(self, client):
        _seed(client.mock_supabase, memberships=[("org-1", "owner", "active", "2026-01-01")],
              licensed_orgs=["org-1"], ativo=False)
        assert client.post("/api/sso/token", json={"product_slug": "social-wiring"}).status_code == 403

    def test_a_profile_without_any_membership_is_denied_never_trusted(self, client):
        _seed(client.mock_supabase, memberships=[], licensed_orgs=["org-1"])
        assert client.post("/api/sso/token", json={"product_slug": "social-wiring"}).status_code == 403

    def test_unauthenticated_is_401(self, unauth_client):
        assert unauth_client.post("/api/sso/token", json={"product_slug": "social-wiring"}).status_code == 401
