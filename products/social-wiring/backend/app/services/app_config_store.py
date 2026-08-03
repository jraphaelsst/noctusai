"""Product seam over ``noctusai_lib.security.app_config`` — app-wide
encrypted config (currently: the Meta App ID / App Secret pair) with
DB-first / env-fallback resolution.

Mirrors ``credential_vault.build_credential_store``: the SAME
``ENCRYPTION_KEY`` / :class:`~app.services.credential_vault.EncryptionNotConfigured`
Fernet key the per-org credential vault uses — one crypto key, one
loud-config-gap check, not a second inline copy. Backed by
``social_wiring.app_integration_config`` (migration 022).

Unlike ``credential_vault`` / ``IntegrationAccountService`` (which map a
missing/malformed key to a 503 at the router boundary), reading the Meta
app credential pair must NEVER hard-fail the read-only call sites in
``services/meta`` / ``_meta_common`` / ``integration_accounts_router`` —
those already have an env fallback (``META_APP_ID`` / ``META_APP_SECRET``)
that must keep working even before ``ENCRYPTION_KEY`` is configured
(e.g. local dev). :func:`resolve_meta_app_creds` therefore degrades to
env-only when the store cannot be built, rather than raising.
"""
from __future__ import annotations

from typing import Optional

from noctusai_lib.security.app_config import (
    META_APP_ID_KEY,
    META_APP_SECRET_KEY,
    AppConfigStore,
)
from noctusai_lib.security.app_config import (
    build_app_config_store as _seed_build_app_config_store,
)
from noctusai_lib.security.app_config import (
    resolve_meta_app_credentials as _seed_resolve_meta_app_credentials,
)

from app.config import settings as default_settings
from app.dependencies import get_admin_client
from app.services.credential_vault import EncryptionNotConfigured, require_fernet

__all__ = [
    "INSTAGRAM_APP_ID_KEY",
    "INSTAGRAM_APP_SECRET_KEY",
    "META_APP_ID_KEY",
    "META_APP_SECRET_KEY",
    "build_app_config_store",
    "resolve_instagram_app_creds",
    "resolve_meta_app_creds",
    "resolve_meta_ads_config",
    "resolve_meta_webhook_verify_token",
    "META_SYSTEM_USER_TOKEN_KEY",
    "META_AD_ACCOUNT_ID_KEY",
    "META_ADS_ORG_ID_KEY",
    "META_WEBHOOK_VERIFY_TOKEN_KEY",
]

# Instagram Business Login app-config keys — product-local (not part of
# the seed's `noctusai_lib.security.app_config` well-known-key pair,
# which is Meta/Facebook-Login-specific). Same DB-first/env-fallback
# shape as `resolve_meta_app_creds` below, keyed on these two instead.
INSTAGRAM_APP_ID_KEY = "instagram_app_id"
INSTAGRAM_APP_SECRET_KEY = "instagram_app_secret"

# Meta Ads console config keys (roadmap `meta-ads-console-2026-07`). The
# System User TOKEN is a secret; the ad-account id + owning-org id are
# identifiers. All three follow the same DB-first / env-fallback shape as
# the app-cred pairs so prod consumes them Fernet-encrypted from
# `app_integration_config` (dev falls back to the root `.env`) —
# `feedback_dev_prod_key_storage_model`. Storing the two non-secret
# identifiers in the (encrypting) config table too keeps prod needing ZERO
# Meta env vars — one resolution path, one place.
META_SYSTEM_USER_TOKEN_KEY = "meta_system_user_token"
META_AD_ACCOUNT_ID_KEY = "meta_ad_account_id"
META_ADS_ORG_ID_KEY = "meta_ads_org_id"

# Lead-Ads webhook handshake token (`hub.verify_token`). Vaulted alongside
# the keys above so prod needs zero Meta env vars. 🔴 NOT the HMAC secret —
# see `resolve_meta_webhook_verify_token`'s docstring.
META_WEBHOOK_VERIFY_TOKEN_KEY = "meta_webhook_verify_token"


def build_app_config_store(
    client=None,
    *,
    encryption_key: Optional[str] = None,
) -> AppConfigStore:
    """Build the app-wide config store, admin-client + Fernet-backed.

    Validates the Fernet key loudly first via :func:`require_fernet`
    (raises :class:`EncryptionNotConfigured` on a missing/malformed key
    — routers that write config map this to a 503 config-gap, exactly
    as ``credential_vault.build_credential_store`` does) so a
    misconfigured deployment never silently persists plaintext.
    """
    key = encryption_key if encryption_key is not None else default_settings.encryption_key
    require_fernet(key)  # loud EncryptionNotConfigured on missing/malformed key
    return _seed_build_app_config_store(
        client=client if client is not None else get_admin_client(),
        fernet_key=key.encode("utf-8"),
    )


def resolve_meta_app_creds(
    *,
    settings=None,
    store: Optional[AppConfigStore] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Resolve the Meta App ID / Secret pair: DB value wins, env falls
    back per-key (each of the two keys resolved independently — see
    ``noctusai_lib.security.app_config.resolve_meta_app_credentials``).

    Degrades to env-only when the app-config store cannot be built
    (``ENCRYPTION_KEY`` missing/malformed) — a read-only credential
    lookup must never hard-fail a Meta OAuth/scopes/status call that
    would otherwise work off env vars alone.

    ``store`` is a DI seam: pass an already-built (or already-attempted,
    possibly ``None``) store — e.g. from a router's
    ``Depends(get_app_config_store_...)`` seam — to reuse the SAME
    instance a preceding write/read used (or a test's
    ``FakeAppConfigStore``) instead of constructing a second one.
    ``None`` (default) builds one internally, same as before.
    """
    settings = settings or default_settings
    env_app_id = getattr(settings, "meta_app_id", "") or None
    env_app_secret = getattr(settings, "meta_app_secret", "") or None
    if store is None:
        try:
            store = build_app_config_store()
        except EncryptionNotConfigured:
            return env_app_id, env_app_secret
    return _seed_resolve_meta_app_credentials(
        store, env_app_id=env_app_id, env_app_secret=env_app_secret
    )


def resolve_instagram_app_creds(
    *,
    settings=None,
    store: Optional[AppConfigStore] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Resolve the Instagram App ID / Secret pair: DB value wins, env
    falls back per-key. Mirrors :func:`resolve_meta_app_creds` exactly
    (same DB-first/env-fallback shape, same graceful degrade to
    env-only when the app-config store can't be built) but keyed on
    ``INSTAGRAM_APP_ID_KEY`` / ``INSTAGRAM_APP_SECRET_KEY`` — a
    SEPARATE app credential pair from the Facebook-Login
    ``meta_app_id``/``meta_app_secret`` (Instagram Business Login
    authenticates against its own Instagram App ID/Secret).
    """
    settings = settings or default_settings
    env_app_id = getattr(settings, "instagram_app_id", "") or None
    env_app_secret = getattr(settings, "instagram_app_secret", "") or None
    if store is None:
        try:
            store = build_app_config_store()
        except EncryptionNotConfigured:
            return env_app_id, env_app_secret
    app_id = store.get(INSTAGRAM_APP_ID_KEY)
    if app_id is None:
        app_id = env_app_id
    app_secret = store.get(INSTAGRAM_APP_SECRET_KEY)
    if app_secret is None:
        app_secret = env_app_secret
    return app_id, app_secret


def resolve_meta_ads_config(
    *,
    settings=None,
    store: Optional[AppConfigStore] = None,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Resolve the Meta Ads console config — ``(system_user_token,
    ad_account_id, ads_org_id)`` — DB-first per key, env fallback.

    Same DB-first/env-fallback shape + graceful degrade-to-env-only (when
    the app-config store can't be built, e.g. `ENCRYPTION_KEY` missing) as
    :func:`resolve_meta_app_creds`. Prod consumes all three Fernet-encrypted
    from ``app_integration_config``; dev falls back to the root ``.env``
    (`settings.meta_system_user_token` / `.meta_ad_account_id` /
    `.meta_ads_org_id`). See `feedback_dev_prod_key_storage_model`."""
    settings = settings or default_settings
    env_token = getattr(settings, "meta_system_user_token", "") or None
    env_account = getattr(settings, "meta_ad_account_id", "") or None
    env_org = getattr(settings, "meta_ads_org_id", "") or None
    if store is None:
        try:
            store = build_app_config_store()
        except EncryptionNotConfigured:
            return env_token, env_account, env_org
    token = store.get(META_SYSTEM_USER_TOKEN_KEY) or env_token
    account = store.get(META_AD_ACCOUNT_ID_KEY) or env_account
    org = store.get(META_ADS_ORG_ID_KEY) or env_org
    return token, account, org


def resolve_meta_webhook_verify_token(
    *,
    settings=None,
    store: Optional[AppConfigStore] = None,
) -> Optional[str]:
    """Resolve the Lead-Ads webhook ``hub.verify_token`` — DB-first, env
    fallback, same shape + graceful degrade as
    :func:`resolve_meta_ads_config`.

    🔴 This is the HANDSHAKE token only. It is NOT the HMAC signing secret
    — that is the Meta **App Secret**, resolved by
    :func:`resolve_meta_app_creds`. Passing this value to a signature
    verifier is the `erp-imobiliario` defect (`meta_api.py:70`), where it
    makes every genuine Meta delivery fail its signature check.

    Returns ``None`` when unset anywhere, which the handshake route must
    treat as "refuse" — never as "accept anything". An empty configured
    token compared against an empty supplied token would otherwise let any
    caller register our endpoint as their webhook target.
    """
    settings = settings or default_settings
    env_token = getattr(settings, "meta_webhook_verify_token", "") or None
    if store is None:
        try:
            store = build_app_config_store()
        except EncryptionNotConfigured:
            return env_token
    return store.get(META_WEBHOOK_VERIFY_TOKEN_KEY) or env_token
