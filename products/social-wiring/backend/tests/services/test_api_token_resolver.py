"""Tests for the seed's ``SupabaseApiTokenResolver`` — DB-backed ``pk_*``
lookup, as consumed by social-wiring (SEED-1 promotion).

Exercises the resolver against ``MockSupabaseClient`` seeded with rows
matching the real ``social_wiring.api_tokens`` schema (the same shape
the W2 migration + the SEED-1 ``105_api_tokens_scopes_and_audit.sql``
column-add create). No monkey-patching of internals — we inject the
mock client through the constructor (DI seam).

SEED-1 (``project-history/roadmaps/julia-agents-academia-2026-09.md``):
the product-local ``app.services.api_token_resolver.SupabaseApiTokenResolver``
is retired — this suite now targets the promoted seed adapter
(``noctusai_lib.api.auth.session.SupabaseApiTokenResolver``), which
takes ``schema`` as an explicit keyword instead of a module constant.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from noctusai_lib.api.auth.session import SupabaseApiTokenResolver, hash_token
from noctusai_lib.testing import MockSupabaseClient


_ORG = UUID("00000000-0000-4000-8000-0000000000aa")
_TOKEN_ID = UUID("00000000-0000-4000-8000-0000000000bb")
_AGENT = UUID("00000000-0000-4000-8000-0000000000cc")
_MINTER = UUID("00000000-0000-4000-8000-0000000000dd")


def _row(
    secret: str,
    *,
    token_id: UUID = _TOKEN_ID,
    org_id: UUID = _ORG,
    scopes: list[str] | None = None,
    revoked: bool = False,
    expires_at: str | None = None,
    principal_agent_id: str | None = None,
    human_personal: bool = False,
    minted_by: str | None = None,
) -> dict:
    """Build a fixture row matching the ``api_tokens`` insert shape."""
    return {
        "id": str(token_id),
        "org_id": str(org_id),
        "label": "test-token",
        "token_hash": hash_token(secret),
        "token_prefix": secret[:11],
        "scopes": list(scopes or []),
        "created_by": None,
        "created_at": "2026-05-20T00:00:00+00:00",
        "last_used_at": None,
        "revoked_at": "2026-05-20T01:00:00+00:00" if revoked else None,
        "expires_at": expires_at,
        "principal_agent_id": principal_agent_id,
        "human_personal": human_personal,
        "minted_by": minted_by,
    }


def _client_with(rows: list[dict]) -> MockSupabaseClient:
    """Build a mock client seeded with the rows the resolver SELECTs.

    `validate_schema=False` because `MockSupabaseClient` would otherwise
    require the migration cache to include the schema-qualified table —
    out of scope for unit tests of the resolver itself.
    """
    return MockSupabaseClient(rows, validate_schema=False)


class TestResolveSuccess:
    @pytest.mark.asyncio
    async def test_resolves_active_token_to_auth_context(self):
        secret = "pk_" + "a" * 32
        client = _client_with([_row(secret, scopes=["publish", "read"])])
        resolver = SupabaseApiTokenResolver(client, schema="social_wiring")

        ctx = await resolver.resolve(secret)

        assert ctx is not None
        assert ctx.caller_kind == "product"
        assert ctx.org_id == _ORG
        assert ctx.user_id is None
        assert ctx.scopes == ["publish", "read"]
        assert ctx.api_token_id == _TOKEN_ID
        assert ctx.raw_token == str(_TOKEN_ID)

    @pytest.mark.asyncio
    async def test_marks_last_used_at_on_hit(self):
        """The resolver MUST bump `last_used_at` on every successful
        resolution so the UI can surface stale-token warnings.

        `MockSupabaseClient.schema()` returns a NEW client (with its own
        empty `_tables`), so each `.schema(...).table(...)` chain builds
        a fresh `MockRequestBuilder`. To observe the update we wrap the
        client to capture every table-builder produced, then read
        `updated_payloads` off the captured set. This is DI / wrapping,
        not monkey-patching of our own code.
        """
        secret = "pk_" + "b" * 32
        client = _client_with([_row(secret)])
        captured_builders: list = []

        class _CaptureClient:
            def __init__(self, inner):
                self._inner = inner

            def schema(self, name):
                return _CaptureClient(self._inner.schema(name))

            def table(self, name):
                builder = self._inner.table(name)
                captured_builders.append(builder)
                return builder

            def from_(self, name):
                return self.table(name)

        resolver = SupabaseApiTokenResolver(_CaptureClient(client), schema="social_wiring")

        await resolver.resolve(secret)

        # At least one captured builder MUST carry an `updated_payloads`
        # entry mentioning `last_used_at`.
        all_updates = [
            p for b in captured_builders for p in b.updated_payloads
        ]
        assert all_updates, (
            "Expected at least one UPDATE call to bump last_used_at"
        )
        assert any("last_used_at" in p for p in all_updates), (
            f"Expected last_used_at in {all_updates!r}"
        )


class TestResolveMisses:
    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_token(self):
        # No rows at all → unknown token.
        client = _client_with([])
        resolver = SupabaseApiTokenResolver(client, schema="social_wiring")

        ctx = await resolver.resolve("pk_" + "x" * 32)

        assert ctx is None

    @pytest.mark.asyncio
    async def test_returns_none_for_revoked_token(self):
        # Row exists but `revoked_at` is set. The resolver's
        # `.is_("revoked_at", None)` filter (PostgREST `WHERE
        # revoked_at IS NULL`) MUST exclude the row — `MockSupabaseClient`
        # honours that filter via `_eval_is`. Returning a context for a
        # revoked token would be a security regression.
        secret = "pk_" + "c" * 32
        client = _client_with([_row(secret, revoked=True)])
        resolver = SupabaseApiTokenResolver(client, schema="social_wiring")

        ctx = await resolver.resolve(secret)

        assert ctx is None

    @pytest.mark.asyncio
    async def test_returns_none_for_malformed_non_pk_token(self):
        client = _client_with([])
        resolver = SupabaseApiTokenResolver(client, schema="social_wiring")

        # Cheap pre-filter: bearer not starting with `pk_` rejected
        # without a DB round-trip.
        ctx = await resolver.resolve("sk_" + "y" * 32)

        assert ctx is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_token(self):
        client = _client_with([])
        resolver = SupabaseApiTokenResolver(client, schema="social_wiring")

        ctx = await resolver.resolve("")

        assert ctx is None


class TestHashIsolation:
    """Asserts the resolver does NOT accept a token that doesn't
    hash to a stored digest — even when the stored row's plaintext
    prefix collides. The production invariant is *hash-equality, not
    string-equality* — a typo in the bearer must miss."""

    @pytest.mark.asyncio
    async def test_typo_in_secret_misses_lookup(self):
        good = "pk_" + "e" * 32
        bad = "pk_" + "f" * 32  # different secret → different hash
        client = _client_with([_row(good)])
        resolver = SupabaseApiTokenResolver(client, schema="social_wiring")

        ctx_good = await resolver.resolve(good)
        ctx_bad = await resolver.resolve(bad)

        assert ctx_good is not None
        assert ctx_bad is None


class TestSeed1TokenScopes:
    """SEED-1 (``julia-agents-academia-2026-09``): expiry enforcement +
    the new ``principal_agent_id`` / ``human_personal`` / ``minted_by``
    fields populated onto the resolved ``AuthContext``."""

    @pytest.mark.asyncio
    async def test_returns_none_for_expired_token(self):
        secret = "pk_" + "g" * 32
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        client = _client_with([_row(secret, expires_at=past)])
        resolver = SupabaseApiTokenResolver(client, schema="social_wiring")

        ctx = await resolver.resolve(secret)

        assert ctx is None

    @pytest.mark.asyncio
    async def test_resolves_unexpired_token_with_future_expires_at(self):
        secret = "pk_" + "h" * 32
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        client = _client_with([_row(secret, expires_at=future)])
        resolver = SupabaseApiTokenResolver(client, schema="social_wiring")

        ctx = await resolver.resolve(secret)

        assert ctx is not None
        assert ctx.expires_at is not None

    @pytest.mark.asyncio
    async def test_resolves_token_with_no_expires_at_set(self):
        """A pre-SEED-1 row (``expires_at IS NULL``, the backfill's
        pending state before the migration's UPDATE runs) still
        resolves — absence of an expiry is never treated as
        already-expired."""
        secret = "pk_" + "i" * 32
        client = _client_with([_row(secret, expires_at=None)])
        resolver = SupabaseApiTokenResolver(client, schema="social_wiring")

        ctx = await resolver.resolve(secret)

        assert ctx is not None
        assert ctx.expires_at is None

    @pytest.mark.asyncio
    async def test_populates_principal_agent_id_human_personal_minted_by(self):
        secret = "pk_" + "j" * 32
        client = _client_with(
            [
                _row(
                    secret,
                    principal_agent_id=str(_AGENT),
                    human_personal=True,
                    minted_by=str(_MINTER),
                )
            ]
        )
        resolver = SupabaseApiTokenResolver(client, schema="social_wiring")

        ctx = await resolver.resolve(secret)

        assert ctx is not None
        assert ctx.principal_agent_id == _AGENT
        assert ctx.human_personal is True
        assert ctx.minted_by == _MINTER

    @pytest.mark.asyncio
    async def test_defaults_when_new_columns_absent(self):
        """A row with no ``principal_agent_id`` / ``human_personal`` /
        ``minted_by`` set resolves with the ``AuthContext`` defaults —
        the back-compat case for every token minted before SEED-1."""
        secret = "pk_" + "k" * 32
        client = _client_with([_row(secret)])
        resolver = SupabaseApiTokenResolver(client, schema="social_wiring")

        ctx = await resolver.resolve(secret)

        assert ctx is not None
        assert ctx.principal_agent_id is None
        assert ctx.human_personal is False
        assert ctx.minted_by is None
