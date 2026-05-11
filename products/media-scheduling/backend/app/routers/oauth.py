"""Google Calendar OAuth — init + callback + admin status.

Single-account-per-product flow (the media crew shares one Google
Calendar). Persists tokens to `media_scheduling.oauth_credentials` via
the Supabase admin client (RLS-bypass; OAuth tokens are admin-only).

Frontend contract (Phase 5 hooks):
  - `GET /api/oauth/google/status` — `useOAuthStatus()` reads
    `{connected, expires_at, account_email, last_error}` here.
  - `GET /oauth/google/init`       — `redirectToOAuthInit()` browser
    redirects here; we 302 to Google's consent screen.
  - `POST /oauth/google/init`      — programmatic init returning the
    Google URL as JSON (per architect's Phase 3 spec). Useful for SPA
    flows that pop a window or set window.location themselves.
  - `GET /oauth/google/callback`   — Google redirects back; we exchange
    code → tokens, persist, redirect to a frontend success page.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from app.config import settings
from app.database import get_supabase_client
from app.dependencies import get_current_user_org
from app.rate_limit import limiter

logger = logging.getLogger(__name__)


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

REQUESTED_SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/calendar",
]


# --- Two router prefixes per the frontend contract -----------------------
#
# `/oauth/google/{init,callback}` — public-ish; init bounces to Google,
# callback receives Google's redirect. Status endpoint sits under
# `/api/...` because it's an admin-gated read of credential metadata.
public_router = APIRouter(prefix="/oauth/google", tags=["OAuth"])
admin_router = APIRouter(prefix="/api/oauth/google", tags=["OAuth"])


def _oauth_configured() -> bool:
    return bool(
        settings.google_oauth_client_id
        and settings.google_oauth_client_secret
        and settings.google_oauth_redirect_uri
    )


def _consent_url() -> str:
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": " ".join(REQUESTED_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


# --- Init (GET browser-redirect + POST programmatic) ----------------------


@public_router.get("/init")
@limiter.limit("10/minute")
def init_google_oauth_get(request: Request) -> RedirectResponse:
    """Browser-redirect flow.

    Frontend's `redirectToOAuthInit()` does `window.location.href = '/oauth/google/init'`,
    so we 302 straight to Google's consent screen. After consent Google
    redirects to `/oauth/google/callback` (see `google_oauth_callback`).
    """
    if not _oauth_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Google OAuth not configured. Set GOOGLE_OAUTH_CLIENT_ID, "
                "GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI in .env."
            ),
        )
    return RedirectResponse(_consent_url())


@public_router.post("/init")
@limiter.limit("10/minute")
def init_google_oauth_post(request: Request) -> dict[str, str]:
    """Programmatic flow — returns the Google consent URL as JSON.

    Per the architect's Phase 3 spec — useful for SPA flows that want to
    open a popup or set `window.location` from JS rather than relying on
    a server redirect. The frontend's current hook uses the GET variant
    above.
    """
    if not _oauth_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Google OAuth not configured. Set GOOGLE_OAUTH_CLIENT_ID, "
                "GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI in .env."
            ),
        )
    return {"authorize_url": _consent_url()}


# --- Callback ------------------------------------------------------------


@public_router.get("/callback")
@limiter.limit("10/minute")
async def google_oauth_callback(
    request: Request,
    code: str | None = Query(None),
    error: str | None = Query(None),
) -> dict[str, Any]:
    """Receive Google's OAuth redirect. Exchange code → tokens, persist."""
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error from Google: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
    if not _oauth_configured():
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_response.status_code != 200:
            logger.error("oauth: token exchange failed: %s", token_response.text)
            raise HTTPException(
                status_code=token_response.status_code,
                detail=f"Token exchange failed: {token_response.text}",
            )
        tokens = token_response.json()

        userinfo_response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        if userinfo_response.status_code != 200:
            raise HTTPException(
                status_code=userinfo_response.status_code,
                detail=f"Userinfo fetch failed: {userinfo_response.text}",
            )
        account_email = userinfo_response.json().get("email")
        if not account_email:
            raise HTTPException(status_code=400, detail="Userinfo response missing email")

    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=int(tokens.get("expires_in", 3600))
    )
    refresh_token = tokens.get("refresh_token")
    access_token = tokens["access_token"]
    scopes = tokens.get("scope", "")

    db = get_supabase_client()
    payload: dict[str, Any] = {
        "provider": "google",
        "account_email": account_email,
        "access_token": access_token,
        "access_token_expires_at": expires_at.isoformat(),
        "scopes": scopes,
    }
    # Refresh token comes back ONLY on first consent. Subsequent grants
    # without `prompt=consent` may omit it; never overwrite an existing
    # row's refresh_token with NULL.
    if refresh_token:
        payload["refresh_token"] = refresh_token

    existing_q = (
        db.table("oauth_credentials")
        .select("id, refresh_token")
        .eq("provider", "google")
        .eq("account_email", account_email)
        .limit(1)
        .execute()
    )
    existing_rows = existing_q.data or []

    if existing_rows:
        row = existing_rows[0]
        if not refresh_token and not row.get("refresh_token"):
            raise HTTPException(
                status_code=400,
                detail="No refresh_token returned from Google and none stored. "
                "Revoke access in Google account settings then re-connect with "
                "prompt=consent (already set).",
            )
        update_payload = {k: v for k, v in payload.items() if k != "provider"}
        result = (
            db.table("oauth_credentials")
            .update(update_payload)
            .eq("id", row["id"])
            .execute()
        )
        cred = (result.data or [None])[0] or {"id": row["id"], **update_payload}
    else:
        if not refresh_token:
            raise HTTPException(
                status_code=400,
                detail="No refresh_token returned from Google on first connect. "
                "Revoke previous access in Google account settings then retry.",
            )
        result = db.table("oauth_credentials").insert(payload).execute()
        cred = (result.data or [payload])[0]

    return {
        "status": "connected",
        "account_email": account_email,
        "credential_id": cred.get("id"),
        "scopes": scopes,
    }


# --- Status (admin-gated) -------------------------------------------------


@admin_router.get("/status")
async def google_oauth_status(
    auth=Depends(get_current_user_org),
) -> dict[str, Any]:
    """Return `{connected, expires_at, account_email, last_error}`.

    Connected when at least one `oauth_credentials` row with provider=google
    exists. We surface the most recent row (by `updated_at desc`) — single-
    account flow today, so "most recent" === "current".

    Admin gate via the seed-canonical ``get_current_user_org`` factory.
    """
    db = get_supabase_client()
    result = (
        db.table("oauth_credentials")
        .select("account_email, access_token_expires_at, scopes, updated_at")
        .eq("provider", "google")
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return {"connected": False}
    row = rows[0]
    return {
        "connected": True,
        "account_email": row.get("account_email"),
        "expires_at": row.get("access_token_expires_at"),
        "last_error": None,
    }
