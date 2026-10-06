"""SEC hotfix 2026-10-06 — a user whose ``user_metadata.org_id`` names ANOTHER
org must get only their TRUSTED org (``public.noctus_users``) or be refused.

Covers the seed surface: trusted legacy-JWT bridge, ``/api/auth/login`` cookie
session org, API-token mint org pin, and ``require_scopes`` org pin.
KB § PATTERNS/backend/no-metadata-authz.md
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from noctusai_lib.api.auth.session import (
    AuthContext,
    make_trusted_legacy_jwt_resolver,
    require_scopes,
)
from noctusai_lib.testing.mocks import MockSupabaseClient
from noctusai_seed.auth_router import create_auth_router

TRUSTED_ORG = "00000000-0000-4000-8000-0000000000aa"
OTHER_ORG = "00000000-0000-4000-8000-0000000000bb"
USER_ID = "00000000-0000-4000-8000-0000000000cc"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _Core:
    def __init__(self, rows=None, error=None):
        self._sb = MockSupabaseClient(rows or [], validate_schema=False, schema="public")
        self._error = error

    def _check(self):
        if self._error is not None:
            raise self._error

    def table(self, name):
        self._check()
        return self._sb.table(name)

    def from_(self, name):
        self._check()
        return self._sb.from_(name)


def _spoofed_user():
    return SimpleNamespace(
        id=USER_ID, email="a@b.c", user_metadata={"org_id": OTHER_ORG, "org_role": "owner"}
    )


def _get_user_fn(user):
    async def _fn(authorization=None):
        if user is None:
            raise HTTPException(status_code=401)
        return user, "tok"

    return _fn


class TestTrustedLegacyBridge:
    def test_spoofed_metadata_org_is_ignored_trusted_org_wins(self):
        core = _Core([{"id": USER_ID, "org_id": TRUSTED_ORG, "org_role": "owner"}])
        resolver = make_trusted_legacy_jwt_resolver(_get_user_fn(_spoofed_user()), lambda: core)
        ctx = _run(resolver("jwt"))
        assert ctx.org_id == UUID(TRUSTED_ORG)
        assert ctx.org_id != UUID(OTHER_ORG)

    def test_no_row_is_403_even_if_metadata_names_an_org(self):
        resolver = make_trusted_legacy_jwt_resolver(
            _get_user_fn(_spoofed_user()), lambda: _Core([])
        )
        with pytest.raises(HTTPException) as exc:
            _run(resolver("jwt"))
        assert exc.value.status_code == 403

    def test_customer_role_refused_unless_allowed(self):
        core = _Core([{"id": USER_ID, "org_id": TRUSTED_ORG, "org_role": "membro"}])
        strict = make_trusted_legacy_jwt_resolver(_get_user_fn(_spoofed_user()), lambda: core)
        with pytest.raises(HTTPException) as exc:
            _run(strict("jwt"))
        assert exc.value.status_code == 403
        allowed = make_trusted_legacy_jwt_resolver(
            _get_user_fn(_spoofed_user()), lambda: core, allow_customer=True
        )
        assert _run(allowed("jwt")).org_id == UUID(TRUSTED_ORG)

    def test_db_error_fails_closed_503(self):
        resolver = make_trusted_legacy_jwt_resolver(
            _get_user_fn(_spoofed_user()), lambda: _Core(error=RuntimeError("db down"))
        )
        with pytest.raises(HTTPException) as exc:
            _run(resolver("jwt"))
        assert exc.value.status_code == 503

    def test_invalid_jwt_returns_none_for_401(self):
        resolver = make_trusted_legacy_jwt_resolver(_get_user_fn(None), lambda: _Core([]))
        assert _run(resolver("bad")) is None


def _user_ctx(org: str) -> AuthContext:
    return AuthContext(
        org_id=UUID(org), caller_kind="user", user_id=UUID(USER_ID),
        scopes=[], raw_token="sid", api_token_id=None,
    )


class TestRequireScopesOrgPin:
    def _dep(self, rows):
        async def _gac(ctx=None):
            return ctx

        return require_scopes(
            user_roles=frozenset({"owner", "admin"}),
            get_auth_context=_gac,
            get_core_client=lambda: _Core(rows),
        )

    def test_user_ctx_org_not_trusted_org_is_403_org_mismatch(self):
        dep = self._dep([{"id": USER_ID, "org_id": TRUSTED_ORG, "org_role": "owner"}])
        with pytest.raises(HTTPException) as exc:
            _run(dep(ctx=_user_ctx(OTHER_ORG)))
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "org_mismatch"

    def test_user_ctx_with_trusted_org_passes(self):
        dep = self._dep([{"id": USER_ID, "org_id": TRUSTED_ORG, "org_role": "owner"}])
        ctx = _user_ctx(TRUSTED_ORG)
        assert _run(dep(ctx=ctx)) is ctx


def _router(core, admin):
    deps = SimpleNamespace(get_core_client=lambda: core, get_admin_client=lambda: admin)
    settings = SimpleNamespace(
        supabase_url="http://x", supabase_anon_key="k", redis_url=None,
        redis_session_encryption_key="",
    )
    return create_auth_router(deps, settings), settings


def _endpoint(router, method, path):
    for route in router.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError(f"no route {method} {path}")


class TestLoginAndMint:
    def _login(self, rows, error=None):
        from noctusai_seed.auth_router import LoginRequest

        router, settings = _router(_Core(rows, error), MockSupabaseClient([], validate_schema=False))
        fake_auth = SimpleNamespace(
            user=_spoofed_user(),
            session=SimpleNamespace(refresh_token="rt"),
        )
        fake_client = SimpleNamespace(
            auth=SimpleNamespace(sign_in_with_password=lambda creds: fake_auth)
        )
        response = SimpleNamespace(set_cookie=lambda **kw: None)
        with patch("supabase.create_client", return_value=fake_client):
            result = _run(
                _endpoint(router, "POST", "/api/auth/login")(
                    LoginRequest(email="a@b.co", password="x" * 12), response
                )
            )
        return result

    def test_login_session_org_is_trusted_not_metadata(self):
        result = self._login([{"id": USER_ID, "org_id": TRUSTED_ORG, "org_role": "owner"}])
        assert result.org.id == TRUSTED_ORG

    def test_login_no_row_is_403(self):
        with pytest.raises(HTTPException) as exc:
            self._login([])
        assert exc.value.status_code == 403

    def test_login_db_error_is_503(self):
        with pytest.raises(HTTPException) as exc:
            self._login([], error=RuntimeError("db down"))
        assert exc.value.status_code == 503

    def _mint(self, ctx_org, rows):
        from noctusai_seed.auth_router import ApiTokenCreateRequest

        admin = MockSupabaseClient([], validate_schema=False)
        router, _ = _router(_Core(rows), admin)
        body = ApiTokenCreateRequest(
            label="t", scopes=[],
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        return _run(
            _endpoint(router, "POST", "/api/settings/api-tokens")(
                body, ctx=_user_ctx(ctx_org)
            )
        )

    def test_mint_refused_when_ctx_org_is_not_trusted_org(self):
        rows = [{"id": USER_ID, "org_id": TRUSTED_ORG, "org_role": "owner"}]
        with pytest.raises(HTTPException) as exc:
            self._mint(OTHER_ORG, rows)
        assert exc.value.status_code == 403

    def test_mint_ok_for_trusted_org_admin(self):
        rows = [{"id": USER_ID, "org_id": TRUSTED_ORG, "org_role": "owner"}]
        assert self._mint(TRUSTED_ORG, rows).token
