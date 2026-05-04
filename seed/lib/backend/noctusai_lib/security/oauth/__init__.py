"""Generic OAuth callback infrastructure — Protocol + Google + Fake + factory + router.

WHY this module
---------------
Before this lift, every product hand-rolled its own
`/api/oauth/<vendor>/...` endpoints. Path conventions disagreed
(`/api/auth/oauth/callback`, `/oauth/google/callback`,
`/api/oauth/google/status`). The token-exchange code drifted across
products. The seed shipped a Google adapter (in
`integrations/google_calendar/oauth_adapter.py`) but it was coupled to
the calendar use case — it converted resolved credentials into a
Calendar API client; it did NOT provide the dance itself.

This module collapses all of that into one generic surface:

  - `OAuthProvider` — the four-method Protocol every vendor satisfies.
  - `GoogleProvider` — concrete implementation (lifted from the
    media-scheduling product's hand-rolled router + the calendar
    oauth_adapter's refresh logic).
  - `FakeOAuthProvider` — deterministic, network-free; for tests + FakeMode.
  - `make_oauth_provider(...)` — factory; today only `"google"` is
    registered. Designed to grow (Stripe, Slack, ...).
  - `oauth_router(*providers, on_callback=...)` — FastAPI APIRouter
    that mounts authorize + callback + refresh + revoke at
    `/api/oauth/<provider>/...` for every registered provider.

After this module, OAuth-path inconsistency becomes structurally
impossible: every product mounts the same router, the path is fixed,
and the four-method contract is enforced by Protocol.

Token persistence is the consumer's concern — pair the router with
`noctusai_lib.security.encrypted_tokens.encrypt(...)` inside the
`on_callback` hook to store at-rest-encrypted access + refresh tokens.

Public surface
--------------
- Value objects: `AuthorizationURL`, `TokenSet`, `OAuthCallbackResult`.
- Contract: `OAuthProvider` (Protocol).
- Concrete: `GoogleProvider`, `FakeOAuthProvider`.
- Wiring: `make_oauth_provider`, `oauth_router`.

Filed in `projects/seed-hardening-from-youtube-crawler/` Phase 2.3.
"""

from noctusai_lib.security.oauth.factory import make_oauth_provider
from noctusai_lib.security.oauth.fake import FakeOAuthProvider
from noctusai_lib.security.oauth.google_provider import GoogleProvider
from noctusai_lib.security.oauth.protocol import OAuthProvider
from noctusai_lib.security.oauth.router import CallbackHook, oauth_router
from noctusai_lib.security.oauth.types import (
    AuthorizationURL,
    OAuthCallbackResult,
    TokenSet,
)


__all__ = [
    "AuthorizationURL",
    "CallbackHook",
    "FakeOAuthProvider",
    "GoogleProvider",
    "OAuthCallbackResult",
    "OAuthProvider",
    "TokenSet",
    "make_oauth_provider",
    "oauth_router",
]
