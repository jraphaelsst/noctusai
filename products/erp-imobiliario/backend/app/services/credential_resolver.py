"""
Credential Resolver — Single source of truth for API key/token resolution.

Resolution chain (per CLAUDE.md):
  1. org_settings table (per-org override, keyed by org_id + key)
  2. platform_settings table (global NoctusAI-wide default)
  3. Environment variable (via config.py Settings)

Both settings tables live in the `public` schema, so this module creates
its own public-schema client — the ERP default client targets `erp`.

All services that need credentials (OpenAI, InfoSimples, Resend, ClickSign,
DocuSign, D4Sign) must use `resolve_credential()` instead of implementing
their own resolution logic.
"""
import logging
from typing import Optional

from noctusai_lib.database import make_supabase_client
from app.config import settings

logger = logging.getLogger(__name__)

_public_client = None


def _get_public_client():
    """Lazy-init a public-schema service-role client (singleton)."""
    global _public_client
    if _public_client is None:
        _public_client = make_supabase_client(
            url=settings.supabase_url,
            anon_key=settings.supabase_anon_key,
            service_role_key=settings.supabase_service_role_key,
        )
    return _public_client


def resolve_credential(key: str, org_id: Optional[str] = None) -> Optional[str]:
    """Resolve a credential value through the standard chain.

    Args:
        key: Setting key name (e.g. "openai_api_key", "infosimples_token").
             Must match the key used in org_settings/platform_settings tables
             AND the attribute name in config.py Settings.
        org_id: Organization ID for org-level lookups. If None, skips step 1.

    Returns:
        The resolved value, or None if not found anywhere.
    """
    # 1. org_settings (per-org override)
    if org_id:
        try:
            db = _get_public_client()
            result = (
                db.table("org_settings")
                .select("value")
                .eq("org_id", org_id)
                .eq("key", key)
                .execute()
            )
            if result.data and result.data[0].get("value"):
                return result.data[0]["value"]
        except Exception as e:
            logger.debug("org_settings lookup failed for %s: %s", key, e)

    # 2. platform_settings (global default)
    try:
        db = _get_public_client()
        result = (
            db.table("platform_settings")
            .select("value")
            .eq("key", key)
            .execute()
        )
        if result.data and result.data[0].get("value"):
            return result.data[0]["value"]
    except Exception as e:
        logger.debug("platform_settings lookup failed for %s: %s", key, e)

    # 3. Environment variable (via config.py)
    value = getattr(settings, key, None)
    return value or None
