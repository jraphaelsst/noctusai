"""Coverage for erp-imobiliario's seed-mounted ``/api/settings/api-tokens``
routes (SW1, ``project-history/roadmaps/julia-agents-academia-2026-09.md``).

``standard_routers=["auth"]`` (``app/main.py``) mounts the seed's
``noctusai_seed.auth_router.create_auth_router`` mint / list / revoke
endpoints unchanged — before this file, ZERO tests exercised them on
erp.

**Two auth shapes, deliberately different from each other.**

``app/main.py``'s own docstring explains why erp's mount is reachable
by NEITHER of the shared test fixtures' usual credentials: it passes
no ``legacy_jwt_resolver`` (unlike social-wiring's own direct
``create_auth_router(...)`` call), so the mounted router's internal
``get_auth_context`` closure 401s the shared ``client`` fixture's
default ``Authorization: Bearer test-token-valid`` with "Bearer token
not recognised" — and that closure is not module-exported, so there
is no ``app.dependency_overrides`` seam onto it either. A cookie
session is technically possible via
``noctusai_seed.auth_router.get_session_store(settings)``, but that
store's Real/Fake choice depends on ``settings.redis_url`` — an
AMBIENT env value this test file must not gamble on (a Redis URL set
but unreachable in a given run environment would hang/fail session
creation for reasons entirely unrelated to the route logic under
test).

So:

  - **The ONE true unauthenticated-401 case** goes through the REAL
    HTTP → dependency-resolution chain (``client.raw()``, no
    credential at all) — the "no credential" branch of
    ``make_get_auth_context`` raises 401 BEFORE touching any session
    store, so it is unaffected by the ambient-Redis question. This is
    the auth-boundary assertion
    (``KB § PATTERNS/compliance/auth-boundary-false-green.md``) — strict
    ``== 401``, never ``in (401, 404, 422)``.
  - **Every authenticated case** calls the mounted router's OWN
    endpoint function directly with an explicit ``ctx=AuthContext(...)``
    keyword, bypassing FastAPI's ``Depends(...)`` resolution
    machinery on purpose — the SAME technique
    ``mcp/noctusai/tests/test_seed_token_scopes.py`` already
    establishes for this exact auth-session package ("each dependency
    closure is invoked directly with an explicit ctx= argument"). The
    endpoint objects are looked up on the REAL mounted ``app.routes``
    (not a parallel ``create_auth_router(...)`` reconstruction), so
    this exercises the EXACT production code path erp serves — DB
    writes via ``deps.get_admin_client()``, the trusted-DB admin-role
    re-check via ``deps.get_core_client()``, Pydantic body validation
    — everything except the outer dependency-injection/session-store
    layer, which the 401 case above already covers independently.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from noctusai_lib.api.auth.session import AuthContext

_ORG = "00000000-0000-4000-8000-0000000000aa"
_USER = "00000000-0000-4000-8000-0000000000bb"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _expires_soon() -> str:
    """A valid ``expires_at`` (contract §B.0: required, <= 90 days ahead)."""
    return (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()


def _user_ctx() -> AuthContext:
    return AuthContext(
        org_id=UUID(_ORG),
        caller_kind="user",
        user_id=UUID(_USER),
        scopes=[],
        raw_token="direct-call-not-a-real-session",
        api_token_id=None,
    )


def _endpoint(method: str, path: str):
    """Look up the REAL endpoint function the mounted app serves for
    ``method path`` (see module docstring for why this bypasses HTTP)."""
    from app.main import app

    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(
            route, "methods", set()
        ):
            return route.endpoint
    raise AssertionError(f"no mounted route for {method} {path}")


def _admin_noctus_users_row(client) -> None:
    """Seed the trusted-DB ``noctus_users`` row ``_require_org_admin``
    reads (``deps.get_core_client()`` — the SAME ``client.mock_supabase``
    instance under test)."""
    client.mock_supabase.set_table_data(
        "noctus_users",
        [{"id": _USER, "org_id": _ORG, "org_role": "owner"}],
    )


class _SchemaIdentityClient:
    """Wraps a ``MockSupabaseClient`` so ``.schema(name)`` returns SELF
    instead of a fresh, empty-per-table-cache client.

    ``MockSupabaseClient.schema(name)`` constructs a BRAND NEW instance
    on every call (documented defect — see
    ``app/dependencies.py::get_scoped_admin_client`` in social-wiring,
    the production-side fix for the same defect). ``SupabaseApiTokenResolver
    .resolve()`` always calls ``self._sb.schema(self._schema)`` before
    ``.table(...)`` — in PRODUCTION the admin client it receives is
    ALREADY schema-scoped at construction, so a real Supabase client
    re-scoping to the SAME schema is a no-op; on the mock, re-scoping
    silently drops every row written earlier through the SAME
    ``client.mock_supabase`` instance the mint/revoke calls wrote to.
    This proxy restores identity-scoping for the mock ONLY, so the
    resolver in this test sees the SAME row state the write above it
    produced — the honest way to test "revoke's DB write is understood
    by the SAME resolver contract the platform ships", without erp
    wiring `pk_*` auth onto any business route (explicitly out of
    SEED-1's scope per the roadmap contract's §B.0 erp note).
    """

    def __init__(self, inner):
        self._inner = inner

    def schema(self, name):  # noqa: ARG002 — identity by design
        return self

    def table(self, name):
        return self._inner.table(name)


class TestApiTokensCreate:
    """``POST /api/settings/api-tokens`` — owner/admin only, secret
    returned exactly once, ``minted_by`` recorded on the row."""

    def test_unauthenticated_mint_is_exactly_401(self, client):
        resp = client.raw().post(
            "/api/settings/api-tokens",
            json={"label": "x", "scopes": [], "expires_at": _expires_soon()},
        )
        assert resp.status_code == 401, resp.text

    def test_missing_expires_at_rejected(self, client):
        """``expires_at`` is a REQUIRED field on ``ApiTokenCreateRequest``
        (contract §B.0) — omitting it is the exact shape FastAPI's own
        body-parsing turns into a 422 response; asserting the
        ``pydantic.ValidationError`` here exercises the SAME validator
        the HTTP layer calls, without this test depending on how the
        caller authenticated (see module docstring)."""
        from noctusai_seed.auth_router import ApiTokenCreateRequest

        with pytest.raises(ValidationError):
            ApiTokenCreateRequest.model_validate(
                {"label": "julia-academia", "scopes": ["academia:read"]}
            )

    def test_expires_at_too_far_ahead_rejected(self, client):
        """> 90 days ahead → the model's own ``@field_validator`` raises
        (contract §B.0), same rationale as the missing-field case above."""
        from noctusai_seed.auth_router import ApiTokenCreateRequest

        too_far = (datetime.now(timezone.utc) + timedelta(days=91)).isoformat()
        with pytest.raises(ValidationError):
            ApiTokenCreateRequest.model_validate(
                {
                    "label": "julia-academia",
                    "scopes": ["academia:read"],
                    "expires_at": too_far,
                }
            )

    def test_valid_admin_mint_returns_201_with_secret_once_and_minted_by_set(
        self, client
    ):
        from noctusai_seed.auth_router import ApiTokenCreateRequest

        _admin_noctus_users_row(client)
        mint = _endpoint("POST", "/api/settings/api-tokens")
        body = ApiTokenCreateRequest.model_validate(
            {
                "label": "julia-academia",
                "scopes": ["academia:read"],
                "expires_at": _expires_soon(),
            }
        )

        result = _run(mint(body=body, ctx=_user_ctx()))

        assert result.label == "julia-academia"
        assert result.token.startswith("pk_")
        assert result.prefix.startswith("pk_")
        assert result.scopes == ["academia:read"]
        assert result.expires_at

        # The secret is returned in THIS response only — the DB row
        # persists just the hash, never the raw secret; the write's
        # `minted_by` attributes the mint to the caller.
        inserted = client.mock_supabase.table("api_tokens").inserted_payloads
        assert len(inserted) == 1
        row = inserted[0]
        assert row["minted_by"] == _USER
        assert row["token_hash"] != result.token
        assert "token" not in row

    def test_non_admin_caller_is_403(self, client):
        """``_require_org_admin`` refuses a non-owner/admin org role —
        the SAME trusted-DB gate ``test_missing_expires_at_rejected``'s
        docstring references. Exercised here directly to confirm the
        mounted route (not just the model) enforces it."""
        from noctusai_seed.auth_router import ApiTokenCreateRequest

        client.mock_supabase.set_table_data(
            "noctus_users",
            [{"id": _USER, "org_id": _ORG, "org_role": "member"}],
        )
        mint = _endpoint("POST", "/api/settings/api-tokens")
        body = ApiTokenCreateRequest.model_validate(
            {"label": "x", "scopes": [], "expires_at": _expires_soon()}
        )

        with pytest.raises(HTTPException) as exc_info:
            _run(mint(body=body, ctx=_user_ctx()))

        assert exc_info.value.status_code == 403


class TestApiTokensList:
    """``GET /api/settings/api-tokens`` — never leaks the raw secret or
    its hash."""

    def test_list_does_not_leak_secrets(self, client):
        client.mock_supabase.set_table_data(
            "api_tokens",
            [
                {
                    "id": "10000000-0000-4000-8000-000000000001",
                    "org_id": _ORG,
                    "label": "julia-academia",
                    "token_hash": "deadbeef" * 8,
                    "token_prefix": "pk_abc12345",
                    "scopes": ["academia:read"],
                    "created_at": "2026-09-01T00:00:00+00:00",
                    "last_used_at": None,
                    "revoked_at": None,
                }
            ],
        )
        list_tokens = _endpoint("GET", "/api/settings/api-tokens")

        result = _run(list_tokens(ctx=_user_ctx()))

        assert len(result) == 1
        item = result[0]
        assert not hasattr(item, "token")
        assert not hasattr(item, "token_hash")
        assert item.prefix == "pk_abc12345"


class TestApiTokensRevoke:
    """``DELETE /api/settings/api-tokens/{id}`` soft-revokes by
    stamping ``revoked_at`` — a subsequent resolve of the same secret
    against the SAME (schema-identity-wrapped) admin client is refused,
    proving the write erp's revoke route makes is the SAME shape the
    seed's ``SupabaseApiTokenResolver`` refuses on (contract §B.0:
    revoked or expired both refuse via a ``None`` resolve, mapped to
    401 by the dep)."""

    def test_revoke_then_resolve_refuses_the_token(self, client):
        from noctusai_lib.api.auth.session import SupabaseApiTokenResolver, hash_token

        _admin_noctus_users_row(client)
        secret = "pk_" + "a" * 64
        row_id = uuid4()
        # Seed the row directly — bypasses re-deriving the raw secret
        # from a mint response, and lets this test assert on the exact
        # `hash_token(secret)` the resolver re-computes.
        client.mock_supabase.set_table_data(
            "api_tokens",
            [
                {
                    "id": str(row_id),
                    "org_id": _ORG,
                    "label": "julia-academia",
                    "token_hash": hash_token(secret),
                    "token_prefix": secret[:11],
                    "scopes": ["academia:read"],
                    "created_at": "2026-09-01T00:00:00+00:00",
                    "last_used_at": None,
                    "revoked_at": None,
                    "expires_at": _expires_soon(),
                }
            ],
        )

        identity_client = _SchemaIdentityClient(client.mock_supabase)
        resolver = SupabaseApiTokenResolver(identity_client, schema="erp")

        # Before revoke: the token resolves.
        ctx_before = _run(resolver.resolve(secret))
        assert ctx_before is not None
        assert str(ctx_before.org_id) == _ORG

        revoke = _endpoint("DELETE", "/api/settings/api-tokens/{token_id}")
        _run(revoke(token_id=row_id, ctx=_user_ctx()))

        # After revoke: the SAME secret is refused.
        ctx_after = _run(resolver.resolve(secret))
        assert ctx_after is None

    def test_revoke_unknown_token_is_404(self, client):
        _admin_noctus_users_row(client)
        revoke = _endpoint("DELETE", "/api/settings/api-tokens/{token_id}")

        with pytest.raises(HTTPException) as exc_info:
            _run(revoke(token_id=uuid4(), ctx=_user_ctx()))

        assert exc_info.value.status_code == 404
