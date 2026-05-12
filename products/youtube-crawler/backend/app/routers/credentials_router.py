"""Operator-facing Google credentials router.

Phase 1 of `youtube-crawler-domain-implementation` (PROJECT.md §6 Phase 1).

ENDPOINTS
---------
- POST /api/credentials/connect    → returns `{auth_url, state}` (start OAuth)
- GET  /api/credentials/callback   → Google redirects here w/ ?code&state
- POST /api/credentials/disconnect → revoke at Google + mark row revoked
- GET  /api/credentials/status     → non-secret snapshot (connected? scopes? email?)

SHAPE DECISION
--------------
The seed ships `oauth_router(*providers, on_callback=...)` mounting at
`/api/oauth/google/...`. The brief asks for `/api/credentials/...` — a
product-specific shape. Underneath this router consumes `GoogleProvider`
+ `FakeOAuthProvider` from `noctusai_lib.security.oauth`, so the OAuth
mechanics are not forked at the seed.

The seed's `oauth_router` is a generic Google-OAuth-callback surface for
products that DON'T need product-specific persistence shape. youtube-crawler
needs (a) per-(org,user) row, (b) at-rest encryption with the product's
vault key, (c) state-nonce CSRF guard tied to the row. That's why we
wire a product router instead of consuming `oauth_router` directly.

AUTH
----
- /connect + /disconnect + /status → require `Depends(get_current_user_org)`
  (the operator must be logged in to bind their own creds).
- /callback → NO auth dep. Google redirects the browser here AFTER the
  consent screen; the user's bearer is on a different origin. The route
  is authenticated by the **state nonce** (CSRF guard).

RATE LIMITING
-------------
All four endpoints apply the product's `limiter` via the
`@registry:own:youtube-crawler` CORS scope. The callback bypasses bearer
auth but stays rate-limited so a misbehaving provider can't loop forever.

NOTE: this module deliberately does NOT use `from __future__ import annotations`.
Pydantic v2 + FastAPI need runtime-resolvable types for response_model /
request-body schemas; PEP 563 ForwardRefs break `app.include_router(...)`
at startup with `PydanticUndefinedAnnotation`.
"""
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from noctusai_lib.api import StrictHttpModel

from app.dependencies import get_current_user_org
from app.rate_limit import limiter
from app.services.credential_vault import (
    VaultKeyMissingError,
    make_vault_from_settings,
)
from app.services.google_oauth_service import (
    DEFAULT_SCOPES,
    ConnectionStatus,
    GoogleOAuthService,
    make_google_oauth_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/credentials", tags=["Credentials"])


# ─── Schemas ─────────────────────────────────────────────────────────────────


class ConnectRequest(StrictHttpModel):
    """Body of POST /api/credentials/connect.

    `redirect_uri` MUST exactly match a redirect URI registered with the
    Google Cloud Console OAuth client — otherwise Google rejects the consent
    screen with `redirect_uri_mismatch`. The frontend supplies its own
    redirect URI (typically `${origin}/credentials/callback`) so dev /
    staging / prod can each register their own.
    """

    redirect_uri: str


class ConnectResponse(StrictHttpModel):
    """`{auth_url, state}` — the consent URL the frontend should redirect to."""

    auth_url: str
    state: str


class StatusResponse(StrictHttpModel):
    """Non-secret snapshot of the operator's Google connection."""

    connected: bool
    email: Optional[str] = None
    scopes: list[str] = []
    connected_at: Optional[str] = None      # ISO-8601 or None
    revoked_at: Optional[str] = None        # ISO-8601 or None


class DisconnectResponse(StrictHttpModel):
    """`{disconnected: bool}` — True when we revoked + marked, False when no-op."""

    disconnected: bool


# ─── Service factory (per-request, lazy) ─────────────────────────────────────
#
# We don't cache the service at module load because (a) the settings object
# is patched in tests and (b) the admin client factory ALSO gets patched in
# conftest. Build per-request — the cost is a few attribute lookups, and the
# vault key + provider config are read once per service.


def _build_service() -> GoogleOAuthService:
    """Build a `GoogleOAuthService` from product settings + admin client.

    Imports happen inside the function so the test conftest's monkey-patches
    on `app.database._db.get_admin_client` take effect before we resolve the
    factory.
    """
    # Late import + late-bound callable so the conftest patches on
    # `app.database._db.get_admin_client` AND on `noctusai_seed.database.
    # DatabaseModule.get_admin_client` reach the call site. Capturing the
    # bound method at module import time would freeze the pre-patch
    # reference. The lambda re-resolves on every call.
    from app.config import settings
    from app import database as _db_mod

    try:
        vault = make_vault_from_settings(settings)
    except VaultKeyMissingError as exc:
        # Map missing key → 503 so the operator sees a deployment-config
        # problem rather than a generic 500. Never returned in tests because
        # fixtures inject a deterministic key via patched settings.
        raise HTTPException(
            status_code=503,
            detail=f"Vault not configured: {exc}",
        ) from exc

    client_id = getattr(settings, "google_oauth_client_id", "") or ""
    client_secret = getattr(settings, "google_oauth_client_secret", "") or ""
    use_fake = not (client_id and client_secret)

    return make_google_oauth_service(
        vault=vault,
        get_admin_client=lambda: _db_mod._db.get_admin_client(),
        client_id=client_id or "fake-id",
        client_secret=client_secret or "fake-secret",
        use_fake=use_fake,
        scopes=DEFAULT_SCOPES,
    )


# ─── POST /api/credentials/connect ───────────────────────────────────────────


@router.post("/connect", response_model=ConnectResponse)
@limiter.limit("10/minute")
async def connect(
    request: Request,
    body: ConnectRequest,
    auth=Depends(get_current_user_org),
):
    """Generate the Google consent URL for the logged-in operator.

    Persists the CSRF nonce on the credential row so /callback can verify.
    Returns `{auth_url, state}`; the frontend redirects the browser to
    `auth_url`. Google handles consent + redirects to `redirect_uri?code=…&state=…`.
    """
    user, _token, org_id = auth
    service = _build_service()
    auth_url = await service.initiate(
        org_id=org_id,
        user_id=user.id,
        redirect_uri=body.redirect_uri,
    )
    return ConnectResponse(auth_url=auth_url.url, state=auth_url.state)


# ─── GET /api/credentials/callback ───────────────────────────────────────────


@router.get("/callback")
@limiter.limit("30/minute")
async def callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    redirect_uri: Optional[str] = None,
) -> dict:
    """Google's redirect target. Verifies state, exchanges code, persists tokens.

    Note: `redirect_uri` arrives as a query param the frontend appended to
    the consent URL (since Google itself does NOT echo the redirect_uri
    back — it only sends `code` + `state`). The frontend's `/callback`
    handler MUST pass `redirect_uri` through unchanged.

    On success → 200 with `{ok: true, ...}`. On failure → 400 with `{ok:
    false, error: ...}`. We deliberately don't 500 here: Google's redirect
    is the only signal the operator gets that something went wrong, so we
    want the response surface to be diagnostic.
    """
    if error:
        # Google appends ?error=access_denied when the user declines.
        return {"ok": False, "error": error, "state": state}
    if not code or not state or not redirect_uri:
        raise HTTPException(
            status_code=400,
            detail="missing required query params: code, state, redirect_uri",
        )

    service = _build_service()
    try:
        org_id, user_id = await service.handle_callback(
            code=code, state=state, redirect_uri=redirect_uri
        )
    except ValueError as exc:
        # Known callback failure modes (unknown state, expired state,
        # missing refresh_token) → 400 with the reason. The OAuth provider's
        # network errors come up here too if exchange_code raises; the seed
        # GoogleProvider wraps them in HTTPStatusError. We collapse to 400
        # because the user-facing recovery is always "click connect again".
        logger.warning("credentials callback failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface as 502, never 500
        logger.exception("credentials callback unexpected failure")
        raise HTTPException(
            status_code=502,
            detail=f"callback exchange failed: {exc.__class__.__name__}",
        ) from exc

    return {"ok": True, "state": state, "org_id": org_id, "user_id": user_id}


# ─── POST /api/credentials/disconnect ────────────────────────────────────────


@router.post("/disconnect", response_model=DisconnectResponse)
@limiter.limit("10/minute")
async def disconnect(
    request: Request,
    auth=Depends(get_current_user_org),
):
    """Revoke at Google + mark the row revoked. Idempotent."""
    user, _token, org_id = auth
    service = _build_service()
    did = await service.disconnect(org_id=org_id, user_id=user.id)
    return DisconnectResponse(disconnected=did)


# ─── GET /api/credentials/status ─────────────────────────────────────────────


@router.get("/status", response_model=StatusResponse)
@limiter.limit("60/minute")
async def status(
    request: Request,
    auth=Depends(get_current_user_org),
):
    """Non-secret snapshot of the operator's Google connection state."""
    user, _token, org_id = auth
    service = _build_service()
    snapshot: ConnectionStatus = await service.status(
        org_id=org_id, user_id=user.id
    )
    return StatusResponse(
        connected=snapshot.connected,
        email=snapshot.email,
        scopes=snapshot.scopes,
        connected_at=snapshot.connected_at.isoformat() if snapshot.connected_at else None,
        revoked_at=snapshot.revoked_at.isoformat() if snapshot.revoked_at else None,
    )


__all__ = ["router"]
