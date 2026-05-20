"""YouTube Settings router — Settings → YouTube tab + OAuth callback.

Endpoints:
    GET    /api/settings/youtube/status        connection state + channel metadata
    GET    /api/settings/youtube/auth-url      OAuth consent URL (PKCE)
    DELETE /api/settings/youtube/disconnect    revoke + delete tokens
    GET    /api/youtube/oauth/callback         Google's redirect target (separate router)

The OAuth callback path lives at ``/api/youtube/oauth/callback`` — outside
the ``/settings`` prefix — because Google requires a fixed redirect URI;
moving it under settings would break existing OAuth-client configs. Two
routers are exported (``router`` + ``oauth_router``) so the module's
``register()`` can mount both at the same prefix shape the legacy
app-level settings_router used (zero URL change pre/post-split).

Auth pattern: ``Depends(get_current_user_org)`` returning
``(user, token, raw_org_id)``. The user-scoped Supabase client is then
built via ``get_user_client(token)`` inside the route body — the seed's
``Depends(get_user_client)`` shape doesn't chain because its positional
``token`` arg becomes a required query parameter. See
``KB § PATTERNS/backend.md § Auth — canonical pattern``.
"""
from __future__ import annotations

import logging
import secrets
from urllib.parse import urljoin
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.config import settings
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
    get_user_client,
)
from app.modules.youtube.schemas.settings import YouTubeAuthURL, YouTubeStatus
from app.modules.youtube.services.youtube import YouTubeService, YouTubeServiceError
from app.services.credential_vault import (
    CredentialStore,
    EncryptionNotConfigured,
    build_credential_store,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])
oauth_router = APIRouter(prefix="/api/youtube/oauth", tags=["youtube-oauth"])


# ─── Construction helpers ──────────────────────────────────────────────
def _build_credential_store(supabase) -> CredentialStore:
    """Build a CredentialStore from the request-scoped supabase client.

    A 503 is right when ENCRYPTION_KEY is missing — this is a config gap,
    not a server bug. The Settings → API Keys tab makes the gap visible.
    """
    try:
        return build_credential_store(supabase)
    except EncryptionNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


def _build_youtube_service(supabase) -> YouTubeService:
    try:
        return YouTubeService(
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            redirect_uri=settings.youtube_redirect_uri,
            credential_store=_build_credential_store(supabase),
        )
    except YouTubeServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


# ─── YouTube tab ───────────────────────────────────────────────────────
@router.get("/youtube/status", response_model=YouTubeStatus)
def get_youtube_status(
    auth: tuple = Depends(get_current_user_org),
) -> YouTubeStatus:
    """Connection state + cached channel metadata. Never triggers a
    YouTube API call by itself — uses what was persisted at OAuth time
    + last channel sync. The Settings UI calls this on every page load,
    so making it free of YouTube API quota matters.
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    supabase = get_user_client(token)
    store = _build_credential_store(supabase)
    record = store.get(str(org_id), "youtube")
    if record is None:
        return YouTubeStatus(connected=False)

    return YouTubeStatus(
        connected=True,
        channel_id=record.metadata.get("channel_id"),
        channel_title=record.metadata.get("channel_title"),
        scopes=record.metadata.get("scopes", []),
        connected_at=record.created_at,
    )


_PKCE_VERIFIER_KEY_PREFIX = "youtube:oauth:pkce:"
_PKCE_VERIFIER_TTL_SECONDS = 600  # 10 min — consent flows complete in seconds


def _pkce_redis_client():
    """Lazy Redis client for PKCE verifier round-trip.

    Returns ``None`` if redis is unreachable — the OAuth flow still
    works (Google just rejects the exchange with a clear error message)
    but we don't want to 500 the auth-url request just because Redis
    blipped."""
    try:
        import redis

        client = redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception as exc:  # pragma: no cover — exercised in container only
        logger.warning("PKCE Redis unavailable: %s", exc)
        return None


@router.get("/youtube/auth-url", response_model=YouTubeAuthURL)
def get_youtube_auth_url(
    auth: tuple = Depends(get_current_user_org),
) -> YouTubeAuthURL:
    """Build the consent URL the user should be redirected to.

    The opaque ``state`` round-trips the org_id through Google's flow so
    the callback knows which tenant just connected — without trusting
    redirect_uri parsing alone (which a malicious caller could spoof if
    we relied on the session cookie alone for tenant binding).

    The seed ``GoogleProvider(use_pkce=True)`` generates a fresh RFC 7636
    PKCE ``code_verifier`` per call, embeds the SHA256 challenge in the
    URL, and requires the verifier back at ``exchange_code`` time. We
    persist the verifier in Redis keyed by ``state`` (10-min TTL) so the
    callback handler can replay it without storing OAuth secrets in a
    cookie or in the database. Methodology:
    ``KB § PATTERNS/absorbed-product-seed-shape-seam.md`` (the seed-
    shape-seam pattern; PKCE is the N=3 instance).
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    supabase = get_user_client(token)
    yt = _build_youtube_service(supabase)
    state = f"{org_id}:{secrets.token_urlsafe(16)}"
    auth_url, code_verifier = yt.get_auth_url(state=state)
    redis_client = _pkce_redis_client()
    if redis_client is not None and code_verifier:
        try:
            redis_client.set(
                f"{_PKCE_VERIFIER_KEY_PREFIX}{state}",
                code_verifier,
                ex=_PKCE_VERIFIER_TTL_SECONDS,
            )
        except Exception as exc:
            logger.warning("failed to persist PKCE verifier: %s", exc)
    return YouTubeAuthURL(
        auth_url=auth_url,
        state=state,
    )


@router.delete(
    "/youtube/disconnect",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def disconnect_youtube(
    auth: tuple = Depends(get_current_user_org),
) -> None:
    """Revoke + delete tokens. Idempotent — already-disconnected returns
    204 too, so the UI doesn't need separate handling for the rare race
    where two tabs both click Disconnect."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    supabase = get_user_client(token)
    yt = _build_youtube_service(supabase)
    yt.revoke_and_disconnect(org_id=org_id)


@oauth_router.get("/callback")
def youtube_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    """Google's redirect target. Exchanges ``code`` → tokens, fetches
    channel metadata, persists encrypted, then redirects to the frontend
    Settings page. Must live at the exact path registered as
    redirect_uri in the OAuth client config — relocating breaks every
    deployed install.

    Uses the admin (service-role) Supabase client because Google's
    redirect carries no Authorization header — there's no JWT to bind a
    user-scoped client to. Tenant binding is handled via the opaque
    ``state`` token (parsed below) so RLS bypass here is bounded by
    state-token validity, not blanket trust.
    """
    supabase = get_admin_client()
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
    if not org_part:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token malformed.",
        )
    try:
        org_id = UUID(org_part)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token does not encode a valid org_id.",
        ) from exc

    yt = _build_youtube_service(supabase)
    store = _build_credential_store(supabase)

    # Replay the PKCE verifier that was persisted at auth-url time.
    # Missing → exchange will fail with `invalid_grant: Missing code
    # verifier` and the caller has to re-initiate the flow.
    code_verifier: str | None = None
    redis_client = _pkce_redis_client()
    if redis_client is not None:
        try:
            key = f"{_PKCE_VERIFIER_KEY_PREFIX}{state}"
            code_verifier = redis_client.get(key)
            if code_verifier:
                redis_client.delete(key)  # single-use
        except Exception as exc:
            logger.warning("failed to retrieve PKCE verifier: %s", exc)

    try:
        bundle = yt.exchange_code(code=code, code_verifier=code_verifier)
    except Exception as exc:
        logger.exception("youtube oauth exchange failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth code exchange failed: {exc}",
        ) from exc

    # Persist before fetching channel info so a flaky channels.list call
    # doesn't lose the freshly-issued refresh_token. channel_id +
    # channel_title get filled on the first successful sync.
    store.put(
        str(org_id), "youtube", bundle, metadata={"scopes": bundle.get("scopes", [])})

    try:
        info = yt.get_channel_info(org_id=org_id)
        store.put(
            str(org_id), "youtube", bundle, metadata={"channel_id": info.channel_id, "channel_title": info.title, "scopes": bundle.get("scopes", [])})
    except YouTubeServiceError:
        logger.warning(
            "channel_info fetch failed during oauth callback for org_id=%s — "
            "tokens persisted, channel metadata will populate on next status read",
            org_id,
        )

    # Redirect back to the Settings page; the UI re-fetches /youtube/status
    # to surface the freshly-populated channel info.
    redirect_url = "/configuracoes?youtube=connected"
    if settings.frontend_base_url:
        redirect_url = urljoin(
            settings.frontend_base_url.rstrip("/") + "/",
            "configuracoes?youtube=connected",
        )
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


# Re-export both routers — module register() consumes them.
__all__ = ["router", "oauth_router"]
