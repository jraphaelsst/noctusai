"""Seed token lifecycle routes: rotate, scope allow-list listing, service-account link.

The mint/revoke/list happy paths live in ``test_trusted_org_auth``; this file
covers what S1's ``rotate_token`` function lacked, a route.
"""
from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from noctusai_lib.api.auth.session import AuthContext, MintPolicy, TokenScopeAllowList
from noctusai_lib.testing.mocks import MockSupabaseClient
from noctusai_seed.auth_router import ApiTokenCreateRequest, create_auth_router

ORG = "00000000-0000-4000-8000-0000000000aa"
USER = "00000000-0000-4000-8000-0000000000cc"


def _run(result):
    if inspect.isawaitable(result):
        return asyncio.new_event_loop().run_until_complete(result)
    return result


def _ctx(aal=None) -> AuthContext:
    return AuthContext(
        org_id=UUID(ORG), caller_kind="user", user_id=UUID(USER),
        scopes=[], raw_token="sid", api_token_id=None, aal=aal,
    )


def _endpoint(router, method, path):
    for route in router.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError(f"no route {method} {path}")


def _router(**kwargs):
    core = MockSupabaseClient(
        [{"id": USER, "org_id": ORG, "org_role": "owner"}], validate_schema=False, schema="public"
    )
    admin = MockSupabaseClient([], validate_schema=False)
    deps = SimpleNamespace(get_core_client=lambda: core, get_admin_client=lambda: admin)
    settings = SimpleNamespace(
        supabase_url="http://x", supabase_anon_key="k", redis_url=None, redis_session_encryption_key="",
    )
    return create_auth_router(deps, settings, **kwargs), admin


def _mint(router, **body):
    return _run(_endpoint(router, "POST", "/api/settings/api-tokens")(
        ApiTokenCreateRequest(label="t", no_expiry=True, **body), ctx=_ctx()))


def test_rotate_returns_a_new_noc_secret_and_revokes_the_old_one():
    router, admin = _router(scope_allow_list=TokenScopeAllowList(["a:read"]))
    old = _mint(router, scopes=["a:read"])
    new = _run(_endpoint(router, "POST", "/api/settings/api-tokens/{token_id}/rotate")(
        UUID(old.id), ctx=_ctx()))
    assert new.token.startswith("noc_") and new.token != old.token
    assert new.id != old.id and new.scopes == ["a:read"] and new.expires_at is None
    listed = _run(_endpoint(router, "GET", "/api/settings/api-tokens")(ctx=_ctx()))
    revoked = {t.id: t.revoked_at for t in listed}
    assert revoked[old.id] and not revoked[new.id]


def test_rotate_keeps_the_expiry_of_the_old_token():
    from datetime import datetime, timedelta, timezone

    router, _ = _router()
    expiry = datetime.now(timezone.utc) + timedelta(days=30)
    old = _run(_endpoint(router, "POST", "/api/settings/api-tokens")(
        ApiTokenCreateRequest(label="t", expires_at=expiry), ctx=_ctx()))
    new = _run(_endpoint(router, "POST", "/api/settings/api-tokens/{token_id}/rotate")(
        UUID(old.id), ctx=_ctx()))
    assert datetime.fromisoformat(new.expires_at) == expiry


def test_rotate_unknown_or_revoked_token_is_404():
    router, _ = _router()
    rotate = _endpoint(router, "POST", "/api/settings/api-tokens/{token_id}/rotate")
    with pytest.raises(HTTPException) as exc:
        _run(rotate(uuid4(), ctx=_ctx()))
    assert exc.value.status_code == 404
    old = _mint(router)
    _run(rotate(UUID(old.id), ctx=_ctx()))
    with pytest.raises(HTTPException) as exc:
        _run(rotate(UUID(old.id), ctx=_ctx()))  # already revoked by the first rotation
    assert exc.value.status_code == 404


def test_rotate_needs_mfa_when_the_policy_says_so():
    router, _ = _router(mint_policy=MintPolicy(require_mfa=lambda ctx: True))
    with pytest.raises(HTTPException) as exc:
        _run(_endpoint(router, "POST", "/api/settings/api-tokens/{token_id}/rotate")(
            uuid4(), ctx=_ctx(aal="aal1")))
    assert exc.value.status_code == 403 and exc.value.detail == "mfa_required"


def test_scopes_route_lists_the_allow_list_sorted():
    router, _ = _router(scope_allow_list=TokenScopeAllowList(["b:write", "a:read"]))
    out = _run(_endpoint(router, "GET", "/api/settings/api-tokens/scopes")(ctx=_ctx()))
    assert out.scopes == ["a:read", "b:write"] and out.strict is True


def test_service_account_unsupported_without_a_check():
    router, _ = _router()
    with pytest.raises(HTTPException) as exc:
        _mint(router, service_account_id=uuid4())
    assert exc.value.status_code == 422 and exc.value.detail == "service_accounts_unsupported"


def test_service_account_must_exist_and_is_stored_and_survives_rotation():
    known = uuid4()
    router, admin = _router(service_account_check=lambda sid: sid == known)
    with pytest.raises(HTTPException) as exc:
        _mint(router, service_account_id=uuid4())
    assert exc.value.status_code == 422 and exc.value.detail == "service_account_not_found"
    old = _mint(router, service_account_id=known)
    assert old.service_account_id == str(known)
    new = _run(_endpoint(router, "POST", "/api/settings/api-tokens/{token_id}/rotate")(
        UUID(old.id), ctx=_ctx()))
    assert new.service_account_id == str(known)
    listed = _run(_endpoint(router, "GET", "/api/settings/api-tokens")(ctx=_ctx()))
    assert {t.service_account_id for t in listed} == {str(known)}


def test_token_routes_only_mode_skips_session_routes_and_uses_the_injected_dependency():
    async def my_dep():
        return _ctx()

    router, _ = _router(include_session_routes=False, get_auth_context=my_dep)
    paths = {getattr(r, "path", "") for r in router.routes}
    assert not any(p.startswith("/api/auth") for p in paths)
    assert "/api/settings/api-tokens" in paths and "/api/settings/api-tokens/scopes" in paths
    mint = next(r for r in router.routes if r.path == "/api/settings/api-tokens" and "POST" in r.methods)
    assert my_dep in {d.call for d in mint.dependant.dependencies}
