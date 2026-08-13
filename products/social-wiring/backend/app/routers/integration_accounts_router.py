"""Multi-account integration credentials router — /api/integrations/*.

Endpoints:
    GET    /api/integrations/providers         → list of provider configs
    GET    /api/integrations/accounts          → list of IntegrationAccount (optional ?provider=)
    GET    /api/integrations/accounts/{id}     → fetch one account
    POST   /api/integrations/accounts          → create (manual entry)
    PATCH  /api/integrations/accounts/{id}     → update label/metadata/is_default
    PATCH  /api/integrations/accounts/{id}/set-default → set as default for its provider
        🔴 Kept but currently UNREACHED from any product FE (2026-08-13): the
        "conta padrão" UI concept was removed from every account
        selector/card (no provider has ever had >1 account per marca, so it
        only produced a placeholder users had to swap away from). The
        `is_default` column + this endpoint stay — do not delete without a
        separate decision; see `useSetDefaultAccount` in
        `products/social-wiring/frontend/src/hooks/useIntegrationAccounts.ts`.
    DELETE /api/integrations/accounts/{id}     → delete

    POST   /api/integrations/accounts/youtube/oauth/start       → {auth_url, state}
    GET    /api/integrations/accounts/youtube/oauth/callback    → exchange code, create account
    POST   /api/integrations/accounts/gmail/oauth/start         → {auth_url, state}
    GET    /api/integrations/accounts/gmail/oauth/callback      → exchange code, create account
    POST   /api/integrations/accounts/google_drive/oauth/start  → {auth_url, state}
    GET    /api/integrations/accounts/google_drive/oauth/callback → exchange code, create account
    POST   /api/integrations/accounts/meta/oauth/start           → {auth_url, state}
    GET    /api/integrations/accounts/meta/oauth/callback        → exchange code, create account
    POST   /api/integrations/accounts/instagram/oauth/start      → {auth_url, state}
    GET    /api/integrations/accounts/instagram/oauth/callback   → exchange code, create account
    POST   /api/integrations/accounts/instagram/token            → manual-token fallback, create account

Auth: ``Depends(get_current_user_org)`` throughout. The admin client is
used for all DB writes (mirrors whatsapp_connections_router). The OAuth
callback uses the admin client too (no JWT from Google's redirect).

ENCRYPTION_KEY missing → 503 config-gap (mirrors credential_vault pattern).

OAuth redirect target: all three callbacks redirect to ``/clientes?account_created=<id>``.
``/integrations`` is a FE compat alias that stays valid.
"""
from __future__ import annotations

import logging
import secrets
from typing import Any, Optional
from urllib.parse import urljoin
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from noctusai_lib.integrations.gmail import GMAIL_READONLY_SCOPE, GMAIL_SEND_SCOPE
from noctusai_lib.integrations.meta._meta_api import (
    build_ig_authorize_url,
    exchange_code_for_token,
    exchange_for_long_lived_bundle,
    exchange_ig_code_for_token,
    exchange_ig_for_long_lived,
)
from noctusai_lib.integrations.meta.instagram_login_adapter import (
    InstagramLoginOAuthAdapter,
)
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
from app.services.app_config_store import resolve_instagram_app_creds, resolve_meta_app_creds
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
from app.services.marcas_service import build_marca_service
from app.services.integration_providers import PROVIDERS
from app.services.legacy_adoption import adopt_legacy_account
from app.services.meta import META_PROVIDER, MetaGraphError, MetaOAuthAdapter

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
    marca_id: Optional[UUID] = None
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
    marca_id: Optional[UUID] = None

    class Config:
        extra = "forbid"


class IntegrationAccountUpdate(BaseModel):
    """Patch body — all fields optional."""

    account_label: Optional[str] = None
    metadata: Optional[dict] = None
    is_default: Optional[bool] = None
    marca_id: Optional[UUID] = None
    status: Optional[str] = None

    class Config:
        extra = "forbid"


class OAuthStartOut(BaseModel):
    """Common OAuth start response — authorization URL + CSRF state.

    Shared by YouTube, Gmail, and Google Drive flows (DRY at N=3).
    """

    auth_url: str
    state: str


class OAuthStartIn(BaseModel):
    """Common optional body for OAuth start endpoints.

    ``marca_id`` (migration 017): when supplied the new ``integration_accounts``
    row is linked to the given cliente (must belong to the calling org).
    Absent / null = no link (backward-compatible with callers that send no body).
    """

    marca_id: Optional[UUID] = None


# Backward-compat aliases so existing references (response_model, tests) keep working.
YouTubeOAuthStartOut = OAuthStartOut
YouTubeOAuthStartIn = OAuthStartIn


class InstagramTokenIn(BaseModel):
    """Manual-token fallback body for the Instagram Business Login flow —
    an operator who already has a valid IG User access token (e.g.
    pasted from the Graph API Explorer) can register it directly instead
    of walking the browser OAuth dialog. Validated by probing ``/me``
    before the account is created (never trust an unverified token)."""

    access_token: str
    marca_id: Optional[UUID] = None

    class Config:
        extra = "forbid"


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


def get_sync_yt_service_builder():
    """DI seam for the YouTube service builder used by the sync endpoint.

    Returns the real ``build_youtube_service_for_org`` by default. Tests
    override via ``app.dependency_overrides[get_sync_yt_service_builder]``
    to inject a fake without patching our own module symbols.
    Per KB § PATTERNS/backend/di-test-seam.md (Class-B, service DI).
    """
    from app.services.account_credentials import build_youtube_service_for_org
    return build_youtube_service_for_org


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
        marca_id=account.marca_id,
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
    marca_id: Optional[UUID] = Query(default=None),
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
) -> list[IntegrationAccountOut]:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    accounts = svc.list_accounts(org_id=org_id, provider=provider, marca_id=marca_id)
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
            marca_id=body.marca_id,
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
    # marca_id uses a sentinel: if the field was not supplied in the request
    # body Pydantic leaves it as None (the default); we still need to
    # distinguish "explicitly set to null" from "not provided". Because
    # IntegrationAccountUpdate.marca_id defaults to None, we can't tell the
    # difference from the model alone. The conservative choice: treat None as
    # "not provided" (no change) since clearing the FK via PATCH is an
    # explicit opt-in the FE signals via `marca_id: null` in the body. Pydantic
    # always includes the field; check if it was actually in the raw body via
    # model_fields_set.
    marca_id_arg = _UNSET
    if "marca_id" in body.model_fields_set:
        marca_id_arg = body.marca_id
    try:
        account = svc.update_account(
            account_id=account_id,
            org_id=org_id,
            account_label=body.account_label,
            metadata=body.metadata,
            is_default=body.is_default,
            marca_id=marca_id_arg,
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
    yt_builder=Depends(get_sync_yt_service_builder),
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
        updated = sync_channel_info(
            get_admin_client(), cfg, svc, account,
            yt_service_builder=yt_builder,
        )
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
_GMAIL_PKCE_KEY_PREFIX = "ia:gmail:oauth:pkce:"
_DRIVE_PKCE_KEY_PREFIX = "ia:google_drive:oauth:pkce:"
_YT_PKCE_TTL_SECONDS = 600  # 10 min — shared across all IA Google OAuth flows

# Gmail and Drive OAuth scopes (seed constants where available; inline where not).
_GMAIL_OAUTH_SCOPES = [GMAIL_SEND_SCOPE, GMAIL_READONLY_SCOPE]
_DRIVE_OAUTH_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


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


# ─── Gmail OAuth DI seams ─────────────────────────────────────────────────────
def get_gmail_oauth_provider(
    cfg: SocialWiringSettings = Depends(get_settings),
):
    """GoogleProvider for the Gmail multi-account IA flow.

    Uses ``GOOGLE_OAUTH_CLIENT_ID`` / ``GOOGLE_OAUTH_CLIENT_SECRET`` (shared
    with Calendar — the same GCP OAuth client covers multiple Google APIs).
    Returns ``None`` when not configured so the endpoint raises 503 after
    input validation.
    """
    if not cfg.google_oauth_client_id or not cfg.google_oauth_client_secret:
        return None
    return GoogleProvider(
        client_id=cfg.google_oauth_client_id,
        client_secret=cfg.google_oauth_client_secret,
        use_pkce=True,
    )


def get_gmail_pkce_redis():
    """DI seam: PKCE-verifier Redis client for the Gmail IA flow."""
    return _yt_pkce_redis_client()


# ─── Drive OAuth DI seams ─────────────────────────────────────────────────────
def get_drive_oauth_provider(
    cfg: SocialWiringSettings = Depends(get_settings),
):
    """GoogleProvider for the Google Drive multi-account IA flow.

    Same GCP OAuth client as Gmail / Calendar
    (``GOOGLE_OAUTH_CLIENT_ID`` / ``GOOGLE_OAUTH_CLIENT_SECRET``).
    Returns ``None`` when not configured.
    """
    if not cfg.google_oauth_client_id or not cfg.google_oauth_client_secret:
        return None
    return GoogleProvider(
        client_id=cfg.google_oauth_client_id,
        client_secret=cfg.google_oauth_client_secret,
        use_pkce=True,
    )


def get_drive_pkce_redis():
    """DI seam: PKCE-verifier Redis client for the Drive IA flow."""
    return _yt_pkce_redis_client()


@router.post(
    "/accounts/youtube/oauth/start",
    response_model=YouTubeOAuthStartOut,
)
def youtube_oauth_start(
    body: YouTubeOAuthStartIn = YouTubeOAuthStartIn(),
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
    provider=Depends(get_yt_oauth_provider),
    redis_client=Depends(get_yt_pkce_redis),
) -> YouTubeOAuthStartOut:
    """Build a YouTube OAuth consent URL for the multi-account flow.

    State token: ``{org_id}:{nonce}:{marca_id_or_empty}`` — org-scoped CSRF
    token (extended by migration 017 to carry an optional cliente id through the
    redirect round-trip).  Backward-compatible: callers that send no body get
    the old two-part ``{org_id}:{nonce}`` behavior (empty third segment = no
    link).  PKCE verifier persisted in Redis (10-min TTL, single-use).
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

    # Migration 017 — validate marca_id belongs to the org before encoding.
    marca_id_str = ""
    if body.marca_id is not None:
        marca_svc = build_marca_service(get_admin_client())
        found = marca_svc.get_marca(body.marca_id, org_id)
        if found is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="marca_id not found or does not belong to this org.",
            )
        marca_id_str = str(body.marca_id)

    # Derive the multi-account OAuth callback redirect URI (separate path from
    # /api/youtube/oauth/callback so both flows coexist).
    redirect_uri = _build_ia_youtube_redirect_uri(cfg)

    from app.modules.youtube.services.youtube import YOUTUBE_SCOPES

    # State format: {org_id}:{nonce}:{client_id_or_empty}
    # Neither org_id (UUID) nor token_urlsafe() output ever contain ":" so the
    # three-part split in the callback is unambiguous.
    state = f"{org_id}:{secrets.token_urlsafe(16)}:{marca_id_str}"
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

    # State format: {org_id}:{nonce}:{client_id_or_empty} (migration 017 extended)
    # Older two-part states "{org_id}:{nonce}" have no third segment → client_id_part = "".
    # Split on the FIRST ":" then the LAST ":" to handle both two-part and three-part forms.
    parts = state.split(":")
    if len(parts) < 2 or not parts[0]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token malformed.",
        )
    org_part = parts[0]
    # Third segment (index 2) is marca_id when present; empty string = no link.
    marca_id_part = parts[2] if len(parts) >= 3 else ""
    try:
        org_id = UUID(org_part)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token does not encode a valid org_id.",
        ) from exc

    # Parse marca_id from state (may be empty when caller sent no marca_id).
    _callback_marca_id: Optional[UUID] = None
    if marca_id_part:
        try:
            _callback_marca_id = UUID(marca_id_part)
        except ValueError:
            logger.warning(
                "integration_accounts: OAuth state carries non-UUID marca_id_part=%r — ignoring",
                marca_id_part,
            )

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
            # Migration 017 — link to cliente when carried through OAuth state.
            marca_id=_callback_marca_id,
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

    redirect_url = f"/clientes?account_created={account.id}"
    if cfg.frontend_base_url:
        redirect_url = urljoin(
            cfg.frontend_base_url.rstrip("/") + "/",
            f"clientes?account_created={account.id}",
        )
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


def _build_ia_google_redirect_uri(cfg: SocialWiringSettings, provider: str) -> str:
    """Build the OAuth callback redirect URI for an IA Google provider.

    Provider is the IA provider id (``'youtube'``, ``'gmail'``,
    ``'google_drive'``).  Derives from ``oauth_redirect_base_url`` (or
    ``tunnel_hostname``) when set so a single Cloudflare tunnel env var
    routes all three flows correctly.

    IMPORTANT: every derived URI must be registered in the GCP OAuth client
    (Authorized redirect URIs).
    """
    oauth_base = cfg.oauth_redirect_base_url or cfg.tunnel_hostname
    if oauth_base:
        base = oauth_base.rstrip("/")
        return f"{base}/api/integrations/accounts/{provider}/oauth/callback"
    # Derive from the existing youtube_redirect_uri base to reuse the same
    # env var for the common dev/tunnel case (avoids 3 separate env vars).
    base_uri = cfg.youtube_redirect_uri
    if base_uri.endswith("/api/youtube/oauth/callback"):
        return base_uri.replace(
            "/api/youtube/oauth/callback",
            f"/api/integrations/accounts/{provider}/oauth/callback",
        )
    return f"http://localhost:8011/api/integrations/accounts/{provider}/oauth/callback"


def _build_ia_youtube_redirect_uri(cfg: SocialWiringSettings) -> str:
    """Backward-compat wrapper → delegates to the shared helper."""
    return _build_ia_google_redirect_uri(cfg, "youtube")


# ─── Meta OAuth endpoints ─────────────────────────────────────────────────────
# Per-client Meta connection (Wave 2, `wave2-contract.md` Slice 2A) — clones the
# YouTube multi-account pair above. Not a Google flow (Facebook's OAuth dialog,
# no PKCE) so it does NOT go through `_build_ia_google_redirect_uri` /
# `get_yt_oauth_provider` — it builds its own consent URL + does its own code
# exchange via the seed's `noctusai_lib.integrations.meta` helpers, the SAME
# exchange logic the retired org-level Meta OAuth surface used, just
# persisting into store B — `integration_accounts`, per-client — instead of
# store A — `credential_vault`, per-org-only.

# Pinned scope set (Wave 2 contract) — the full IG+Page surface the product's
# Meta features consume (comments/DMs/insights + posting). Distinct from the
# retired org-level surface's auto-discovered/kitchen-sink scope resolution:
# this per-client flow always requests this exact set so every client
# connection has a consistent, predictable permission surface.
META_IA_OAUTH_SCOPES: tuple[str, ...] = (
    "instagram_basic",
    "instagram_content_publish",
    "instagram_manage_comments",
    "instagram_manage_messages",
    "instagram_manage_insights",
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "pages_manage_engagement",
    # Required by Meta's Instagram Conversations API alongside
    # instagram_basic + instagram_manage_messages — without it, reading IG
    # Direct returns Graph error (#3) "Application does not have the
    # capability to make this API call" even though instagram_manage_messages
    # was granted. Documented at
    # developers.facebook.com/docs/messenger-platform/conversations.
    "pages_manage_metadata",
    # NOTE — do NOT add `pages_messaging` here. It is a real permission but
    # it is NOT enabled in this app's use-case config, so Meta's OAuth flow
    # rejects it as an "Invalid Scope" (blocking the admin's own reconnect).
    # More importantly, reading INSTAGRAM Direct does NOT require it: the
    # `(#200) Requires permission: pages_messaging` we saw came from the
    # MESSENGER branch of the conversations edge (`/{page-id}/conversations`
    # with NO `platform` param). The Instagram branch
    # (`?platform=instagram`) needs only instagram_basic +
    # instagram_manage_messages + pages_manage_metadata (all present). The
    # real remaining blockers are Meta-account-level, not scopes: the IG
    # "Allow Access to Messages" toggle, Business Verification (required for
    # the IG conversations branch), and Advanced Access via App Review for
    # reading accounts the app does not own.
    # KB § — Meta IG-DM Facebook-Login model (memory reference).
)


# ─── Meta OAuth DI seams ──────────────────────────────────────────────────────
# Meta has no single provider OBJECT to inject (unlike GoogleProvider for
# YouTube/Gmail/Drive) — its collaborators are the seed's free-function
# exchange helpers + the MetaOAuthAdapter class. Mirror the same DI-seam shape
# anyway (get_yt_client_factory returns a callable; these do too) so tests
# override via app.dependency_overrides instead of monkeypatching this
# module's own imported symbols (KB § PATTERNS/compliance/testing.md — "no
# monkey-patching, incl. tests"; patching our own collaborators here was a
# false-green: the real exchange/adapter path never ran).
def get_meta_code_exchange():
    """DI seam: the Meta code→token exchange callable
    (``exchange_code_for_token``). Tests override to inject a fake exchange
    function instead of patching this module's import."""
    return exchange_code_for_token


def get_meta_long_lived_exchange():
    """DI seam: the Meta short→long-lived token exchange callable
    (``exchange_for_long_lived_bundle``)."""
    return exchange_for_long_lived_bundle


def get_meta_oauth_adapter_factory():
    """DI seam: the ``MetaOAuthAdapter`` constructor used to probe /me +
    Pages + IG accounts during the callback. Tests override to return a
    fake adapter factory."""
    return MetaOAuthAdapter


def _build_ia_meta_redirect_uri(cfg: SocialWiringSettings) -> str:
    """Redirect URI for the per-client Meta IA OAuth flow.

    Mirrors ``_build_ia_google_redirect_uri``'s derivation shape (own
    function, not a shared call, since Meta isn't a Google provider and
    has no ``get_yt_oauth_provider``-style DI seam): derives from
    ``oauth_redirect_base_url`` / ``tunnel_hostname`` when set (one env
    var routes every IA OAuth flow, Meta included); falls back to
    deriving from the org-level ``meta_oauth_redirect_uri`` when neither
    is set; a localhost default for pure dev.

    IMPORTANT: every derived URI must be registered as a valid OAuth
    Redirect URI in the Meta App dashboard (App Review → Facebook Login
    → Settings → Valid OAuth Redirect URIs).
    """
    oauth_base = cfg.oauth_redirect_base_url or cfg.tunnel_hostname
    if oauth_base:
        base = oauth_base.rstrip("/")
        return f"{base}/api/integrations/accounts/meta/oauth/callback"
    base_uri = cfg.meta_oauth_redirect_uri
    if base_uri.endswith("/api/meta/oauth/callback"):
        return base_uri.replace(
            "/api/meta/oauth/callback",
            "/api/integrations/accounts/meta/oauth/callback",
        )
    return "http://localhost:8011/api/integrations/accounts/meta/oauth/callback"


@router.post(
    "/accounts/meta/oauth/start",
    response_model=OAuthStartOut,
)
def meta_oauth_start(
    body: OAuthStartIn = OAuthStartIn(),
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
) -> OAuthStartOut:
    """Build a Facebook consent URL for the multi-account per-client Meta
    connection flow.

    Mirrors ``youtube_oauth_start``: 3-part state
    ``{org_id}:{nonce}:{marca_id_or_empty}``; ``marca_id`` is validated
    against the calling org BEFORE it's encoded into the redirect
    round-trip (never trust an unvalidated FK). App ID/secret resolve
    DB-first (Settings-writable) with env fallback via
    ``resolve_meta_app_creds`` — a 503 config-gap when neither is set,
    same shape the retired org-level Meta OAuth-start endpoint used.
    """
    app_id, app_secret = resolve_meta_app_creds(settings=cfg)
    if not app_id or not app_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "META_APP_ID / META_APP_SECRET not configured. Set them in "
                ".env or Settings → Meta App to enable OAuth."
            ),
        )

    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    # Migration 017-style client-link validation (mirrors youtube_oauth_start).
    marca_id_str = ""
    if body.marca_id is not None:
        marca_svc = build_marca_service(get_admin_client())
        found = marca_svc.get_marca(body.marca_id, org_id)
        if found is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="marca_id not found or does not belong to this org.",
            )
        marca_id_str = str(body.marca_id)

    redirect_uri = _build_ia_meta_redirect_uri(cfg)
    # Neither org_id (UUID) nor token_urlsafe() output ever contain ":" so the
    # three-part split in the callback is unambiguous (mirrors YouTube's state).
    state = f"{org_id}:{secrets.token_urlsafe(16)}:{marca_id_str}"

    from urllib.parse import urlencode

    auth_params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "scope": ",".join(META_IA_OAUTH_SCOPES),
        "response_type": "code",
        "state": state,
        # Re-ask for previously denied permissions on every flow — same
        # rationale as the retired org-level Meta OAuth flow.
        "auth_type": "rerequest",
    }
    auth_url = (
        f"https://www.facebook.com/{cfg.meta_graph_api_version}"
        f"/dialog/oauth?{urlencode(auth_params)}"
    )
    return OAuthStartOut(auth_url=auth_url, state=state)


@router.get("/accounts/meta/oauth/callback")
def meta_oauth_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    error_description: Optional[str] = Query(default=None),
    cfg: SocialWiringSettings = Depends(get_settings),
    svc: IntegrationAccountService = Depends(get_account_service),
    code_exchange=Depends(get_meta_code_exchange),
    long_lived_exchange=Depends(get_meta_long_lived_exchange),
    adapter_factory=Depends(get_meta_oauth_adapter_factory),
):
    """Facebook's redirect target for the multi-account per-client Meta flow.

    Exchanges code → short-lived → long-lived user token (seed helpers,
    identical to the retired org-level Meta OAuth callback), probes
    ``/me`` + Pages + IG accounts for a channel label (best-effort
    — a probe failure never blocks account creation), creates (or
    re-authenticates, keyed on ``channel_id``) a store-B
    ``integration_accounts`` row, then redirects to
    ``/clientes?account_created=<id>``.

    Uses the admin client throughout (no JWT in Facebook's redirect —
    mirrors ``youtube_oauth_callback``). ``code_exchange`` /
    ``long_lived_exchange`` / ``adapter_factory`` are DI seams (mirroring
    ``get_yt_client_factory``) — tests override them via
    ``app.dependency_overrides`` instead of monkeypatching this module's
    own imported symbols.
    """
    if error:
        detail = f"OAuth flow returned an error: {error}"
        if error_description:
            detail = f"{detail} — {error_description}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth callback missing code or state.",
        )

    # State format: {org_id}:{nonce}:{client_id_or_empty} (mirrors YouTube's).
    parts = state.split(":")
    if len(parts) < 2 or not parts[0]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token malformed.",
        )
    try:
        org_id = UUID(parts[0])
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token does not encode a valid org_id.",
        ) from exc

    marca_id_part = parts[2] if len(parts) >= 3 else ""
    _callback_marca_id: Optional[UUID] = None
    if marca_id_part:
        try:
            _callback_marca_id = UUID(marca_id_part)
        except ValueError:
            logger.warning(
                "integration_accounts: Meta OAuth state carries non-UUID "
                "marca_id_part=%r — ignoring",
                marca_id_part,
            )

    app_id, app_secret = resolve_meta_app_creds(settings=cfg)
    if not app_id or not app_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="META_APP_ID / META_APP_SECRET not configured.",
        )

    redirect_uri = _build_ia_meta_redirect_uri(cfg)

    # 1) code → short-lived user token (seed exchange — same helper the
    # org-level flow uses; raises MetaGraphError on a Graph error envelope,
    # never a silent falsey result).
    try:
        short_token = code_exchange(
            code=code,
            app_id=app_id,
            app_secret=app_secret,
            redirect_uri=redirect_uri,
            version=cfg.meta_graph_api_version,
        )
    except MetaGraphError as exc:
        logger.exception("integration_accounts: Meta OAuth code exchange failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth code exchange failed: {exc}",
        ) from exc
    if not short_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meta did not return an access_token from the code exchange.",
        )

    # 2) short → long-lived user token.
    try:
        long_bundle = long_lived_exchange(
            short_token=short_token,
            app_id=app_id,
            app_secret=app_secret,
            version=cfg.meta_graph_api_version,
        )
    except MetaGraphError as exc:
        logger.exception("integration_accounts: Meta long-lived exchange failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Long-lived token exchange failed: {exc}",
        ) from exc

    long_token = long_bundle.access_token or short_token
    token_type = long_bundle.token_type or "bearer"
    expires_in = long_bundle.expires_in

    # 3) probe /me + Pages + IG accounts for a channel label — via a
    # transient MetaOAuthAdapter over the fresh token (never persisted
    # mid-probe). Reuses the seed adapter's typed Graph calls instead of
    # hand-rolling a second copy of the /me + /me/accounts request shape
    # (the retired org-level Meta OAuth callback already owned that
    # copy for the org-scoped flow — this is N=2 via the seed's own
    # abstraction, not a 3rd fork). `system_user_token=` here just means
    # "the bearer token this adapter authenticates every call with" — the
    # token itself is the per-client long-lived USER token, not an actual
    # Meta System User Token; the adapter draws no distinction for reads.
    probe_adapter = adapter_factory(
        system_user_token=long_token, graph_version=cfg.meta_graph_api_version
    )
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None
    try:
        me = probe_adapter.me()
        user_id = me.get("id")
        user_name = me.get("name")
    except MetaGraphError as exc:  # noqa: BLE001 — best-effort; account still created
        logger.warning(
            "integration_accounts: Meta /me probe failed during OAuth callback "
            "for org_id=%s — using fallback label: %s",
            org_id,
            exc,
        )
    try:
        pages = probe_adapter.list_facebook_pages()
        ig_accounts = probe_adapter.list_instagram_accounts()
        # IG account is the primary label when present (the product's Meta
        # features are IG-first — comments/DMs/insights); a connected Page
        # with no linked IG still gets a usable label.
        if ig_accounts:
            channel_id = ig_accounts[0].id
            channel_title = ig_accounts[0].username
        elif pages:
            channel_id = pages[0].id
            channel_title = pages[0].name
    except MetaGraphError as exc:  # noqa: BLE001 — best-effort; account still created
        logger.warning(
            "integration_accounts: Meta pages/IG probe failed during OAuth "
            "callback for org_id=%s — using fallback label: %s",
            org_id,
            exc,
        )

    bundle = {
        "access_token": long_token,
        "token_type": token_type,
        "expires_in": expires_in,
        "scope": ",".join(META_IA_OAUTH_SCOPES),
        "user_id": user_id,
        "user_name": user_name,
    }
    account_label = channel_title or user_name or f"Meta account ({org_id})"
    metadata = {
        "user_id": user_id,
        "user_name": user_name,
        "channel_id": channel_id,
        "channel_title": channel_title,
        "scopes": list(META_IA_OAUTH_SCOPES),
    }
    metadata = {k: v for k, v in metadata.items() if v is not None}

    from datetime import datetime as _dt
    from datetime import timezone as _tz

    _channel_info: dict = {}
    if channel_id:
        _channel_info = {"channel_id": channel_id, "title": channel_title or ""}

    # Idempotent on channel_id (mirrors youtube_oauth_callback) — reconnecting
    # the same Page/IG account re-authenticates the existing row (persists the
    # fresh token bundle) instead of inserting a duplicate.
    meta_accounts = svc.list_accounts(org_id, provider=META_PROVIDER)
    existing = (
        next(
            (a for a in meta_accounts if (a.metadata or {}).get("channel_id") == channel_id),
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
        account = svc.update_channel_info(
            account_id=existing.id,
            org_id=org_id,
            channel_info=_channel_info,
            status="validated",
            last_synced_at=_dt.now(_tz.utc),
        )
    else:
        existing_labels = {a.account_label for a in meta_accounts}
        unique_label = account_label
        if unique_label in existing_labels and channel_id:
            unique_label = f"{account_label} · {channel_id[-6:]}"
        account = svc.create_account(
            org_id=org_id,
            provider=META_PROVIDER,
            account_label=unique_label,
            credential_dict=bundle,
            metadata=metadata,
            is_default=not meta_accounts,
            status="validated",
            marca_id=_callback_marca_id,
        )
        if _channel_info:
            account = svc.update_channel_info(
                account_id=account.id,
                org_id=org_id,
                channel_info=_channel_info,
                status="validated",
                last_synced_at=_dt.now(_tz.utc),
            )

    redirect_url = f"/clientes?account_created={account.id}"
    if cfg.frontend_base_url:
        redirect_url = urljoin(
            cfg.frontend_base_url.rstrip("/") + "/",
            f"clientes?account_created={account.id}",
        )
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


# ─── Instagram Business Login (Instagram-Login model) OAuth endpoints ────────
# Distinct model from the Meta (Facebook-Login) flow above: authenticates
# against a SEPARATE Instagram App ID/Secret, no Facebook Page required, and
# the token chain runs through www.instagram.com (consent) →
# api.instagram.com (code exchange) → graph.instagram.com (long-lived
# exchange + subsequent reads) rather than graph.facebook.com throughout.
# See `noctusai_lib.integrations.meta.instagram_login_adapter` +
# `KB § INTEGRATIONS/meta.md` (Model contrast table) +
# roadmap ``ig-login-messaging-migration-2026-07``.

INSTAGRAM_PROVIDER = "instagram"

# Pinned scope set per Meta's documented Instagram Business Login contract —
# the minimum surface for reading + replying to IG Direct as this product's
# agency-model client connection.
IG_IA_OAUTH_SCOPES: tuple[str, ...] = (
    "instagram_business_basic",
    "instagram_business_manage_messages",
)


# ─── Instagram OAuth DI seams ─────────────────────────────────────────────────
# Mirrors the Meta DI-seam shape immediately above (get_meta_code_exchange /
# get_meta_long_lived_exchange / get_meta_oauth_adapter_factory) — tests
# override via app.dependency_overrides instead of monkeypatching this
# module's own imported symbols.
def get_ig_code_exchange():
    """DI seam: the IG code→short-lived-token exchange callable
    (``exchange_ig_code_for_token``)."""
    return exchange_ig_code_for_token


def get_ig_long_lived_exchange():
    """DI seam: the IG short→long-lived token exchange callable
    (``exchange_ig_for_long_lived``)."""
    return exchange_ig_for_long_lived


def get_instagram_oauth_adapter_factory():
    """DI seam: the ``InstagramLoginOAuthAdapter`` constructor used to
    probe ``/me`` for a username/id label during the callback (and to
    validate a manually-pasted token on the ``/token`` fallback). Tests
    override to return a fake adapter factory."""
    return InstagramLoginOAuthAdapter


def _build_ia_instagram_redirect_uri(cfg: SocialWiringSettings) -> str:
    """Redirect URI for the Instagram Business Login flow.

    Mirrors ``_build_ia_meta_redirect_uri``'s derivation shape: derives
    from ``oauth_redirect_base_url`` / ``tunnel_hostname`` when set (one
    env var routes every IA OAuth flow, Instagram included); falls back
    to ``cfg.instagram_oauth_redirect_uri`` otherwise.

    IMPORTANT: every derived URI must be registered as a valid OAuth
    redirect URI in the Instagram app's Business Login product settings.
    """
    oauth_base = cfg.oauth_redirect_base_url or cfg.tunnel_hostname
    if oauth_base:
        base = oauth_base.rstrip("/")
        return f"{base}/api/integrations/accounts/instagram/oauth/callback"
    return cfg.instagram_oauth_redirect_uri


@router.post(
    "/accounts/instagram/oauth/start",
    response_model=OAuthStartOut,
)
def instagram_oauth_start(
    body: OAuthStartIn = OAuthStartIn(),
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
) -> OAuthStartOut:
    """Build an Instagram Business Login consent URL.

    Mirrors ``meta_oauth_start``: 3-part state
    ``{org_id}:{nonce}:{marca_id_or_empty}``; ``marca_id`` is validated
    against the calling org BEFORE it's encoded into the redirect
    round-trip. App ID/secret resolve DB-first (Settings-writable) with
    env fallback via ``resolve_instagram_app_creds`` — a 503 config-gap
    when neither is set.
    """
    app_id, app_secret = resolve_instagram_app_creds(settings=cfg)
    if not app_id or not app_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "INSTAGRAM_APP_ID / INSTAGRAM_APP_SECRET not configured. Set "
                "them in .env or Settings → Instagram App to enable OAuth."
            ),
        )

    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    marca_id_str = ""
    if body.marca_id is not None:
        marca_svc = build_marca_service(get_admin_client())
        found = marca_svc.get_marca(body.marca_id, org_id)
        if found is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="marca_id not found or does not belong to this org.",
            )
        marca_id_str = str(body.marca_id)

    redirect_uri = _build_ia_instagram_redirect_uri(cfg)
    state = f"{org_id}:{secrets.token_urlsafe(16)}:{marca_id_str}"
    auth_url = build_ig_authorize_url(
        app_id=app_id,
        redirect_uri=redirect_uri,
        scopes=IG_IA_OAUTH_SCOPES,
        state=state,
    )
    return OAuthStartOut(auth_url=auth_url, state=state)


@router.get("/accounts/instagram/oauth/callback")
def instagram_oauth_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    error_description: Optional[str] = Query(default=None),
    cfg: SocialWiringSettings = Depends(get_settings),
    svc: IntegrationAccountService = Depends(get_account_service),
    code_exchange=Depends(get_ig_code_exchange),
    long_lived_exchange=Depends(get_ig_long_lived_exchange),
    adapter_factory=Depends(get_instagram_oauth_adapter_factory),
):
    """Instagram's redirect target for the Instagram Business Login flow.

    Exchanges code → short-lived → long-lived IG User token (falls back
    to the short-lived token if the long-lived exchange fails — a 60d
    token is preferred but a 1h token is still usable for the initial
    connection), probes ``/me`` for a username/id label (best-effort — a
    probe failure never blocks account creation), creates (or
    re-authenticates, keyed on ``metadata.channel_id``) a
    ``provider="instagram"`` ``integration_accounts`` row, then redirects
    to ``/clientes?account_created=<id>``.

    Uses the admin client throughout (no JWT in Instagram's redirect —
    mirrors ``meta_oauth_callback``). ``code_exchange`` /
    ``long_lived_exchange`` / ``adapter_factory`` are DI seams; tests
    override them via ``app.dependency_overrides``.
    """
    if error:
        detail = f"OAuth flow returned an error: {error}"
        if error_description:
            detail = f"{detail} — {error_description}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth callback missing code or state.",
        )

    parts = state.split(":")
    if len(parts) < 2 or not parts[0]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token malformed.",
        )
    try:
        org_id = UUID(parts[0])
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token does not encode a valid org_id.",
        ) from exc

    marca_id_part = parts[2] if len(parts) >= 3 else ""
    _callback_marca_id: Optional[UUID] = None
    if marca_id_part:
        try:
            _callback_marca_id = UUID(marca_id_part)
        except ValueError:
            logger.warning(
                "integration_accounts: Instagram OAuth state carries "
                "non-UUID marca_id_part=%r — ignoring",
                marca_id_part,
            )

    app_id, app_secret = resolve_instagram_app_creds(settings=cfg)
    if not app_id or not app_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="INSTAGRAM_APP_ID / INSTAGRAM_APP_SECRET not configured.",
        )

    redirect_uri = _build_ia_instagram_redirect_uri(cfg)

    # 1) code → short-lived IG User token.
    try:
        short = code_exchange(
            code=code,
            app_id=app_id,
            app_secret=app_secret,
            redirect_uri=redirect_uri,
        )
    except MetaGraphError as exc:
        logger.exception("integration_accounts: Instagram OAuth code exchange failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth code exchange failed: {exc}",
        ) from exc
    if not short or not short.access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Instagram did not return an access_token from the code exchange.",
        )

    # 2) short → long-lived IG User token. Falls back to the short-lived
    # token on failure — still usable for the initial connection, and the
    # account is re-synced (re-running the OAuth flow) rather than losing
    # the connection outright over a transient long-lived-exchange error.
    long_token = short.access_token
    token_type = "bearer"
    expires_in: Optional[int] = None
    try:
        long_bundle = long_lived_exchange(
            short_token=short.access_token,
            app_secret=app_secret,
        )
        long_token = long_bundle.access_token or short.access_token
        token_type = long_bundle.token_type or "bearer"
        expires_in = long_bundle.expires_in
    except MetaGraphError as exc:
        logger.warning(
            "integration_accounts: Instagram long-lived exchange failed for "
            "org_id=%s — falling back to the short-lived token: %s",
            org_id,
            exc,
        )

    # 3) probe /me for a username/id label — best-effort; never blocks
    # account creation on a probe failure.
    probe_adapter = adapter_factory(long_token)
    user_id: Optional[str] = short.user_id
    user_name: Optional[str] = None
    try:
        me = probe_adapter.me()
        user_id = str(me.get("id")) if me.get("id") is not None else user_id
        user_name = me.get("username")
    except MetaGraphError as exc:  # noqa: BLE001 — best-effort; account still created
        logger.warning(
            "integration_accounts: Instagram /me probe failed during OAuth "
            "callback for org_id=%s — using fallback label: %s",
            org_id,
            exc,
        )

    bundle = {
        "access_token": long_token,
        "token_type": token_type,
        "expires_in": expires_in,
        "scope": ",".join(IG_IA_OAUTH_SCOPES),
        "user_id": user_id,
    }
    account_label = user_name or f"Instagram account ({org_id})"
    metadata = {
        "user_id": user_id,
        "channel_id": user_id,
        "channel_title": user_name,
        "scopes": list(IG_IA_OAUTH_SCOPES),
        "model": "instagram_login",
    }
    metadata = {k: v for k, v in metadata.items() if v is not None}

    from datetime import datetime as _dt
    from datetime import timezone as _tz

    channel_info: dict = {}
    if user_id:
        channel_info = {"channel_id": user_id, "title": user_name or ""}

    # Idempotent on channel_id (mirrors meta_oauth_callback) — reconnecting
    # the same IG account re-authenticates the existing row instead of
    # inserting a duplicate.
    ig_accounts = svc.list_accounts(org_id, provider=INSTAGRAM_PROVIDER)
    existing = (
        next(
            (a for a in ig_accounts if (a.metadata or {}).get("channel_id") == user_id),
            None,
        )
        if user_id
        else None
    )
    if existing is not None:
        account = svc.update_credential(
            account_id=existing.id,
            org_id=org_id,
            credential_dict=bundle,
            metadata=metadata,
        )
        account = svc.update_channel_info(
            account_id=existing.id,
            org_id=org_id,
            channel_info=channel_info,
            status="validated",
            last_synced_at=_dt.now(_tz.utc),
        )
    else:
        existing_labels = {a.account_label for a in ig_accounts}
        unique_label = account_label
        if unique_label in existing_labels and user_id:
            unique_label = f"{account_label} · {user_id[-6:]}"
        account = svc.create_account(
            org_id=org_id,
            provider=INSTAGRAM_PROVIDER,
            account_label=unique_label,
            credential_dict=bundle,
            metadata=metadata,
            is_default=not ig_accounts,
            status="validated",
            marca_id=_callback_marca_id,
        )
        if channel_info:
            account = svc.update_channel_info(
                account_id=account.id,
                org_id=org_id,
                channel_info=channel_info,
                status="validated",
                last_synced_at=_dt.now(_tz.utc),
            )

    redirect_url = f"/clientes?account_created={account.id}"
    if cfg.frontend_base_url:
        redirect_url = urljoin(
            cfg.frontend_base_url.rstrip("/") + "/",
            f"clientes?account_created={account.id}",
        )
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


@router.post(
    "/accounts/instagram/token",
    response_model=IntegrationAccountOut,
    status_code=status.HTTP_201_CREATED,
)
def instagram_manual_token(
    body: InstagramTokenIn,
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
    adapter_factory=Depends(get_instagram_oauth_adapter_factory),
) -> IntegrationAccountOut:
    """Manual-token fallback: register an already-obtained IG User access
    token directly (no browser OAuth round-trip).

    Validated by probing ``/me`` via ``InstagramLoginOAuthAdapter`` — an
    invalid or unauthorized token 400s with a clear message rather than
    persisting an untested credential. Idempotent on ``metadata.channel_id``
    (same reconnect semantics as the OAuth callback).
    """
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    marca_id: Optional[UUID] = None
    if body.marca_id is not None:
        marca_svc = build_marca_service(get_admin_client())
        found = marca_svc.get_marca(body.marca_id, org_id)
        if found is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="marca_id not found or does not belong to this org.",
            )
        marca_id = body.marca_id

    probe_adapter = adapter_factory(body.access_token)
    try:
        me = probe_adapter.me()
    except MetaGraphError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="token inválido ou sem permissão",
        ) from exc

    user_id = str(me.get("id")) if me.get("id") is not None else None
    user_name = me.get("username")

    bundle = {
        "access_token": body.access_token,
        "token_type": "bearer",
        "expires_in": None,
        "scope": "manual",
        "user_id": user_id,
    }
    account_label = user_name or f"Instagram account ({org_id})"
    metadata = {
        "user_id": user_id,
        "channel_id": user_id,
        "channel_title": user_name,
        "model": "instagram_login",
    }
    metadata = {k: v for k, v in metadata.items() if v is not None}

    from datetime import datetime as _dt
    from datetime import timezone as _tz

    channel_info: dict = {}
    if user_id:
        channel_info = {"channel_id": user_id, "title": user_name or ""}

    ig_accounts = svc.list_accounts(org_id, provider=INSTAGRAM_PROVIDER)
    existing = (
        next(
            (a for a in ig_accounts if (a.metadata or {}).get("channel_id") == user_id),
            None,
        )
        if user_id
        else None
    )
    if existing is not None:
        account = svc.update_credential(
            account_id=existing.id,
            org_id=org_id,
            credential_dict=bundle,
            metadata=metadata,
        )
        if channel_info:
            account = svc.update_channel_info(
                account_id=existing.id,
                org_id=org_id,
                channel_info=channel_info,
                status="validated",
                last_synced_at=_dt.now(_tz.utc),
            )
    else:
        existing_labels = {a.account_label for a in ig_accounts}
        unique_label = account_label
        if unique_label in existing_labels and user_id:
            unique_label = f"{account_label} · {user_id[-6:]}"
        account = svc.create_account(
            org_id=org_id,
            provider=INSTAGRAM_PROVIDER,
            account_label=unique_label,
            credential_dict=bundle,
            metadata=metadata,
            is_default=not ig_accounts,
            status="validated",
            marca_id=marca_id,
        )
        if channel_info:
            account = svc.update_channel_info(
                account_id=account.id,
                org_id=org_id,
                channel_info=channel_info,
                status="validated",
                last_synced_at=_dt.now(_tz.utc),
            )

    return _out(account)


# ─── Gmail OAuth endpoints ────────────────────────────────────────────────────

@router.post(
    "/accounts/gmail/oauth/start",
    response_model=OAuthStartOut,
)
def gmail_oauth_start(
    body: OAuthStartIn = OAuthStartIn(),
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
    provider=Depends(get_gmail_oauth_provider),
    redis_client=Depends(get_gmail_pkce_redis),
) -> OAuthStartOut:
    """Build a Gmail OAuth consent URL for the multi-account IA flow.

    State format: ``{org_id}:{nonce}:{marca_id_or_empty}`` (same as YouTube).
    Scopes: ``gmail.send`` + ``gmail.readonly`` from the seed.
    """
    import asyncio

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET not configured. "
                "Set them in .env to enable Gmail OAuth."
            ),
        )

    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    marca_id_str = ""
    if body.marca_id is not None:
        marca_svc = build_marca_service(get_admin_client())
        found = marca_svc.get_marca(body.marca_id, org_id)
        if found is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="marca_id not found or does not belong to this org.",
            )
        marca_id_str = str(body.marca_id)

    redirect_uri = _build_ia_google_redirect_uri(cfg, "gmail")
    state = f"{org_id}:{secrets.token_urlsafe(16)}:{marca_id_str}"
    auth_result = asyncio.run(
        provider.authorization_url(
            state=state, scopes=_GMAIL_OAUTH_SCOPES, redirect_uri=redirect_uri
        )
    )

    if redis_client is not None and auth_result.code_verifier:
        try:
            redis_client.set(
                f"{_GMAIL_PKCE_KEY_PREFIX}{state}",
                auth_result.code_verifier,
                ex=_YT_PKCE_TTL_SECONDS,
            )
        except Exception as exc:
            logger.warning("integration_accounts: Gmail PKCE Redis write failed: %s", exc)

    return OAuthStartOut(auth_url=auth_result.url, state=state)


@router.get("/accounts/gmail/oauth/callback")
def gmail_oauth_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    cfg: SocialWiringSettings = Depends(get_settings),
    svc: IntegrationAccountService = Depends(get_account_service),
    provider=Depends(get_gmail_oauth_provider),
    redis_client=Depends(get_gmail_pkce_redis),
):
    """Google redirect target for the Gmail multi-account IA flow.

    Exchanges code → tokens, fetches the Gmail profile email address,
    creates an ``integration_accounts`` row (provider=``'gmail'``), then
    redirects to ``/clientes?account_created=<id>``.
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

    parts = state.split(":")
    if len(parts) < 2 or not parts[0]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token malformed.",
        )
    org_part = parts[0]
    marca_id_part = parts[2] if len(parts) >= 3 else ""
    try:
        org_id = UUID(org_part)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token does not encode a valid org_id.",
        ) from exc

    _callback_marca_id: Optional[UUID] = None
    if marca_id_part:
        try:
            _callback_marca_id = UUID(marca_id_part)
        except ValueError:
            logger.warning(
                "integration_accounts: Gmail OAuth state carries non-UUID "
                "marca_id_part=%r — ignoring",
                marca_id_part,
            )

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET not configured.",
        )

    import asyncio

    redirect_uri = _build_ia_google_redirect_uri(cfg, "gmail")

    code_verifier: Optional[str] = None
    if redis_client is not None:
        try:
            key = f"{_GMAIL_PKCE_KEY_PREFIX}{state}"
            code_verifier = redis_client.get(key)
            if code_verifier:
                redis_client.delete(key)
        except Exception as exc:
            logger.warning(
                "integration_accounts: Gmail PKCE Redis read failed: %s", exc
            )

    try:
        tokens = asyncio.run(
            provider.exchange_code(
                code=code,
                state=state,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
        )
    except Exception as exc:
        logger.exception("integration_accounts: Gmail OAuth exchange failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth code exchange failed: {exc}",
        ) from exc

    bundle = {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "scopes": tokens.scope or _GMAIL_OAUTH_SCOPES,
        "expires_at": tokens.expires_at.isoformat() if tokens.expires_at else None,
        **(tokens.raw or {}),
    }

    # Best-effort: fetch the Gmail account email via the Gmail profile endpoint.
    email_address: Optional[str] = None
    try:
        from google.oauth2.credentials import Credentials as GCredentials
        from googleapiclient.discovery import build as _gapi_build

        _gcreds = GCredentials(
            token=bundle.get("access_token"),
            refresh_token=bundle.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=cfg.google_oauth_client_id,
            client_secret=cfg.google_oauth_client_secret,
            scopes=_GMAIL_OAUTH_SCOPES,
        )
        _gmail_svc = _gapi_build("gmail", "v1", credentials=_gcreds, cache_discovery=False)
        profile = _gmail_svc.users().getProfile(userId="me").execute()
        email_address = profile.get("emailAddress")
    except Exception as exc:
        logger.warning(
            "integration_accounts: Gmail profile fetch failed for org_id=%s — "
            "using fallback label: %s",
            org_id,
            exc,
        )

    account_label = email_address or f"Gmail account ({org_id})"
    metadata = {
        "email": email_address,
        "scopes": bundle.get("scopes", _GMAIL_OAUTH_SCOPES),
        "expires_at": bundle.get("expires_at"),
    }
    metadata = {k: v for k, v in metadata.items() if v is not None}

    # Idempotent on email: re-connecting the same Gmail account re-auths it.
    existing_accounts = svc.list_accounts(org_id, provider="gmail")
    existing = (
        next(
            (a for a in existing_accounts if (a.metadata or {}).get("email") == email_address),
            None,
        )
        if email_address
        else None
    )
    if existing is not None:
        account = svc.update_credential(
            account_id=existing.id,
            org_id=org_id,
            credential_dict=bundle,
            metadata=metadata,
        )
    else:
        existing_labels = {a.account_label for a in existing_accounts}
        unique_label = account_label
        if unique_label in existing_labels:
            unique_label = f"{account_label} (2)"
        account = svc.create_account(
            org_id=org_id,
            provider="gmail",
            account_label=unique_label,
            credential_dict=bundle,
            metadata=metadata,
            is_default=not existing_accounts,
            status="validated",
            marca_id=_callback_marca_id,
        )

    redirect_url = f"/clientes?account_created={account.id}"
    if cfg.frontend_base_url:
        redirect_url = urljoin(
            cfg.frontend_base_url.rstrip("/") + "/",
            f"clientes?account_created={account.id}",
        )
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


# ─── Google Drive OAuth endpoints ────────────────────────────────────────────

@router.post(
    "/accounts/google_drive/oauth/start",
    response_model=OAuthStartOut,
)
def drive_oauth_start(
    body: OAuthStartIn = OAuthStartIn(),
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
    provider=Depends(get_drive_oauth_provider),
    redis_client=Depends(get_drive_pkce_redis),
) -> OAuthStartOut:
    """Build a Google Drive OAuth consent URL for the multi-account IA flow.

    Scopes: ``drive.readonly`` — read access to the user's Drive.
    """
    import asyncio

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET not configured. "
                "Set them in .env to enable Google Drive OAuth."
            ),
        )

    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    marca_id_str = ""
    if body.marca_id is not None:
        marca_svc = build_marca_service(get_admin_client())
        found = marca_svc.get_marca(body.marca_id, org_id)
        if found is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="marca_id not found or does not belong to this org.",
            )
        marca_id_str = str(body.marca_id)

    redirect_uri = _build_ia_google_redirect_uri(cfg, "google_drive")
    state = f"{org_id}:{secrets.token_urlsafe(16)}:{marca_id_str}"
    auth_result = asyncio.run(
        provider.authorization_url(
            state=state, scopes=_DRIVE_OAUTH_SCOPES, redirect_uri=redirect_uri
        )
    )

    if redis_client is not None and auth_result.code_verifier:
        try:
            redis_client.set(
                f"{_DRIVE_PKCE_KEY_PREFIX}{state}",
                auth_result.code_verifier,
                ex=_YT_PKCE_TTL_SECONDS,
            )
        except Exception as exc:
            logger.warning("integration_accounts: Drive PKCE Redis write failed: %s", exc)

    return OAuthStartOut(auth_url=auth_result.url, state=state)


@router.get("/accounts/google_drive/oauth/callback")
def drive_oauth_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    cfg: SocialWiringSettings = Depends(get_settings),
    svc: IntegrationAccountService = Depends(get_account_service),
    provider=Depends(get_drive_oauth_provider),
    redis_client=Depends(get_drive_pkce_redis),
):
    """Google redirect target for the Drive multi-account IA flow.

    Exchanges code → tokens, fetches the Drive account email via
    ``drive.about.get``, creates an ``integration_accounts`` row
    (provider=``'google_drive'``), then redirects to
    ``/clientes?account_created=<id>``.
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

    parts = state.split(":")
    if len(parts) < 2 or not parts[0]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token malformed.",
        )
    org_part = parts[0]
    marca_id_part = parts[2] if len(parts) >= 3 else ""
    try:
        org_id = UUID(org_part)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token does not encode a valid org_id.",
        ) from exc

    _callback_marca_id: Optional[UUID] = None
    if marca_id_part:
        try:
            _callback_marca_id = UUID(marca_id_part)
        except ValueError:
            logger.warning(
                "integration_accounts: Drive OAuth state carries non-UUID "
                "marca_id_part=%r — ignoring",
                marca_id_part,
            )

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET not configured.",
        )

    import asyncio

    redirect_uri = _build_ia_google_redirect_uri(cfg, "google_drive")

    code_verifier: Optional[str] = None
    if redis_client is not None:
        try:
            key = f"{_DRIVE_PKCE_KEY_PREFIX}{state}"
            code_verifier = redis_client.get(key)
            if code_verifier:
                redis_client.delete(key)
        except Exception as exc:
            logger.warning(
                "integration_accounts: Drive PKCE Redis read failed: %s", exc
            )

    try:
        tokens = asyncio.run(
            provider.exchange_code(
                code=code,
                state=state,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
        )
    except Exception as exc:
        logger.exception("integration_accounts: Drive OAuth exchange failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth code exchange failed: {exc}",
        ) from exc

    bundle = {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "scopes": tokens.scope or _DRIVE_OAUTH_SCOPES,
        "expires_at": tokens.expires_at.isoformat() if tokens.expires_at else None,
        **(tokens.raw or {}),
    }

    # Best-effort: fetch the Drive account email via drive.about.get.
    drive_email: Optional[str] = None
    try:
        from google.oauth2.credentials import Credentials as GCredentials
        from googleapiclient.discovery import build as _gapi_build

        _gcreds = GCredentials(
            token=bundle.get("access_token"),
            refresh_token=bundle.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=cfg.google_oauth_client_id,
            client_secret=cfg.google_oauth_client_secret,
            scopes=_DRIVE_OAUTH_SCOPES,
        )
        _drive_svc = _gapi_build("drive", "v3", credentials=_gcreds, cache_discovery=False)
        about = _drive_svc.about().get(fields="user").execute()
        drive_email = (about.get("user") or {}).get("emailAddress")
    except Exception as exc:
        logger.warning(
            "integration_accounts: Drive about.get failed for org_id=%s — "
            "using fallback label: %s",
            org_id,
            exc,
        )

    account_label = drive_email or f"Google Drive account ({org_id})"
    metadata = {
        "email": drive_email,
        "scopes": bundle.get("scopes", _DRIVE_OAUTH_SCOPES),
        "expires_at": bundle.get("expires_at"),
    }
    metadata = {k: v for k, v in metadata.items() if v is not None}

    # Idempotent on email: re-connecting the same Drive account re-auths it.
    existing_accounts = svc.list_accounts(org_id, provider="google_drive")
    existing = (
        next(
            (a for a in existing_accounts if (a.metadata or {}).get("email") == drive_email),
            None,
        )
        if drive_email
        else None
    )
    if existing is not None:
        account = svc.update_credential(
            account_id=existing.id,
            org_id=org_id,
            credential_dict=bundle,
            metadata=metadata,
        )
    else:
        existing_labels = {a.account_label for a in existing_accounts}
        unique_label = account_label
        if unique_label in existing_labels:
            unique_label = f"{account_label} (2)"
        account = svc.create_account(
            org_id=org_id,
            provider="google_drive",
            account_label=unique_label,
            credential_dict=bundle,
            metadata=metadata,
            is_default=not existing_accounts,
            status="validated",
            marca_id=_callback_marca_id,
        )

    redirect_url = f"/clientes?account_created={account.id}"
    if cfg.frontend_base_url:
        redirect_url = urljoin(
            cfg.frontend_base_url.rstrip("/") + "/",
            f"clientes?account_created={account.id}",
        )
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


__all__ = ["router"]
