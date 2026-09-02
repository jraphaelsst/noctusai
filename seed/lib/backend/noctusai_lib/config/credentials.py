"""
Credential Resolver — Single source of truth for API key / token resolution.

Resolution chain (in order):

  0. Product-local override         — OPTIONAL, off unless the product calls
                                      `register_credential_override()`. For a
                                      product that keeps its own encrypted,
                                      org-scoped store. See that function.
  1. `org_settings` table           — per-org overrides, keyed by (org_id, key)
  2. `platform_settings` table      — platform-wide NoctusAI defaults
  3. Environment variable           — last-resort fallback (key.upper())

Both tables live in the `public` schema (used by every product). This module
is product-agnostic: it takes Supabase connection config once via
`configure_credentials()` at startup, then serves `resolve_credential()` calls
for the rest of the process.

Usage:

    # In each product's main.py, before create_product_app():
    from noctusai_lib.config.credentials import configure_credentials
    configure_credentials(
        supabase_url=settings.supabase_url,
        supabase_anon_key=settings.supabase_anon_key,
        supabase_service_role_key=settings.supabase_service_role_key,
    )

    # In any service:
    from noctusai_lib.config.credentials import resolve_credential
    api_key = resolve_credential("openai_api_key", org_id=user_org_id)

All services needing credentials (LLM providers, Resend, ClickSign, etc.)
must use this instead of implementing their own resolution logic.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from noctusai_lib.integrations.database import make_supabase_client

logger = logging.getLogger(__name__)

_config: Optional[dict] = None
_public_client = None
#: Optional product-local tier consulted before `org_settings`.
#: See `register_credential_override`. None => the historical 3-tier chain.
_override: Optional[Callable[[str, Optional[str]], Optional[str]]] = None


def configure_credentials(
    *,
    supabase_url: str,
    supabase_anon_key: str,
    supabase_service_role_key: str,
) -> None:
    """Configure credential resolution. Call once at product startup.

    Safe to call multiple times — the last configuration wins. Resets the
    cached public-schema client so subsequent calls pick up new config.
    """
    global _config, _public_client
    _config = {
        "url": supabase_url,
        "anon_key": supabase_anon_key,
        "service_role_key": supabase_service_role_key,
    }
    _public_client = None
    logger.info("Credential resolution configured (url=%s)", supabase_url)


def _get_public_client():
    """Lazy-init the public-schema service-role client (singleton)."""
    if _config is None:
        return None  # Tier 1+2 simply miss; Tier 3 (env) still works.
    global _public_client
    if _public_client is None:
        _public_client = make_supabase_client(
            url=_config["url"],
            anon_key=_config["anon_key"],
            service_role_key=_config["service_role_key"],
        )
    return _public_client


def register_credential_override(
    fn: Optional[Callable[[str, Optional[str]], Optional[str]]],
) -> None:
    """Install a product-local tier consulted BEFORE `org_settings`.

    WHY THIS EXISTS
    ---------------
    A product may keep its own encrypted, org-scoped key store (social-wiring
    puts operator-entered keys in `social_wiring.credentials`, Fernet-encrypted
    via the seed `token_store`). Without this seam, only the code paths that
    call the product's own resolver see those keys — and the paths that go
    through `resolve_credential` do not. That split is a FALSE GREEN of the
    worst shape: a pre-flight check reads the product store and passes, then
    the real call resolves through this chain, finds nothing, and fails. The
    operator sees "key configured" and a failure in the same breath.

    Registering here closes it at the root instead of at each call site —
    which matters because the call sites are not enumerable: `chat_completion`
    reaches keys through `LLMConfig.key_provider`, while the document
    transcriber calls `resolve_credential` directly, and the next consumer
    will pick whichever it likes.

    CONTRACT
    --------
    - `fn(key, org_id) -> value | None`. It MUST NOT call `resolve_credential`
      (that recurses); pass a store-only reader.
    - Registering `None` removes the override — behaviour is then byte-identical
      to before this seam existed, which is what every product that does not
      opt in continues to get.
    - A raising override does NOT take resolution down: the failure is logged
      at WARNING (loud, named — an encryption-key rotation gap must not be
      mistaken for "no key configured") and the chain continues to tier 1.
    """
    global _override
    _override = fn


def resolve_credential(key: str, org_id: Optional[str] = None) -> Optional[str]:
    """Resolve a credential value through the tier chain.

    Args:
        key: Lowercase setting key (e.g. "openai_api_key", "resend_api_key").
             Must match the `key` column in `org_settings` / `platform_settings`.
             The env-var fallback uses `key.upper()`.
        org_id: Organization ID for tier-1 lookup. If None, tier 1 is skipped
                and resolution starts at tier 2.

    Returns:
        The resolved value (first non-empty match), or None if no tier has it.
    """
    # Tier 0 — product-local store, when one is registered. See
    # `register_credential_override`. Absent an override this is a single
    # `is None` test and the chain below is unchanged.
    if _override is not None:
        try:
            value = _override(key, org_id)
        except Exception as exc:
            logger.warning(
                "credential override failed for %s (org=%s): %s — falling "
                "through to org_settings. This is NOT the same as 'no key "
                "configured'; check ENCRYPTION_KEY and the product store.",
                key, org_id, exc,
            )
        else:
            if value:
                return value

    db = _get_public_client()

    # Tier 1 — org_settings (per-org override)
    if org_id and db is not None:
        try:
            result = (
                db.table("org_settings")
                .select("value")
                .eq("org_id", org_id)
                .eq("key", key)
                .execute()
            )
            if result.data and result.data[0].get("value"):
                return result.data[0]["value"]
        except Exception as exc:
            logger.debug("org_settings lookup failed for %s: %s", key, exc)

    # Tier 2 — platform_settings (NoctusAI global default)
    if db is not None:
        try:
            result = (
                db.table("platform_settings")
                .select("value")
                .eq("key", key)
                .execute()
            )
            if result.data and result.data[0].get("value"):
                return result.data[0]["value"]
        except Exception as exc:
            logger.debug("platform_settings lookup failed for %s: %s", key, exc)

    # Tier 3 — environment variable
    return os.environ.get(key.upper()) or None


def _reset_for_testing() -> None:
    """Test-only hook to clear module-level state between test cases."""
    global _config, _public_client, _override
    _config = None
    _public_client = None
    _override = None
