"""
Shared authentication helpers for all NoctusAI APIs.

Provides the common get_current_user auth dependency, SSO-role resolution,
and (as of `core-seed-wiring-v2` Phase 4 — 2026-04-23) reusable SSO-JWT
primitives + session cache for any identity-source product. Today's sole
consumer is `core`; the primitives live in the seed lib so a future
2nd identity-source product composes them out of the box rather than
reimplementing.

**What's here:**

- `first_or_none(result)` — Supabase list-response helper.
- `make_get_current_user(fn)` — factory for product-specific JWT validation.
- `resolve_sso_role(user)` — reads `org_role` / `noctus_role` from user_metadata.
- `get_sso_context(user)` — extracts full SSO context from user_metadata.
- `make_require_role(get_current_user_fn, get_user_role_fn)` — factory for
  product-specific role-guard dependency factories. Mirrors the
  `make_get_current_user(fn)` pattern: products bind it once at module load
  and use the resulting `require_role(*roles)` at every router site.
- **NEW** `create_sso_token_factory(settings)` — returns a token-mint callable
  parameterized by product settings (`jwt_secret`, `jwt_algorithm`,
  `sso_token_expiration_minutes`).
- **NEW** `verify_sso_token_factory(settings)` — returns a token-verify callable.
- **NEW** `SSOSessionCache(ttl_seconds=300)` — thread-safe in-memory cache with
  per-key locks and explicit invalidation API.

**Not here:**

- SSO endpoint routers (`/api/auth/*`, `/api/sso/*`). Those stay local to core
  as organ routers — per the recurrence rule in `KB § 01-PHILOSOPHY § Triage at
  decision time`, seam formalization happens when 2+ products share the shape.
"""
from __future__ import annotations

import datetime
import threading
import time
from typing import Callable, Dict, Optional, Tuple

import jwt
from fastapi import Header, HTTPException

from noctusai_lib.primitives.timeutil import now_utc


def first_or_none(result) -> Optional[dict]:
    """Extract first record from a Supabase list response, or None."""
    if not result.data:
        return None
    if isinstance(result.data, dict):
        return result.data
    return result.data[0]


async def _get_current_user(
    authorization: Optional[str] = Header(None),
    *,
    _get_supabase_client=None,
):
    """
    Internal JWT validator. Products MUST use make_get_current_user() to
    obtain a product-specific dependency — never import this directly.

    Extract and validate the JWT from the Authorization header.
    Returns (user, token) tuple.

    The _get_supabase_client parameter is injected by each product's
    dependencies.py to supply the product-specific client factory. This
    avoids a circular dependency between shared auth and product database
    modules.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")

    token = authorization.replace("Bearer ", "")
    try:
        if _get_supabase_client is None:
            raise RuntimeError(
                "get_current_user must be called via a product-specific wrapper "
                "that supplies _get_supabase_client"
            )
        admin = _get_supabase_client()  # service role to validate
        user_response = admin.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Token inválido")
        return user_response.user, token
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Não autenticado")


def make_get_current_user(get_supabase_client_fn):
    """
    Factory that creates a product-specific get_current_user dependency.

    Usage in each product's dependencies.py:

        from noctusai_lib.api.auth import make_get_current_user, first_or_none
        from app.database import get_supabase_client

        get_current_user = make_get_current_user(get_supabase_client)
    """
    async def _product_get_current_user(authorization: Optional[str] = Header(None)):
        return await _get_current_user(
            authorization,
            _get_supabase_client=get_supabase_client_fn,
        )
    return _product_get_current_user


# ---------------------------------------------------------------------------
# SSO role resolution
# ---------------------------------------------------------------------------


def resolve_sso_role(user) -> Optional[str]:
    """Check SSO metadata for product-level admin access.

    When a user enters a product via SSO from the NoctusAI Core platform,
    the Core's ``/api/sso/session`` endpoint syncs ``org_role`` and
    ``noctus_role`` into the user's ``user_metadata``.

    Resolution order:
    1. ``org_role`` in (owner, admin) → ``"platform_admin"`` — the user's
       org bought the product license; they manage it.
    2. ``noctus_role == "admin"`` → ``"platform_admin"`` — NoctusAI
       platform admins have full access to every product.
    3. Otherwise → ``None`` — caller falls through to product-specific
       role logic (e.g. therapy-native roles, ERP DB roles).

    Products should call this first in their ``get_user_role()``::

        def get_user_role(user) -> str:
            sso = resolve_sso_role(user)
            if sso:
                return sso
            # … product-specific logic …
    """
    metadata = getattr(user, "user_metadata", None) or {}
    if metadata.get("org_role") in ("owner", "admin"):
        return "platform_admin"
    if metadata.get("noctus_role") == "admin":
        return "platform_admin"
    return None


def get_sso_context(user) -> dict:
    """Extract all SSO-synced context from user_metadata.

    Returns a dict with keys: ``noctus_role``, ``org_role``, ``org_id``,
    ``org_name``, ``org_logo_url``, ``plan_slug``, ``plan_max_users``,
    ``plan_max_products``, ``plan_features``, ``subscription_status``,
    ``subscription_expires_at``, ``license_expires_at``.

    All values default to None when not present in metadata.
    Products can use this in services to check plan limits, display
    org branding, or show license/trial warnings.
    """
    metadata = getattr(user, "user_metadata", None) or {}
    keys = (
        "noctus_role", "org_role", "org_id",
        "org_name", "org_logo_url",
        "plan_slug", "plan_max_users", "plan_max_products", "plan_features",
        "subscription_status", "subscription_expires_at",
        "license_expires_at",
    )
    return {k: metadata.get(k) for k in keys}


def make_require_role(get_current_user_fn, get_user_role_fn):
    """Factory that creates a product-specific ``require_role`` dependency factory.

    Mirrors the :func:`make_get_current_user` pattern: products bind it once
    at module load with their already-wrapped ``get_current_user`` (which
    knows the product's Supabase client) and their ``get_user_role``
    callable, then use the resulting ``require_role(*roles)`` at every
    router site.

    Parameters:
        get_current_user_fn: The product's already-wrapped
            ``get_current_user`` dependency (typically the return value
            of :func:`make_get_current_user`). Must be an async callable
            that takes ``authorization: Optional[str]`` and returns
            ``(user, token)``.
        get_user_role_fn: A callable ``(user) -> str`` that returns
            the resolved role for the user. Each product provides its own
            (typically falls through ``resolve_sso_role`` to product-native
            roles).

    Returns:
        A ``require_role(*allowed_roles: str)`` factory; calling it
        produces a FastAPI dependency that:
          - extracts + validates the JWT via the product's get_current_user
          - resolves the user's role via ``get_user_role_fn``
          - raises ``HTTPException(403)`` if the role is not in
            ``allowed_roles``
          - returns ``(user, token, role)`` to dependent endpoints.

    Usage in a product's ``app/dependencies.py``::

        from noctusai_lib.api.auth import make_require_role
        from app.dependencies import get_current_user, get_user_role

        require_role = make_require_role(get_current_user, get_user_role)

    And then in routers::

        @router.get("/admin/dashboard")
        async def dashboard(
            auth_role=Depends(require_role("platform_admin")),
        ):
            user, token, role = auth_role
            ...
    """
    def require_role(*allowed_roles: str):
        async def _check_role(authorization: Optional[str] = Header(None)):
            user, token = await get_current_user_fn(authorization)
            role = get_user_role_fn(user)
            if role not in allowed_roles:
                raise HTTPException(
                    status_code=403,
                    detail=f"Acesso negado. Restrito a: {', '.join(allowed_roles)}",
                )
            return user, token, role
        return _check_role
    return require_role


def make_get_current_user_org(
    get_current_user_fn,
    get_org_id_fn,
    *,
    required: bool = True,
    missing_status: int = 403,
    missing_detail: str = "Usuario sem organizacao associada",
):
    """Factory that creates a product-specific ``get_current_user_org`` dependency.

    Mirrors the :func:`make_require_role` pattern: products bind it once at
    module load with their already-wrapped ``get_current_user`` (which knows
    the product's Supabase client) and a pure ``get_org_id`` resolver, then
    use the resulting dep at every router site that needs ``(user, token, org_id)``.

    Surfaced by the ``personal-finance-wiring`` Phase 1 Verify-the-seed-ships-it
    test (2026-05-04). PF's ``dependencies.py:get_current_user_org`` and ERP's
    ``dependencies.py:get_org_id`` shared the ``(user.user_metadata or {}).get(
    "org_id")`` resolution body in different request-time wrappings — N=2
    recurrence, formalized as this factory.

    Parameters:
        get_current_user_fn: The product's already-wrapped
            ``get_current_user`` dependency (typically the return value
            of :func:`make_get_current_user`). Must be an async callable
            that takes ``authorization: Optional[str]`` and returns
            ``(user, token)``.
        get_org_id_fn: A sync callable ``(user) -> Optional[str]`` that
            resolves the org_id for a user. Each product provides its own
            (typically ``lambda u: (u.user_metadata or {}).get("org_id")``
            or ERP's pre-existing ``get_org_id(user)`` resolver).
        required: When True (default), raises ``HTTPException(missing_status,
            missing_detail)`` if the resolved org_id is falsy. PF's shape.
            When False, the dep returns ``(user, token, None)`` on missing
            org_id — no exception. Tuple-with-None lets callers branch on
            membership without re-running auth.
        missing_status: HTTP status code raised when ``required=True`` and
            org_id is missing. Defaults to 403 (PF). ERP's local ``get_org_id(
            required=True)`` uses 400 — pass ``missing_status=400`` to mirror.
        missing_detail: HTTP detail string raised with ``missing_status``.
            Defaults to PF's "Usuario sem organizacao associada".

    Returns:
        An async dependency callable
        ``get_current_user_org(authorization: Optional[str] = Header(None))``
        that resolves ``(user, token, org_id|None)``.

    Usage in a product's ``app/dependencies.py``::

        from noctusai_lib.api.auth import make_get_current_user, make_get_current_user_org
        from app.database import get_supabase_client

        get_current_user = make_get_current_user(get_supabase_client)
        get_current_user_org = make_get_current_user_org(
            get_current_user,
            lambda u: (u.user_metadata or {}).get("org_id"),
            required=True,  # 403 on missing
        )

    And then in routers::

        @router.get("/things")
        async def list_things(
            auth=Depends(get_current_user_org),
        ):
            user, token, org_id = auth
            ...
    """
    async def get_current_user_org(authorization: Optional[str] = Header(None)):
        user, token = await get_current_user_fn(authorization)
        org_id = get_org_id_fn(user)
        if not org_id:
            if required:
                raise HTTPException(
                    status_code=missing_status,
                    detail=missing_detail,
                )
            return user, token, None
        return user, token, org_id
    return get_current_user_org


# ---------------------------------------------------------------------------
# SSO JWT primitives — Phase 4 promotion (2026-04-23)
# ---------------------------------------------------------------------------
#
# Promoted verbatim from `products/core/backend/app/dependencies.py` so any
# future identity-source product (a 2nd "control-plane product") can compose
# them instead of reimplementing. Today's sole caller is `core`.
#
# Settings requirements (product's settings object must expose):
#   - `jwt_secret: str`
#   - `jwt_algorithm: str`             (e.g. "HS256")
#   - `sso_token_expiration_minutes: int`
#
# Usage in a product's `app/dependencies.py`::
#
#     from noctusai_lib.api.auth import create_sso_token_factory, verify_sso_token_factory
#     create_sso_token = create_sso_token_factory(settings)
#     verify_sso_token = verify_sso_token_factory(settings)


def create_sso_token_factory(settings) -> Callable[..., str]:
    """Return a `create_sso_token` callable bound to `settings`.

    Signature of the returned callable::

        create_sso_token(
            user_id: str,
            org_id: str,
            product_slug: str,
            email: str,
            role: str = "user",
            org_role: str = "member",
        ) -> str

    `role` is the NoctusAI platform-level role (admin / manager / user).
    `org_role` is the user's role within their org (owner / admin / member /
    viewer). Products use `org_role` to decide product-level admin access.
    """
    def create_sso_token(
        user_id: str,
        org_id: str,
        product_slug: str,
        email: str,
        role: str = "user",
        org_role: str = "member",
    ) -> str:
        payload = {
            "sub": user_id,
            "org_id": org_id,
            "product": product_slug,
            "email": email,
            "role": role,
            "org_role": org_role,
            "type": "sso",
            "exp": now_utc() + datetime.timedelta(
                minutes=settings.sso_token_expiration_minutes
            ),
            "iat": now_utc(),
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    return create_sso_token


def verify_sso_token_factory(settings) -> Callable[[str], dict]:
    """Return a `verify_sso_token(token) -> payload` callable bound to `settings`.

    Raises `HTTPException(401)` on expired / invalid / non-SSO tokens.
    """
    def verify_sso_token(token: str) -> dict:
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
            )
            if payload.get("type") != "sso":
                raise HTTPException(status_code=401, detail="Token não é SSO")
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token SSO expirado")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Token SSO inválido")

    return verify_sso_token


class SSOSessionCache:
    """Thread-safe in-memory SSO session cache with TTL + per-key locking.

    Promoted from `products/core/backend/app/routers/sso.py::_SSOSessionCache`
    so any identity-source product can reuse the same concurrency semantics.

    Shape preserved byte-for-byte: get/set/invalidate/clear + per-key lock
    acquisition to serialize expensive Supabase session generation per user.

    TTL is parameterizable. Core uses 300s (5 min) — above Supabase's 60s
    rate limit between magic-link generations but tight enough to let role
    revocations take effect quickly. Explicit invalidation via `invalidate(email)`
    or `clear()` flushes on demand (role-change / license-revoke / org-reassign
    hooks should call invalidate; see core's `invalidate_sso_cache_for_user`).
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        self._store: Dict[str, Tuple[dict, float]] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def get(self, email: str) -> Optional[dict]:
        """Return cached session for email or None (expired / absent)."""
        entry = self._store.get(email)
        if entry is None:
            return None
        data, created_at = entry
        if time.monotonic() - created_at > self._ttl:
            self._store.pop(email, None)
            return None
        return data

    def set(self, email: str, data: dict) -> None:
        """Store session data keyed by email with current timestamp."""
        self._store[email] = (data, time.monotonic())

    def get_lock(self, email: str) -> threading.Lock:
        """Per-email lock — serializes concurrent SSO session generation."""
        with self._global_lock:
            if email not in self._locks:
                self._locks[email] = threading.Lock()
            return self._locks[email]

    def invalidate(self, email: str) -> bool:
        """Remove a single entry. Returns True iff removed."""
        return self._store.pop(email, None) is not None

    def clear(self) -> None:
        """Flush every entry and every per-key lock."""
        self._store.clear()
        with self._global_lock:
            self._locks.clear()
