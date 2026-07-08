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
    hash_token,
)
from noctusai_lib.api.auth.session.dep import (
    LegacyJwtResolver,
    make_get_auth_context,
)
from noctusai_lib.api.auth.session.factory import (
    make_session_store,
)
from noctusai_lib.api.auth.session.redis_store import (
    RedisSessionStore,
)
from noctusai_lib.api.auth.session.store import (
    FakeSessionStore,
    SessionStore,
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
from noctusai_lib.api.auth.session.types import (
    AuthContext,
    CallerKind,
    ExpiredSessionError,
    InvalidCredentialsError,
    RevokedApiTokenError,
    SessionTokens,
)

__all__ = [
    "ApiTokenResolver",
    "AuthContext",
    "CallerKind",
    "ExpiredSessionError",
    "FakeApiTokenResolver",
    "FakeSessionStore",
    "FakeTokenExchanger",
    "InvalidCredentialsError",
    "LegacyJwtResolver",
    "RedisSessionStore",
    "RefreshResult",
    "RevokedApiTokenError",
    "SessionStore",
    "SessionTokens",
    "SupabaseTokenExchanger",
    "TokenExchangeError",
    "TokenExchanger",
    "hash_token",
    "make_default_refresh_fn",
    "make_get_auth_context",
    "make_session_store",
    "make_token_exchanger",
]
