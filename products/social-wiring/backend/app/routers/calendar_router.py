"""Google Calendar OAuth bootstrap + status endpoints.

Two surfaces:

1. **OAuth bootstrap** — one-time consent flow that turns
   ``GOOGLE_OAUTH_CLIENT_ID`` / ``GOOGLE_OAUTH_CLIENT_SECRET`` into a
   stored credential row (encrypted via :class:`CredentialStore`,
   provider=``google_calendar``). Mirrors the YouTube OAuth callback
   pattern that already lives in ``settings_router.oauth_router``.

   Flow:
   - ``GET /api/calendar/oauth/start`` — operator visits this URL,
     server responds with a 302 to Google's consent screen.
   - User completes consent → Google redirects to
     ``GET /api/calendar/oauth/callback?code=...&state=<org_id>:<nonce>``.
   - Server exchanges the code, persists the bundle, then 302's the
     operator back to the platform Settings page.

2. **Status check** — ``GET /api/calendar/status`` returns which
   adapter the factory would build today (oauth/service-account/fake)
   so the operator can see whether consent is needed.

OAuth path identical in shape to ``whatsapp-google-scheduling``'s
``app/api/oauth.py`` so the operator's Google Cloud Console OAuth
client + redirect-URI registration can be reused with one URL change.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.config import settings
from app.dependencies import get_admin_client
from app.services.calendar import (
    CALENDAR_PROVIDER,
    FakeCalendarAdapter,
    GoogleCalendarAdapter,
    GoogleCalendarOAuthAdapter,
    get_calendar_adapter,
)
from app.services.credential_store import (
    CredentialStore,
    EncryptionNotConfigured,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


# ─── Response shapes ───────────────────────────────────────────────────
class CalendarStatus(BaseModel):
    configured: bool
    adapter: str  # "oauth" | "service_account" | "fake"
    account_email: str | None = None
    default_calendar_id: str
    default_timezone: str
    consent_required: bool


class CalendarOAuthStartResponse(BaseModel):
    auth_url: str
    state: str
    scopes: list[str] = []
    scope_source: str = "configured"  # "configured" | "kitchen-sink"


# ─── Helpers ───────────────────────────────────────────────────────────
def _build_store() -> CredentialStore:
    try:
        return CredentialStore(get_admin_client(), settings.encryption_key)
    except EncryptionNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


def _resolve_org_id(raw: str | None) -> UUID:
    """The Calendar surface runs unauthenticated for now (no JWT) so we
    take org_id either via the query string or fall back to the
    local-dev org. Mirrors what whatsapp_router does for chat."""
    if raw:
        try:
            return UUID(raw)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid org_id",
            ) from exc
    return UUID(settings.local_dev_org_id)


def _adapter_label(adapter) -> str:
    if isinstance(adapter, GoogleCalendarOAuthAdapter):
        return "oauth"
    if isinstance(adapter, GoogleCalendarAdapter):
        return "service_account"
    if isinstance(adapter, FakeCalendarAdapter):
        return "fake"
    return type(adapter).__name__


# ─── Status ────────────────────────────────────────────────────────────
@router.get("/status", response_model=CalendarStatus)
def calendar_status(org_id: str | None = Query(default=None)) -> CalendarStatus:
    """Which calendar adapter would the factory return today?

    Useful for the platform UI to show "connect Google Calendar" or
    "consented as <email>". No side effects.
    """
    resolved_org = _resolve_org_id(org_id)
    try:
        store = _build_store()
    except HTTPException:
        store = None

    adapter = get_calendar_adapter(
        org_id=resolved_org if store else None,
        credential_store=store,
    )
    label = _adapter_label(adapter)
    consent_required = label == "fake" and bool(settings.google_oauth_client_id)
    return CalendarStatus(
        configured=label != "fake",
        adapter=label,
        account_email=settings.google_oauth_account_email or None,
        default_calendar_id=settings.google_calendar_default_id,
        default_timezone=settings.google_calendar_default_timezone,
        consent_required=consent_required,
    )


# ─── OAuth start ───────────────────────────────────────────────────────
@router.get("/oauth/start", response_model=CalendarOAuthStartResponse)
def calendar_oauth_start(
    org_id: str | None = Query(default=None),
    redirect_to_consent: bool = Query(default=True),
) -> Any:
    """Begin the Google OAuth consent flow.

    Returns either:
    - A 302 redirect to Google's consent screen (default — the operator
      just opens this URL in a browser).
    - A JSON payload with ``auth_url`` (when ``redirect_to_consent=false``)
      so the frontend can render its own "Connect Calendar" button.

    ``state`` is ``<org_id>:<nonce>`` — same pattern as the YouTube
    OAuth flow. The callback parses it back to bind the new credential
    to the right tenant.
    """
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET not configured.",
        )

    resolved_org = _resolve_org_id(org_id)
    nonce = secrets.token_urlsafe(16)
    state = f"{resolved_org}:{nonce}"

    # Resolve scopes via the shared resolver — supports
    # GOOGLE_OAUTH_SCOPES="auto" (kitchen-sink), empty (same), or an
    # explicit comma/space-separated list.
    from app.services.google_scopes import (
        GOOGLE_KITCHEN_SINK_SCOPES,
        format_scopes_for_authorize,
        resolve_google_scopes,
    )

    scopes = resolve_google_scopes(configured=settings.google_oauth_scopes)
    raw = (settings.google_oauth_scopes or "").strip()
    if raw and raw.lower() != "auto":
        scope_source = "configured"
    elif scopes == list(GOOGLE_KITCHEN_SINK_SCOPES):
        scope_source = "kitchen-sink"
    else:
        scope_source = "configured"

    # Build the URL manually so we don't pull google-auth-oauthlib for
    # just the consent screen. Parameters match the standard Google
    # OAuth 2.0 authorization-code flow.
    from urllib.parse import urlencode

    auth_params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": format_scopes_for_authorize(scopes),
        "access_type": "offline",
        "prompt": "consent",  # forces refresh_token issuance every time
        "state": state,
        "include_granted_scopes": "true",
    }
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(auth_params)
    )

    if redirect_to_consent:
        return RedirectResponse(auth_url, status_code=status.HTTP_302_FOUND)
    return CalendarOAuthStartResponse(
        auth_url=auth_url,
        state=state,
        scopes=scopes,
        scope_source=scope_source,
    )


# ─── OAuth callback ────────────────────────────────────────────────────
@router.get("/oauth/callback")
def calendar_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    """Google's redirect target. Exchanges ``code`` → bundle, fetches
    the consenting user's email, persists encrypted via
    :class:`CredentialStore`, then redirects to the frontend Settings
    page (or returns JSON when no frontend base URL is configured).
    """
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth flow returned an error: {error}",
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth callback missing code or state.",
        )

    org_part, _, _nonce = state.partition(":")
    try:
        org_id = UUID(org_part)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token does not encode a valid org_id.",
        ) from exc

    store = _build_store()

    # Exchange the code via httpx — keeps the dep surface minimal (no
    # google-auth-oauthlib import). Mirrors whatsapp-scheduling's
    # ``app/api/oauth.py`` shape.
    import httpx

    token_payload = {
        "code": code,
        "client_id": settings.google_oauth_client_id,
        "client_secret": settings.google_oauth_client_secret,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "grant_type": "authorization_code",
    }
    try:
        with httpx.Client(timeout=30) as client:
            token_response = client.post(
                "https://oauth2.googleapis.com/token", data=token_payload
            )
            token_response.raise_for_status()
            bundle = token_response.json()
    except httpx.HTTPError as exc:
        logger.exception("calendar oauth code exchange failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth code exchange failed: {exc}",
        ) from exc

    if not bundle.get("refresh_token"):
        # access_type=offline + prompt=consent should always produce a
        # refresh_token, but a second consent for an already-consented
        # account can skip it. Refuse rather than store an unusable
        # bundle.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Google did not return a refresh_token. Re-consent with "
                "the OAuth client and revoke prior access first at "
                "https://myaccount.google.com/permissions."
            ),
        )

    # Compute the expiry timestamp from `expires_in`.
    expires_at: str | None = None
    expires_in = bundle.get("expires_in")
    if isinstance(expires_in, int):
        from datetime import timedelta

        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        ).isoformat()

    # Probe the userinfo endpoint for the consenting account email.
    account_email = settings.google_oauth_account_email or None
    try:
        with httpx.Client(timeout=15) as client:
            ui = client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {bundle['access_token']}"},
            )
            if ui.status_code == 200:
                account_email = ui.json().get("email") or account_email
    except Exception:
        logger.exception("calendar oauth: userinfo probe failed (non-fatal)")

    # Resolve scopes via the shared resolver so the stored credential
    # row reflects what was actually requested at consent (not the raw
    # env value, which may have been "auto").
    from app.services.google_scopes import resolve_google_scopes

    requested_scopes = resolve_google_scopes(configured=settings.google_oauth_scopes)
    stored_tokens = {
        "access_token": bundle["access_token"],
        "refresh_token": bundle["refresh_token"],
        "expiry": expires_at,
        # Google's response includes the granted scope string — keep
        # that if present, otherwise fall back to what we requested.
        "scope": bundle.get("scope") or " ".join(requested_scopes),
        "token_type": bundle.get("token_type", "Bearer"),
        "account_email": account_email,
    }
    store.upsert(
        org_id=org_id,
        provider=CALENDAR_PROVIDER,
        tokens=stored_tokens,
        channel_id=None,
        channel_title=account_email,
        scopes=requested_scopes,
    )

    # Redirect back to the frontend if we have one configured; otherwise
    # return a small confirmation JSON so the operator sees a successful
    # result inline.
    if settings.frontend_base_url:
        target = (
            settings.frontend_base_url.rstrip("/")
            + "/configuracoes?calendar=connected"
        )
        return RedirectResponse(target, status_code=status.HTTP_302_FOUND)
    return {"ok": True, "account_email": account_email, "org_id": str(org_id)}


__all__ = ["router"]
