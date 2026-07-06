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
``meta_router`` / ``services/meta`` / ``_meta_common`` — those already
have an env fallback (``META_APP_ID`` / ``META_APP_SECRET``) that must
keep working even before ``ENCRYPTION_KEY`` is configured (e.g. local
dev). :func:`resolve_meta_app_creds` therefore degrades to env-only
when the store cannot be built, rather than raising.
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
    "META_APP_ID_KEY",
    "META_APP_SECRET_KEY",
    "build_app_config_store",
    "resolve_meta_app_creds",
]


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
