"""CI-gating coverage for SEED-1 (project-history/roadmaps/
julia-agents-academia-2026-09.md, contract §B.0).

``seed/lib/backend/tests/`` is NOT run by CI (open drift, 2026-09-09) —
this file is the CI-gating leg for the seed-lib changes SEED-1 makes:

  - ``AuthContext`` gains 4 new defaulted fields; the OLD constructor
    call shape (only the original 6 fields) must keep working.
  - ``SupabaseApiTokenResolver`` (promoted from social-wiring) refuses
    a revoked OR expired token, and populates the new
    ``principal_agent_id`` / ``human_personal`` / ``minted_by`` fields
    on a valid resolve — exercised against a Fake admin client
    (``noctusai_lib.testing.MockSupabaseClient``).
  - ``require_scopes``'s 401/403 matrix: product-without-scope,
    user-outside-role-set, the ``product_only`` restriction on a user
    caller, and the missing-credential-is-exactly-401 case (the auth
    boundary must never fall through to 403/404/422 —
    ``KB § PATTERNS/compliance/auth-boundary-false-green.md``).

This is a Python-import-level suite (no FastAPI app / TestClient) —
each dependency closure is invoked directly with an explicit ``ctx=``
argument, bypassing FastAPI's ``Depends(...)`` resolution machinery on
purpose (the closures accept a plain keyword override).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.api.auth.session import (
    AuthContext,
    SupabaseApiTokenResolver,
    is_org_admin,
    make_require_org_admin,
    require_org_admin_role,
    require_scopes,
)
from noctusai_lib.testing import MockSupabaseClient


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


_ORG = UUID("00000000-0000-4000-8000-0000000000aa")
_TOKEN_ID = UUID("00000000-0000-4000-8000-0000000000bb")
_AGENT = UUID("00000000-0000-4000-8000-0000000000cc")
_MINTER = UUID("00000000-0000-4000-8000-0000000000dd")
_USER = UUID("00000000-0000-4000-8000-0000000000ee")


class TestAuthContextBackCompat:
    """The 4 new fields default so every pre-SEED-1 constructor call
    (positional or keyword, only the original 6 fields) keeps working
    unchanged."""

    def test_old_positional_construction_still_works(self):
        ctx = AuthContext(
            _ORG,
            "user",
            _USER,
            [],
            "raw-token",
            None,
        )
        assert ctx.org_id == _ORG
        assert ctx.caller_kind == "user"
        assert ctx.principal_agent_id is None
        assert ctx.expires_at is None
        assert ctx.human_personal is False
        assert ctx.minted_by is None
        assert ctx.issuer is None

    def test_old_keyword_construction_still_works(self):
        ctx = AuthContext(
            org_id=_ORG,
            caller_kind="product",
            user_id=None,
            scopes=["read"],
            raw_token=str(_TOKEN_ID),
            api_token_id=_TOKEN_ID,
        )
        assert ctx.scopes == ["read"]
        assert ctx.principal_agent_id is None
        assert ctx.human_personal is False
        assert ctx.issuer is None

    def test_new_fields_are_settable(self):
        ctx = AuthContext(
            org_id=_ORG,
            caller_kind="product",
            user_id=None,
            scopes=["academia:read"],
            raw_token=str(_TOKEN_ID),
            api_token_id=_TOKEN_ID,
            principal_agent_id=_AGENT,
            human_personal=True,
            minted_by=_MINTER,
            issuer="agents",
        )
        assert ctx.principal_agent_id == _AGENT
        assert ctx.human_personal is True
        assert ctx.minted_by == _MINTER
        assert ctx.issuer == "agents"


def _token_row(
    secret_hash: str,
    *,
    revoked_at: str | None = None,
    expires_at: str | None = None,
    principal_agent_id: str | None = None,
    human_personal: bool = False,
    minted_by: str | None = None,
    scopes: list[str] | None = None,
    issuer: str | None = None,
) -> dict:
    return {
        "id": str(_TOKEN_ID),
        "org_id": str(_ORG),
        "scopes": list(scopes or []),
        "revoked_at": revoked_at,
        "expires_at": expires_at,
        "principal_agent_id": principal_agent_id,
        "human_personal": human_personal,
        "minted_by": minted_by,
        "token_hash": secret_hash,
        "issuer": issuer,
    }


class TestSupabaseApiTokenResolver:
    """Resolver behaviour against a Fake admin client
    (``MockSupabaseClient``) — revoked/expired refuse, valid populates
    the new fields."""

    def _client(self, rows: list[dict]) -> MockSupabaseClient:
        return MockSupabaseClient(rows, validate_schema=False)

    def test_revoked_token_returns_none(self):
        from noctusai_lib.api.auth.session import hash_token

        secret = "pk_" + "a" * 32
        row = _token_row(
            hash_token(secret), revoked_at="2026-01-01T00:00:00+00:00"
        )
        resolver = SupabaseApiTokenResolver(
            self._client([row]), schema="academia_de_reciclagem"
        )

        ctx = _run(resolver.resolve(secret))

        assert ctx is None

    def test_expired_token_returns_none(self):
        from noctusai_lib.api.auth.session import hash_token

        secret = "pk_" + "b" * 32
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        row = _token_row(hash_token(secret), expires_at=past)
        resolver = SupabaseApiTokenResolver(
            self._client([row]), schema="academia_de_reciclagem"
        )

        ctx = _run(resolver.resolve(secret))

        assert ctx is None

    def test_valid_token_populates_new_fields(self):
        from noctusai_lib.api.auth.session import hash_token

        secret = "pk_" + "c" * 32
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        row = _token_row(
            hash_token(secret),
            expires_at=future,
            principal_agent_id=str(_AGENT),
            human_personal=True,
            minted_by=str(_MINTER),
            scopes=["academia:read"],
            issuer="agents",
        )
        resolver = SupabaseApiTokenResolver(
            self._client([row]), schema="academia_de_reciclagem"
        )

        ctx = _run(resolver.resolve(secret))

        assert ctx is not None
        assert ctx.caller_kind == "product"
        assert ctx.org_id == _ORG
        assert ctx.principal_agent_id == _AGENT
        assert ctx.human_personal is True
        assert ctx.minted_by == _MINTER
        assert ctx.scopes == ["academia:read"]
        assert ctx.issuer == "agents"

    def test_unknown_token_returns_none(self):
        resolver = SupabaseApiTokenResolver(
            self._client([]), schema="academia_de_reciclagem"
        )

        ctx = _run(resolver.resolve("pk_" + "d" * 32))

        assert ctx is None

    def test_issuer_populated_from_row(self):
        """SW1 (contract §E.6): the resolver reads + populates
        ``AuthContext.issuer`` from the token row's ``issuer`` column —
        the field the bridge route's ``ctx.issuer != "agents"`` check
        depends on."""
        from noctusai_lib.api.auth.session import hash_token

        secret = "pk_" + "e" * 32
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        row = _token_row(hash_token(secret), expires_at=future, issuer="agents")
        resolver = SupabaseApiTokenResolver(
            self._client([row]), schema="social_wiring"
        )

        ctx = _run(resolver.resolve(secret))

        assert ctx is not None
        assert ctx.issuer == "agents"

    def test_issuer_none_when_absent(self):
        """A token row with no ``issuer`` value (pre-SW1 token, or one
        minted without an issuer) resolves with ``ctx.issuer is None``
        — never an empty string or a KeyError."""
        from noctusai_lib.api.auth.session import hash_token

        secret = "pk_" + "f" * 32
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        row = _token_row(hash_token(secret), expires_at=future)
        resolver = SupabaseApiTokenResolver(
            self._client([row]), schema="social_wiring"
        )

        ctx = _run(resolver.resolve(secret))

        assert ctx is not None
        assert ctx.issuer is None


class _FakeCoreClient:
    """Minimal stand-in for ``deps.get_core_client()`` — a
    ``public``-scoped Supabase-shaped client exposing ``.from_(...)``.
    Backed by ``MockSupabaseClient`` (the platform's canonical Fake for
    this shape), not a bespoke mock."""

    def __init__(self, rows: list[dict]) -> None:
        self._sb = MockSupabaseClient(rows, validate_schema=False, schema="public")

    def from_(self, name: str):
        return self._sb.from_(name)


async def _always_401() -> AuthContext:
    """Stand-in ``get_auth_context`` dep for the "missing credential"
    case — mirrors ``make_get_auth_context``'s own behaviour (raises
    401, never falls through to 403/404/422 —
    ``KB § PATTERNS/compliance/auth-boundary-false-green.md``). A
    no-arg signature — FastAPI introspects a dependency callable's
    signature to build its own sub-parameters, and ``*args, **kwargs``
    is read as two REQUIRED query params (``args``/``kwargs``), which
    would 422 before this body ever runs."""
    raise HTTPException(status_code=401, detail="Not authenticated")


async def _ctx_dep(ctx: AuthContext):
    return ctx


class TestRequireScopes:
    """The 401/403 matrix. Each dependency closure is invoked directly
    with an explicit ``ctx=`` kwarg — bypassing FastAPI's
    ``Depends(...)`` resolution on purpose (unit-testing the branch
    logic, not the ASGI wiring)."""

    def test_product_caller_missing_scope_is_403_scope_missing(self):
        ctx = AuthContext(
            org_id=_ORG,
            caller_kind="product",
            user_id=None,
            scopes=["academia:read"],
            raw_token=str(_TOKEN_ID),
            api_token_id=_TOKEN_ID,
        )
        dep = require_scopes(
            "academia:kb:write",
            get_auth_context=lambda: _ctx_dep(ctx),
        )

        with pytest.raises(HTTPException) as exc_info:
            _run(dep(ctx=ctx))

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "scope_missing"

    def test_product_caller_with_every_scope_passes(self):
        ctx = AuthContext(
            org_id=_ORG,
            caller_kind="product",
            user_id=None,
            scopes=["academia:read", "academia:kb:write"],
            raw_token=str(_TOKEN_ID),
            api_token_id=_TOKEN_ID,
        )
        dep = require_scopes(
            "academia:kb:write",
            get_auth_context=lambda: _ctx_dep(ctx),
        )

        result = _run(dep(ctx=ctx))

        assert result is ctx

    def test_user_caller_outside_role_set_is_403_role_missing(self):
        ctx = AuthContext(
            org_id=_ORG,
            caller_kind="user",
            user_id=_USER,
            scopes=[],
            raw_token="session-id",
            api_token_id=None,
        )
        core_client = _FakeCoreClient(
            [{"id": str(_USER), "org_role": "viewer"}]
        )
        dep = require_scopes(
            user_roles=frozenset({"owner", "admin"}),
            get_auth_context=lambda: _ctx_dep(ctx),
            get_core_client=lambda: core_client,
        )

        with pytest.raises(HTTPException) as exc_info:
            _run(dep(ctx=ctx))

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "role_missing"

    def test_user_caller_with_role_in_set_passes(self):
        ctx = AuthContext(
            org_id=_ORG,
            caller_kind="user",
            user_id=_USER,
            scopes=[],
            raw_token="session-id",
            api_token_id=None,
        )
        core_client = _FakeCoreClient(
            [{"id": str(_USER), "org_role": "owner"}]
        )
        dep = require_scopes(
            user_roles=frozenset({"owner", "admin"}),
            get_auth_context=lambda: _ctx_dep(ctx),
            get_core_client=lambda: core_client,
        )

        result = _run(dep(ctx=ctx))

        assert result is ctx

    def test_product_only_restriction_rejects_user_caller(self):
        ctx = AuthContext(
            org_id=_ORG,
            caller_kind="user",
            user_id=_USER,
            scopes=[],
            raw_token="session-id",
            api_token_id=None,
        )
        dep = require_scopes(
            "social-wiring:one-chat:read",
            get_auth_context=lambda: _ctx_dep(ctx),
            restrict="product_only",
        )

        with pytest.raises(HTTPException) as exc_info:
            _run(dep(ctx=ctx))

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "product_required"

    def test_user_only_restriction_rejects_product_caller(self):
        ctx = AuthContext(
            org_id=_ORG,
            caller_kind="product",
            user_id=None,
            scopes=[],
            raw_token=str(_TOKEN_ID),
            api_token_id=_TOKEN_ID,
        )
        dep = require_scopes(
            user_roles=frozenset({"owner", "admin", "member"}),
            get_auth_context=lambda: _ctx_dep(ctx),
            get_core_client=lambda: _FakeCoreClient([]),
            restrict="user_only",
        )

        with pytest.raises(HTTPException) as exc_info:
            _run(dep(ctx=ctx))

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "user_required"

    def test_missing_credential_is_exactly_401_never_403_or_404_or_422(self):
        """Auth-boundary false-green guard: composed on top of a
        ``get_auth_context`` that raises 401 for "no credential", the
        wrapping ``require_scopes`` dependency must never intercept
        that into a 403/404/422. Driven through a REAL FastAPI
        ``Depends(...)`` resolution (a tiny app + ``TestClient``) so
        this exercises the actual ASGI wiring, not just the branch
        logic below the upstream dep — the upstream 401 must
        propagate untouched, never falling through to
        ``KB § PATTERNS/compliance/auth-boundary-false-green.md``'s
        non-401 shape."""
        dep = require_scopes(
            "academia:read",
            get_auth_context=_always_401,
        )

        app = FastAPI()

        @app.get("/protected")
        async def protected(ctx: AuthContext = Depends(dep)):
            return {"org_id": str(ctx.org_id)}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/protected")

        assert resp.status_code == 401, resp.text


# ─── `is_org_admin` / `require_org_admin_role` / `make_require_org_admin`
#     — the N=3 shared trusted-DB predicate (2026-09-2x) ───────────────────
#
# Formalizes what `noctusai_seed.auth_router._require_org_admin` already did
# correctly (trusted-DB `public.noctus_users` read) into a reusable
# bool-predicate + imperative-raise + dependency-factory trio, so a product
# route stops hand-rolling a FOURTH copy — or worse, a spoofable
# `user_metadata.org_role` read (the class this closes; see
# `resolve_org_role`'s own docstring + `products/core/backend/app/routers
# /admin_llm_usage.py`'s note on the exact spoof).


class TestIsOrgAdmin:
    def test_owner_is_admin(self):
        core = _FakeCoreClient([{"id": str(_USER), "org_role": "owner"}])
        assert is_org_admin(core, _USER) is True

    def test_admin_is_admin(self):
        core = _FakeCoreClient([{"id": str(_USER), "org_role": "admin"}])
        assert is_org_admin(core, _USER) is True

    def test_member_is_not_admin(self):
        core = _FakeCoreClient([{"id": str(_USER), "org_role": "member"}])
        assert is_org_admin(core, _USER) is False

    def test_a_jwt_metadata_admin_claim_is_irrelevant_only_the_db_row_counts(self):
        """The exact scenario a spoofed `user_metadata.org_role='admin'`
        used to defeat: the TRUSTED row says `member`, so this is strictly
        `False` regardless of anything a caller-controlled token might
        claim (this predicate never even looks at `user_metadata`)."""
        core = _FakeCoreClient([{"id": str(_USER), "org_role": "member"}])
        assert is_org_admin(core, _USER) is False

    def test_no_row_is_not_admin(self):
        core = _FakeCoreClient([])
        assert is_org_admin(core, _USER) is False

    def test_none_user_id_is_not_admin(self):
        core = _FakeCoreClient([{"id": str(_USER), "org_role": "owner"}])
        assert is_org_admin(core, None) is False

    def test_custom_admin_roles_are_respected(self):
        core = _FakeCoreClient([{"id": str(_USER), "org_role": "lead"}])
        assert is_org_admin(core, _USER, admin_roles=frozenset({"lead"})) is True
        assert is_org_admin(core, _USER) is False


class TestRequireOrgAdminRole:
    def test_admin_passes_silently(self):
        core = _FakeCoreClient([{"id": str(_USER), "org_role": "admin"}])
        require_org_admin_role(core, _USER, "Chaves de API")  # no raise

    def test_member_raises_403_naming_the_context(self):
        core = _FakeCoreClient([{"id": str(_USER), "org_role": "member"}])
        with pytest.raises(HTTPException) as exc_info:
            require_org_admin_role(core, _USER, "Chaves de API")
        assert exc_info.value.status_code == 403
        assert "Chaves de API" in str(exc_info.value.detail)


class TestMakeRequireOrgAdmin:
    """The dependency-factory shape — a route can `Depends()` this INSTEAD
    OF its own `get_current_user_org`."""

    def _user(self, org_role_claim: str | None = "admin"):
        # `org_role_claim` lives on `user_metadata` — mirrors a token a
        # caller could themselves rewrite via `auth.updateUser({data})`.
        # `make_require_org_admin` must never read it.
        return SimpleNamespace(
            id=str(_USER), user_metadata={"org_role": org_role_claim},
        )

    def test_trusted_db_member_is_403_even_with_a_spoofed_admin_claim(self):
        auth = (self._user("admin"), "token", str(_ORG))

        async def _get_current_user_org():
            return auth

        core = _FakeCoreClient([{"id": str(_USER), "org_role": "member"}])
        dep = make_require_org_admin(_get_current_user_org, lambda: core)

        with pytest.raises(HTTPException) as exc_info:
            _run(dep(auth=auth))
        assert exc_info.value.status_code == 403

    def test_trusted_db_admin_passes_and_returns_the_auth_tuple(self):
        auth = (self._user("member"), "token", str(_ORG))

        async def _get_current_user_org():
            return auth

        core = _FakeCoreClient([{"id": str(_USER), "org_role": "owner"}])
        dep = make_require_org_admin(_get_current_user_org, lambda: core)

        result = _run(dep(auth=auth))
        assert result is auth

    def test_wired_through_a_real_fastapi_dependency(self):
        """Same ASGI-wiring proof `test_missing_credential_is_exactly_401
        _never_403_or_404_or_422` runs for `require_scopes` — a genuine
        `Depends(...)` resolution, not just the branch logic."""
        auth = (self._user("admin"), "token", str(_ORG))

        async def _get_current_user_org():
            return auth

        core = _FakeCoreClient([{"id": str(_USER), "org_role": "member"}])
        dep = make_require_org_admin(_get_current_user_org, lambda: core)

        app = FastAPI()

        @app.get("/admin-only")
        async def admin_only(auth: tuple = Depends(dep)):
            return {"user_id": auth[0].id}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/admin-only")
        assert resp.status_code == 403, resp.text
