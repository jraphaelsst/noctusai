"""SEED-1 (project-history/roadmaps/julia-agents-academia-2026-09.md,
contract §B.0) — colocated seed-lib coverage for ``AuthContext``'s new
fields, ``SupabaseApiTokenResolver``, and ``require_scopes``.

NOT CI-gating (``seed/lib/backend/tests/`` is not run by CI — open
drift, 2026-09-09). The CI-gating leg for this same surface is
``mcp/noctusai/tests/test_seed_token_scopes.py``; this file is the
local-dev / build-learn-cache colocated copy the seed-fake-real-adapter
convention expects every seed IO module to ship.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi import HTTPException

from noctusai_lib.api.auth.session import (
    AuthContext,
    SupabaseApiTokenResolver,
    hash_token,
    require_scopes,
)
from noctusai_lib.testing import MockSupabaseClient


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


_ORG = UUID("00000000-0000-4000-8000-0000000000aa")
_TOKEN_ID = UUID("00000000-0000-4000-8000-0000000000bb")
_AGENT = UUID("00000000-0000-4000-8000-0000000000cc")
_USER = UUID("00000000-0000-4000-8000-0000000000ee")


def test_auth_context_old_shape_still_constructs():
    ctx = AuthContext(_ORG, "user", _USER, [], "raw", None)
    assert ctx.principal_agent_id is None
    assert ctx.expires_at is None
    assert ctx.human_personal is False
    assert ctx.minted_by is None


class TestResolverExpiryAndRevocation:
    def _client(self, rows):
        return MockSupabaseClient(rows, validate_schema=False)

    def test_revoked_returns_none(self):
        secret = "pk_" + "a" * 32
        row = {
            "id": str(_TOKEN_ID),
            "org_id": str(_ORG),
            "scopes": [],
            "revoked_at": "2026-01-01T00:00:00+00:00",
            "expires_at": None,
            "principal_agent_id": None,
            "human_personal": False,
            "minted_by": None,
            "token_hash": hash_token(secret),
        }
        resolver = SupabaseApiTokenResolver(self._client([row]), schema="academia_de_reciclagem")

        assert _run(resolver.resolve(secret)) is None

    def test_expired_returns_none(self):
        secret = "pk_" + "b" * 32
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        row = {
            "id": str(_TOKEN_ID),
            "org_id": str(_ORG),
            "scopes": [],
            "revoked_at": None,
            "expires_at": past,
            "principal_agent_id": None,
            "human_personal": False,
            "minted_by": None,
            "token_hash": hash_token(secret),
        }
        resolver = SupabaseApiTokenResolver(self._client([row]), schema="academia_de_reciclagem")

        assert _run(resolver.resolve(secret)) is None

    def test_valid_populates_new_fields(self):
        secret = "pk_" + "c" * 32
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        row = {
            "id": str(_TOKEN_ID),
            "org_id": str(_ORG),
            "scopes": ["academia:read"],
            "revoked_at": None,
            "expires_at": future,
            "principal_agent_id": str(_AGENT),
            "human_personal": True,
            "minted_by": str(_USER),
            "token_hash": hash_token(secret),
        }
        resolver = SupabaseApiTokenResolver(self._client([row]), schema="academia_de_reciclagem")

        ctx = _run(resolver.resolve(secret))

        assert ctx is not None
        assert ctx.principal_agent_id == _AGENT
        assert ctx.human_personal is True
        assert ctx.minted_by == _USER


class _FakeCoreClient:
    def __init__(self, rows):
        self._sb = MockSupabaseClient(rows, validate_schema=False, schema="public")

    def from_(self, name):
        return self._sb.from_(name)


async def _ctx_dep(ctx):
    return ctx


class TestRequireScopesMatrix:
    def test_product_missing_scope_403(self):
        ctx = AuthContext(
            org_id=_ORG,
            caller_kind="product",
            user_id=None,
            scopes=[],
            raw_token=str(_TOKEN_ID),
            api_token_id=_TOKEN_ID,
        )
        dep = require_scopes("academia:kb:write", get_auth_context=lambda: _ctx_dep(ctx))

        with pytest.raises(HTTPException) as exc_info:
            _run(dep(ctx=ctx))
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "scope_missing"

    def test_user_outside_role_set_403(self):
        ctx = AuthContext(
            org_id=_ORG,
            caller_kind="user",
            user_id=_USER,
            scopes=[],
            raw_token="session-id",
            api_token_id=None,
        )
        core_client = _FakeCoreClient([{"id": str(_USER), "org_role": "viewer"}])
        dep = require_scopes(
            user_roles=frozenset({"owner", "admin"}),
            get_auth_context=lambda: _ctx_dep(ctx),
            get_core_client=lambda: core_client,
        )

        with pytest.raises(HTTPException) as exc_info:
            _run(dep(ctx=ctx))
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "role_missing"

    def test_product_only_rejects_user_403(self):
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
