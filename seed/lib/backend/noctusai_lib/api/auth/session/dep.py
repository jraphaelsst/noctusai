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

**Identity-mismatch rule (cookie vs bearer).** When a valid session
cookie AND a valid user-bearer (JWT via ``legacy_jwt_resolver``) are
both present and name DIFFERENT users, the dep refuses with a strict
401 and a ``Set-Cookie`` deletion header for the session cookie — it
never silently picks one (a stale cookie of account A used to win over
the bearer of account B, attributing B's actions to A). Same user, or
only one credential present → unchanged behaviour. The rule concerns
two VALID, DIFFERENT identities only: a bearer that is invalid/expired
while the cookie is valid keeps today's behaviour (cookie wins), and a
``pk_*`` token (no user identity) never triggers it. A structured
WARNING with user ids only (never tokens) is logged on mismatch.

Wave 2 consumer projects pass real adapters; Wave 1 dev/test wiring
passes ``FakeSessionStore`` + ``FakeApiTokenResolver``. The factory
itself is identical in both paths — adapter swap is the entire
"go to production" change.

SEED-1 (``julia-agents-academia-2026-09``, contract §B.0): the resolved
``AuthContext`` is stashed on ``request.state.auth_context`` on every
successful resolution — the ONLY channel an ASGI middleware (which runs
outside FastAPI's dependency graph) has to learn who the caller was,
after the response status is known. See
``noctusai_lib.api.auth.session.audit_middleware`` — its sole consumer
today. Purely additive: the return value and every existing
``Depends(get_auth_context)`` call site are unchanged.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from fastapi import Cookie, Header, HTTPException, Request
from fastapi.responses import Response

from noctusai_lib.api.auth.session.api_tokens import ApiTokenResolver
from noctusai_lib.api.auth.session.store import SessionStore
from noctusai_lib.api.auth.session.types import AuthContext

logger = logging.getLogger(__name__)

LegacyJwtResolver = Callable[[str], Awaitable[AuthContext | None]]
"""Optional bridge for the existing JWT-only auth scheme.

Receives the raw bearer payload (without ``Bearer `` prefix), returns
an ``AuthContext`` if the JWT validates against the legacy verifier,
or ``None`` to fall through to 401. Lets the new dep coexist with
``make_get_current_user`` callers during the migration window.
"""


def _cookie_clear_header(cookie_name: str) -> str:
    """``Set-Cookie`` value deleting the session cookie.

    Same attributes the login route sets it with (path/secure/httponly/
    samesite), so the browser matches and drops the exact cookie.
    """
    resp = Response()
    resp.delete_cookie(
        cookie_name, path="/", secure=True, httponly=True, samesite="strict"
    )
    return resp.headers["set-cookie"]


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

    async def _refuse_identity_mismatch(
        request: Request, authorization: str | None, cookie_ctx: AuthContext
    ) -> None:
        """401 + cookie-clear when a valid user bearer names another user."""
        if cookie_ctx.user_id is None:
            return
        if not (authorization and authorization.startswith("Bearer ")):
            return
        token = authorization[len("Bearer ") :].strip()
        # pk_* carries no user identity; no bridge → nothing to compare.
        if token.startswith("pk_") or legacy_jwt_resolver is None:
            return
        try:
            if getattr(legacy_jwt_resolver, "accepts_request", False):
                bearer_ctx = await legacy_jwt_resolver(token, request)
            else:
                bearer_ctx = await legacy_jwt_resolver(token)
        except Exception as exc:  # invalid/expired bearer → cookie wins
            logger.debug("cookie_bearer_check_bearer_unresolved err=%s", type(exc).__name__)
            return
        if (
            bearer_ctx is None
            or bearer_ctx.user_id is None
            or bearer_ctx.user_id == cookie_ctx.user_id
        ):
            return
        logger.warning(
            "auth_cookie_bearer_identity_mismatch cookie_user_id=%s bearer_user_id=%s",
            cookie_ctx.user_id,
            bearer_ctx.user_id,
        )
        raise HTTPException(
            status_code=401,
            detail="Session and bearer identify different users",
            headers={"Set-Cookie": _cookie_clear_header(session_cookie_name)},
        )

    async def get_auth_context(
        request: Request,
        authorization: str | None = Header(None),
        session_cookie: str | None = Cookie(None, alias=session_cookie_name),
    ) -> AuthContext:
        # ── Priority 1: session cookie (human-user UI session) ──
        if session_cookie:
            ctx = await session_store.lookup(session_cookie)
            if ctx is not None:
                await _refuse_identity_mismatch(request, authorization, ctx)
                request.state.auth_context = ctx
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
                    request.state.auth_context = ctx
                    return ctx
                raise HTTPException(
                    status_code=401,
                    detail="API token invalid or revoked",
                )
            # JWT-shaped bearer — defer to the legacy resolver when
            # configured; otherwise 401. The dep never tries to parse
            # JWTs itself — that's the bridge's job.
            if legacy_jwt_resolver is not None:
                if getattr(legacy_jwt_resolver, "accepts_request", False):
                    ctx = await legacy_jwt_resolver(token, request)
                else:
                    ctx = await legacy_jwt_resolver(token)
                if ctx is not None:
                    request.state.auth_context = ctx
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
