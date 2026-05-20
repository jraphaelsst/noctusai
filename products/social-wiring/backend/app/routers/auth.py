"""Auth router — login / me / logout + API-token management.

Wires the Wave-2 unified auth surface:

  - ``POST /api/auth/login`` — email/password → Supabase sign-in →
    server-mints opaque session → ``Set-Cookie: nai_session=...``.
  - ``GET /api/auth/me`` — returns the resolved ``AuthContext``
    projection for the current request (cookie OR bearer).
  - ``POST /api/auth/logout`` — drops the session from the store +
    clears the cookie.
  - ``POST /api/settings/api-tokens`` — mint a new ``pk_*`` automation
    token (owner / admin only). Returns the raw secret ONCE.
  - ``GET /api/settings/api-tokens`` — list the caller's org's tokens
    (no secrets — only prefix + metadata).
  - ``DELETE /api/settings/api-tokens/{token_id}`` — soft-revoke a
    token (sets ``revoked_at = now()``).

Two routers ship because the URL surface spans two prefixes
(``/api/auth`` for session lifecycle + ``/api/settings/api-tokens`` for
the management UI). ``main.py`` includes both via the W2.1 module-
registration seam.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field

from noctusai_lib.api.auth.session import AuthContext, hash_token

from app.dependencies import (
    _get_session_store,
    coerce_org_uuid,
    get_admin_client,
    get_auth_context,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
api_tokens_router = APIRouter(prefix="/api/settings/api-tokens", tags=["auth"])

_SESSION_COOKIE = "nai_session"
_SESSION_TTL_SECONDS = 86400  # 24h


# ─── Request / response schemas ──────────────────────────────────────


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


# ─── Helpers ──────────────────────────────────────────────────────────


_TOKENS_TABLE = "api_tokens"
_TOKENS_SCHEMA = "social_wiring"


def _mint_secret() -> tuple[str, str]:
    """Return ``(raw_secret, prefix)`` for a fresh ``pk_*`` token."""
    secret_body = secrets.token_hex(32)  # 64-hex-char body → 256 bits entropy
    raw = f"pk_{secret_body}"
    prefix = raw[:11]  # ``pk_`` + 8 hex chars (UI display)
    return raw, prefix


def _require_admin_role(user: Any, raw_org: str) -> None:
    """403 unless ``user`` has owner/admin role on ``raw_org``.

    Token management is a sensitive privilege — only org owners /
    admins can mint or revoke. Falls back to the user_metadata path
    used by the seed's role helpers (``resolve_sso_role`` resolves the
    same fields).
    """
    metadata = getattr(user, "user_metadata", None) or {}
    role = metadata.get("org_role") or metadata.get("role")
    if role not in ("owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="API-token management restricted to owner/admin roles",
        )


# ─── Session lifecycle ───────────────────────────────────────────────


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, response: Response) -> LoginResponse:
    """Authenticate against Supabase, mint a server-side session, set
    the HttpOnly cookie. The browser never sees the JWT or refresh
    token — only the opaque session id.
    """
    sb = get_admin_client()
    try:
        auth_response = sb.auth.sign_in_with_password(
            {"email": body.email, "password": body.password}
        )
    except Exception as exc:
        # Supabase auth errors come through as gotrue exceptions; log
        # them but don't leak detail to the caller (timing-safe error).
        logger.info("login_failed email=%s err_type=%s", body.email, type(exc).__name__)
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
    org_id = coerce_org_uuid(raw_org)

    try:
        user_id = UUID(str(user.id))
    except (ValueError, TypeError) as exc:
        logger.warning("login_user_id_non_uuid id=%r err=%s", user.id, exc)
        raise HTTPException(status_code=500, detail="User id shape unexpected")

    refresh_token = getattr(session, "refresh_token", "") or ""
    store = _get_session_store()
    session_id = await store.create(
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


@router.get("/me", response_model=MeResponse)
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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    ctx: AuthContext = Depends(get_auth_context),
    session_cookie: str | None = Cookie(None, alias=_SESSION_COOKIE),
) -> Response:
    """Delete the session row + clear the cookie. No-op when the
    caller authenticated via bearer (no session to delete)."""
    if session_cookie:
        store = _get_session_store()
        await store.delete(session_cookie)
    response.delete_cookie(_SESSION_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


# ─── API-token management ────────────────────────────────────────────


@api_tokens_router.post(
    "", response_model=ApiTokenCreatedDTO, status_code=status.HTTP_201_CREATED
)
async def create_api_token(
    body: ApiTokenCreateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> ApiTokenCreatedDTO:
    """Mint a new ``pk_*`` token. Owner / admin only. The raw secret
    is returned exactly once — the caller MUST persist it."""
    # API tokens cannot be minted BY automation — only humans. A
    # token-authenticated caller minting a new token is a credential-
    # escalation shape the platform refuses.
    if ctx.caller_kind != "user":
        raise HTTPException(
            status_code=403,
            detail="Only human users can mint API tokens",
        )

    # Re-resolve the user's role from the admin-client noctus_users
    # row (the AuthContext doesn't carry org_role — would require a
    # join during dep resolution). One extra query at mint time is
    # acceptable for a privileged op.
    sb = get_admin_client()
    user_lookup = (
        sb.from_("noctus_users")
        .select("org_role")
        .eq("id", str(ctx.user_id))
        .limit(1)
        .execute()
    )
    rows = user_lookup.data or []
    if not rows or rows[0].get("org_role") not in ("owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="API-token management restricted to owner/admin roles",
        )

    raw_secret, prefix = _mint_secret()
    token_id = uuid4()
    now_iso = datetime.now(timezone.utc).isoformat()

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
        (
            sb.schema(_TOKENS_SCHEMA)
            .table(_TOKENS_TABLE)
            .insert(insert_payload)
            .execute()
        )
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

    sb = get_admin_client()
    response = (
        sb.schema(_TOKENS_SCHEMA)
        .table(_TOKENS_TABLE)
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


@api_tokens_router.delete(
    "/{token_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_api_token(
    token_id: UUID,
    ctx: AuthContext = Depends(get_auth_context),
) -> Response:
    """Soft-revoke a token by stamping ``revoked_at = now()``. Owner /
    admin only; cross-org revocation refused at the DB level by the
    ``org_id =`` filter."""
    if ctx.caller_kind != "user":
        raise HTTPException(status_code=403, detail="Restricted to human users")

    sb = get_admin_client()
    user_lookup = (
        sb.from_("noctus_users")
        .select("org_role")
        .eq("id", str(ctx.user_id))
        .limit(1)
        .execute()
    )
    rows = user_lookup.data or []
    if not rows or rows[0].get("org_role") not in ("owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="API-token management restricted to owner/admin roles",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    update_response = (
        sb.schema(_TOKENS_SCHEMA)
        .table(_TOKENS_TABLE)
        .update({"revoked_at": now_iso})
        .eq("id", str(token_id))
        .eq("org_id", str(ctx.org_id))
        .execute()
    )
    affected = update_response.data or []
    if not affected:
        raise HTTPException(status_code=404, detail="Token not found")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router", "api_tokens_router"]
