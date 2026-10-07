"""SEC-1 (2026-09-28) — the seed `team` router trusts `public.noctus_users`,
never `user_metadata`.

`user_metadata` is writable by the user themselves (`supabase.auth.updateUser
({data})`), and every `/api/team` route acts through the SERVICE-ROLE client,
so before this fix:

- `GET /api/team` listed the roster of whatever org `user_metadata.org_id`
  named — any user could read any tenant's members;
- `POST /api/team/invite` gated on `user_metadata.role` and wrote the invite
  into `user_metadata.org_id` with ANY body `role` — invite yourself as owner
  of any org;
- `DELETE /api/team/{id}` gated on `user_metadata.role` and deleted
  `noctus_users` by id with NO org filter — delete any user platform-wide
  (since 2026-10-01 the route never deletes at all: 409, Core-only).

Every test here spoofs the metadata the way an attacker would
(`role=admin`, `org_id=<victim org>`) and asserts a strict status code. The
DB rows are REAL rows in the seed's `MockSupabaseClient`; the only mocked seam
is `deps.get_current_user` — the external GoTrue boundary.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.testing.mocks import MockSupabaseClient
from noctusai_seed.routers import _create_team_router

MY_ORG = "org-mine"
VICTIM_ORG = "org-victim"
AUTH = {"Authorization": "Bearer t"}

#: What an attacker writes into their own metadata via auth.updateUser({data}).
SPOOFED_METADATA = {"role": "admin", "org_role": "owner", "org_id": VICTIM_ORG}


def _user(user_id: str, *, metadata: dict | None = None, email: str = "x@test.com"):
    return SimpleNamespace(id=user_id, email=email, user_metadata=metadata or {})


def _row(user_id: str, org_id: str | None, org_role: str, role: str = "user") -> dict:
    return {
        "id": user_id,
        "email": f"{user_id}@test.com",
        "nome": user_id,
        "org_id": org_id,
        "org_role": org_role,
        "role": role,
    }


ROSTER = [
    _row("me-member", MY_ORG, "member"),
    _row("me-manager", MY_ORG, "manager"),
    _row("me-admin", MY_ORG, "admin"),
    _row("me-owner", MY_ORG, "owner"),
    _row("mate", MY_ORG, "member"),
    _row("co-owner", MY_ORG, "owner"),
    _row("victim-owner", VICTIM_ORG, "owner"),
    _row("victim-member", VICTIM_ORG, "member"),
    _row("operator", MY_ORG, "member", role="admin"),
]


@pytest.fixture
def world(fake_deps, fake_settings, product_name):
    product_db = MockSupabaseClient(validate_schema=False, schema="test")
    product_db.set_table_data("invitations", [])
    core_db = MockSupabaseClient(validate_schema=False, schema="public")
    core_db.set_table_data("noctus_users", [dict(r) for r in ROSTER])
    core_db.set_table_data(
        "organizations",
        [{"id": MY_ORG, "nome": "Minha Org"}, {"id": VICTIM_ORG, "nome": "Vitima"}],
    )
    fake_deps.get_admin_client = MagicMock(return_value=product_db)
    fake_deps.get_core_client = MagicMock(return_value=core_db)
    # The seed conftest's metadata-backed stand-ins must be UNUSED by the team
    # router now — make them loud if anything still reaches for them.
    fake_deps.get_org_id = MagicMock(side_effect=AssertionError("get_org_id is untrusted"))
    fake_deps.get_user_role = MagicMock(side_effect=AssertionError("get_user_role unused"))

    app = FastAPI()
    app.include_router(_create_team_router(fake_deps, fake_settings, product_name))

    def as_user(user_id: str, *, metadata: dict | None = None, email: str = "x@test.com"):
        fake_deps.get_current_user = AsyncMock(
            return_value=(_user(user_id, metadata=metadata, email=email), "tok")
        )
        # /accept resolves the caller through the license-UNGATED seam.
        fake_deps.get_current_user_ungated = fake_deps.get_current_user
        return TestClient(app)

    return SimpleNamespace(as_user=as_user, core=core_db, product=product_db)


def _ids(core, org_id=None):
    rows = core.table("noctus_users")._data
    return {r["id"] for r in rows if org_id is None or r.get("org_id") == org_id}


# ── GET /api/team ──────────────────────────────────────────────────────────


class TestListMembers:
    def test_spoofed_org_id_still_lists_only_the_trusted_org(self, world):
        client = world.as_user("me-member", metadata=SPOOFED_METADATA)
        resp = client.get("/api/team", headers=AUTH)
        assert resp.status_code == 200, resp.text
        listed = {r["id"] for r in resp.json()["data"]}
        assert listed == _ids(world.core, MY_ORG)
        assert "victim-owner" not in listed

    def test_caller_without_membership_row_gets_403_even_with_metadata_org(self, world):
        client = world.as_user("stranger", metadata=SPOOFED_METADATA)
        resp = client.get("/api/team", headers=AUTH)
        assert resp.status_code == 403, resp.text

    def test_unauthenticated_gets_401(self, world, fake_deps):
        from fastapi import HTTPException

        client = world.as_user("me-member")
        fake_deps.get_current_user = AsyncMock(
            side_effect=HTTPException(status_code=401, detail="Token ausente")
        )
        resp = client.get("/api/team")
        assert resp.status_code == 401, resp.text


# ── POST /api/team/invite ──────────────────────────────────────────────────


class TestInvite:
    def test_member_with_spoofed_admin_metadata_gets_403(self, world):
        client = world.as_user("me-member", metadata=SPOOFED_METADATA)
        resp = client.post(
            "/api/team/invite", json={"email": "a@evil.com", "role": "owner"}, headers=AUTH
        )
        assert resp.status_code == 403, resp.text
        assert world.product.table("invitations").inserted_payloads == []

    def test_invite_lands_in_the_trusted_org_not_the_metadata_org(self, world):
        client = world.as_user("me-owner", metadata=SPOOFED_METADATA)
        resp = client.post(
            "/api/team/invite", json={"email": "new@test.com", "role": "member"}, headers=AUTH
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["org_id"] == MY_ORG

    def test_admin_cannot_invite_an_owner(self, world):
        client = world.as_user("me-admin")
        resp = client.post(
            "/api/team/invite", json={"email": "o@test.com", "role": "owner"}, headers=AUTH
        )
        assert resp.status_code == 403, resp.text
        assert world.product.table("invitations").inserted_payloads == []

    def test_manager_cannot_invite_an_admin(self, world):
        client = world.as_user("me-manager")
        resp = client.post(
            "/api/team/invite", json={"email": "a@test.com", "role": "admin"}, headers=AUTH
        )
        assert resp.status_code == 403, resp.text

    def test_manager_can_invite_a_member(self, world):
        client = world.as_user("me-manager")
        resp = client.post(
            "/api/team/invite", json={"email": "m@test.com", "role": "member"}, headers=AUTH
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["role"] == "member"

    def test_owner_can_invite_an_owner(self, world):
        client = world.as_user("me-owner")
        resp = client.post(
            "/api/team/invite", json={"email": "o2@test.com", "role": "owner"}, headers=AUTH
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["role"] == "owner"

    def test_unknown_role_is_rejected_400(self, world):
        client = world.as_user("me-owner")
        resp = client.post(
            "/api/team/invite", json={"email": "x@test.com", "role": "superuser"}, headers=AUTH
        )
        assert resp.status_code == 400, resp.text

    def test_missing_email_is_400_not_500(self, world):
        client = world.as_user("me-owner")
        resp = client.post("/api/team/invite", json={"role": "member"}, headers=AUTH)
        assert resp.status_code == 400, resp.text

    def test_platform_operator_can_invite_within_own_org_only(self, world):
        client = world.as_user("operator", metadata=SPOOFED_METADATA)
        resp = client.post(
            "/api/team/invite", json={"email": "p@test.com", "role": "admin"}, headers=AUTH
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["org_id"] == MY_ORG


# ── GET/DELETE /api/team/invitations ───────────────────────────────────────


class TestInvitations:
    def test_member_with_spoofed_metadata_cannot_list(self, world):
        client = world.as_user("me-member", metadata=SPOOFED_METADATA)
        resp = client.get("/api/team/invitations", headers=AUTH)
        assert resp.status_code == 403, resp.text

    def test_member_with_spoofed_metadata_cannot_cancel(self, world):
        world.product.set_table_data(
            "invitations",
            [{"id": "inv-v", "org_id": VICTIM_ORG, "email": "e@test.com",
              "status": "pending", "token": "t", "role": "member"}],
        )
        client = world.as_user("me-member", metadata=SPOOFED_METADATA)
        resp = client.delete("/api/team/invitations/inv-v", headers=AUTH)
        assert resp.status_code == 403, resp.text
        assert world.product.table("invitations").updated_payloads == []

    def test_admin_lists_only_own_org_invitations(self, world):
        world.product.set_table_data(
            "invitations",
            [
                {"id": "inv-mine", "org_id": MY_ORG, "email": "a@test.com",
                 "status": "pending", "token": "t1", "role": "member",
                 "created_at": "2026-09-01T00:00:00+00:00"},
                {"id": "inv-theirs", "org_id": VICTIM_ORG, "email": "b@test.com",
                 "status": "pending", "token": "t2", "role": "member",
                 "created_at": "2026-09-01T00:00:00+00:00"},
            ],
        )
        client = world.as_user("me-admin", metadata=SPOOFED_METADATA)
        resp = client.get("/api/team/invitations", headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert [r["id"] for r in resp.json()["data"]] == ["inv-mine"]


# ── DELETE /api/team/{user_id} ─────────────────────────────────────────────


class TestRemoveMember:
    """2026-10-01: removal is a NoctusAI Core action. `noctus_users` is one
    platform-wide profile; a product-side delete wiped the person from every
    product sharing the org. The route stays (Equipe pages call it) and
    answers 409 `TEAM_REMOVE_CORE_ONLY` — never deleting anything."""

    def test_member_with_spoofed_admin_metadata_gets_403(self, world):
        client = world.as_user("me-member", metadata=SPOOFED_METADATA)
        resp = client.delete("/api/team/mate", headers=AUTH)
        assert resp.status_code == 403, resp.text
        assert "mate" in _ids(world.core)

    def test_admin_gets_409_core_only_and_nothing_is_deleted(self, world):
        client = world.as_user("me-admin")
        resp = client.delete("/api/team/mate", headers=AUTH)
        assert resp.status_code == 409, resp.text
        # Bare FastAPI app here (no seed exception handler) ⇒ nested under
        # `detail`; the flat wire shape through `create_product_app`'s
        # handler is pinned in test_team_policy.py.
        assert resp.json()["detail"] == {
            "detail": (
                "A remoção de pessoas da organização é feita no NoctusAI Core "
                "(afeta todos os produtos)."
            ),
            "code": "TEAM_REMOVE_CORE_ONLY",
        }
        assert "mate" in _ids(world.core)

    def test_owner_removing_a_co_owner_gets_409_and_nothing_is_deleted(self, world):
        client = world.as_user("me-owner")
        resp = client.delete("/api/team/co-owner", headers=AUTH)
        assert resp.status_code == 409, resp.text
        assert "co-owner" in _ids(world.core)

    def test_admin_targeting_another_org_gets_409_and_nothing_is_deleted(self, world):
        client = world.as_user("me-admin", metadata=SPOOFED_METADATA)
        resp = client.delete("/api/team/victim-member", headers=AUTH)
        assert resp.status_code == 409, resp.text
        assert "victim-member" in _ids(world.core)

    def test_unauthenticated_gets_401(self, world, fake_deps):
        from fastapi import HTTPException

        client = world.as_user("me-admin")
        fake_deps.get_current_user = AsyncMock(
            side_effect=HTTPException(status_code=401, detail="Token ausente")
        )
        resp = client.delete("/api/team/mate")
        assert resp.status_code == 401, resp.text


# ── POST /api/team/accept (authenticated) ──────────────────────────────────


class TestAuthenticatedAcceptMustBeTheInvitee:
    def test_signed_in_user_with_a_different_email_gets_403(self, world):
        world.product.set_table_data(
            "invitations",
            [{"id": "inv-x", "org_id": MY_ORG, "email": "invitee@test.com",
              "status": "pending", "token": "leaked", "role": "admin",
              "expires_at": "2999-01-01T00:00:00+00:00"}],
        )
        client = world.as_user("stranger", email="attacker@evil.com")
        resp = client.post("/api/team/accept", json={"token": "leaked"}, headers=AUTH)
        assert resp.status_code == 403, resp.text
        assert "stranger" not in _ids(world.core)
        assert world.product.table("invitations").updated_payloads == []
