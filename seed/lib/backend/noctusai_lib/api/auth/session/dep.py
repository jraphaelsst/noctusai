"""``make_get_auth_context`` — the FastAPI dependency factory.

Wires a ``SessionStore`` + ``ApiTokenResolver`` (+ optional legacy-JWT
bridge) into one async dependency that produces an ``AuthContext``
regardless of how the caller authenticated. Resolution priority:

  1. Cookie ``<session_cookie_name>`` → ``session_store.lookup``
  2. ``Authorization: Bearer pk_*`` → ``api_token_resolver.resolve``
  3. ``Authorization: Bearer <jwt>`` AND ``legacy_jwt_resolver`` → bridge
  4. → ``HTTPException(401)``

Order matters: cookies win over bearer tokens so a UI session can't
be silently overridden by an automation token attached to the same
request (the security-sensitive case is the inverse — automation
tokens scoped narrowly, must not inherit user-session privileges).

Wave 2 consumer projects pass real adapters; Wave 1 dev/test wiring
passes ``FakeSessionStore`` + ``FakeApiTokenResolver``. The factory
itself is identical in both paths — adapter swap is the entire
"go to production" change.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import Cookie, Header, HTTPException

from noctusai_lib.api.auth.session.api_tokens import ApiTokenResolver
from noctusai_lib.api.auth.session.store import SessionStore
from noctusai_lib.api.auth.session.types import AuthContext

LegacyJwtResolver = Callable[[str], Awaitable[AuthContext | None]]
"""Optional bridge for the existing JWT-only auth scheme.

Receives the raw bearer payload (without ``Bearer `` prefix), returns
an ``AuthContext`` if the JWT validates against the legacy verifier,
or ``None`` to fall through to 401. Lets the new dep coexist with
``make_get_current_user`` callers during the migration window.
"""


def make_get_auth_context(
    *,
    session_store: SessionStore,
    api_token_resolver: ApiTokenResolver,
    legacy_jwt_resolver: LegacyJwtResolver | None = None,
    session_cookie_name: str = "nai_session",
) -> Callable[..., Awaitable[AuthContext]]:
    """Build a FastAPI dependency returning an ``AuthContext``.

    Args:
        session_store: SessionStore implementation. The dep calls
            ``await session_store.lookup(session_id)`` when a session
            cookie is present.
        api_token_resolver: ApiTokenResolver implementation. The dep
            calls ``await api_token_resolver.resolve(bearer)`` when
            the ``Authorization: Bearer ...`` value starts with
            ``pk_`` (the platform's API-token convention).
        legacy_jwt_resolver: Optional async callable invoked when an
            ``Authorization: Bearer <jwt>`` reaches the dep AND the
            value does NOT start with ``pk_``. Returning ``None``
            falls through to 401. Pass ``None`` (default) to disable
            the bridge — pure new-scheme.
        session_cookie_name: Name of the HttpOnly session cookie.
            Default ``"nai_session"`` is the platform convention.

    Returns:
        An async dependency suitable for ``Depends(...)``. Raises
        ``HTTPException(401)`` when no credential resolves; returns
        the resolved ``AuthContext`` otherwise.
    """

    async def get_auth_context(
        authorization: str | None = Header(None),
        session_cookie: str | None = Cookie(None, alias=session_cookie_name),
    ) -> AuthContext:
        # ── Priority 1: session cookie (human-user UI session) ──
        if session_cookie:
            ctx = await session_store.lookup(session_cookie)
            if ctx is not None:
                return ctx
            # Cookie present but unrecognised/expired → 401 with a
            # session-specific detail so the SPA can drop the stale
            # cookie + redirect to /login. Do NOT fall through to
            # bearer; an attacker could otherwise scrub a cookie and
            # downgrade an authn check.
            raise HTTPException(
                status_code=401,
                detail="Session expired or invalid",
            )

        # ── Priority 2/3: bearer token ──
        if authorization and authorization.startswith("Bearer "):
            token = authorization[len("Bearer ") :].strip()
            if token.startswith("pk_"):
                ctx = await api_token_resolver.resolve(token)
                if ctx is not None:
                    return ctx
                raise HTTPException(
                    status_code=401,
                    detail="API token invalid or revoked",
                )
            # JWT-shaped bearer — defer to the legacy resolver when
            # configured; otherwise 401. The dep never tries to parse
            # JWTs itself — that's the bridge's job.
            if legacy_jwt_resolver is not None:
                ctx = await legacy_jwt_resolver(token)
                if ctx is not None:
                    return ctx
            raise HTTPException(
                status_code=401,
                detail="Bearer token not recognised",
            )

        # ── Priority 4: no credential at all ──
        raise HTTPException(status_code=401, detail="Not authenticated")

    return get_auth_context


__all__ = [
    "LegacyJwtResolver",
    "make_get_auth_context",
]
