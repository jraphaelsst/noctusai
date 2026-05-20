"""ApiTokenResolver Protocol + in-memory Fake + ``hash_token`` helper.

Product / automation callers authenticate with opaque ``pk_*`` bearer
tokens that resolve to an ``AuthContext`` with ``caller_kind ==
"product"``. The raw secret is shown to the user **exactly once** (at
mint time); the database stores only the SHA-256 digest. Lookup
compares the digest of the incoming bearer against the stored hash.

Wave 1 (this module) ships **Protocol + Fake only**. The real
``DBApiTokenResolver`` (Supabase-backed) lands in Wave 2 with the
``api_tokens`` table migration.

See ``KB § PATTERNS/seed-fake-real-adapter.md``.
"""

from __future__ import annotations

import hashlib
from typing import Protocol
from uuid import UUID, uuid4

from noctusai_lib.api.auth.session.types import AuthContext


def hash_token(secret: str) -> str:
    """Return the lowercase hex SHA-256 digest of ``secret``.

    The single point of truth for how raw API-token secrets become
    storage-safe identifiers. The DB migration that creates
    ``api_tokens`` stores ``token_hash CHAR(64)`` populated by this
    function; the resolver hashes the incoming bearer the same way
    before the equality check.

    SHA-256 (not bcrypt/argon2) by design: the secret already has
    ≥256 bits of entropy (``pk_<32-bytes-base64>``), so the brute-
    force-resistance of a slow KDF buys nothing while costing per-
    request latency.
    """
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class ApiTokenResolver(Protocol):
    """Resolves a raw ``pk_*`` bearer secret to an ``AuthContext``.

    Concrete impls hash the secret via ``hash_token(...)``, look up
    the row, verify it's not revoked, and project the row +
    ``api_tokens.scopes`` into an ``AuthContext`` with
    ``caller_kind="product"``.

    Returns ``None`` when:
      - no row matches the hash (unknown token),
      - the matching row's ``revoked_at`` is set,
      - or the token has expired (if expiry is implemented).

    Concrete impls MAY raise ``RevokedApiTokenError`` for the
    revoked-specific case so metric pipelines can distinguish
    "unknown" vs "revoked"; the dep treats both the same (401).
    """

    async def resolve(self, token_secret: str) -> AuthContext | None:
        ...


class FakeApiTokenResolver:
    """Deterministic in-memory ``ApiTokenResolver``.

    Tests register tokens via ``register(...)``, optionally revoke
    them with ``revoke(...)``, and resolve via the Protocol method.

    The Fake stores secrets *hashed* (matching the real adapter's
    storage shape) so tests can't accidentally rely on plaintext
    equality.
    """

    def __init__(self) -> None:
        # token_hash -> (api_token_id, org_id, scopes, revoked)
        self._tokens: dict[str, tuple[UUID, UUID, list[str], bool]] = {}

    def register(
        self,
        secret: str,
        *,
        org_id: UUID,
        scopes: list[str] | None = None,
        api_token_id: UUID | None = None,
    ) -> UUID:
        """Register a token (test helper).

        Returns the ``api_token_id`` assigned (auto-generated when
        not supplied).
        """
        token_id = api_token_id or uuid4()
        digest = hash_token(secret)
        self._tokens[digest] = (token_id, org_id, list(scopes or []), False)
        return token_id

    def revoke(self, secret: str) -> None:
        """Mark a registered token as revoked. No-op when unknown."""
        digest = hash_token(secret)
        entry = self._tokens.get(digest)
        if entry is None:
            return
        token_id, org_id, scopes, _was_revoked = entry
        self._tokens[digest] = (token_id, org_id, scopes, True)

    async def resolve(self, token_secret: str) -> AuthContext | None:
        digest = hash_token(token_secret)
        entry = self._tokens.get(digest)
        if entry is None:
            return None
        token_id, org_id, scopes, revoked = entry
        if revoked:
            return None
        return AuthContext(
            org_id=org_id,
            caller_kind="product",
            user_id=None,
            scopes=list(scopes),
            raw_token=str(token_id),
            api_token_id=token_id,
        )


__all__ = [
    "ApiTokenResolver",
    "FakeApiTokenResolver",
    "hash_token",
]
