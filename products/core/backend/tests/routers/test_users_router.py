"""
Tests for Admin Users Router.

GET    /api/admin/users
GET    /api/admin/users/{user_id}
PATCH  /api/admin/users/{user_id}
DELETE /api/admin/users/{user_id}
"""
import pytest
from datetime import date, timedelta
from noctusai_lib.testing import handler_status

today = date.today().isoformat()
yesterday = (date.today() - timedelta(days=1)).isoformat()

ORG_A = "11111111-1111-4111-8111-111111111111"
ORG_B = "22222222-2222-4222-8222-222222222222"

# 🔴 PARITY: mirrors `ORG_ROLES` in `seed/lib/frontend/src/roles.ts` — the
# dropdown the admin panel renders. Every one of these must PATCH cleanly.
ORG_ROLES = ["owner", "admin", "manager", "member", "viewer", "dev", "test", "corretor", "juridico"]

SAMPLE_USERS = [
    {
        "id": "user-1",
        "email": "alice@example.com",
        "nome": "Alice Silva",
        "org_id": "org-1",
        "role": "user",
        "org_role": "member",
        "created_at": yesterday,
    },
    {
        "id": "user-2",
        "email": "bob@example.com",
        "nome": "Bob Santos",
        "org_id": "org-1",
        "role": "admin",
        "org_role": "owner",
        "created_at": today,
    },
]


# ---------------------------------------------------------------------------
# GET /api/admin/users
# ---------------------------------------------------------------------------

class TestListUsers:
    def test_list_users_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", SAMPLE_USERS)

        resp = admin_client.get("/api/admin/users")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["data"], list)
        assert "pagination" in body
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["page_size"] == 20

    def test_list_users_attaches_organization(self, admin_client):
        """The FE's "Org" column reads `u.organization.nome`. Before the join
        the list never carried `organization`, so the column rendered "—" for
        every row — org membership was invisible where an admin goes to see it."""
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", SAMPLE_USERS)
        mock_sb.set_table_data("organizations", [
            {"id": "org-1", "nome": "NoctusAI", "slug": "noctusai", "plano": "enterprise"},
        ])

        resp = admin_client.get("/api/admin/users")
        assert resp.status_code == 200
        rows = resp.json()["data"]
        assert rows, "expected the sample users back"
        assert all(r["organization"]["nome"] == "NoctusAI" for r in rows)

    def test_list_users_organization_is_none_when_orgless(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", [
            {**SAMPLE_USERS[0], "org_id": None},
        ])
        mock_sb.set_table_data("organizations", [])

        resp = admin_client.get("/api/admin/users")
        assert resp.status_code == 200
        assert resp.json()["data"][0]["organization"] is None

    def test_list_users_with_search(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", SAMPLE_USERS)

        resp = admin_client.get("/api/admin/users?busca=alice")
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    def test_list_users_with_role_filter(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", [SAMPLE_USERS[1]])

        resp = admin_client.get("/api/admin/users?role=admin")
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    def test_list_users_pagination(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", SAMPLE_USERS)

        resp = admin_client.get("/api/admin/users?page=2&page_size=1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["page"] == 2
        assert body["pagination"]["page_size"] == 1

    def test_list_users_forbidden_for_non_admin(self, client):
        resp = client.get("/api/admin/users")
        assert resp.status_code == 403

    def test_list_users_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/admin/users")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/admin/users/{user_id}
# ---------------------------------------------------------------------------

class TestGetUser:
    def test_get_user_success(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "user-1",
            "email": "alice@example.com",
            "nome": "Alice Silva",
            "org_id": "org-1",
            "role": "user",
            "org_role": "member",
            "created_at": today,
        })
        mock_sb.set_table_data("organizations", {
            "id": "org-1",
            "nome": "Test Corp",
            "slug": "test-corp",
            "plano": "pro",
        })

        resp = admin_client.get("/api/admin/users/user-1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "user-1"
        assert data["organization"]["id"] == "org-1"

    def test_get_user_without_org(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "user-no-org",
            "email": "orphan@example.com",
            "nome": "Orphan User",
            "org_id": None,
            "role": "user",
            "org_role": "member",
            "created_at": today,
        })

        resp = admin_client.get("/api/admin/users/user-no-org")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["organization"] is None

    def test_get_user_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = admin_client.get("/api/admin/users/nonexistent")
        assert resp.status_code == 404

    def test_get_user_forbidden_for_non_admin(self, client):
        resp = client.get("/api/admin/users/user-1")
        assert resp.status_code == 403

    def test_get_user_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/admin/users/user-1")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/admin/users/{user_id}
# ---------------------------------------------------------------------------

class TestUpdateUser:
    def test_update_user_role(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            # First call: pre-check (select id)
            {"id": "user-1"},
            # Second call: update result
            [{"id": "user-1", "role": "admin", "nome": "Alice Silva", "email": "alice@example.com"}],
        ])

        resp = admin_client.patch("/api/admin/users/user-1", json={"role": "admin"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "admin"

    def test_update_user_nome(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            {"id": "user-1"},
            [{"id": "user-1", "nome": "Alice Updated", "role": "user", "email": "alice@example.com"}],
        ])

        resp = admin_client.patch("/api/admin/users/user-1", json={"nome": "Alice Updated"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["nome"] == "Alice Updated"

    def test_update_user_org_role(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            {"id": "user-1"},
            [{"id": "user-1", "org_role": "admin", "nome": "Alice Silva", "email": "alice@example.com"}],
        ])

        resp = admin_client.patch("/api/admin/users/user-1", json={"org_role": "admin"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["org_role"] == "admin"

    def test_update_user_empty_body(self, admin_client):
        resp = admin_client.patch("/api/admin/users/user-1", json={})
        assert resp.status_code == 400

    def test_update_user_invalid_role(self, admin_client):
        resp = admin_client.patch("/api/admin/users/user-1", json={"role": "superadmin"})
        assert resp.status_code == 422

    def test_update_user_invalid_org_role(self, admin_client):
        resp = admin_client.patch("/api/admin/users/user-1", json={"org_role": "supreme"})
        assert resp.status_code == 422

    def test_update_user_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = admin_client.patch("/api/admin/users/nonexistent", json={"nome": "X"})
        assert resp.status_code == 404

    def test_update_user_forbidden_for_non_admin(self, client):
        resp = client.patch("/api/admin/users/user-1", json={"role": "admin"})
        assert resp.status_code == 403

    def test_update_user_unauthenticated(self, unauth_client):
        resp = unauth_client.patch("/api/admin/users/user-1", json={"role": "admin"})
        assert resp.status_code == 401

    @pytest.mark.parametrize("org_role", ORG_ROLES)
    def test_update_accepts_every_canonical_org_role(self, admin_client, org_role):
        """The 7-role hierarchy in `seed/lib/frontend/src/roles.ts` is what the
        admin panel's dropdown renders — the schema must accept all of it. The
        prior `^(owner|admin|member)$` 422'd on the other four."""
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            {"id": "user-1", "org_id": ORG_A, "org_role": "member"},
            [{"id": "user-1", "org_role": org_role}],
        ])

        resp = admin_client.patch("/api/admin/users/user-1", json={"org_role": org_role})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# PATCH /api/admin/users/{user_id} — org assign / revoke
# ---------------------------------------------------------------------------

class TestReassignUserOrg:
    def test_reassign_moves_user_to_target_org(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            {"id": "user-1", "org_id": ORG_A, "org_role": "member"},
            [{"id": "user-1", "org_id": ORG_B, "org_role": "member"}],
        ])
        mock_sb.set_table_responses("organizations", [
            {"id": ORG_B, "nome": "Target Org", "owner_id": "someone-else"},   # target
            {"id": ORG_A, "nome": "Source Org", "owner_id": "someone-else"},   # source
        ])

        resp = admin_client.patch(f"/api/admin/users/user-1", json={"org_id": ORG_B})
        assert resp.status_code == 200
        assert resp.json()["data"]["org_id"] == ORG_B

    def test_reassign_with_org_role_in_same_request(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            {"id": "user-1", "org_id": ORG_A, "org_role": "owner"},
            [{"id": "user-1", "org_id": ORG_B, "org_role": "admin"}],
        ])
        mock_sb.set_table_responses("organizations", [
            {"id": ORG_B, "nome": "Target Org", "owner_id": "someone-else"},
            {"id": ORG_A, "nome": "Source Org", "owner_id": "someone-else"},
        ])

        resp = admin_client.patch(
            "/api/admin/users/user-1", json={"org_id": ORG_B, "org_role": "admin"}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["org_role"] == "admin"

    def test_reassign_to_unknown_org_is_404(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            {"id": "user-1", "org_id": ORG_A, "org_role": "member"},
        ])
        mock_sb.set_table_responses("organizations", [[]])  # target lookup: no rows

        resp = admin_client.patch("/api/admin/users/user-1", json={"org_id": ORG_B})
        assert resp.status_code == 404

    def test_reassign_refuses_to_orphan_the_source_org(self, admin_client):
        """Moving an org's `owner_id` out would leave the org owned by a
        non-member who can no longer administer it."""
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            {"id": "user-1", "org_id": ORG_A, "org_role": "owner"},
        ])
        mock_sb.set_table_responses("organizations", [
            {"id": ORG_B, "nome": "Target Org", "owner_id": None},
            {"id": ORG_A, "nome": "Source Org", "owner_id": "user-1"},  # user OWNS source
        ])

        resp = admin_client.patch("/api/admin/users/user-1", json={"org_id": ORG_B})
        assert resp.status_code == 409
        assert "proprietário" in resp.json()["error"]["message"]

    def test_reassign_refuses_second_owner_in_target_org(self, admin_client):
        """Landing as `owner` in an org that already has a different `owner_id`
        would leave two tables disagreeing about who owns the tenant."""
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            {"id": "user-1", "org_id": ORG_A, "org_role": "owner"},
        ])
        mock_sb.set_table_responses("organizations", [
            {"id": ORG_B, "nome": "Target Org", "owner_id": "other-owner"},
            {"id": ORG_A, "nome": "Source Org", "owner_id": "someone-else"},
        ])

        # org_role carries over from the profile ("owner") when unspecified.
        resp = admin_client.patch("/api/admin/users/user-1", json={"org_id": ORG_B})
        assert resp.status_code == 409
        assert "proprietário" in resp.json()["error"]["message"]

    def test_same_org_is_a_plain_update_not_a_move(self, admin_client):
        """Re-submitting the edit form unchanged must not trip the move guards."""
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            {"id": "user-1", "org_id": ORG_A, "org_role": "owner"},
            [{"id": "user-1", "org_id": ORG_A, "nome": "Alice Updated"}],
        ])
        # Owns the org — would 409 if this were treated as a move.
        mock_sb.set_table_responses("organizations", [
            {"id": ORG_A, "nome": "Source Org", "owner_id": "user-1"},
        ])

        resp = admin_client.patch(
            "/api/admin/users/user-1", json={"org_id": ORG_A, "nome": "Alice Updated"}
        )
        assert resp.status_code == 200

    def test_reassign_rejects_malformed_org_id(self, admin_client):
        resp = admin_client.patch("/api/admin/users/user-1", json={"org_id": "not-a-uuid"})
        assert resp.status_code == 422

    def test_reassign_forbidden_for_non_admin(self, client):
        resp = client.patch("/api/admin/users/user-1", json={"org_id": ORG_B})
        assert resp.status_code == 403

    def test_reassign_also_syncs_the_org_onto_the_auth_token(self, admin_client):
        """🔴 A reassignment is TWO writes and half of it is invisible.

        `noctus_users.org_id` is what RLS resolves through, but product
        backends read the org off the JWT, populated from `user_metadata`.
        Writing only the table moves the user for the database and leaves
        every product serving them their OLD org — a correct-looking account
        with an empty board. That shipped (2026-09-02) and is why this exists.
        """
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            {"id": "user-1", "org_id": ORG_A, "org_role": "member"},
            [{"id": "user-1", "org_id": ORG_B}],
        ])
        mock_sb.set_table_responses("organizations", [
            {"id": ORG_B, "nome": "Target Org", "owner_id": "someone-else"},
            {"id": ORG_A, "nome": "Source Org", "owner_id": "someone-else"},
        ])

        resp = admin_client.patch("/api/admin/users/user-1", json={"org_id": ORG_B})
        assert resp.status_code == 200

        mock_sb.auth.admin.update_user_by_id.assert_called_once_with(
            "user-1", {"user_metadata": {"org_id": ORG_B}}
        )

    def test_a_failed_sync_502s_before_anything_moves(self, admin_client):
        """Unlike signup's best-effort sync, a failure HERE is the split-brain
        being prevented — the metadata sync runs FIRST, so a failure is a 502
        with nothing changed (no membership move, no profile write)."""
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            {"id": "user-1", "org_id": ORG_A, "org_role": "member"},
        ])
        mock_sb.set_table_responses("organizations", [
            {"id": ORG_B, "nome": "Target Org", "owner_id": "someone-else"},
            {"id": ORG_A, "nome": "Source Org", "owner_id": "someone-else"},
        ])
        mock_sb.auth.admin.update_user_by_id.side_effect = RuntimeError("auth down")

        resp = admin_client.patch("/api/admin/users/user-1", json={"org_id": ORG_B})

        assert handler_status(resp) == 502
        assert mock_sb.rpc_calls == []
        assert mock_sb.table("noctus_users").updated_payloads == []

    def test_reassign_is_a_transfer_through_the_membership_move_op(self, admin_client):
        """D3 (owner, 2026-10-14): the old membership ENDS (it used to stay ACTIVE) -- the
        reassignment is the same SQL op every move uses, with the admin as the actor."""
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            {"id": "user-1", "org_id": ORG_A, "org_role": "member"},
            [{"id": "user-1", "org_id": ORG_B, "org_role": "member"}],
        ])
        mock_sb.set_table_responses("organizations", [
            {"id": ORG_B, "nome": "Target Org", "owner_id": "someone-else"},
            {"id": ORG_A, "nome": "Source Org", "owner_id": "someone-else"},
        ])
        mock_sb.set_rpc_data("team_member_move", {"mode": "transfer", "source_ended": True})

        resp = admin_client.patch("/api/admin/users/user-1", json={"org_id": ORG_B})

        assert resp.status_code == 200, resp.text
        assert mock_sb.rpc_calls == [("team_member_move", {
            "p_actor_id": "admin-user-456", "p_user_id": "user-1", "p_source_org_id": ORG_A,
            "p_target_org_id": ORG_B, "p_role": "member", "p_mode": "transfer"})]
        # the profile is moved by the op, never by a PostgREST write here
        assert mock_sb.table("noctus_users").updated_payloads == []

    def test_a_refused_move_restores_the_metadata_and_keeps_the_refusal_status(self, admin_client):
        from postgrest.exceptions import APIError

        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("noctus_users", [
            {"id": "user-1", "org_id": ORG_A, "org_role": "owner"},
        ])
        mock_sb.set_table_responses("organizations", [
            {"id": ORG_B, "nome": "Target Org", "owner_id": None},
            {"id": ORG_A, "nome": "Source Org", "owner_id": "someone-else"},
        ])
        err = APIError({"message": "team_membership:last_owner", "code": "P0001", "details": None, "hint": None})
        mock_sb.rpc = lambda name, params=None: type("R", (), {"execute": staticmethod(
            lambda: (_ for _ in ()).throw(err))})()

        resp = admin_client.patch("/api/admin/users/user-1", json={"org_id": ORG_B})

        assert resp.status_code == 409
        calls = mock_sb.auth.admin.update_user_by_id.call_args_list
        assert [c.args[1]["user_metadata"]["org_id"] for c in calls] == [ORG_B, ORG_A]


# ---------------------------------------------------------------------------
# DELETE /api/admin/users/{user_id}
# ---------------------------------------------------------------------------

class TestDeleteUser:
    def test_delete_user_success(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"id": "user-1"})

        resp = admin_client.delete("/api/admin/users/user-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert "excluído" in body["message"]

    def test_delete_user_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = admin_client.delete("/api/admin/users/nonexistent")
        assert resp.status_code == 404

    def test_delete_user_forbidden_for_non_admin(self, client):
        resp = client.delete("/api/admin/users/user-1")
        assert resp.status_code == 403

    def test_delete_user_unauthenticated(self, unauth_client):
        resp = unauth_client.delete("/api/admin/users/user-1")
        assert resp.status_code == 401
