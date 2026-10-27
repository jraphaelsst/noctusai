"""Multi-org S4b -- owner decisions D2-D5 (2026-10-14) at the core router boundary.

The SQL functions (core ``member_access_rules``) are the authority for moves, blocks, the
last-owner override and the personal org; their behaviour is proven on a real Postgres in
``mcp/noctusai/tests/test_core_member_access_rules_on_replay.py``. Here: who reaches them, with
which arguments, and how refusals map -- plus SSO admission and the dashboard honouring D5.

* D2: platform staff (``noctus_users.role='admin'`` + home org ``is_platform`` + owner/admin
  there) manage ANY org's team (``?org_id=``) and may touch an ``owner`` target; everyone else
  keeps the old rules; the LAST-owner override is decided in SQL from the actor (never a flag).
* D3: ``POST /api/team/move`` -- authority/role cap/last owner in SQL, mapped strictly.
* D4: removal of a sole-org member creates a personal org and hands it to the RPC.
* D5: per-member product blocks; SSO never admits through a blocked org; the dashboard hides it.
"""
from __future__ import annotations

import jwt
from postgrest.exceptions import APIError

from app.config import settings
from noctusai_lib.api.auth import SSO_AUDIENCE, SSO_ISSUER

ADMIN = "admin-user-456"   # admin_client's user (role=admin, profile org-1)
USER = "test-user-123"     # client's user
PLATFORM = "org-platform"


def _refuse(mock_sb, code: str) -> None:
    err = APIError({"message": f"team_membership:{code}", "code": "P0001", "details": None, "hint": None})
    mock_sb.rpc = lambda name, params=None: type("R", (), {"execute": staticmethod(
        lambda: (_ for _ in ()).throw(err))})()


def _staff(mock_sb, *, staff_org_role="admin", target_role="owner"):
    """ADMIN is platform staff (home = the is_platform org); org-7 is a customer org."""
    mock_sb.set_table_data("noctus_users", [
        {"id": ADMIN, "org_id": PLATFORM, "org_role": staff_org_role, "role": "admin", "email": "s@x.com"},
        {"id": "u-target", "org_id": "org-7", "org_role": target_role, "role": "user",
         "email": "t@x.com", "nome": "Target"},
    ])
    mock_sb.set_table_data("organizations", [
        {"id": PLATFORM, "nome": "NoctusAI", "is_platform": True},
        {"id": "org-7", "nome": "Cliente", "is_platform": False},
    ])
    mock_sb.set_table_data("org_memberships", [
        {"user_id": ADMIN, "org_id": PLATFORM, "org_role": staff_org_role, "status": "active"},
        {"user_id": "u-target", "org_id": "org-7", "org_role": target_role, "status": "active"},
        {"user_id": "u-target", "org_id": "org-8", "org_role": "member", "status": "active"},
    ])


class TestD2PlatformStaffManageAnyOrg:
    def test_staff_list_another_orgs_team(self, admin_client):
        _staff(admin_client.mock_supabase)
        resp = admin_client.get("/api/team?org_id=org-7")
        assert resp.status_code == 200, resp.text
        assert [r["id"] for r in resp.json()["data"]] == ["u-target"]

    def test_staff_may_remove_an_owner_and_the_actor_rides_to_sql(self, admin_client):
        mock_sb = admin_client.mock_supabase
        _staff(mock_sb, target_role="owner")
        mock_sb.set_rpc_data("team_member_remove", {"profile_moved_to": "org-8"})
        resp = admin_client.delete("/api/team/u-target?org_id=org-7")
        assert resp.status_code == 200, resp.text
        assert mock_sb.rpc_calls == [("team_member_remove", {
            "p_org_id": "org-7", "p_user_id": "u-target", "p_actor_id": ADMIN, "p_personal_org_id": None})]

    def test_a_noctusai_admin_hitting_the_last_owner_rule_is_refused_409(self, admin_client):
        # SQL decides the override from the actor: only the NoctusAI OWNER passes it.
        mock_sb = admin_client.mock_supabase
        _staff(mock_sb, staff_org_role="admin", target_role="owner")
        _refuse(mock_sb, "last_owner")
        assert admin_client.delete("/api/team/u-target?org_id=org-7").status_code == 409

    def test_staff_may_demote_an_owner_role_change_carries_the_actor(self, admin_client):
        mock_sb = admin_client.mock_supabase
        _staff(mock_sb, staff_org_role="owner", target_role="owner")
        mock_sb.set_table_data("roles", [{"id": "r", "slug": "member"}])
        mock_sb.set_rpc_data("team_member_set_role", {"org_id": "org-7", "org_role": "member"})
        resp = admin_client.patch("/api/team/u-target/role?org_id=org-7", json={"role": "member"})
        assert resp.status_code == 200, resp.text
        assert mock_sb.rpc_calls == [("team_member_set_role", {
            "p_org_id": "org-7", "p_user_id": "u-target", "p_role": "member", "p_actor_id": ADMIN})]

    def test_staff_scope_on_an_unknown_org_is_404(self, admin_client):
        _staff(admin_client.mock_supabase)
        assert admin_client.get("/api/team?org_id=org-nope").status_code == 404

    def test_a_non_staff_superadmin_flag_outside_the_platform_org_is_not_staff(self, admin_client):
        mock_sb = admin_client.mock_supabase
        _staff(mock_sb)
        mock_sb.set_table_data("organizations", [
            {"id": PLATFORM, "nome": "NoctusAI", "is_platform": False},
            {"id": "org-7", "nome": "Cliente", "is_platform": False},
        ])
        assert admin_client.get("/api/team?org_id=org-7").status_code == 403


class TestOrgScopeForOrgAdmins:
    def _member_of(self, mock_sb, org_role):
        mock_sb.set_table_data("noctus_users", [
            {"id": USER, "org_id": "org-1", "org_role": "owner", "role": "user"},
            {"id": "u-x", "org_id": "org-2", "org_role": "member", "role": "user", "email": "x@x.com"},
        ])
        mock_sb.set_table_data("org_memberships", [
            {"user_id": USER, "org_id": "org-1", "org_role": "owner", "status": "active"},
            {"user_id": USER, "org_id": "org-2", "org_role": org_role, "status": "active"},
            {"user_id": "u-x", "org_id": "org-2", "org_role": "member", "status": "active"},
        ])

    def test_an_admin_member_of_another_org_manages_its_team(self, client):
        self._member_of(client.mock_supabase, "admin")
        assert client.get("/api/team?org_id=org-2").status_code == 200

    def test_a_plain_member_of_another_org_does_not(self, client):
        self._member_of(client.mock_supabase, "member")
        assert client.get("/api/team?org_id=org-2").status_code == 403
        assert client.delete("/api/team/u-x?org_id=org-2").status_code == 403
        assert client.mock_supabase.rpc_calls == []

    def test_a_stranger_to_the_org_does_not(self, client):
        self._member_of(client.mock_supabase, "admin")
        assert client.get("/api/team?org_id=org-9").status_code == 403


class TestD3Move:
    BODY = {"user_id": "11111111-1111-4111-8111-111111111111",
            "source_org_id": "22222222-2222-4222-8222-222222222222",
            "target_org_id": "33333333-3333-4333-8333-333333333333",
            "role": "member", "mode": "transfer"}

    def _roles(self, mock_sb):
        mock_sb.set_table_data("roles", [{"id": "r", "slug": "member"}])

    def test_move_calls_the_transactional_op_with_the_actor_and_mode(self, client):
        mock_sb = client.mock_supabase
        self._roles(mock_sb)
        mock_sb.set_rpc_data("team_member_move", {"mode": "transfer", "source_ended": True})
        for mode in ("transfer", "add"):
            mock_sb.rpc_calls.clear()
            resp = client.post("/api/team/move", json={**self.BODY, "mode": mode})
            assert resp.status_code == 200, resp.text
            assert mock_sb.rpc_calls == [("team_member_move", {
                "p_actor_id": USER, "p_user_id": self.BODY["user_id"],
                "p_source_org_id": self.BODY["source_org_id"], "p_target_org_id": self.BODY["target_org_id"],
                "p_role": "member", "p_mode": mode})]

    def test_an_org_admin_of_only_one_side_is_refused_403(self, client):
        mock_sb = client.mock_supabase
        self._roles(mock_sb)
        _refuse(mock_sb, "forbidden")
        resp = client.post("/api/team/move", json=self.BODY)
        assert resp.status_code == 403
        # The contract's machine code reaches the client (the team UI maps it to pt-BR).
        assert resp.json()["code"] == "forbidden"
        assert resp.json()["detail"] == "Você não tem permissão para gerenciar esta organização"

    def test_a_role_above_the_actor_is_refused_403(self, client):
        mock_sb = client.mock_supabase
        self._roles(mock_sb)
        _refuse(mock_sb, "role_above_actor")
        resp = client.post("/api/team/move", json=self.BODY)
        assert resp.status_code == 403
        assert resp.json()["code"] == "role_above_actor"

    def test_transfer_of_the_last_owner_is_refused_409(self, client):
        mock_sb = client.mock_supabase
        self._roles(mock_sb)
        _refuse(mock_sb, "last_owner")
        resp = client.post("/api/team/move", json=self.BODY)
        assert resp.status_code == 409
        assert resp.json()["code"] == "last_owner"

    def test_unknown_mode_is_422_and_unknown_role_is_400(self, client):
        mock_sb = client.mock_supabase
        self._roles(mock_sb)
        assert client.post("/api/team/move", json={**self.BODY, "mode": "copy"}).status_code == 422
        assert client.post("/api/team/move", json={**self.BODY, "role": "ghost"}).status_code == 400
        assert mock_sb.rpc_calls == []

    def test_unauthenticated_is_401(self, unauth_client):
        assert unauth_client.post("/api/team/move", json=self.BODY).status_code == 401


class TestD4SoleOrgRemovalKeepsTheProfile:
    def _sole(self, mock_sb):
        mock_sb.set_table_data("noctus_users", [
            {"id": ADMIN, "org_id": "org-1", "org_role": "admin", "role": "admin", "email": "a@x.com"},
            {"id": "u-solo", "org_id": "org-1", "org_role": "member", "role": "user",
             "email": "solo@x.com", "nome": "Ana Solo"},
        ])
        mock_sb.set_table_data("org_memberships", [
            {"user_id": ADMIN, "org_id": "org-1", "org_role": "admin", "status": "active"},
            {"user_id": "u-solo", "org_id": "org-1", "org_role": "member", "status": "active"},
        ])

    def test_a_personal_org_is_created_through_the_signup_path_and_handed_to_the_rpc(self, admin_client):
        mock_sb = admin_client.mock_supabase
        self._sole(mock_sb)
        mock_sb.set_rpc_data("team_member_remove", {"personal_org_id": "mock-organizations-1",
                                                    "profile_moved_to": "mock-organizations-1"})
        resp = admin_client.delete("/api/team/u-solo")
        assert resp.status_code == 200, resp.text
        org = mock_sb.table("organizations").inserted_payloads[0]
        assert (org["owner_id"], org["is_personal"], org["org_type"]) == ("u-solo", True, "individual")
        assert org["slug"].startswith("indv_ana-solo")
        assert mock_sb.rpc_calls[0][1]["p_personal_org_id"] == "mock-organizations-1"
        # S5b: the response says what happened (the personal org the profile now lives in)
        assert resp.json()["data"] == {"removed": True, "profile_moved_to": "mock-organizations-1",
                                       "personal_org_id": "mock-organizations-1"}

    def test_a_failed_removal_discards_the_unused_personal_org(self, admin_client):
        mock_sb = admin_client.mock_supabase
        self._sole(mock_sb)
        # seed the row the insert will name, so the discard is observable on the mock's data
        mock_sb.set_table_data("organizations", [{"id": "mock-organizations-1", "nome": "Pessoal — Ana Solo"}])
        _refuse(mock_sb, "last_owner")
        assert admin_client.delete("/api/team/u-solo").status_code == 409
        assert mock_sb.table("organizations").inserted_payloads  # created...
        left = mock_sb.table("organizations").select("id").eq("id", "mock-organizations-1").execute().data
        assert left == []  # ...and discarded


class TestD5ProductAccess:
    def _org(self, mock_sb, *, caller_role="admin"):
        mock_sb.set_table_data("noctus_users", [
            {"id": USER, "org_id": "org-1", "org_role": caller_role, "role": "user"},
        ])
        mock_sb.set_table_data("organizations", [{"id": "org-1", "nome": "A", "is_platform": False}])
        mock_sb.set_table_data("org_memberships", [
            {"user_id": USER, "org_id": "org-1", "org_role": caller_role, "status": "active"},
            {"user_id": "u-m", "org_id": "org-1", "org_role": "member", "status": "active"},
        ])
        mock_sb.set_table_data("licenses", [
            {"id": "l1", "org_id": "org-1", "product_id": "p-sw", "status": "active", "fim": None},
            {"id": "l2", "org_id": "org-1", "product_id": "p-ag", "status": "active", "fim": None},
        ])
        mock_sb.set_table_data("products", [
            {"id": "p-sw", "slug": "social-wiring", "nome": "Social Wiring"},
            {"id": "p-ag", "slug": "agents", "nome": "Agents"},
        ])
        mock_sb.set_table_data("org_member_product_access", [
            {"id": "b1", "user_id": "u-m", "org_id": "org-1", "product_id": "p-sw",
             "blocked_at": "2026-10-14T00:00:00Z", "blocked_by": USER, "unblocked_at": None},
        ])

    def test_an_org_admin_lists_the_members_access_per_licensed_product(self, client):
        self._org(client.mock_supabase)
        resp = client.get("/api/team/u-m/product-access")
        assert resp.status_code == 200, resp.text
        rows = {r["slug"]: r["blocked"] for r in resp.json()["data"]["products"]}
        assert rows == {"social-wiring": True, "agents": False}

    def test_a_manager_may_not_read_or_change_product_access(self, client):
        self._org(client.mock_supabase, caller_role="manager")
        assert client.get("/api/team/u-m/product-access").status_code == 403

    def test_block_calls_the_rpc_with_the_actor(self, client):
        mock_sb = client.mock_supabase
        self._org(mock_sb, caller_role="owner")
        mock_sb.set_rpc_data("org_member_product_access_set", {"blocked": True, "changed": True})
        resp = client.put("/api/team/u-m/product-access/agents", json={"blocked": True})
        assert resp.status_code == 200, resp.text
        assert mock_sb.rpc_calls == [("org_member_product_access_set", {
            "p_actor_id": USER, "p_org_id": "org-1", "p_user_id": "u-m",
            "p_product_slug": "agents", "p_blocked": True})]

    def test_sql_refusals_map_strictly(self, client):
        mock_sb = client.mock_supabase
        self._org(mock_sb, caller_role="owner")
        for code, status in (("forbidden", 403), ("not_licensed", 409), ("product_not_found", 404),
                             ("not_a_member", 404), ("cannot_block_staff", 409)):
            _refuse(mock_sb, code)
            resp = client.put("/api/team/u-m/product-access/x", json={"blocked": True})
            assert resp.status_code == status
            assert resp.json()["code"] == code

    def test_unauthenticated_is_401(self, unauth_client):
        assert unauth_client.get("/api/team/u-m/product-access").status_code == 401
        assert unauth_client.put("/api/team/u-m/product-access/agents", json={"blocked": True}).status_code == 401

    def test_the_dashboard_does_not_offer_a_blocked_product(self, client):
        mock_sb = client.mock_supabase
        self._org(mock_sb)
        mock_sb.set_table_data("noctus_users", [
            {"id": USER, "org_id": "org-1", "org_role": "member", "role": "user"}])
        mock_sb.set_table_data("products", [
            {"id": "p-sw", "slug": "social-wiring", "nome": "Social Wiring", "ativo": True, "url_base": "http://x"},
            {"id": "p-ag", "slug": "agents", "nome": "Agents", "ativo": True, "url_base": "http://y"},
        ])
        mock_sb.set_table_data("org_member_product_access", [
            {"id": "b1", "user_id": USER, "org_id": "org-1", "product_id": "p-sw", "unblocked_at": None}])
        resp = client.get("/api/auth/me")
        assert resp.status_code == 200, resp.text
        access = {p["slug"]: p["has_access"] for p in resp.json()["products"]}
        assert access == {"social-wiring": False, "agents": True}


class TestOwnerDecisionsP1P3P5:
    """Owner decisions 2026-10-14: P1 owner grants are staff-only; P3 staff are never blocked; P5
    blocks are by the org OWNER or staff only (an org admin reads, never changes). SQL (core 084)
    decides too; these pin the early Python answers + the typed codes."""

    BODY = TestD3Move.BODY

    def _p5(self, mock_sb, caller_role):
        TestD5ProductAccess()._org(mock_sb, caller_role=caller_role)

    def test_an_org_admin_reads_product_access_but_may_not_change_it(self, client):
        mock_sb = client.mock_supabase
        self._p5(mock_sb, "admin")
        data = client.get("/api/team/u-m/product-access").json()["data"]
        assert (data["can_edit"], data["target_is_staff"]) == (False, False)
        resp = client.put("/api/team/u-m/product-access/agents", json={"blocked": True})
        assert resp.status_code == 403
        assert resp.json()["code"] == "forbidden"
        resp = client.put("/api/team/u-m/product-access/social-wiring", json={"blocked": False})
        assert resp.status_code == 403
        assert mock_sb.rpc_calls == []

    def test_the_org_owner_may_change_it(self, client):
        mock_sb = client.mock_supabase
        self._p5(mock_sb, "owner")
        assert client.get("/api/team/u-m/product-access").json()["data"]["can_edit"] is True

    def test_staff_are_never_blocked_and_the_ui_is_told(self, client):
        mock_sb = client.mock_supabase
        self._p5(mock_sb, "owner")
        mock_sb.set_table_data("noctus_users", [
            {"id": USER, "org_id": "org-1", "org_role": "owner", "role": "user"},
            {"id": ADMIN, "org_id": PLATFORM, "org_role": "admin", "role": "admin"},
        ])
        mock_sb.set_table_data("organizations", [
            {"id": "org-1", "nome": "A", "is_platform": False},
            {"id": PLATFORM, "nome": "NoctusAI", "is_platform": True},
        ])
        mock_sb.set_table_data("org_memberships", [
            {"user_id": USER, "org_id": "org-1", "org_role": "owner", "status": "active"},
            {"user_id": ADMIN, "org_id": "org-1", "org_role": "member", "status": "active"},
        ])
        assert client.get(f"/api/team/{ADMIN}/product-access").json()["data"]["target_is_staff"] is True
        resp = client.put(f"/api/team/{ADMIN}/product-access/agents", json={"blocked": True})
        assert resp.status_code == 409
        assert resp.json()["code"] == "cannot_block_staff"
        assert mock_sb.rpc_calls == []

    def test_an_org_owner_may_not_grant_owner_by_role_change(self, client):
        mock_sb = client.mock_supabase
        TestOrgScopeForOrgAdmins()._member_of(mock_sb, "owner")
        mock_sb.set_table_data("roles", [{"id": "r", "slug": "owner"}])
        resp = client.patch("/api/team/u-x/role?org_id=org-2", json={"role": "owner"})
        assert resp.status_code == 403
        assert resp.json()["code"] == "owner_grant_forbidden"
        assert mock_sb.rpc_calls == []

    def test_staff_may_grant_owner_by_role_change(self, admin_client):
        mock_sb = admin_client.mock_supabase
        _staff(mock_sb, target_role="member")
        mock_sb.set_table_data("roles", [{"id": "r", "slug": "owner"}])
        mock_sb.set_rpc_data("team_member_set_role", {"org_id": "org-7", "org_role": "owner"})
        resp = admin_client.patch("/api/team/u-target/role?org_id=org-7", json={"role": "owner"})
        assert resp.status_code == 200, resp.text
        assert mock_sb.rpc_calls == [("team_member_set_role", {
            "p_org_id": "org-7", "p_user_id": "u-target", "p_role": "owner", "p_actor_id": ADMIN})]

    def test_an_org_owner_may_not_move_someone_in_as_owner(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("roles", [{"id": "r", "slug": "owner"}])
        resp = client.post("/api/team/move", json={**self.BODY, "role": "owner"})
        assert resp.status_code == 403
        assert resp.json()["code"] == "owner_grant_forbidden"
        assert mock_sb.rpc_calls == []

    def test_staff_may_move_someone_in_as_owner(self, admin_client):
        mock_sb = admin_client.mock_supabase
        _staff(mock_sb)
        mock_sb.set_table_data("roles", [{"id": "r", "slug": "owner"}])
        mock_sb.set_rpc_data("team_member_move", {"org_role": "owner"})
        resp = admin_client.post("/api/team/move", json={**self.BODY, "role": "owner"})
        assert resp.status_code == 200, resp.text
        assert mock_sb.rpc_calls[0][1]["p_role"] == "owner"

    def test_the_sql_owner_grant_refusal_maps_to_403(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("roles", [{"id": "r", "slug": "member"}])
        _refuse(mock_sb, "owner_grant_forbidden")
        resp = client.post("/api/team/move", json=self.BODY)
        assert resp.status_code == 403
        assert resp.json()["code"] == "owner_grant_forbidden"


class TestD5SsoNeverAdmitsThroughABlockedOrg:
    def _seed(self, mock_sb, blocks):
        mock_sb.set_table_data("noctus_users", {"id": USER, "org_id": "org-1", "role": "user", "email": "test@example.com"})
        mock_sb.set_table_data("org_memberships", [
            {"user_id": USER, "org_id": "org-1", "org_role": "member", "status": "active", "updated_at": "2026-01-02"},
            {"user_id": USER, "org_id": "org-2", "org_role": "owner", "status": "active", "updated_at": "2026-01-01"},
        ])
        mock_sb.set_table_data("products", {
            "id": "prod-1", "slug": "social-wiring", "url_base": "http://localhost:8080",
            "aceita_clientes": False, "ativo": True, "deploy_scope": "live"})
        mock_sb.set_table_data("licenses", [
            {"id": f"l-{o}", "status": "active", "fim": None, "org_id": o, "product_id": "prod-1"}
            for o in ("org-1", "org-2")])
        mock_sb.set_table_data("org_member_product_access", [
            {"id": f"b-{o}", "user_id": USER, "org_id": o, "product_id": "prod-1", "unblocked_at": None}
            for o in blocks])

    def test_a_blocked_profile_org_is_skipped_for_another_licensed_membership(self, client):
        self._seed(client.mock_supabase, blocks=["org-1"])
        resp = client.post("/api/sso/token", json={"product_slug": "social-wiring"})
        assert resp.status_code == 200, resp.text
        claims = jwt.decode(resp.json()["sso_token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm],
                            audience=SSO_AUDIENCE, issuer=SSO_ISSUER)
        assert (claims["org_id"], claims["org_role"]) == ("org-2", "owner")

    def test_blocked_in_every_licensed_org_is_denied(self, client):
        self._seed(client.mock_supabase, blocks=["org-1", "org-2"])
        assert client.post("/api/sso/token", json={"product_slug": "social-wiring"}).status_code == 403
        assert client.get("/api/sso/launch/social-wiring", follow_redirects=False).status_code == 403


class TestDashboardAdmitsLikeSso:
    """S4: the dashboard's has_access is the SSO admission rule -- a product licensed only to one
    of the user's OTHER active orgs is open (2026-10-27: a multi-org owner saw the card locked
    while /api/sso/token would have admitted her through her own org)."""

    def _seed(self, mock_sb, *, other_role="owner", blocks=()):
        mock_sb.set_table_data("noctus_users", {"id": USER, "org_id": "org-1", "org_role": "admin",
                                                 "role": "user", "email": "test@example.com"})
        mock_sb.set_table_data("organizations", {"id": "org-1", "nome": "Home"})
        mock_sb.set_table_data("org_memberships", [
            {"user_id": USER, "org_id": "org-1", "org_role": "admin", "status": "active", "updated_at": "2026-01-02"},
            {"user_id": USER, "org_id": "org-2", "org_role": other_role, "status": "active", "updated_at": "2026-01-01"},
        ])
        mock_sb.set_table_data("products", [{
            "id": "p-mo", "slug": "monica", "nome": "Monica", "url_base": "http://localhost:8080",
            "aceita_clientes": False, "ativo": True, "deploy_scope": "live"}])
        mock_sb.set_table_data("licenses", [
            {"id": "l-2", "status": "active", "fim": None, "org_id": "org-2", "product_id": "p-mo"}])
        mock_sb.set_table_data("org_member_product_access", [
            {"id": f"b-{o}", "user_id": USER, "org_id": o, "product_id": "p-mo", "unblocked_at": None}
            for o in blocks])

    def _has_access(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 200, resp.text
        return {p["slug"]: p["has_access"] for p in resp.json()["products"]}["monica"]

    def test_a_product_licensed_only_to_another_membership_org_is_open(self, client):
        self._seed(client.mock_supabase)
        assert self._has_access(client) is True
        assert client.post("/api/sso/token", json={"product_slug": "monica"}).status_code == 200

    def test_blocked_in_the_only_licensed_org_is_locked(self, client):
        self._seed(client.mock_supabase, blocks=["org-2"])
        assert self._has_access(client) is False
        assert client.post("/api/sso/token", json={"product_slug": "monica"}).status_code == 403

    def test_a_customer_role_in_the_licensed_org_is_locked(self, client):
        self._seed(client.mock_supabase, other_role="membro")
        assert self._has_access(client) is False
        assert client.post("/api/sso/token", json={"product_slug": "monica"}).status_code == 403

    def test_unauthenticated_is_401(self, unauth_client):
        assert unauth_client.get("/api/auth/me").status_code == 401
