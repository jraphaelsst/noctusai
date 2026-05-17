"""Meta (Facebook + Instagram) OAuth bootstrap + status endpoints.

Shape mirrors ``calendar_router``:

1. **OAuth bootstrap** — one-time consent flow that turns
   ``META_APP_ID`` / ``META_APP_SECRET`` into a stored credential row
   (encrypted via :class:`CredentialStore`, provider=``meta``).

   Flow:
   - ``GET /api/meta/oauth/start`` — operator visits this URL; server
     responds with a 302 to ``https://www.facebook.com/v21.0/dialog/oauth?...``.
   - User completes consent → Facebook redirects to
     ``GET /api/meta/oauth/callback?code=...&state=<org_id>:<nonce>``.
   - Server exchanges the code (short-lived) → swaps for long-lived,
     probes /me, persists the bundle, then 302's the operator back to
     the platform Settings page.

2. **Status check** — ``GET /api/meta/status`` returns which adapter
   the factory would build today plus a summary of connected pages /
   IG accounts. No side effects.

The ``state`` token encodes ``<org_id>:<nonce>`` — same shape as
calendar_router so the inbox plumbing is identical.
"""
from __future__ import annotations

import logging
import secrets
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.config import settings
from app.dependencies import get_admin_client
from app.services.credential_store import (
    CredentialStore,
    EncryptionNotConfigured,
)
from app.services.meta import (
    META_PROVIDER,
    FakeMetaAdapter,
    MetaOAuthAdapter,
    get_meta_adapter,
)
from app.services.meta._meta_api import (
    META_KITCHEN_SINK_SCOPES,
    MetaGraphError,
    discover_app_permissions,
    exchange_code_for_token,
    exchange_short_for_long_lived,
    graph_get,
    resolve_oauth_scopes,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meta", tags=["meta"])


# ─── Response shapes ───────────────────────────────────────────────────
class MetaStatusResponse(BaseModel):
    configured: bool          # env vars set
    adapter: str              # "oauth" | "fake"
    auth_mode: str            # "system_user" | "user_oauth" | "none"
    consent_required: bool    # configured AND no stored credential AND no system-user-token
    user_id: str | None = None
    user_name: str | None = None
    pages_count: int = 0
    instagram_accounts_count: int = 0
    error: str | None = None


class MetaOAuthStartResponse(BaseModel):
    auth_url: str
    state: str
    scopes: list[str]
    scope_source: str  # "configured" | "auto-discovered" | "kitchen-sink-fallback"


class MetaScopesResponse(BaseModel):
    configured: list[str]                  # what META_OAUTH_SCOPES would request
    discovered_from_graph: list[str] | None  # what /{app-id}/permissions returns
    kitchen_sink_fallback: list[str]       # the hardcoded full list
    granted_to_user: list[str] | None      # what the user actually approved (after consent)
    declined_by_user: list[str] | None     # what the user denied at consent
    note: str


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
    """Mirror calendar_router's resolution: query string overrides
    fall back to the local-dev org id while the Meta surface runs
    without auth in front of it."""
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
    if isinstance(adapter, MetaOAuthAdapter):
        return "oauth"
    if isinstance(adapter, FakeMetaAdapter):
        return "fake"
    return type(adapter).__name__


# ─── Status ────────────────────────────────────────────────────────────
@router.get("/status", response_model=MetaStatusResponse)
def meta_status(org_id: str | None = Query(default=None)) -> MetaStatusResponse:
    """Which Meta adapter would the factory return today, and what does
    it see?

    Probes ``/me`` + counts pages + counts IG accounts when the adapter
    is OAuth-backed. Returns a structured ``error`` field instead of
    raising so the platform UI can render "needs reconnection".
    """
    resolved_org = _resolve_org_id(org_id)
    has_system_user = bool(settings.meta_system_user_token)
    has_oauth_pair = bool(settings.meta_app_id and settings.meta_app_secret)
    configured = has_system_user or has_oauth_pair

    try:
        store = _build_store()
    except HTTPException:
        store = None

    adapter = get_meta_adapter(
        org_id=resolved_org if store else None,
        credential_store=store,
    )
    label = _adapter_label(adapter)
    auth_mode = (
        getattr(adapter, "auth_mode", "none")
        if not isinstance(adapter, FakeMetaAdapter)
        else "none"
    )
    # consent_required only matters for the user_oauth path; system_user
    # mode bypasses consent entirely.
    consent_required = (
        not has_system_user and has_oauth_pair and label == "fake"
    )

    if label == "fake":
        return MetaStatusResponse(
            configured=configured,
            adapter=label,
            auth_mode=auth_mode,
            consent_required=consent_required,
        )

    # Live adapter — probe /me + counts.
    try:
        me = adapter.me()
        pages = adapter.list_pages()
        ig_accounts = adapter.list_instagram_accounts()
    except MetaGraphError as exc:
        return MetaStatusResponse(
            configured=configured,
            adapter=label,
            auth_mode=auth_mode,
            consent_required=exc.is_auth_error and auth_mode == "user_oauth",
            error=str(exc),
        )

    return MetaStatusResponse(
        configured=configured,
        adapter=label,
        auth_mode=auth_mode,
        consent_required=False,
        user_id=me.get("id"),
        user_name=me.get("name"),
        pages_count=len(pages),
        instagram_accounts_count=len(ig_accounts),
    )


# ─── OAuth start ───────────────────────────────────────────────────────
@router.get("/oauth/start", response_model=MetaOAuthStartResponse)
def meta_oauth_start(
    org_id: str | None = Query(default=None),
    redirect_to_consent: bool = Query(default=True),
) -> Any:
    """Begin the Facebook OAuth consent flow.

    Returns either a 302 to FB's consent dialog (default) or JSON with
    ``auth_url`` (when ``redirect_to_consent=false``) so the frontend
    can render its own "Connect Meta" button.

    Scopes requested live in ``META_OAUTH_SCOPES`` — defaults to the
    read-only set we need. Posting scopes (``pages_manage_posts``,
    ``instagram_content_publish``) are NOT in the v1 default because
    they require app review and we're not posting yet.
    """
    if not settings.meta_app_id or not settings.meta_app_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="META_APP_ID / META_APP_SECRET not configured.",
        )

    resolved_org = _resolve_org_id(org_id)
    nonce = secrets.token_urlsafe(16)
    state = f"{resolved_org}:{nonce}"

    # Resolve scopes:
    # - If META_OAUTH_SCOPES is set to a real list → use it verbatim
    # - If empty or "auto" → discover from Graph (fallback to kitchen-sink)
    scopes = resolve_oauth_scopes(
        configured=settings.meta_oauth_scopes,
        app_id=settings.meta_app_id,
        app_secret=settings.meta_app_secret,
    )
    raw = (settings.meta_oauth_scopes or "").strip()
    if raw and raw.lower() != "auto":
        scope_source = "configured"
    elif scopes == list(META_KITCHEN_SINK_SCOPES):
        scope_source = "kitchen-sink-fallback"
    else:
        scope_source = "auto-discovered"

    from urllib.parse import urlencode

    auth_params = {
        "client_id": settings.meta_app_id,
        "redirect_uri": settings.meta_oauth_redirect_uri,
        "scope": ",".join(scopes),
        "response_type": "code",
        "state": state,
        # ``auth_type=rerequest`` forces FB to re-ask for previously
        # denied permissions on every flow — useful while we're
        # iterating on the scope set.
        "auth_type": "rerequest",
    }
    auth_url = (
        f"https://www.facebook.com/{settings.meta_graph_api_version}"
        f"/dialog/oauth?{urlencode(auth_params)}"
    )

    if redirect_to_consent:
        return RedirectResponse(auth_url, status_code=status.HTTP_302_FOUND)
    return MetaOAuthStartResponse(
        auth_url=auth_url,
        state=state,
        scopes=scopes,
        scope_source=scope_source,
    )


# ─── Scope introspection ───────────────────────────────────────────────
@router.get("/scopes", response_model=MetaScopesResponse)
def meta_scopes(org_id: str | None = Query(default=None)) -> MetaScopesResponse:
    """Show what scopes the app COULD ask for + what the user HAS granted.

    Useful when figuring out "did Meta accept all my Use Cases?" without
    having to spelunk through the app dashboard. Returns:

    * ``configured``: scope list straight from META_OAUTH_SCOPES env (or
      auto-resolved list if env is empty / "auto").
    * ``discovered_from_graph``: what Graph's ``/{app-id}/permissions``
      endpoint returns — i.e. what the app is actually approved for.
      None if META_APP_ID/SECRET aren't configured.
    * ``kitchen_sink_fallback``: the hardcoded full list of read+write
      scopes the code knows about — what gets used when Graph discovery
      returns empty (common in pure dev mode).
    * ``granted_to_user`` / ``declined_by_user``: after a user has
      consented, what they actually approved vs. declined. Comes from
      ``GET /me/permissions`` with the stored user token. None if no
      consent yet.
    """
    if not settings.meta_app_id or not settings.meta_app_secret:
        return MetaScopesResponse(
            configured=[],
            discovered_from_graph=None,
            kitchen_sink_fallback=list(META_KITCHEN_SINK_SCOPES),
            granted_to_user=None,
            declined_by_user=None,
            note=(
                "META_APP_ID / META_APP_SECRET not configured — set them "
                "in .env and restart to enable discovery."
            ),
        )

    configured = resolve_oauth_scopes(
        configured=settings.meta_oauth_scopes,
        app_id=settings.meta_app_id,
        app_secret=settings.meta_app_secret,
    )

    discovered: list[str] | None = None
    try:
        discovered = discover_app_permissions(
            app_id=settings.meta_app_id,
            app_secret=settings.meta_app_secret,
        )
        # discover_app_permissions falls back to kitchen-sink on empty —
        # surface a None instead of the fallback so the UI distinguishes.
        if discovered == list(META_KITCHEN_SINK_SCOPES):
            discovered = None
    except Exception as exc:
        logger.warning("Meta scope discovery failed: %s", exc)

    granted: list[str] | None = None
    declined: list[str] | None = None
    try:
        resolved_org = _resolve_org_id(org_id)
        store = _build_store()
        from app.services.meta import META_PROVIDER

        stored = store.get(org_id=resolved_org, provider=META_PROVIDER)
        if stored and stored.tokens.get("access_token"):
            try:
                body = graph_get(
                    "/me/permissions",
                    access_token=stored.tokens["access_token"],
                )
                granted = [
                    r["permission"] for r in (body.get("data") or [])
                    if r.get("status") == "granted"
                ]
                declined = [
                    r["permission"] for r in (body.get("data") or [])
                    if r.get("status") == "declined"
                ]
            except MetaGraphError as exc:
                logger.warning("Meta /me/permissions probe failed: %s", exc)
    except HTTPException:
        pass

    note = (
        f"Will request {len(configured)} scope(s) at next consent. "
        "Set META_OAUTH_SCOPES=auto in .env (or leave empty) for full "
        "kitchen-sink discovery; set a comma-separated list to pin a "
        "specific subset."
    )

    return MetaScopesResponse(
        configured=configured,
        discovered_from_graph=discovered,
        kitchen_sink_fallback=list(META_KITCHEN_SINK_SCOPES),
        granted_to_user=granted,
        declined_by_user=declined,
        note=note,
    )


# ─── OAuth callback ────────────────────────────────────────────────────
@router.get("/oauth/callback")
def meta_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    """Facebook's redirect target. Exchanges code → short-lived →
    long-lived → /me probe → persist.
    """
    if error:
        detail = f"OAuth flow returned an error: {error}"
        if error_description:
            detail = f"{detail} — {error_description}"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
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

    # 1) code → short-lived user token
    try:
        short_bundle = exchange_code_for_token(
            code=code,
            client_id=settings.meta_app_id,
            client_secret=settings.meta_app_secret,
            redirect_uri=settings.meta_oauth_redirect_uri,
        )
    except MetaGraphError as exc:
        logger.exception("meta oauth code exchange failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth code exchange failed: {exc}",
        ) from exc

    short_token = short_bundle.get("access_token")
    if not short_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meta did not return an access_token from the code exchange.",
        )

    # 2) short → long-lived user token
    try:
        long_bundle = exchange_short_for_long_lived(
            short_lived_token=short_token,
            client_id=settings.meta_app_id,
            client_secret=settings.meta_app_secret,
        )
    except MetaGraphError as exc:
        logger.exception("meta oauth long-lived exchange failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Long-lived token exchange failed: {exc}",
        ) from exc

    long_token = long_bundle.get("access_token") or short_token
    expires_in = long_bundle.get("expires_in")

    # 3) probe /me so we can store user_id + name for display.
    user_id: str | None = None
    user_name: str | None = None
    try:
        me = graph_get(
            "/me",
            access_token=long_token,
            params={"fields": "id,name"},
        )
        user_id = me.get("id")
        user_name = me.get("name")
    except MetaGraphError:
        logger.exception("meta oauth /me probe failed (non-fatal)")

    # 4) persist
    # Resolve which scopes were requested at consent — same logic
    # oauth_start used, so the stored credential reflects what the user
    # was prompted with (not just the static env value).
    requested_scopes = resolve_oauth_scopes(
        configured=settings.meta_oauth_scopes,
        app_id=settings.meta_app_id,
        app_secret=settings.meta_app_secret,
    )

    stored_tokens = {
        "access_token": long_token,
        "token_type": long_bundle.get("token_type", "bearer"),
        "expires_in": expires_in,
        "scope": ",".join(requested_scopes),
        "user_id": user_id,
        "user_name": user_name,
    }
    store.upsert(
        org_id=org_id,
        provider=META_PROVIDER,
        tokens=stored_tokens,
        channel_id=user_id,
        channel_title=user_name,
        scopes=requested_scopes,
    )

    if settings.frontend_base_url:
        target = (
            settings.frontend_base_url.rstrip("/")
            + "/configuracoes?meta=connected"
        )
        return RedirectResponse(target, status_code=status.HTTP_302_FOUND)
    return {
        "ok": True,
        "user_id": user_id,
        "user_name": user_name,
        "org_id": str(org_id),
    }


__all__ = ["router"]
