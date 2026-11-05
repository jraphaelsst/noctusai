"""M2M token policy (Julia-line D6): ``noc_`` minting, dual-prefix acceptance,
scope allow-list, rotate, resolver factory refusing the Fake in deploy."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.api.auth._reasons import token_shape
from noctusai_lib.api.auth.session import (
    AuthContext,
    FakeApiTokenResolver,
    FakeProductTokenAdmin,
    FakeSessionStore,
    SupabaseApiTokenResolver,
    TokenScopeAllowList,
    UnknownTokenScopeError,
    has_api_token_prefix,
    hash_token,
    make_api_token_resolver,
    make_get_auth_context,
    mint_token_secret,
    rotate_token,
)
from noctusai_lib.testing.mocks import MockSupabaseClient

EXPIRES = datetime.now(timezone.utc) + timedelta(days=30)


def test_mint_is_noc_and_never_pk():
    raw, prefix = mint_token_secret()
    assert raw.startswith("noc_") and not raw.startswith("pk_")
    assert prefix == raw[:12]


def test_prefix_helpers_accept_both_and_refuse_others():
    assert has_api_token_prefix("noc_abc") and has_api_token_prefix("pk_abc")
    assert not has_api_token_prefix("eyJ.a.b")
    assert token_shape("noc_x") == token_shape("pk_x") == "api_token"


def _app(resolver):
    app = FastAPI()
    dep = make_get_auth_context(
        session_store=FakeSessionStore(), api_token_resolver=resolver,
        session_cookie_name="nai_session",
    )

    @app.get("/whoami")
    def whoami(ctx: AuthContext = Depends(dep)):
        return {"kind": ctx.caller_kind}

    return TestClient(app)


@pytest.mark.parametrize("secret", ["noc_good_one", "pk_legacy_one"])
def test_dep_accepts_both_prefixes_and_401s_unknown(secret):
    resolver = FakeApiTokenResolver()
    resolver.register(secret, org_id=uuid4())
    client = _app(resolver)
    assert client.get("/whoami", headers={"Authorization": f"Bearer {secret}"}).status_code == 200
    unknown = secret + "_nope"
    assert client.get("/whoami", headers={"Authorization": f"Bearer {unknown}"}).status_code == 401


def test_supabase_resolver_accepts_noc_and_legacy_pk():
    org = uuid4()
    rows = []
    for secret in ("noc_" + "a" * 32, "pk_" + "b" * 32):
        rows.append({
            "id": str(uuid4()), "org_id": str(org), "scopes": ["x"], "revoked_at": None,
            "expires_at": None, "principal_agent_id": None, "human_personal": False,
            "minted_by": None, "issuer": "agents", "token_hash": hash_token(secret),
        })
    resolver = SupabaseApiTokenResolver(MockSupabaseClient(rows, validate_schema=False), schema="s")
    for secret in ("noc_" + "a" * 32, "pk_" + "b" * 32):
        ctx = asyncio.new_event_loop().run_until_complete(resolver.resolve(secret))
        assert ctx is not None and ctx.org_id == org and ctx.issuer == "agents"
    assert asyncio.new_event_loop().run_until_complete(resolver.resolve("sk_" + "c" * 32)) is None


class TestScopeAllowList:
    def test_mint_refuses_unknown_scope(self):
        admin = FakeProductTokenAdmin(TokenScopeAllowList(["a:read"]))
        admin.mint("s", org_id=uuid4(), label="ok", scopes=["a:read"], expires_at=EXPIRES)
        with pytest.raises(UnknownTokenScopeError) as exc:
            admin.mint("s", org_id=uuid4(), label="bad", scopes=["a:read", "evil:*"], expires_at=EXPIRES)
        assert exc.value.unknown == ("evil:*",)
        assert len(admin.rows["s"]) == 1  # the refused mint wrote nothing

    def test_products_register_their_scopes(self):
        allow = TokenScopeAllowList()
        allow.register("p:one", "p:two")
        assert allow.validate(["p:one"]) == ["p:one"]
        assert "p:two" in allow

    def test_global_registry_is_permissive_until_enforced(self):
        allow = TokenScopeAllowList(strict=False)
        assert allow.validate(["anything"]) == ["anything"]
        allow.enforce()
        with pytest.raises(UnknownTokenScopeError):
            allow.validate(["anything"])


class TestNoExpiryAndRotate:
    def _admin(self):
        return FakeProductTokenAdmin(TokenScopeAllowList(["a:read", "b:write"]))

    def test_no_expiry_token_resolves_and_keeps_revocation(self):
        admin = self._admin()
        org = uuid4()
        minted = admin.mint("s", org_id=org, label="forever", scopes=["a:read"], expires_at=None)
        assert minted.info.expires_at is None
        assert admin.find_by_secret("s", minted.secret).revoked_at is None
        assert admin.revoke("s", minted.info.id, org_id=org) is True
        assert admin.find_by_secret("s", minted.secret).revoked_at is not None

    def test_rotate_mints_new_then_revokes_old_keeping_shape(self):
        admin = self._admin()
        org = uuid4()
        old = admin.mint("s", org_id=org, label="tools", scopes=["a:read", "b:write"],
                         expires_at=None, issuer="agents")
        rotated = rotate_token(admin, "s", old.info.id, org_id=org)
        assert rotated.new.secret != old.secret
        assert rotated.new.secret.startswith("noc_")
        assert rotated.new.info.scopes == old.info.scopes
        assert rotated.new.info.issuer == "agents"
        assert rotated.new.info.expires_at is None
        assert admin.find_by_secret("s", old.secret).revoked_at is not None
        assert admin.find_by_secret("s", rotated.new.secret).revoked_at is None

    def test_rotate_unknown_token_is_a_lookup_error(self):
        with pytest.raises(LookupError):
            rotate_token(self._admin(), "s", uuid4(), org_id=uuid4())

    def test_failed_old_revoke_rolls_back_the_new_token(self):
        class _StuckOldToken(FakeProductTokenAdmin):
            stuck = None

            def revoke(self, schema, token_id, *, org_id):
                if token_id == self.stuck:
                    return False
                return super().revoke(schema, token_id, org_id=org_id)

        admin = _StuckOldToken(TokenScopeAllowList(["a:read"]))
        org = uuid4()
        old = admin.mint("s", org_id=org, label="t", scopes=["a:read"], expires_at=EXPIRES)
        admin.stuck = old.info.id
        with pytest.raises(RuntimeError):
            rotate_token(admin, "s", old.info.id, org_id=org)
        live = [r for r in admin.rows["s"] if not r["revoked_at"]]
        assert [r["id"] for r in live] == [str(old.info.id)]


class TestResolverFactory:
    def test_fake_allowed_outside_deploy(self):
        assert isinstance(make_api_token_resolver(deploy_context=False), FakeApiTokenResolver)

    def test_fake_refused_in_deploy(self):
        with pytest.raises(RuntimeError, match="deploy context"):
            make_api_token_resolver(deploy_context=True)

    def test_real_when_client_and_schema_given(self):
        r = make_api_token_resolver(MockSupabaseClient([], validate_schema=False),
                                    schema="s", deploy_context=True)
        assert isinstance(r, SupabaseApiTokenResolver)

    def test_client_without_schema_is_refused(self):
        with pytest.raises(ValueError):
            make_api_token_resolver(MockSupabaseClient([], validate_schema=False))

    def test_env_detection_refuses_fake_when_app_env_production(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        with pytest.raises(RuntimeError):
            make_api_token_resolver()


def test_allow_list_scopes_are_listed_sorted():
    from noctusai_lib.api.auth.session import TokenScopeAllowList

    assert TokenScopeAllowList(["b:write", "a:read", "a:read"]).scopes() == ["a:read", "b:write"]


def test_token_row_carries_service_account_only_when_set():
    from datetime import datetime, timezone
    from uuid import uuid4

    from noctusai_lib.api.auth.session.token_admin import build_api_token_row

    base = dict(token_id=uuid4(), raw_secret="noc_x", org_id=uuid4(), label="l", scopes=[],
                expires_at=None, created_at=datetime.now(timezone.utc))
    assert "service_account_id" not in build_api_token_row(**base)
    sa = uuid4()
    assert build_api_token_row(**base, service_account_id=sa)["service_account_id"] == str(sa)
