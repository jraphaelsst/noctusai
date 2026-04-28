"""
Credential Resolver — Single source of truth for API key / token resolution.

Resolution chain (3 tiers, in order):

  1. `org_settings` table           — per-org overrides, keyed by (org_id, key)
  2. `platform_settings` table      — platform-wide NoctusAI defaults
  3. Environment variable           — last-resort fallback (key.upper())

Both tables live in the `public` schema (used by every product). This module
is product-agnostic: it takes Supabase connection config once via
`configure_credentials()` at startup, then serves `resolve_credential()` calls
for the rest of the process.

Usage:

    # In each product's main.py, before create_product_app():
    from noctusai_lib.credentials import configure_credentials
    configure_credentials(
        supabase_url=settings.supabase_url,
        supabase_anon_key=settings.supabase_anon_key,
        supabase_service_role_key=settings.supabase_service_role_key,
    )

    # In any service:
    from noctusai_lib.credentials import resolve_credential
    api_key = resolve_credential("openai_api_key", org_id=user_org_id)

All services needing credentials (LLM providers, Resend, ClickSign, etc.)
must use this instead of implementing their own resolution logic.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from noctusai_lib.database import make_supabase_client

logger = logging.getLogger(__name__)

_config: Optional[dict] = None
_public_client = None


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


def resolve_credential(key: str, org_id: Optional[str] = None) -> Optional[str]:
    """Resolve a credential value through the 3-tier chain.

    Args:
        key: Lowercase setting key (e.g. "openai_api_key", "resend_api_key").
             Must match the `key` column in `org_settings` / `platform_settings`.
             The env-var fallback uses `key.upper()`.
        org_id: Organization ID for tier-1 lookup. If None, tier 1 is skipped
                and resolution starts at tier 2.

    Returns:
        The resolved value (first non-empty match), or None if no tier has it.
    """
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
    global _config, _public_client
    _config = None
    _public_client = None
