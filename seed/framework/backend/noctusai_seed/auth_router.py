"""``create_auth_router(deps, settings)`` — the seed cookie-session router.

Promotes the Wave-2 unified auth surface out of the ``social-wiring`` fork
(``products/social-wiring/backend/app/routers/auth.py``) into the seed, per
Slice 1b of ``project-history/roadmaps/erp-httponly-cookie-session-2026-07.md``:

  - ``POST /api/auth/login`` — email/password → Supabase sign-in →
    server-mints opaque session → ``Set-Cookie: nai_session=...``.
  - ``GET /api/auth/me`` — returns the resolved ``AuthContext``
    projection for the current request (cookie only — see
    "Scope" below).
  - ``POST /api/auth/logout`` — revokes the session upstream at GoTrue
    (SEC-4) THEN drops the session row + clears the cookie.
  - ``POST /api/settings/api-tokens`` — mint a new ``pk_*`` automation
    token (trusted-DB owner/admin only). Returns the raw secret ONCE.
  - ``GET /api/settings/api-tokens`` — list the caller's org's tokens.
  - ``DELETE /api/settings/api-tokens/{token_id}`` — soft-revoke a token.

Two sub-routers ship (``/api/auth`` + ``/api/settings/api-tokens``) composed
into the ONE ``APIRouter`` this factory returns, so ``"auth"`` stays a
single entry in ``noctusai_seed.routers._STANDARD_ROUTERS``.

**Decoupling.** This module imports NOTHING from ``app.*`` — every product
using ``standard_routers=["auth", ...]`` gets it via ``deps`` (the seed's
``ProductDependencies``, built once by ``create_product_app``) + the
product's own ``settings`` (``ProductSettings`` — ``supabase_url`` /
``supabase_anon_key`` / ``redis_url`` / ``session_encryption_key`` all live
there already).

**Scope — what this router's OWN ``get_auth_context`` resolves.** The 5
routes above authenticate via the cookie session by default (+ the
seed's ``FakeApiTokenResolver`` for ``pk_*`` bearers when the caller
doesn't supply one). A product with a REAL ``ApiTokenResolver`` and/or
its own legacy-JWT bridge (e.g. a pre-existing ``app.dependencies.
get_auth_context`` composition) passes them through the
``api_token_resolver`` / ``legacy_jwt_resolver`` kwargs below — this is
the seam a consumer wires its real adapters through instead of
inheriting the Fake silently. Products that don't pass anything get the
"pure new-scheme, cookie-only" default this docstring described
originally. Both compositions share the SAME ``SessionStore`` instance
(see ``get_session_store`` below), so a cookie minted by THIS router's
``/login`` is visible to a lookup running through EITHER composition.

SEC-4 (upstream revoke): ``session_revoke.SessionRevoker`` — see
``KB § PATTERNS/backend/seed-fake-real-adapter.md`` for the Protocol+Fake+
Real+factory shape this whole module composes.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field

from noctusai_lib.api.auth.session import (
    ApiTokenResolver,
    AuthContext,
    FakeApiTokenResolver,
    LegacyJwtResolver,
    SessionRevoker,
    SessionStore,
    hash_token,
    make_get_auth_context,
    make_session_revoker,
    make_session_store,
)

logger = logging.getLogger(__name__)

_SESSION_COOKIE = "nai_session"
_SESSION_TTL_SECONDS = 86400  # 24h
_TOKENS_TABLE = "api_tokens"


# ─── Shared session infra — process-local singletons keyed by settings ────
#
# `get_session_store` / `get_session_revoker` are the ONE place a process
# builds these adapters. A product's own auth composition (e.g.
# `app/dependencies.py::_get_session_store`) MUST delegate here rather than
# calling `make_session_store(...)` a second time — for the Redis-backed
# Real adapter two separate Python objects are behaviourally identical (the
# shared Redis IS the state), but for the in-memory Fake (dev without Redis)
# a second instance is a SEPARATE empty dict: a session created by this
# router's `/login` would be invisible to a lookup running against the
# product's own second Fake instance. Centralizing construction here closes
# that hazard by construction instead of by convention.

_session_store: Optional[SessionStore] = None
_session_store_settings_id: Optional[int] = None
_session_revoker: Optional[SessionRevoker] = None
_session_revoker_settings_id: Optional[int] = None


def get_session_store(settings) -> SessionStore:
    """Process-local ``SessionStore`` singleton for ``settings``.

    Redis-backed (SEC-3 encrypted-at-rest) when ``settings.redis_url`` is
    set; the in-memory ``FakeSessionStore`` otherwise (dev / no Redis
    configured). ``require_encryption=True`` unconditionally — refuses to
    build a plaintext-Redis store even if a caller forgets
    ``session_encryption_key`` (fails loudly at boot per SEC-3, matching
    ``make_session_store``'s documented production-wiring recommendation).

    Keyed by ``id(settings)`` (not memoized forever) so per-product test
    suites that construct a fresh ``Settings()`` per test get an isolated
    store instead of leaking session state across tests.
    """
    global _session_store, _session_store_settings_id
    if _session_store is None or _session_store_settings_id != id(settings):
        raw_key = getattr(settings, "session_encryption_key", "") or ""
        encryption_key = raw_key.encode() if raw_key else None
        _session_store = make_session_store(
            redis_url=getattr(settings, "redis_url", None),
            encryption_key=encryption_key,
            require_encryption=True,
        )
        _session_store_settings_id = id(settings)
    return _session_store


def get_session_revoker(settings) -> SessionRevoker:
    """Process-local ``SessionRevoker`` singleton for ``settings`` (SEC-4).

    Real (``SupabaseSessionRevoker``, throwaway-anon-client sign-out) when
    both ``supabase_url`` + ``supabase_anon_key`` are set; the in-memory
    ``FakeSessionRevoker`` otherwise (dev / tests).
    """
    global _session_revoker, _session_revoker_settings_id
    if _session_revoker is None or _session_revoker_settings_id != id(settings):
        _session_revoker = make_session_revoker(
            supabase_url=getattr(settings, "supabase_url", None) or None,
            supabase_anon_key=getattr(settings, "supabase_anon_key", None) or None,
        )
        _session_revoker_settings_id = id(settings)
    return _session_revoker


# ─── Request / response schemas (unchanged shape from the fork) ───────────


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class LoginUserDTO(BaseModel):
    id: str
    email: str | None = None


class LoginOrgDTO(BaseModel):
    id: str
    name: str | None = None


class LoginResponse(BaseModel):
    user: LoginUserDTO
    org: LoginOrgDTO


class MeResponse(BaseModel):
    user: LoginUserDTO | None = None
    org: LoginOrgDTO
    caller_kind: str
    scopes: list[str] = Field(default_factory=list)


class ApiTokenCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=list)


class ApiTokenCreatedDTO(BaseModel):
    """Returned ONCE at mint time — caller MUST persist the secret."""

    id: str
    label: str
    token: str  # the raw pk_* secret, shown exactly once
    prefix: str
    scopes: list[str]
    created_at: str


class ApiTokenListItem(BaseModel):
    id: str
    label: str
    prefix: str
    scopes: list[str]
    created_at: str
    last_used_at: str | None = None
    revoked_at: str | None = None


# ─── Helpers ───────────────────────────────────────────────────────────────


def _mint_secret() -> tuple[str, str]:
    """Return ``(raw_secret, prefix)`` for a fresh ``pk_*`` token."""
    secret_body = secrets.token_hex(32)  # 64-hex-char body → 256 bits entropy
    raw = f"pk_{secret_body}"
    prefix = raw[:11]  # ``pk_`` + 8 hex chars (UI display)
    return raw, prefix


def _coerce_org_uuid(raw_org: Any) -> UUID:
    """Coerce the auth-side org_id (string or UUID) into a UUID.

    Recurs verbatim (N=5: daily-life / knowledge-extractor / orbity /
    products/seed / social-wiring each carry a private copy) — flagged as
    a `scoped-improvement:` seed-absorption candidate in this delivery's
    footer rather than absorbed here (out of this slice's file-disjoint
    scope; a fleet-wide `noctusai_lib.primitives` lift touches every
    product's `dependencies.py`, not just this router).
    """
    try:
        return UUID(str(raw_org))
    except (ValueError, TypeError):
        import uuid as _uuid

        return _uuid.uuid5(_uuid.NAMESPACE_OID, str(raw_org))


def _require_org_admin(core_client: Any, ctx: AuthContext) -> None:
    """403 unless ``ctx.user_id`` has owner/admin ``org_role`` on the
    TRUSTED ``public.noctus_users`` row.

    Trusted-DB read — SEC follow-up from the 2026-07-14 role-cascade audit
    (auto-improvement ts=2026-07-14T21:47:53+00:00, target
    ``products/social-wiring/backend/app/routers/auth.py``): the fork's
    ``_require_admin_role`` read ``user_metadata.org_role``/``role``
    directly (a user can rewrite their own metadata via
    ``auth.updateUser({data})`` — the same spoof class the org_id +
    platform-role trusted-DB fixes closed elsewhere, cf69ab2f / 0411ff2a).
    It was ALSO dead code (auto-improvement ts=2026-07-06T18:29:10+00:00 —
    no call sites; the two real gates ran their own inline
    ``noctus_users`` query instead). This helper is the single trusted-DB
    gate BOTH ``create_api_token`` and ``revoke_api_token`` call, closing
    the N=2 duplication that same 2026-07-06 entry flagged.

    ``core_client`` MUST be a ``public``-schema-scoped client
    (``deps.get_core_client()``) — ``noctus_users`` lives in ``public``,
    NOT the product's own schema; a product-schema-scoped client 500s with
    PGRST205 (see ``feedback_product_client_schema_scoping_public_tables``
    memory entry).
    """
    lookup = (
        core_client.from_("noctus_users")
        .select("org_role")
        .eq("id", str(ctx.user_id))
        .limit(1)
        .execute()
    )
    rows = lookup.data or []
    if not rows or rows[0].get("org_role") not in ("owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="API-token management restricted to owner/admin roles",
        )


def create_auth_router(
    deps,
    settings,
    *,
    api_token_resolver: Optional[ApiTokenResolver] = None,
    legacy_jwt_resolver: Optional[LegacyJwtResolver] = None,
) -> APIRouter:
    """Build the combined ``/api/auth`` + ``/api/settings/api-tokens`` router.

    Args:
        deps: A ``noctusai_seed.dependencies.ProductDependencies`` instance
            (or anything exposing the same ``get_admin_client()`` /
            ``get_core_client()`` surface). ``get_admin_client()`` returns
            a client already scoped to the PRODUCT's own schema (the
            ``api_tokens`` table lives there); ``get_core_client()``
            returns a ``public``-scoped client (``noctus_users`` lives
            there).
        settings: The product's ``ProductSettings`` instance —
            ``supabase_url`` / ``supabase_anon_key`` (login + SEC-4
            revoke) and ``redis_url`` / ``session_encryption_key`` (the
            session store, SEC-3) are read off it.
        api_token_resolver: Optional REAL ``ApiTokenResolver`` (e.g. a
            product's DB-backed ``SupabaseApiTokenResolver``). Defaults
            to the seed's ``FakeApiTokenResolver()`` (always-empty — no
            ``pk_*`` bearer resolves) when omitted. A product whose
            ``pk_*`` tokens must resolve through THIS router's ``/me``
            or api-token endpoints MUST pass its real resolver here —
            inheriting the Fake default silently is the regression this
            kwarg exists to prevent (no Real ``DBApiTokenResolver``
            ships in the seed itself yet; each product's table lives in
            its own schema, so the seed has no generic one to default
            to — see the ``api_tokens`` module docstring, "Wave 2").
        legacy_jwt_resolver: Optional async ``Callable[[str],
            Awaitable[AuthContext | None]]`` bridging a raw Supabase-JWT
            bearer (the pre-cookie-session auth style) to an
            ``AuthContext``. Defaults to ``None`` (pure new-scheme,
            cookie + ``pk_*``-only) — pass a product's existing bridge
            (e.g. its ``app.dependencies._legacy_jwt_resolver``) to keep
            legacy-JWT callers of ``/me``/``/logout``/the api-token
            endpoints working across the migration window.

    Returns:
        One ``APIRouter`` combining both prefixes — register it under the
        seed's ``"auth"`` standard-router name (a single registry entry;
        see ``noctusai_seed.routers._STANDARD_ROUTERS``) OR call this
        factory directly (bypassing the registry) when a product needs
        the ``api_token_resolver`` / ``legacy_jwt_resolver`` kwargs — the
        registry's ``_build_auth_router(deps, settings, product_name,
        version)`` builder has a fixed 4-arg signature shared by every
        standard router and has no seam to thread per-product overrides
        through, so a product with real adapters to wire calls
        ``create_auth_router(...)`` directly from its own module-
        registration seam instead of opting into ``standard_routers=
        ["auth"]``.
    """
    session_store = get_session_store(settings)
    session_revoker = get_session_revoker(settings)

    # This router's OWN identity resolver — cookie sessions + `pk_*` bearer
    # (Fake by default; Real when the caller passes one) + an optional
    # legacy-JWT bridge. See the kwarg docstrings above for the by-
    # construction reasoning; the bare default (no overrides) stays the
    # "pure new-scheme, cookie-only" shape this router shipped with.
    get_auth_context = make_get_auth_context(
        session_store=session_store,
        api_token_resolver=api_token_resolver or FakeApiTokenResolver(),
        legacy_jwt_resolver=legacy_jwt_resolver,
        session_cookie_name=_SESSION_COOKIE,
    )

    auth_router = APIRouter(prefix="/api/auth", tags=["auth"])
    api_tokens_router = APIRouter(prefix="/api/settings/api-tokens", tags=["auth"])

    # ── Session lifecycle ──────────────────────────────────────────────

    @auth_router.post("/login", response_model=LoginResponse)
    async def login(body: LoginRequest, response: Response) -> LoginResponse:
        """Authenticate against Supabase, mint a server-side session, set
        the HttpOnly cookie. The browser never sees the JWT or refresh
        token — only the opaque session id.

        SEC-1: the sign-in runs on a THROWAWAY ``create_client(url,
        anon_key)`` — never the shared admin singleton (the 2026-05-23
        core prod outage class).
        """
        from supabase import create_client

        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        try:
            auth_response = client.auth.sign_in_with_password(
                {"email": body.email, "password": body.password}
            )
        except Exception as exc:
            # Supabase auth errors come through as gotrue exceptions; log
            # them but don't leak detail to the caller (timing-safe error).
            logger.info(
                "login_failed email=%s err_type=%s", body.email, type(exc).__name__
            )
            raise HTTPException(status_code=401, detail="Invalid email or password")

        user = getattr(auth_response, "user", None)
        session = getattr(auth_response, "session", None)
        if user is None or session is None:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        metadata = getattr(user, "user_metadata", None) or {}
        raw_org = metadata.get("org_id")
        if not raw_org:
            raise HTTPException(
                status_code=403,
                detail="User has no organisation — contact your administrator",
            )
        org_id = _coerce_org_uuid(raw_org)

        try:
            user_id = UUID(str(user.id))
        except (ValueError, TypeError) as exc:
            logger.warning("login_user_id_non_uuid id=%r err=%s", user.id, exc)
            raise HTTPException(status_code=500, detail="User id shape unexpected")

        refresh_token = getattr(session, "refresh_token", "") or ""
        session_id = await session_store.create(
            user_id=user_id,
            org_id=org_id,
            supabase_refresh_token=refresh_token,
            ttl_seconds=_SESSION_TTL_SECONDS,
        )

        response.set_cookie(
            key=_SESSION_COOKIE,
            value=session_id,
            max_age=_SESSION_TTL_SECONDS,
            httponly=True,
            secure=True,
            samesite="strict",
            path="/",
        )

        org_name = metadata.get("org_name")
        return LoginResponse(
            user=LoginUserDTO(id=str(user.id), email=getattr(user, "email", None)),
            org=LoginOrgDTO(id=str(org_id), name=org_name),
        )

    @auth_router.get("/me", response_model=MeResponse)
    async def me(ctx: AuthContext = Depends(get_auth_context)) -> MeResponse:
        """Return a lightweight projection of the current ``AuthContext``."""
        user_dto: LoginUserDTO | None
        if ctx.user_id is not None:
            user_dto = LoginUserDTO(id=str(ctx.user_id), email=None)
        else:
            user_dto = None
        return MeResponse(
            user=user_dto,
            org=LoginOrgDTO(id=str(ctx.org_id), name=None),
            caller_kind=ctx.caller_kind,
            scopes=list(ctx.scopes),
        )

    @auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(
        response: Response,
        ctx: AuthContext = Depends(get_auth_context),
        session_cookie: str | None = Cookie(None, alias=_SESSION_COOKIE),
    ) -> Response:
        """Revoke the session upstream (SEC-4) THEN delete the local
        session row + clear the cookie. No-op when the caller
        authenticated via bearer (no session to delete/revoke).

        SEC-4: the upstream revoke is best-effort-but-logged — it never
        raises into this handler (``SessionRevoker.revoke`` swallows +
        logs), so a GoTrue outage never blocks a user's ability to clear
        their local session + cookie.
        """
        if session_cookie:
            tokens = await session_store.read_tokens(session_cookie)
            if tokens is not None and tokens.refresh_token:
                await session_revoker.revoke(tokens.refresh_token)
            await session_store.delete(session_cookie)
        response.delete_cookie(_SESSION_COOKIE, path="/")
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    # ── API-token management ────────────────────────────────────────────

    @api_tokens_router.post(
        "", response_model=ApiTokenCreatedDTO, status_code=status.HTTP_201_CREATED
    )
    async def create_api_token(
        body: ApiTokenCreateRequest,
        ctx: AuthContext = Depends(get_auth_context),
    ) -> ApiTokenCreatedDTO:
        """Mint a new ``pk_*`` token. Trusted-DB owner/admin only. The raw
        secret is returned exactly once — the caller MUST persist it."""
        # API tokens cannot be minted BY automation — only humans. A
        # token-authenticated caller minting a new token is a credential-
        # escalation shape the platform refuses.
        if ctx.caller_kind != "user":
            raise HTTPException(
                status_code=403,
                detail="Only human users can mint API tokens",
            )

        _require_org_admin(deps.get_core_client(), ctx)

        raw_secret, prefix = _mint_secret()
        token_id = uuid4()
        now_iso = datetime.now(timezone.utc).isoformat()

        sb = deps.get_admin_client()
        insert_payload = {
            "id": str(token_id),
            "org_id": str(ctx.org_id),
            "label": body.label,
            "token_hash": hash_token(raw_secret),
            "token_prefix": prefix,
            "scopes": list(body.scopes or []),
            "created_by": str(ctx.user_id) if ctx.user_id else None,
            "created_at": now_iso,
            "last_used_at": None,
            "revoked_at": None,
        }
        try:
            sb.table(_TOKENS_TABLE).insert(insert_payload).execute()
        except Exception as exc:
            logger.exception(
                "api_token_insert_failed org=%s err=%s", ctx.org_id, type(exc).__name__
            )
            raise HTTPException(status_code=500, detail="Failed to mint API token")

        return ApiTokenCreatedDTO(
            id=str(token_id),
            label=body.label,
            token=raw_secret,
            prefix=prefix,
            scopes=list(body.scopes or []),
            created_at=now_iso,
        )

    @api_tokens_router.get("", response_model=list[ApiTokenListItem])
    async def list_api_tokens(
        ctx: AuthContext = Depends(get_auth_context),
    ) -> list[ApiTokenListItem]:
        """List tokens for the caller's org. Hashes / secrets never returned."""
        if ctx.caller_kind != "user":
            # Automation tokens can't introspect the token pool.
            raise HTTPException(status_code=403, detail="Restricted to human users")

        sb = deps.get_admin_client()
        response = (
            sb.table(_TOKENS_TABLE)
            .select("id, label, token_prefix, scopes, created_at, last_used_at, revoked_at")
            .eq("org_id", str(ctx.org_id))
            .order("created_at", desc=True)
            .execute()
        )
        rows = response.data or []
        return [
            ApiTokenListItem(
                id=str(r["id"]),
                label=r.get("label") or "",
                prefix=r.get("token_prefix") or "",
                scopes=list(r.get("scopes") or []),
                created_at=str(r.get("created_at") or ""),
                last_used_at=str(r["last_used_at"]) if r.get("last_used_at") else None,
                revoked_at=str(r["revoked_at"]) if r.get("revoked_at") else None,
            )
            for r in rows
        ]

    @api_tokens_router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def revoke_api_token(
        token_id: UUID,
        ctx: AuthContext = Depends(get_auth_context),
    ) -> Response:
        """Soft-revoke a token by stamping ``revoked_at = now()``.
        Trusted-DB owner/admin only; cross-org revocation refused at the
        DB level by the ``org_id =`` filter."""
        if ctx.caller_kind != "user":
            raise HTTPException(status_code=403, detail="Restricted to human users")

        _require_org_admin(deps.get_core_client(), ctx)

        now_iso = datetime.now(timezone.utc).isoformat()
        sb = deps.get_admin_client()
        update_response = (
            sb.table(_TOKENS_TABLE)
            .update({"revoked_at": now_iso})
            .eq("id", str(token_id))
            .eq("org_id", str(ctx.org_id))
            .execute()
        )
        affected = update_response.data or []
        if not affected:
            raise HTTPException(status_code=404, detail="Token not found")

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    router = APIRouter()
    router.include_router(auth_router)
    router.include_router(api_tokens_router)
    return router


__all__ = [
    "create_auth_router",
    "get_session_store",
    "get_session_revoker",
]
