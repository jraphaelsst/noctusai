"""Core M2M tokens: mint/rotate/revoke through the seed routes, the MFA-to-mint platform setting,
`noc_` / legacy `pk_` authentication, and strict 401 for a revoked token.

Wiring is `dependency_overrides` + the `configure_token_db` DI seam only: the role checks, the MFA
policy, scope allow-list, hashing, resolver and audit run for real against an in-memory table set.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.api.auth.session import AuthContext, hash_token
from noctusai_lib.testing.mocks import MockSupabaseClient

from app import auth_context
from app.auth_context import get_auth_context, build_tokens_router
from app.routers import admin_tokens
from app.services import api_tokens
from app.services.trusted_auth import get_session_aal, get_session_user, get_trusted_db

ORG = "00000000-0000-4000-8000-0000000000aa"
ADMIN = "00000000-0000-4000-8000-0000000000a1"
MEMBER = "00000000-0000-4000-8000-0000000000a2"
NOC_AGENT = "00000000-0000-4000-8000-0000000000b1"


class _PublicDb(MockSupabaseClient):
    """The mock's ``schema()`` hands back a fresh, empty client; core's real client is already pinned to
    ``public``, so ``schema("public")`` is the identity there -- the same here."""

    def schema(self, name):
        return self


class Env:
    def __init__(self) -> None:
        self.db = _PublicDb(schema="public")
        self.db.set_table_data("noctus_users", [
            {"id": ADMIN, "org_id": ORG, "org_role": "owner", "role": "admin"},
            {"id": MEMBER, "org_id": ORG, "org_role": "owner", "role": "member"},
        ])
        self.db.set_table_data("platform_settings", [])
        self.db.set_table_data("api_tokens", [])
        self.db.set_table_data("api_token_audit", [])
        self.db.set_table_data("service_accounts", [{"id": NOC_AGENT, "slug": "noc-agent", "name": "noc-agent", "disabled_at": None}])
        self.who = {"user": ADMIN, "aal": "aal1"}

        app = FastAPI()
        app.include_router(build_tokens_router())
        app.include_router(admin_tokens.router)

        @app.get("/whoami")  # the REAL shared dependency
        async def whoami(ctx: AuthContext = Depends(get_auth_context)):
            return {"kind": ctx.caller_kind, "org": str(ctx.org_id), "scopes": list(ctx.scopes)}

        async def human():
            return AuthContext(
                org_id=UUID(ORG), caller_kind="user", user_id=UUID(self.who["user"]),
                scopes=[], raw_token="jwt", api_token_id=None, aal=self.who["aal"],
            )

        async def session_user():
            return SimpleNamespace(id=self.who["user"])

        self.app = app
        self.human_override = human
        app.dependency_overrides[get_trusted_db] = lambda: self.db
        app.dependency_overrides[get_session_user] = session_user
        app.dependency_overrides[get_session_aal] = lambda: self.who["aal"]
        self.client = TestClient(app)
        auth_context.configure_token_db(lambda: self.db)

    def as_human(self, user=ADMIN, aal="aal1"):
        self.who.update(user=user, aal=aal)
        self.app.dependency_overrides[get_auth_context] = self.human_override

    def as_real_auth(self):
        self.app.dependency_overrides.pop(get_auth_context, None)

    def set_mfa(self, value: str) -> None:
        self.db.set_table_data("platform_settings", [{"key": api_tokens.MFA_SETTING_KEY, "value": value}])

    def mint(self, **over):
        body = {"label": "noc-agent", "scopes": ["reminders:read"], "no_expiry": True, **over}
        return self.client.post("/api/settings/api-tokens", json=body)

    def rows(self):
        return self.db.table("api_tokens").select("*").execute().data


@pytest.fixture
def env():
    e = Env()
    yield e
    auth_context.configure_token_db(None)


# ── mint ────────────────────────────────────────────────────────────────────────

def test_mint_with_mfa_off_succeeds_without_mfa(env):
    env.as_human(aal="aal1")
    r = env.mint()
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token"].startswith("noc_") and body["expires_at"] is None
    assert body["prefix"] == body["token"][:12]
    stored = env.rows()[0]
    assert stored["token_hash"] == hash_token(body["token"]) and body["token"] not in str(stored)


def test_mfa_setting_row_absent_means_off(env):
    env.as_human()
    assert env.client.get("/api/admin/tokens/settings").json() == {"data": {"mfa_required": False}}


def test_mint_with_mfa_on_and_unmet_is_refused_by_name(env):
    env.set_mfa("true")
    env.as_human(aal="aal1")
    r = env.mint()
    assert r.status_code == 403 and r.json()["detail"] == "mfa_required"
    assert env.rows() == []


def test_mint_with_mfa_on_and_met_succeeds(env):
    env.set_mfa("true")
    env.as_human(aal="aal2")
    assert env.mint().status_code == 201


def test_rotate_with_mfa_on_and_unmet_is_refused_by_name(env):
    env.as_human()
    token_id = env.mint().json()["id"]
    env.set_mfa("true")
    r = env.client.post(f"/api/settings/api-tokens/{token_id}/rotate")
    assert r.status_code == 403 and r.json()["detail"] == "mfa_required"
    assert [t["revoked_at"] for t in env.rows()] == [None]


def test_unparseable_setting_fails_closed(env):
    env.set_mfa("talvez")
    env.as_human(aal="aal1")
    assert env.mint().status_code == 403


def test_mint_refuses_scopes_outside_the_core_allow_list(env):
    env.as_human()
    r = env.mint(scopes=["root:*"])
    assert r.status_code == 422 and "root:*" in r.json()["detail"]


def test_scopes_route_lists_the_allow_list_including_reminders(env):
    env.as_human()
    body = env.client.get("/api/settings/api-tokens/scopes").json()
    assert body["strict"] is True
    assert {"reminders:read", "reminders:write", "transcription:read", "transcription:write"} <= set(body["scopes"])


def test_mint_for_a_service_account_stores_the_link(env):
    env.as_human()
    r = env.mint(service_account_id=NOC_AGENT)
    assert r.status_code == 201 and r.json()["service_account_id"] == NOC_AGENT
    assert env.rows()[0]["service_account_id"] == NOC_AGENT
    assert env.mint(service_account_id="00000000-0000-4000-8000-0000000000ff").status_code == 422


def test_only_platform_admins_manage_tokens(env):
    env.as_human(user=MEMBER)  # an org owner who is NOT platform staff
    r = env.mint()
    assert r.status_code == 403 and r.json()["detail"]["code"] == "platform_admin_required"
    assert env.client.get("/api/settings/api-tokens").status_code == 403


# ── the MFA switch ──────────────────────────────────────────────────────────────

def test_admin_can_toggle_the_mfa_setting_and_it_applies_at_once(env):
    env.as_human(aal="aal1")
    assert env.mint().status_code == 201
    r = env.client.put("/api/admin/tokens/settings", json={"mfa_required": True})
    assert r.status_code == 200 and r.json() == {"data": {"mfa_required": True}}
    assert env.client.get("/api/admin/tokens/settings").json()["data"]["mfa_required"] is True
    assert env.mint().status_code == 403
    env.client.put("/api/admin/tokens/settings", json={"mfa_required": False})
    assert env.mint().status_code == 201


def test_non_admin_cannot_read_or_toggle_the_setting(env):
    env.as_human(user=MEMBER)
    env.who["user"] = MEMBER
    assert env.client.put("/api/admin/tokens/settings", json={"mfa_required": True}).status_code == 403
    assert env.client.get("/api/admin/tokens/settings").status_code == 403
    assert env.db.table("platform_settings").select("*").execute().data == []


def test_setting_body_is_strict(env):
    env.as_human()
    assert env.client.put("/api/admin/tokens/settings", json={"mfa_required": True, "x": 1}).status_code == 422
    assert env.client.put("/api/admin/tokens/settings", json={"mfa_required": "sim"}).status_code == 422


def test_service_accounts_listed_for_admins(env):
    env.as_human()
    data = env.client.get("/api/admin/tokens/service-accounts").json()["data"]
    assert [a["slug"] for a in data] == ["noc-agent"]


# ── authentication with the minted token (the REAL shared get_auth_context) ────

def test_a_minted_noc_token_authenticates_and_stamps_last_used(env):
    env.as_human()
    secret = env.mint(scopes=["reminders:read"]).json()["token"]
    env.as_real_auth()
    r = env.client.get("/whoami", headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 200
    assert r.json() == {"kind": "product", "org": ORG, "scopes": ["reminders:read"]}
    assert env.rows()[0]["last_used_at"]


def test_a_legacy_pk_token_is_still_accepted(env):
    # NOC-REMEDIATE[pk-prefix-cutoff]: this test flips to a 401 when the cutoff ships.
    secret = "pk_" + "ab" * 32
    env.db.set_table_data("api_tokens", [{
        "id": "00000000-0000-4000-8000-0000000000c1", "org_id": ORG, "label": "legacy",
        "token_hash": hash_token(secret), "token_prefix": secret[:11], "scopes": ["transcription:read"],
        "revoked_at": None, "expires_at": None,
    }])
    r = env.client.get("/whoami", headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 200 and r.json()["kind"] == "product"


def test_a_revoked_token_is_a_strict_401(env):
    env.as_human()
    minted = env.mint().json()
    assert env.client.delete(f"/api/settings/api-tokens/{minted['id']}").status_code == 204
    env.as_real_auth()
    assert env.client.get("/whoami", headers={"Authorization": f"Bearer {minted['token']}"}).status_code == 401


def test_an_expired_or_unknown_token_is_a_strict_401(env):
    env.as_real_auth()
    assert env.client.get("/whoami", headers={"Authorization": "Bearer noc_" + "00" * 32}).status_code == 401
    assert env.client.get("/whoami").status_code == 401


def test_rotate_replaces_the_token_and_the_old_one_stops_working(env):
    env.as_human()
    old = env.mint(scopes=["reminders:write"]).json()
    new = env.client.post(f"/api/settings/api-tokens/{old['id']}/rotate").json()
    assert new["token"].startswith("noc_") and new["token"] != old["token"] and new["scopes"] == ["reminders:write"]
    env.as_real_auth()
    assert env.client.get("/whoami", headers={"Authorization": f"Bearer {new['token']}"}).status_code == 200
    assert env.client.get("/whoami", headers={"Authorization": f"Bearer {old['token']}"}).status_code == 401


def test_a_token_cannot_mint_another_token(env):
    env.as_human()
    secret = env.mint().json()["token"]
    env.as_real_auth()
    r = env.client.post("/api/settings/api-tokens", headers={"Authorization": f"Bearer {secret}"},
                        json={"label": "x", "no_expiry": True})
    assert r.status_code == 403


def test_list_exposes_masking_inputs_expiry_and_last_used(env):
    env.as_human()
    env.mint(label="a")
    row = env.client.get("/api/settings/api-tokens").json()[0]
    assert row["prefix"].startswith("noc_") and len(row["prefix"]) == 12
    assert {"expires_at", "last_used_at", "scopes", "service_account_id", "revoked_at"} <= set(row)


def test_the_real_app_mounts_the_token_routes_and_keeps_core_login():
    from app.main import app

    paths = {(m, r.path) for r in app.routes for m in getattr(r, "methods", ())}
    assert ("POST", "/api/settings/api-tokens") in paths
    assert ("POST", "/api/settings/api-tokens/{token_id}/rotate") in paths
    assert ("PUT", "/api/admin/tokens/settings") in paths
    logins = [r for r in app.routes if getattr(r, "path", "") == "/api/auth/login"]
    assert len(logins) == 1 and logins[0].endpoint.__module__ == "app.routers.auth"
    assert any(m.cls.__name__ == "ApiTokenAuditMiddleware" for m in app.user_middleware)
