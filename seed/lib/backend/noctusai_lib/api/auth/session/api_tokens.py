"""ApiTokenResolver Protocol + in-memory Fake + ``hash_token`` helper +
the ``SupabaseApiTokenResolver`` Real adapter.

Product / automation callers authenticate with opaque ``pk_*`` bearer
tokens that resolve to an ``AuthContext`` with ``caller_kind ==
"product"``. The raw secret is shown to the user **exactly once** (at
mint time); the database stores only the SHA-256 digest. Lookup
compares the digest of the incoming bearer against the stored hash.

Wave 1 shipped Protocol + Fake only. SEED-1
(``project-history/roadmaps/julia-agents-academia-2026-09.md``)
promotes ``SupabaseApiTokenResolver`` here from its
``products/social-wiring/backend/app/services/api_token_resolver.py``
fork — every product's ``api_tokens`` table lives in ITS OWN schema
(the seed has no generic one), so the Real adapter takes ``schema`` as
a required keyword rather than hard-coding one.

See ``KB § PATTERNS/seed-fake-real-adapter.md``.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from noctusai_lib.api.auth.session.types import AuthContext

logger = logging.getLogger(__name__)


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


class SupabaseApiTokenResolver:
    """Concrete :class:`ApiTokenResolver` over a Supabase admin client.

    Promoted from ``products/social-wiring/backend/app/services.
    api_token_resolver.SupabaseApiTokenResolver`` (SEED-1) —
    behaviour-preserving for that product: the ``pk_`` pre-filter,
    SHA-256 hash lookup, and best-effort ``last_used_at`` bump are
    unchanged. ``schema`` is now an explicit required keyword (was a
    module-level constant hard-coded to ``"social_wiring"``) since
    every product's ``api_tokens`` table lives in its own schema.

    Args:
        admin_client: A supabase client built with the service-role
            key (RLS would otherwise block the lookup — the caller
            hasn't authenticated yet, so resolving the bearer IS the
            authentication step).
        schema: The product's own Postgres schema (e.g.
            ``"social_wiring"``, ``"erp"``, ``"academia_de_reciclagem"``).
    """

    def __init__(self, admin_client: Any, *, schema: str) -> None:
        self._sb = admin_client
        self._schema = schema

    async def resolve(self, token_secret: str) -> AuthContext | None:
        # Cheap pre-filter — the dep already gates on this prefix but
        # ``ApiTokenResolver`` is a Protocol callers may invoke directly,
        # so we re-check here for defense in depth.
        if not token_secret.startswith("pk_"):
            return None

        digest = hash_token(token_secret)

        try:
            response = (
                self._sb.schema(self._schema)
                .table("api_tokens")
                .select(
                    "id, org_id, scopes, revoked_at, expires_at, "
                    "principal_agent_id, human_personal, minted_by"
                )
                .eq("token_hash", digest)
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception(
                "api_token_lookup_failed schema=%s digest_prefix=%s",
                self._schema,
                digest[:8],
            )
            return None

        rows = response.data or []
        if not rows:
            return None

        row = rows[0]
        try:
            token_id = UUID(str(row["id"]))
            org_id = UUID(str(row["org_id"]))
        except (KeyError, ValueError, TypeError):
            logger.warning(
                "api_token_row_malformed schema=%s digest_prefix=%s row_keys=%s",
                self._schema,
                digest[:8],
                list(row.keys()) if isinstance(row, dict) else type(row).__name__,
            )
            return None

        # Revoked or expired — SEED-1 §B.0: both refuse the token (401
        # via the dep), never distinguished to the caller.
        if row.get("revoked_at"):
            return None

        expires_at_raw = row.get("expires_at")
        expires_at: datetime | None = None
        if expires_at_raw:
            try:
                expires_at = datetime.fromisoformat(
                    str(expires_at_raw).replace("Z", "+00:00")
                )
            except ValueError:
                logger.warning(
                    "api_token_expires_at_unparseable schema=%s token_id=%s value=%r",
                    self._schema,
                    token_id,
                    expires_at_raw,
                )
                return None
            if expires_at <= datetime.now(timezone.utc):
                return None

        principal_agent_id: UUID | None = None
        raw_principal = row.get("principal_agent_id")
        if raw_principal:
            try:
                principal_agent_id = UUID(str(raw_principal))
            except (ValueError, TypeError):
                logger.warning(
                    "api_token_principal_agent_id_malformed schema=%s token_id=%s value=%r",
                    self._schema,
                    token_id,
                    raw_principal,
                )

        minted_by: UUID | None = None
        raw_minted_by = row.get("minted_by")
        if raw_minted_by:
            try:
                minted_by = UUID(str(raw_minted_by))
            except (ValueError, TypeError):
                logger.warning(
                    "api_token_minted_by_malformed schema=%s token_id=%s value=%r",
                    self._schema,
                    token_id,
                    raw_minted_by,
                )

        scopes = list(row.get("scopes") or [])
        human_personal = bool(row.get("human_personal") or False)

        # Best-effort last_used_at bump. Failure here must not break
        # the auth path — log and continue.
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            (
                self._sb.schema(self._schema)
                .table("api_tokens")
                .update({"last_used_at": now_iso})
                .eq("id", str(token_id))
                .execute()
            )
        except Exception:
            logger.warning(
                "api_token_last_used_update_failed schema=%s token_id=%s",
                self._schema,
                token_id,
            )

        return AuthContext(
            org_id=org_id,
            caller_kind="product",
            user_id=None,
            scopes=scopes,
            raw_token=str(token_id),
            api_token_id=token_id,
            principal_agent_id=principal_agent_id,
            expires_at=expires_at,
            human_personal=human_personal,
            minted_by=minted_by,
        )


__all__ = [
    "ApiTokenResolver",
    "FakeApiTokenResolver",
    "SupabaseApiTokenResolver",
    "hash_token",
]
