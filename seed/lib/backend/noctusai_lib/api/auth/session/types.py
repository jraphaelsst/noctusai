"""Value objects + errors for the unified auth-session resolver.

Lands as the **canonical caller-identity carrier** for any FastAPI
route under the modernized auth scheme: one ``AuthContext`` regardless
of whether the caller is a human user (HttpOnly cookie → Redis-backed
session store) or a product/automation API token (opaque ``pk_*``
bearer → DB-backed token row).

Used by the dep returned from
``noctusai_lib.api.auth.session.make_get_auth_context(...)``. Wave 2
(consumer-side, owned by ``E-SW-AUTH``) wires the real ``SessionStore``
+ ``ApiTokenResolver`` implementations; Wave 1 (this scaffolding) ships
Protocols + Fakes only.

See also: ``KB § PATTERNS/seed-fake-real-adapter.md`` (Protocol + Fake +
Real + factory shape mirrored from ``integrations/google_calendar``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, NamedTuple
from uuid import UUID

# ``Literal`` exposed as a single-source-of-truth for callers that
# need to type-narrow on caller_kind without re-declaring the union.
CallerKind = Literal["user", "product"]


class AuthContext(NamedTuple):
    """Canonical caller identity, independent of the credential shape.

    Returned by ``make_get_auth_context(...)`` for every authenticated
    request. Routes that previously took
    ``Depends(get_current_user_org)`` will, post-migration, take
    ``Depends(get_auth_context)`` and read ``ctx.org_id`` /
    ``ctx.caller_kind`` instead of unpacking the legacy ``(user,
    token, org_id)`` tuple.

    Fields:
        org_id: Organization the caller is acting on behalf of. For
            user sessions this is the user's home org (sync'd from
            Supabase ``user_metadata.org_id`` at session-create time).
            For product/automation tokens this is the org that owns
            the token (typically the org that minted it via the
            API-tokens management UI).
        caller_kind: ``"user"`` for human-session callers,
            ``"product"`` for ``pk_*`` automation/integration tokens.
            Route handlers branch on this when the policy differs
            (e.g. UI-only endpoints reject ``"product"``).
        user_id: Supabase user id when ``caller_kind == "user"``;
            ``None`` for ``"product"`` (tokens are not user-bound).
        scopes: List of permission scopes attached to the credential.
            User sessions carry the user's org-role-derived scope set;
            product tokens carry the explicit scopes assigned at mint
            time. Authorization checks should consult ``scopes``
            instead of re-resolving the role.
        raw_token: An *opaque identifier* for the credential — the
            session id for users or the api_token id (NOT the raw
            secret) for products. Used for audit logging, never to
            re-authenticate. The secret value itself never enters the
            ``AuthContext`` after resolution.
        api_token_id: Convenience accessor; the token row id for
            ``caller_kind == "product"`` and ``None`` for user
            sessions. Lets handlers join against ``api_tokens`` for
            rate-limit / scope-policy lookups without re-resolving.
        principal_agent_id: SEED-1 (Julia/academia auth posture). For a
            ``caller_kind == "product"`` token minted on behalf of an
            automation principal (e.g. an ``agents`` product agent
            acting through a product token), the agent's id — carried
            through so a write can attribute ``kb_revisions.agent_id``
            without a second lookup. ``None`` for user sessions and for
            product tokens with no bound principal (e.g. a plain n8n/
            MCP integration token). Defaulted so every existing
            constructor call keeps working unchanged.
        expires_at: SEED-1. The token row's expiry (product tokens
            only); ``None`` for user sessions, which expire via the
            session TTL instead. Carried onto the resolved context for
            callers that want to warn/display remaining lifetime
            without a second DB round-trip. The RESOLVER is what
            refuses an already-expired token (returns ``None`` → 401);
            this field is a read-only echo of that check, never
            re-validated by consumers.
        human_personal: SEED-1. ``True`` for a product token flagged at
            mint time as a human's PERSONAL automation token (e.g.
            terminal-Julia's own token) rather than a control-plane
            token acting on behalf of an agent. A write from a
            ``human_personal`` token needs no ``X-Approval-Assertion``
            (contract §B.0) and records ``kb_revisions.user_id =
            minted_by`` instead of an agent attribution. ``False`` by
            default for both user sessions and ordinary product
            tokens.
        minted_by: SEED-1. The Supabase user id of the human who minted
            this token (``ApiTokenCreateRequest`` → ``ctx.user_id`` at
            mint time). ``None`` for user sessions (irrelevant — the
            session already carries ``user_id``) and for any token
            minted before this field existed.
    """

    org_id: UUID
    caller_kind: CallerKind
    user_id: UUID | None
    scopes: list[str]
    raw_token: str
    api_token_id: UUID | None
    principal_agent_id: UUID | None = None
    expires_at: datetime | None = None
    human_personal: bool = False
    minted_by: UUID | None = None


class SessionTokens(NamedTuple):
    """Server-side-only token bundle for a user session.

    This is the counterpart to :class:`AuthContext`: where ``AuthContext``
    is the *caller-facing* identity that route handlers receive (and which
    deliberately NEVER carries the Supabase tokens — see ``raw_token``), a
    ``SessionTokens`` is what the :class:`SessionStore` hands to the
    :class:`~noctusai_lib.api.auth.session.token_exchange.TokenExchanger`
    so it can mint an RLS-scoped Supabase client for the request.

    It is read/written by ``SessionStore.read_tokens`` / ``write_tokens``
    ONLY — never returned from ``lookup`` and never serialized to the
    browser. The refresh token (and the cached access token) live in the
    store **encrypted at rest** (SEC-3); a ``SessionTokens`` holds the
    *decrypted* values, alive only in process memory for the duration of a
    token-exchange.

    Fields:
        refresh_token: The Supabase refresh token for this session. Used by
            the exchanger to obtain a fresh access token near expiry. Supabase
            rotates this on every refresh (reuse-detection), so the exchanger
            MUST write the rotated value back (SEC-2).
        access_token: The most-recently-minted Supabase access token, cached
            so the vast majority of requests need NO upstream refresh call
            (SEC-2). ``None`` before the first exchange.
        access_expires_at: Unix epoch seconds at which ``access_token``
            expires (Supabase ``Session.expires_at``). ``None`` when no access
            token is cached. The exchanger refreshes only when within a small
            skew of this time.
    """

    refresh_token: str
    access_token: str | None
    access_expires_at: int | None


# ── Errors ───────────────────────────────────────────────────────────


class InvalidCredentialsError(Exception):
    """Raised by stores/resolvers when a credential is malformed or
    not recognised. The dep translates this into ``HTTPException(401)``
    so route handlers never see it directly."""


class ExpiredSessionError(Exception):
    """Raised by ``SessionStore.lookup`` (or callers polling the
    store) when a session row exists but has aged past its TTL.
    Distinguishes ageout from outright absence so caller-side metrics
    can track the rate independently."""


class RevokedApiTokenError(Exception):
    """Raised by ``ApiTokenResolver.resolve`` when a token's row is
    found but has been marked revoked. Distinguishes revocation from
    "no row at all" so the dep can return 401 with a more pointed
    detail string for users debugging a revoked-token error."""


__all__ = [
    "AuthContext",
    "SessionTokens",
    "CallerKind",
    "ExpiredSessionError",
    "InvalidCredentialsError",
    "RevokedApiTokenError",
]
