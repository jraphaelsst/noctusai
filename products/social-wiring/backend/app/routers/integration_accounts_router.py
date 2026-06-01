"""Multi-account integration credentials router — /api/integrations/*.

Endpoints:
    GET    /api/integrations/providers         → list of provider configs
    GET    /api/integrations/accounts          → list of IntegrationAccount (optional ?provider=)
    GET    /api/integrations/accounts/{id}     → fetch one account
    POST   /api/integrations/accounts          → create (manual entry)
    PATCH  /api/integrations/accounts/{id}     → update label/metadata/is_default
    PATCH  /api/integrations/accounts/{id}/set-default → set as default for its provider
    DELETE /api/integrations/accounts/{id}     → delete

    POST   /api/integrations/accounts/youtube/oauth/start    → {auth_url, state}
    GET    /api/integrations/accounts/youtube/oauth/callback → exchange code, create account

Auth: ``Depends(get_current_user_org)`` throughout. The admin client is
used for all DB writes (mirrors whatsapp_connections_router). The OAuth
callback uses the admin client too (no JWT from Google's redirect).

ENCRYPTION_KEY missing → 503 config-gap (mirrors credential_vault pattern).
"""
from __future__ import annotations

import logging
import secrets
from typing import Any, Optional
from urllib.parse import urljoin
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from noctusai_lib.integrations.youtube import make_youtube_client
from noctusai_lib.security.oauth import GoogleProvider
from pydantic import BaseModel, Field

from app.config import settings
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
    get_settings,
    get_user_client,
)
from app.config import SocialWiringSettings
from app.services.credential_vault import (
    CredentialStoreError,
    EncryptionNotConfigured,
)
from app.services.integration_account_service import (
    IntegrationAccount,
    IntegrationAccountNotFound,
    IntegrationAccountService,
    build_integration_account_service,
)
from app.services.integration_providers import PROVIDERS
from app.services.legacy_adoption import adopt_legacy_account

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


# ─── Pydantic schemas ─────────────────────────────────────────────────────────
class IntegrationAccountOut(BaseModel):
    """REST-safe representation — never exposes credentials."""

    id: UUID
    org_id: UUID
    provider: str
    account_label: str
    metadata: dict = Field(default_factory=dict)
    is_default: bool
    created_at: Any = None
    updated_at: Any = None
    # Channel-object fields (migration 008)
    client_id: Optional[UUID] = None
    status: str = "validated"
    channel_info: dict = Field(default_factory=dict)
    last_synced_at: Any = None

    class Config:
        from_attributes = True


class IntegrationAccountCreate(BaseModel):
    """Manual account creation body."""

    provider: str
    account_label: str
    credential: dict  # provider-specific key/value bag — Fernet-encrypted at rest
    metadata: dict = Field(default_factory=dict)
    is_default: bool = False
    client_id: Optional[UUID] = None

    class Config:
        extra = "forbid"


class IntegrationAccountUpdate(BaseModel):
    """Patch body — all fields optional."""

    account_label: Optional[str] = None
    metadata: Optional[dict] = None
    is_default: Optional[bool] = None
    client_id: Optional[UUID] = None
    status: Optional[str] = None

    class Config:
        extra = "forbid"


class YouTubeOAuthStartOut(BaseModel):
    auth_url: str
    state: str


# ─── DI seam ─────────────────────────────────────────────────────────────────
def get_account_service(
    cfg: SocialWiringSettings = Depends(get_settings),
) -> IntegrationAccountService:
    """Yield a wired IntegrationAccountService, mapping ENCRYPTION_KEY
    config-gap to a 503. Tests override via
    ``app.dependency_overrides[get_account_service]``. Per
    KB § PATTERNS/di-test-seam.md (Class-B, service DI)."""
    try:
        return build_integration_account_service(
            get_admin_client(), encryption_key=cfg.encryption_key
        )
    except EncryptionNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


# ─── helpers ──────────────────────────────────────────────────────────────────
def _out(account: IntegrationAccount) -> IntegrationAccountOut:
    return IntegrationAccountOut(
        id=account.id,
        org_id=account.org_id,
        provider=account.provider,
        account_label=account.account_label,
        metadata=account.metadata,
        is_default=account.is_default,
        created_at=account.created_at,
        updated_at=account.updated_at,
        client_id=account.client_id,
        status=account.status,
        channel_info=account.channel_info or {},
        last_synced_at=account.last_synced_at,
    )


def _require_account(
    svc: IntegrationAccountService,
    account_id: UUID,
    org_id: UUID,
) -> IntegrationAccount:
    """Fetch an account owner-scoped or 404."""
    acct = svc.get_account(account_id, org_id)
    if acct is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="integration account not found",
        )
    return acct


# ─── Provider registry ────────────────────────────────────────────────────────
@router.get("/providers")
def list_providers() -> list[dict]:
    """Return the v1 provider registry (display_name, oauth_supported,
    manual_key_fields, etc.). FE uses this to build the "Connect account"
    picker without hardcoding provider configs."""
    return PROVIDERS


# ─── Account CRUD ─────────────────────────────────────────────────────────────
@router.get("/accounts", response_model=list[IntegrationAccountOut])
def list_accounts(
    provider: Optional[str] = Query(default=None),
    client_id: Optional[UUID] = Query(default=None),
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
) -> list[IntegrationAccountOut]:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    accounts = svc.list_accounts(org_id=org_id, provider=provider, client_id=client_id)
    return [_out(a) for a in accounts]


@router.post(
    "/accounts/{provider}/adopt-legacy",
    response_model=Optional[IntegrationAccountOut],
)
def adopt_legacy(
    provider: str,
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
    cfg: SocialWiringSettings = Depends(get_settings),
) -> Optional[IntegrationAccountOut]:
    """Adopt a pre-existing single-account connection for ``provider`` into
    the multi-account model as a first-class (default) account.

    The canonical "import an existing connection" path — YouTube is pilot
    #1; the other single-account providers adopt through the SAME
    ``legacy_adoption.adopt_legacy_account`` function. Explicit + idempotent:
    returns the existing default if already adopted, or ``null`` if there is
    no legacy connection to adopt. The unified Conexões page calls this on
    load so an existing connection appears as a card (no silent GET-side
    backfill — adoption is a deliberate, observable step)."""
    from app.services.integration_providers import SUPPORTED_PROVIDER_IDS
    if provider not in SUPPORTED_PROVIDER_IDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unsupported provider '{provider}'",
        )
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    account = adopt_legacy_account(get_admin_client(), svc, org_id, provider, cfg)
    return _out(account) if account is not None else None


@router.get("/accounts/{account_id}", response_model=IntegrationAccountOut)
def get_account(
    account_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
) -> IntegrationAccountOut:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return _out(_require_account(svc, account_id, org_id))


@router.post(
    "/accounts",
    response_model=IntegrationAccountOut,
    status_code=status.HTTP_201_CREATED,
)
def create_account(
    body: IntegrationAccountCreate,
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
) -> IntegrationAccountOut:
    """Create an account via manual key entry. For OAuth-backed providers
    prefer the ``/accounts/{provider}/oauth/start`` endpoint instead —
    this path still works for providers that support both modes (e.g.
    meta with a system user token)."""
    from app.services.integration_providers import SUPPORTED_PROVIDER_IDS
    if body.provider not in SUPPORTED_PROVIDER_IDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unsupported provider '{body.provider}'",
        )
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        account = svc.create_account(
            org_id=org_id,
            provider=body.provider,
            account_label=body.account_label,
            credential_dict=body.credential,
            metadata=body.metadata,
            is_default=body.is_default,
            client_id=body.client_id,
        )
    except CredentialStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return _out(account)


@router.patch("/accounts/{account_id}", response_model=IntegrationAccountOut)
def update_account(
    account_id: UUID,
    body: IntegrationAccountUpdate,
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
) -> IntegrationAccountOut:
    from app.services.integration_account_service import _UNSET

    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    # Confirm ownership first.
    _require_account(svc, account_id, org_id)
    # client_id uses a sentinel: if the field was not supplied in the request
    # body Pydantic leaves it as None (the default); we still need to
    # distinguish "explicitly set to null" from "not provided". Because
    # IntegrationAccountUpdate.client_id defaults to None, we can't tell the
    # difference from the model alone. The conservative choice: treat None as
    # "not provided" (no change) since clearing the FK via PATCH is an
    # explicit opt-in the FE signals via `client_id: null` in the body. Pydantic
    # always includes the field; check if it was actually in the raw body via
    # model_fields_set.
    client_id_arg = _UNSET
    if "client_id" in body.model_fields_set:
        client_id_arg = body.client_id
    try:
        account = svc.update_account(
            account_id=account_id,
            org_id=org_id,
            account_label=body.account_label,
            metadata=body.metadata,
            is_default=body.is_default,
            client_id=client_id_arg,
            status=body.status,
        )
    except IntegrationAccountNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="integration account not found",
        )
    return _out(account)


@router.patch(
    "/accounts/{account_id}/set-default",
    response_model=IntegrationAccountOut,
)
def set_default(
    account_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
) -> IntegrationAccountOut:
    """Atomically set this account as the default for its provider.

    Clears any other existing default for the same (org, provider) pair."""
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    _require_account(svc, account_id, org_id)
    try:
        account = svc.set_default(account_id=account_id, org_id=org_id)
    except IntegrationAccountNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="integration account not found",
        )
    return _out(account)


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
) -> Response:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    deleted = svc.delete_account(account_id=account_id, org_id=org_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="integration account not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Channel sync ─────────────────────────────────────────────────────────────

@router.post("/accounts/{account_id}/sync", response_model=IntegrationAccountOut)
def sync_account(
    account_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
    cfg: SocialWiringSettings = Depends(get_settings),
) -> IntegrationAccountOut:
    """Validate a YouTube account by fetching live channel info from the API.

    Sets status='validating', calls channels.list bound to this account,
    then writes channel_info + status='validated' + last_synced_at on success,
    or status='error' + channel_info={'error': ...} on failure.
    """
    from app.services.account_credentials import sync_channel_info

    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    account = _require_account(svc, account_id, org_id)
    try:
        updated = sync_channel_info(get_admin_client(), cfg, svc, account)
    except Exception as exc:
        logger.exception("sync_account: unexpected error for account %s", account_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"channel sync failed: {exc}",
        ) from exc
    return _out(updated)


# ─── YouTube OAuth ────────────────────────────────────────────────────────────
# Reuses the SAME credentials (youtube_client_id / youtube_client_secret /
# youtube_redirect_uri) that the single-account YouTube Settings tab uses —
# no new config required. The result row goes into integration_accounts
# (multi-account) instead of the credentials table (single-account).
# This is an ADDITIVE path; the existing /api/settings/youtube/... routes
# continue to work unchanged.

_YT_PKCE_KEY_PREFIX = "ia:youtube:oauth:pkce:"
_YT_PKCE_TTL_SECONDS = 600  # 10 min


def _yt_pkce_redis_client():
    """Lazy Redis client for PKCE verifier. Returns None if unavailable
    (same fallback-tolerant approach as the YouTube settings OAuth)."""
    try:
        import redis
        client = redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception as exc:
        logger.warning("integration_accounts: PKCE Redis unavailable: %s", exc)
        return None


# ─── DI seams ─────────────────────────────────────────────────────────────────
# Mirror whatsapp_connections_router's get_connection_store /
# get_waha_client_factory: injectable seams so tests supply the seed Fakes via
# app.dependency_overrides instead of monkeypatching our own symbols
# (KB § PATTERNS/compliance/testing.md — "no monkey-patching, incl. tests";
# a MagicMock'd provider hid that this flow called a non-existent provider API).
def get_yt_oauth_provider(
    cfg: SocialWiringSettings = Depends(get_settings),
):
    """The YouTube OAuth provider for the multi-account flow.

    Returns ``None`` when YT OAuth isn't configured — the endpoints raise 503
    AFTER their own request validations, so error ordering is preserved. Tests
    override this with the seed ``FakeOAuthProvider`` so the flow exercises the
    REAL async ``OAuthProvider`` contract (``authorization_url`` /
    ``exchange_code`` → ``TokenSet``) rather than a MagicMock that masks drift.
    """
    if not cfg.youtube_client_id or not cfg.youtube_client_secret:
        return None
    return GoogleProvider(
        client_id=cfg.youtube_client_id,
        client_secret=cfg.youtube_client_secret,
        use_pkce=True,
    )


def get_yt_pkce_redis():
    """DI seam: the PKCE-verifier Redis client (``None`` when unavailable)."""
    return _yt_pkce_redis_client()


def get_yt_client_factory():
    """DI seam: the YouTube client factory. Tests override to return a
    ``make_youtube_client(use_fake=True, ...)`` flavour."""
    return make_youtube_client


@router.post(
    "/accounts/youtube/oauth/start",
    response_model=YouTubeOAuthStartOut,
)
def youtube_oauth_start(
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
    provider=Depends(get_yt_oauth_provider),
    redis_client=Depends(get_yt_pkce_redis),
) -> YouTubeOAuthStartOut:
    """Build a YouTube OAuth consent URL for the multi-account flow.

    State token: ``{org_id}:{nonce}`` — org-scoped CSRF token that the
    callback uses to resolve the tenant without trusting the redirect URI
    alone. PKCE verifier persisted in Redis (10-min TTL, single-use).
    """
    import asyncio

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET not configured. "
                "Set them in .env to enable OAuth."
            ),
        )

    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    # Derive the multi-account OAuth callback redirect URI (separate path from
    # /api/youtube/oauth/callback so both flows coexist).
    redirect_uri = _build_ia_youtube_redirect_uri(cfg)

    from app.modules.youtube.services.youtube import YOUTUBE_SCOPES

    state = f"{org_id}:{secrets.token_urlsafe(16)}"
    # Seed OAuthProvider methods are async; this endpoint is sync (AnyIO worker
    # thread), so bridge via asyncio.run — the same pattern the callback uses
    # for the YouTube client. `provider` (real GoogleProvider or an injected
    # Fake) comes from the get_yt_oauth_provider DI seam.
    auth_result = asyncio.run(
        provider.authorization_url(
            state=state, scopes=YOUTUBE_SCOPES, redirect_uri=redirect_uri
        )
    )

    if redis_client is not None and auth_result.code_verifier:
        try:
            redis_client.set(
                f"{_YT_PKCE_KEY_PREFIX}{state}",
                auth_result.code_verifier,
                ex=_YT_PKCE_TTL_SECONDS,
            )
        except Exception as exc:
            logger.warning("integration_accounts: failed to persist PKCE verifier: %s", exc)

    return YouTubeOAuthStartOut(auth_url=auth_result.url, state=state)


@router.get("/accounts/youtube/oauth/callback")
def youtube_oauth_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    cfg: SocialWiringSettings = Depends(get_settings),
    svc: IntegrationAccountService = Depends(get_account_service),
    provider=Depends(get_yt_oauth_provider),
    redis_client=Depends(get_yt_pkce_redis),
    yt_client_factory=Depends(get_yt_client_factory),
):
    """Google redirect target for the multi-account YouTube OAuth flow.

    Exchanges code → tokens, fetches channel info, creates an
    ``integration_accounts`` row, then redirects to
    ``/integrations?account_created=<id>``.

    Uses the admin client (no JWT in Google's redirect — mirrors the
    existing /api/youtube/oauth/callback pattern).
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

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET not configured.",
        )

    import asyncio

    redirect_uri = _build_ia_youtube_redirect_uri(cfg)

    from app.modules.youtube.services.youtube import YOUTUBE_SCOPES

    code_verifier: Optional[str] = None
    if redis_client is not None:
        try:
            key = f"{_YT_PKCE_KEY_PREFIX}{state}"
            code_verifier = redis_client.get(key)
            if code_verifier:
                redis_client.delete(key)  # single-use
        except Exception as exc:
            logger.warning(
                "integration_accounts: failed to retrieve PKCE verifier: %s", exc
            )

    try:
        # Seed OAuthProvider.exchange_code is async → canonical TokenSet;
        # bridge via asyncio.run (sync endpoint). `provider` is the
        # get_yt_oauth_provider seam (real GoogleProvider or injected Fake).
        tokens = asyncio.run(
            provider.exchange_code(
                code=code,
                state=state,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
        )
    except Exception as exc:
        logger.exception("integration_accounts: YouTube OAuth exchange failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth code exchange failed: {exc}",
        ) from exc

    # Canonical TokenSet → the credential bundle persisted on the account row
    # (the downstream metadata/creds code consumes a dict). `raw` carries any
    # provider-specific extras (e.g. an `email` claim) when present.
    bundle = {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "scopes": tokens.scope or YOUTUBE_SCOPES,
        "expires_at": tokens.expires_at.isoformat() if tokens.expires_at else None,
        **(tokens.raw or {}),
    }

    # Fetch channel info to populate account_label + metadata. Build a transient
    # Credentials object from the fresh bundle and call the seed YoutubeClient
    # (via the get_yt_client_factory seam) — no CredentialStore write here.
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None
    try:
        from google.oauth2.credentials import Credentials as GCredentials

        creds = GCredentials(
            token=bundle.get("access_token"),
            refresh_token=bundle.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=cfg.youtube_client_id,
            client_secret=cfg.youtube_client_secret,
            scopes=bundle.get("scopes", YOUTUBE_SCOPES),
        )
        yt_client = yt_client_factory(oauth_credentials=creds)
        # asyncio.run gives a fresh loop so this works in both test + prod.
        info = asyncio.run(yt_client.get_channel_info_mine())
        channel_id = info.channel_id
        channel_title = info.title
    except Exception as exc:  # noqa: BLE001 — best-effort; account still created
        logger.warning(
            "integration_accounts: channels.list failed during OAuth callback "
            "for org_id=%s — using fallback label: %s",
            org_id,
            exc,
        )

    account_label = channel_title or f"YouTube account ({org_id})"
    metadata = {
        "channel_id": channel_id,
        "channel_title": channel_title,
        "scopes": bundle.get("scopes", YOUTUBE_SCOPES),
        "expires_at": bundle.get("expires_at"),
        "oauth_account_email": bundle.get("email"),
    }
    # Strip None values so the metadata column is clean.
    metadata = {k: v for k, v in metadata.items() if v is not None}

    # Channel object: persist what we fetched (thumbnail not available from
    # OAuth channel info; sync endpoint provides the full projection).
    from datetime import datetime as _dt, timezone as _tz
    _now_iso = _dt.now(_tz.utc).isoformat()
    _channel_info: dict = {}
    if channel_id:
        _channel_info = {
            "channel_id": channel_id,
            "title": channel_title or "",
        }

    # Idempotent on channel_id. Re-connecting a channel that's already an
    # account for this org RE-AUTHENTICATES it (persists the fresh token bundle)
    # instead of inserting a duplicate row — this is what makes the legacy
    # auto-adopted "Padrão" account fully UI-manageable (the connect button
    # doubles as re-auth) and eliminates the UNIQUE(org, provider,
    # account_label) CONFLICT the channel-title collision was raising. A
    # genuinely NEW channel creates a new account → true multi-account.
    youtube_accounts = svc.list_accounts(org_id, provider="youtube")
    existing = (
        next(
            (a for a in youtube_accounts if (a.metadata or {}).get("channel_id") == channel_id),
            None,
        )
        if channel_id
        else None
    )
    if existing is not None:
        account = svc.update_credential(
            account_id=existing.id,
            org_id=org_id,
            credential_dict=bundle,
            metadata=metadata,
        )
        # Also refresh channel_info + status on re-auth.
        account = svc.update_channel_info(
            account_id=existing.id,
            org_id=org_id,
            channel_info=_channel_info,
            status="validated",
            last_synced_at=_dt.now(_tz.utc),
        )
    else:
        # Disambiguate only if a DIFFERENT channel already holds this label
        # (two channels can share a title) — keeps the UNIQUE constraint happy
        # without masking a real re-connect (handled by the channel_id branch).
        existing_labels = {a.account_label for a in youtube_accounts}
        unique_label = account_label
        if unique_label in existing_labels and channel_id:
            unique_label = f"{account_label} · {channel_id[-6:]}"
        account = svc.create_account(
            org_id=org_id,
            provider="youtube",
            account_label=unique_label,
            credential_dict=bundle,
            metadata=metadata,
            is_default=not youtube_accounts,  # first-ever account becomes default
            status="validated",
        )
        # Write channel_info for the new account too (same as re-auth path).
        if _channel_info:
            account = svc.update_channel_info(
                account_id=account.id,
                org_id=org_id,
                channel_info=_channel_info,
                status="validated",
                last_synced_at=_dt.now(_tz.utc),
            )

    redirect_url = f"/integrations?account_created={account.id}"
    if cfg.frontend_base_url:
        redirect_url = urljoin(
            cfg.frontend_base_url.rstrip("/") + "/",
            f"integrations?account_created={account.id}",
        )
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


def _build_ia_youtube_redirect_uri(cfg: SocialWiringSettings) -> str:
    """Derive the redirect URI for the integration-accounts YouTube OAuth flow.

    Derives from ``oauth_redirect_base_url`` (or ``tunnel_hostname``) when
    set; falls back to the product's configured ``youtube_redirect_uri`` +
    ``/accounts`` suffix to distinguish the two flows at Google's end.

    IMPORTANT: register this URI in the Google Cloud Console OAuth client.
    """
    oauth_base = cfg.oauth_redirect_base_url or cfg.tunnel_hostname
    if oauth_base:
        base = oauth_base.rstrip("/")
        return f"{base}/api/integrations/accounts/youtube/oauth/callback"
    # Derive from the existing youtube_redirect_uri base to avoid introducing
    # a new env var for the common case.
    base_uri = cfg.youtube_redirect_uri
    if base_uri.endswith("/api/youtube/oauth/callback"):
        return base_uri.replace(
            "/api/youtube/oauth/callback",
            "/api/integrations/accounts/youtube/oauth/callback",
        )
    return "http://localhost:8011/api/integrations/accounts/youtube/oauth/callback"


__all__ = ["router"]
