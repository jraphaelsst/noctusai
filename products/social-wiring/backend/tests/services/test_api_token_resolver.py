"""Tests for ``SupabaseApiTokenResolver`` — DB-backed ``pk_*`` lookup.

Exercises the resolver against ``MockSupabaseClient`` seeded with rows
matching the real ``social_wiring.api_tokens`` schema (the same shape
the W2 migration creates). No monkey-patching of internals — we inject
the mock client through the constructor (DI seam).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from noctusai_lib.api.auth.session import hash_token
from noctusai_lib.testing import MockSupabaseClient

from app.services.api_token_resolver import SupabaseApiTokenResolver


_ORG = UUID("00000000-0000-4000-8000-0000000000aa")
_TOKEN_ID = UUID("00000000-0000-4000-8000-0000000000bb")


def _row(
    secret: str,
    *,
    token_id: UUID = _TOKEN_ID,
    org_id: UUID = _ORG,
    scopes: list[str] | None = None,
    revoked: bool = False,
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
        resolver = SupabaseApiTokenResolver(client)

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

        resolver = SupabaseApiTokenResolver(_CaptureClient(client))

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
        resolver = SupabaseApiTokenResolver(client)

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
        resolver = SupabaseApiTokenResolver(client)

        ctx = await resolver.resolve(secret)

        assert ctx is None

    @pytest.mark.asyncio
    async def test_returns_none_for_malformed_non_pk_token(self):
        client = _client_with([])
        resolver = SupabaseApiTokenResolver(client)

        # Cheap pre-filter: bearer not starting with `pk_` rejected
        # without a DB round-trip.
        ctx = await resolver.resolve("sk_" + "y" * 32)

        assert ctx is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_token(self):
        client = _client_with([])
        resolver = SupabaseApiTokenResolver(client)

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
        resolver = SupabaseApiTokenResolver(client)

        ctx_good = await resolver.resolve(good)
        ctx_bad = await resolver.resolve(bad)

        assert ctx_good is not None
        assert ctx_bad is None
