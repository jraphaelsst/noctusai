"""`TeamPolicy` — the named seam shaping the seed `team` router (2026-10-01).

The platform org is shared by every product AND by end customers, so the
pre-seam router listed every product's staff (and would have listed customers)
on every product's Equipe page, could not invite a product-specific staff role
(community's `moderador`), deleted a platform-wide profile from a product page,
and silently re-roled an existing member on invite-accept.

DB rows are real rows in the seed's `MockSupabaseClient`; the only mocked seam
is `deps.get_current_user` — the external GoTrue boundary.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.primitives.exceptions import http_exception_handler
from noctusai_lib.primitives.roles import ORG_ROLE_LABELS, ORG_ROLES
from noctusai_lib.testing.mocks import MockSupabaseClient
from noctusai_seed import TeamPolicy
from noctusai_seed.routers import _create_team_router, build_standard_routers

ORG = "org-shared"
OTHER_ORG = "org-other"
AUTH = {"Authorization": "Bearer t"}

COMMUNITY = TeamPolicy(
    staff_roles=frozenset({"owner", "admin", "moderador", "dev"}),
    invitable_roles=frozenset({"admin", "moderador"}),
    extra_role_labels={"moderador": "Moderador"},
)


def _row(user_id: str, org_id: str | None, org_role: str | None, role: str = "user") -> dict:
    return {
        "id": user_id,
        "email": f"{user_id}@test.com",
        "nome": user_id,
        "org_id": org_id,
        "org_role": org_role,
        "role": role,
    }


ROSTER = [
    _row("owner-1", ORG, "owner"),
    _row("admin-1", ORG, "admin"),
    _row("manager-1", ORG, "manager"),
    _row("corretor-1", ORG, "corretor"),
    _row("mod-1", ORG, "moderador"),
    _row("dev-1", ORG, "dev"),
    _row("no-role", ORG, None),
    _row("customer-1", ORG, "membro"),
    _row("customer-2", ORG, "membro"),
    _row("elsewhere", OTHER_ORG, "owner"),
]


def _invitation(token: str, *, role: str, email: str, org_id: str = ORG) -> dict:
    return {
        "id": f"inv-{token}",
        "org_id": org_id,
        "email": email,
        "role": role,
        "invited_by": "owner-1",
        "token": token,
        "status": "pending",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }


@pytest.fixture
def make_world(fake_deps, fake_settings, product_name):
    def _make(policy: TeamPolicy | None = None, *, seed_handler: bool = False):
        product_db = MockSupabaseClient(validate_schema=False, schema="test")
        product_db.set_table_data("invitations", [])
        core_db = MockSupabaseClient(validate_schema=False, schema="public")
        core_db.set_table_data("noctus_users", [dict(r) for r in ROSTER])
        core_db.set_table_data("organizations", [{"id": ORG, "nome": "NoctusAI"}])
        core_db.auth.admin.list_users.return_value = []
        fake_deps.get_admin_client = MagicMock(return_value=product_db)
        fake_deps.get_core_client = MagicMock(return_value=core_db)

        app = FastAPI()
        if seed_handler:
            app.add_exception_handler(HTTPException, http_exception_handler)
        app.include_router(_create_team_router(fake_deps, fake_settings, product_name, policy))

        def as_user(user_id: str, *, email: str | None = None):
            user = SimpleNamespace(
                id=user_id, email=email or f"{user_id}@test.com", user_metadata={},
            )
            fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
            # /accept resolves the caller through the license-UNGATED seam.
            fake_deps.get_current_user_ungated = fake_deps.get_current_user
            return TestClient(app)

        def anonymous():
            fake_deps.get_current_user = AsyncMock(
                side_effect=HTTPException(status_code=401, detail="Token ausente")
            )
            fake_deps.get_current_user_ungated = fake_deps.get_current_user
            return TestClient(app)

        return SimpleNamespace(
            as_user=as_user, anonymous=anonymous, core=core_db, product=product_db,
        )

    return _make


# ── TeamPolicy construction ────────────────────────────────────────────────


class TestTeamPolicyValidation:
    def test_default_policy_is_the_pre_seam_contract(self):
        contract = TeamPolicy().as_contract()
        assert contract["staff_roles"] == list(ORG_ROLES)
        assert contract["invitable_roles"] == list(ORG_ROLES)
        assert contract["labels"] == {r: ORG_ROLE_LABELS[r] for r in ORG_ROLES}

    def test_declared_policy_contract_shape(self):
        assert COMMUNITY.as_contract() == {
            "staff_roles": ["owner", "admin", "dev", "moderador"],
            "invitable_roles": ["admin", "moderador"],
            "labels": {
                "owner": "Proprietário",
                "admin": "Administrador",
                "dev": "Desenvolvedor",
                "moderador": "Moderador",
            },
        }

    def test_staff_only_policy_narrows_default_invitable_to_staff(self):
        policy = TeamPolicy(staff_roles=frozenset({"owner", "admin", "corretor"}))
        assert policy.effective_invitable_roles() == ["owner", "admin", "corretor"]

    def test_moderador_does_not_join_org_roles(self):
        assert "moderador" not in ORG_ROLES
        assert "moderador" not in TeamPolicy().effective_invitable_roles()

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"staff_roles": frozenset()},
            {"invitable_roles": frozenset()},
            {"staff_roles": frozenset({"owner", "membro"})},
            {"invitable_roles": frozenset({"membro"})},
            {"staff_roles": frozenset({"owner", "moderador"})},  # extra w/o label
            {
                "staff_roles": frozenset({"owner", "admin"}),
                "invitable_roles": frozenset({"member"}),  # invitable ⊄ staff
            },
            {"extra_role_labels": {"owner": "Dono"}},  # relabel a platform role
        ],
    )
    def test_incoherent_policy_refused_at_construction(self, kwargs):
        with pytest.raises(ValueError):
            TeamPolicy(**kwargs)


# ── GET /api/team/policy ───────────────────────────────────────────────────


class TestPolicyEndpoint:
    def test_unauthenticated_gets_401(self, make_world):
        world = make_world(COMMUNITY)
        resp = world.anonymous().get("/api/team/policy")
        assert resp.status_code == 401, resp.text

    def test_caller_without_membership_gets_403(self, make_world):
        world = make_world(COMMUNITY)
        resp = world.as_user("stranger").get("/api/team/policy", headers=AUTH)
        assert resp.status_code == 403, resp.text

    def test_customer_caller_gets_403(self, make_world):
        world = make_world(COMMUNITY)
        resp = world.as_user("customer-1").get("/api/team/policy", headers=AUTH)
        assert resp.status_code == 403, resp.text

    def test_staff_gets_the_declared_contract(self, make_world):
        world = make_world(COMMUNITY)
        resp = world.as_user("mod-1").get("/api/team/policy", headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert resp.json() == COMMUNITY.as_contract()

    def test_no_policy_returns_the_default_contract(self, make_world):
        world = make_world(None)
        resp = world.as_user("corretor-1").get("/api/team/policy", headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert resp.json() == TeamPolicy().as_contract()


# ── GET /api/team ──────────────────────────────────────────────────────────


def _listed(resp) -> set[str]:
    return {r["id"] for r in resp.json()["data"]}


class TestListFilter:
    def test_unauthenticated_gets_401(self, make_world):
        resp = make_world(None).anonymous().get("/api/team")
        assert resp.status_code == 401, resp.text

    def test_default_excludes_customers_and_keeps_every_other_member(self, make_world):
        world = make_world(None)
        resp = world.as_user("admin-1").get("/api/team", headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert _listed(resp) == {
            "owner-1", "admin-1", "manager-1", "corretor-1", "mod-1", "dev-1", "no-role",
        }

    def test_declared_staff_roles_filter_the_roster(self, make_world):
        world = make_world(COMMUNITY)
        resp = world.as_user("admin-1").get("/api/team", headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert _listed(resp) == {"owner-1", "admin-1", "mod-1", "dev-1"}

    def test_customers_never_listed_even_if_a_policy_could_name_them(self, make_world):
        # A policy cannot declare a customer role (refused at construction),
        # so under every constructible policy customers stay out.
        world = make_world(TeamPolicy(staff_roles=frozenset(ORG_ROLES)))
        resp = world.as_user("admin-1").get("/api/team", headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert not {"customer-1", "customer-2"} & _listed(resp)

    def test_roster_past_one_page_is_returned_whole(self, make_world):
        """PostgREST caps an unranged select at 1000 rows and reports success;
        the roster pages with `.range()` so no member silently disappears."""
        world = make_world(None)
        many = [_row(f"m-{i:04d}", ORG, "corretor") for i in range(1500)]
        world.core.set_table_data("noctus_users", [*ROSTER, *many])
        resp = world.as_user("admin-1").get("/api/team", headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert len(_listed(resp)) == 7 + 1500

    def test_customer_caller_gets_403(self, make_world):
        resp = make_world(None).as_user("customer-1").get("/api/team", headers=AUTH)
        assert resp.status_code == 403, resp.text

    def test_selects_explicit_columns_that_exist_on_noctus_users(
        self, fake_deps, fake_settings, product_name,
    ):
        """A schema-validating client rejects an unknown column — so the
        explicit column list is checked against the real `public.noctus_users`
        migrations, and `*` is gone."""
        core_db = MockSupabaseClient(validate_schema=True, schema="public")
        core_db.set_table_data("noctus_users", [dict(r) for r in ROSTER])
        fake_deps.get_core_client = MagicMock(return_value=core_db)
        user = SimpleNamespace(id="admin-1", email="admin-1@test.com", user_metadata={})
        fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
        app = FastAPI()
        app.include_router(_create_team_router(fake_deps, fake_settings, product_name))
        resp = TestClient(app).get("/api/team", headers=AUTH)
        assert resp.status_code == 200, resp.text


# ── POST /api/team/invite ──────────────────────────────────────────────────


class TestInviteRoles:
    def test_declared_extra_role_is_invitable(self, make_world):
        world = make_world(COMMUNITY)
        resp = world.as_user("admin-1").post(
            "/api/team/invite", json={"email": "m@test.com", "role": "moderador"}, headers=AUTH,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["role"] == "moderador"

    def test_extra_role_is_not_invitable_without_a_policy(self, make_world):
        world = make_world(None)
        resp = world.as_user("admin-1").post(
            "/api/team/invite", json={"email": "m@test.com", "role": "moderador"}, headers=AUTH,
        )
        assert resp.status_code == 400, resp.text
        assert world.product.table("invitations").inserted_payloads == []

    def test_platform_role_outside_declared_invitable_is_400(self, make_world):
        world = make_world(COMMUNITY)
        resp = world.as_user("owner-1").post(
            "/api/team/invite", json={"email": "c@test.com", "role": "corretor"}, headers=AUTH,
        )
        assert resp.status_code == 400, resp.text

    def test_customer_role_is_never_invitable(self, make_world):
        world = make_world(None)
        resp = world.as_user("owner-1").post(
            "/api/team/invite", json={"email": "c@test.com", "role": "membro"}, headers=AUTH,
        )
        assert resp.status_code == 400, resp.text

    def test_default_policy_still_invites_any_org_role(self, make_world):
        world = make_world(None)
        resp = world.as_user("owner-1").post(
            "/api/team/invite", json={"email": "c@test.com", "role": "corretor"}, headers=AUTH,
        )
        assert resp.status_code == 200, resp.text

    def test_grant_matrix_still_applies_under_a_policy(self, make_world):
        world = make_world(COMMUNITY)
        world.core.set_table_data(
            "noctus_users", [*ROSTER, _row("mgr-x", ORG, "manager")],
        )
        resp = world.as_user("mod-1").post(
            "/api/team/invite", json={"email": "a@test.com", "role": "admin"}, headers=AUTH,
        )
        assert resp.status_code == 403, resp.text

    def test_unauthenticated_invite_gets_401(self, make_world):
        resp = make_world(COMMUNITY).anonymous().post(
            "/api/team/invite", json={"email": "a@test.com", "role": "admin"},
        )
        assert resp.status_code == 401, resp.text


# ── DELETE /api/team/{user_id} — wire shape through the seed handler ───────


class TestRemoveIsCoreOnly:
    def test_flat_seed_error_shape_through_the_seed_handler(self, make_world):
        world = make_world(COMMUNITY, seed_handler=True)
        resp = world.as_user("admin-1").delete("/api/team/mod-1", headers=AUTH)
        assert resp.status_code == 409, resp.text
        assert resp.json() == {
            "detail": (
                "A remoção de pessoas da organização é feita no NoctusAI Core "
                "(afeta todos os produtos)."
            ),
            "code": "TEAM_REMOVE_CORE_ONLY",
        }
        assert any(r["id"] == "mod-1" for r in world.core.table("noctus_users")._data)

    def test_invitation_cancel_still_works(self, make_world):
        world = make_world(COMMUNITY)
        world.product.set_table_data(
            "invitations", [_invitation("tc", role="moderador", email="x@test.com")],
        )
        resp = world.as_user("admin-1").delete("/api/team/invitations/inv-tc", headers=AUTH)
        assert resp.status_code == 200, resp.text


# ── POST /api/team/accept — never overwrite an existing org_role ───────────


class TestAcceptNoOverwrite:
    def test_existing_member_with_a_different_role_gets_409(self, make_world):
        world = make_world(COMMUNITY)
        world.product.set_table_data(
            "invitations", [_invitation("t1", role="moderador", email="corretor-1@test.com")],
        )
        client = world.as_user("corretor-1", email="corretor-1@test.com")
        resp = client.post("/api/team/accept", json={"token": "t1"}, headers=AUTH)
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == (
            "Você já participa da organização com o papel Corretor. "
            "Peça ao administrador para alterar no NoctusAI Core."
        )
        assert world.core.table("noctus_users").updated_payloads == []
        world.core.auth.admin.update_user_by_id.assert_not_called()
        # Invitation stays pending — usable once Core changes the role.
        assert world.product.table("invitations").updated_payloads == []

    def test_existing_member_with_an_extra_role_label_in_the_409(self, make_world):
        world = make_world(COMMUNITY)
        world.product.set_table_data(
            "invitations", [_invitation("t2", role="admin", email="mod-1@test.com")],
        )
        client = world.as_user("mod-1", email="mod-1@test.com")
        resp = client.post("/api/team/accept", json={"token": "t2"}, headers=AUTH)
        assert resp.status_code == 409, resp.text
        assert "papel Moderador." in resp.json()["detail"]

    def test_existing_customer_is_not_promoted_by_an_invite(self, make_world):
        world = make_world(None)
        world.product.set_table_data(
            "invitations", [_invitation("t3", role="admin", email="customer-1@test.com")],
        )
        client = world.as_user("customer-1", email="customer-1@test.com")
        resp = client.post("/api/team/accept", json={"token": "t3"}, headers=AUTH)
        assert resp.status_code == 409, resp.text
        assert world.core.table("noctus_users").updated_payloads == []

    def test_same_role_reaccept_is_200(self, make_world):
        world = make_world(COMMUNITY)
        world.product.set_table_data(
            "invitations", [_invitation("t4", role="moderador", email="mod-1@test.com")],
        )
        client = world.as_user("mod-1", email="mod-1@test.com")
        resp = client.post("/api/team/accept", json={"token": "t4"}, headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["org_role"] == "moderador"


# ── wiring: build_standard_routers / create_product_app(team=...) ─────────


class TestWiring:
    def test_policy_without_team_router_is_refused(
        self, fake_deps, fake_settings, product_name, version,
    ):
        with pytest.raises(ValueError, match="team"):
            build_standard_routers(
                fake_deps, fake_settings, product_name=product_name, version=version,
                names=["health"], team_policy=COMMUNITY,
            )

    def test_policy_reaches_the_team_router(
        self, fake_deps, fake_settings, product_name, version,
    ):
        core_db = MockSupabaseClient(validate_schema=False, schema="public")
        core_db.set_table_data("noctus_users", [dict(r) for r in ROSTER])
        fake_deps.get_core_client = MagicMock(return_value=core_db)
        fake_deps.get_current_user = AsyncMock(
            return_value=(SimpleNamespace(id="admin-1", email="a@t", user_metadata={}), "tok")
        )
        app = FastAPI()
        for router in build_standard_routers(
            fake_deps, fake_settings, product_name=product_name, version=version,
            names=["team"], team_policy=COMMUNITY,
        ):
            app.include_router(router)
        resp = TestClient(app).get("/api/team/policy", headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert resp.json()["invitable_roles"] == ["admin", "moderador"]

    def test_create_product_app_accepts_team_kwarg(self):
        import inspect

        from noctusai_seed import create_product_app

        assert "team" in inspect.signature(create_product_app).parameters
