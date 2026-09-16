"""Unified auth-session module — the ``AuthContext`` resolver seam.

**What ships (Wave 1 — scaffolding):**

- ``AuthContext`` (``NamedTuple``) + ``CallerKind`` (``Literal``) +
  3 typed errors — the canonical caller-identity value object.
- ``SessionStore`` (``Protocol``) + ``FakeSessionStore`` — server-side
  session persistence for cookie-based human-user auth.
- ``ApiTokenResolver`` (``Protocol``) + ``FakeApiTokenResolver`` +
  ``hash_token(secret) -> hex`` — opaque ``pk_*`` bearer resolution.
- ``make_get_auth_context(...)`` — FastAPI dep factory composing the
  two adapters (+ optional legacy-JWT bridge) into one resolver with
  fixed priority: cookie → ``pk_*`` bearer → legacy-JWT → 401.

**What does NOT ship here (Wave 2 — consumer-side ``E-SW-AUTH``):**

- ``RedisSessionStore`` real adapter (Redis-backed).
- ``DBApiTokenResolver`` real adapter (Supabase ``api_tokens`` table).
- The login flow (Supabase sign-in → mint session → set cookie).
- Migration SQL for ``api_tokens`` (owned by ``E-MIGRATION``,
  file-disjoint).
- Consumer route migrations (``Depends(get_current_user_org)`` →
  ``Depends(get_auth_context)``).

See ``KB § PATTERNS/seed-fake-real-adapter.md`` for the
Protocol+Fake+Real+factory shape and
``projects/platform-auth-modernization/PROJECT.md`` §5 for the
wave-by-wave plan.
"""

from noctusai_lib.api.auth.session.api_tokens import (
    ApiTokenResolver,
    FakeApiTokenResolver,
    SupabaseApiTokenResolver,
    hash_token,
)
from noctusai_lib.api.auth.session.audit import (
    ApiTokenAuditWriter,
    FakeApiTokenAuditWriter,
    SupabaseApiTokenAuditWriter,
    make_api_token_audit_writer,
)
from noctusai_lib.api.auth.session.audit_middleware import (
    ApiTokenAuditMiddleware,
)
from noctusai_lib.api.auth.session.dep import (
    LegacyJwtResolver,
    make_get_auth_context,
)
from noctusai_lib.api.auth.session.factory import (
    make_session_store,
)
from noctusai_lib.api.auth.session.scopes import (
    CallerRestriction,
    require_scopes,
    resolve_org_role,
)
from noctusai_lib.api.auth.session.redis_store import (
    RedisSessionStore,
)
from noctusai_lib.api.auth.session.store import (
    FakeSessionStore,
    SessionStore,
)
from noctusai_lib.api.auth.session.session_revoke import (
    FakeSessionRevoker,
    SessionRevoker,
    SupabaseSessionRevoker,
    make_default_revoke_fn,
    make_session_revoker,
)
from noctusai_lib.api.auth.session.token_exchange import (
    FakeTokenExchanger,
    RefreshResult,
    SupabaseTokenExchanger,
    TokenExchangeError,
    TokenExchanger,
    make_default_refresh_fn,
    make_token_exchanger,
)
from noctusai_lib.api.auth.session.token_admin import (
    ApiTokenInfo,
    FakeProductTokenAdmin,
    MintedApiToken,
    ProductTokenAdmin,
    SupabaseProductTokenAdmin,
    build_api_token_row,
    make_product_token_admin,
    mint_token_secret,
)
from noctusai_lib.api.auth.session.types import (
    AuthContext,
    CallerKind,
    ExpiredSessionError,
    InvalidCredentialsError,
    RevokedApiTokenError,
    SessionTokens,
)

__all__ = [
    "ApiTokenAuditMiddleware",
    "ApiTokenInfo",
    "ApiTokenAuditWriter",
    "ApiTokenResolver",
    "AuthContext",
    "CallerKind",
    "CallerRestriction",
    "ExpiredSessionError",
    "FakeApiTokenAuditWriter",
    "FakeApiTokenResolver",
    "FakeProductTokenAdmin",
    "FakeSessionRevoker",
    "FakeSessionStore",
    "FakeTokenExchanger",
    "InvalidCredentialsError",
    "LegacyJwtResolver",
    "MintedApiToken",
    "ProductTokenAdmin",
    "RedisSessionStore",
    "RefreshResult",
    "RevokedApiTokenError",
    "SessionRevoker",
    "SessionStore",
    "SessionTokens",
    "SupabaseApiTokenAuditWriter",
    "SupabaseApiTokenResolver",
    "SupabaseProductTokenAdmin",
    "SupabaseSessionRevoker",
    "SupabaseTokenExchanger",
    "TokenExchangeError",
    "TokenExchanger",
    "build_api_token_row",
    "hash_token",
    "make_api_token_audit_writer",
    "make_default_refresh_fn",
    "make_default_revoke_fn",
    "make_get_auth_context",
    "make_product_token_admin",
    "make_session_revoker",
    "make_session_store",
    "make_token_exchanger",
    "mint_token_secret",
    "require_scopes",
    "resolve_org_role",
]
