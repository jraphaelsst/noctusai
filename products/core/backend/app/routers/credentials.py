"""
Platform credentials router — consolidated LLM-provider-key surface.

Thin convenience wrapper around `public.platform_settings` (noctus admin
scope) and `public.org_settings` (per-org scope). Same tables used by
`noctusai_lib.credentials.resolve_credential`.

Endpoints:
  GET /api/platform/credentials             — masked presence per provider
  PUT /api/platform/credentials             — upsert one or more keys

Scope rules:
  - platform_admin (noctus admin) writes `platform_settings`
  - org owner / admin writes `org_settings` for their org
  - GET returns the resolved state — org overrides if set, platform if not,
    null otherwise. The masked string never reveals the full key.

All keys stored go into `{provider}_api_key` rows — matching the lookup key
`noctusai_lib.credentials.resolve_credential` expects.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header

from app.database import get_admin_client
from app.dependencies import get_current_user
from app.schemas.credentials import CredentialsBody

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/platform/credentials", tags=["Platform Credentials"])

# Providers exposed through this convenience endpoint. The Core UI needs to
# know which credential rows to surface; the underlying tables are generic
# key/value (and still reachable via /api/settings/*).
_LLM_PROVIDERS = ("openai", "anthropic", "gemini")


def _mask(value: Optional[str]) -> Optional[str]:
    """Return a masked version showing only the last 4 chars, or None."""
    if not value:
        return None
    if len(value) <= 4:
        return "****"
    return "*" * (len(value) - 4) + value[-4:]


def _fetch_key(db, table: str, key: str, org_id: Optional[str] = None) -> Optional[str]:
    """Fetch one value from org_settings or platform_settings. Silent None on miss."""
    try:
        query = db.table(table).select("value").eq("key", key)
        if table == "org_settings" and org_id is not None:
            query = query.eq("org_id", org_id)
        result = query.execute()
        if result.data and result.data[0].get("value"):
            return result.data[0]["value"]
    except Exception as exc:
        logger.debug("%s lookup failed for %s: %s", table, key, exc)
    return None


@router.get("")
async def obter_credentials(authorization: Optional[str] = Header(None)):
    """Return the caller-visible credential state per LLM provider.

    For each provider, returns:
      - "masked": masked value if configured at org or platform level, else null
      - "scope":  "org" | "platform" | null — where the value came from

    Org admins see their own org's overrides; platform_admin sees platform values.
    """
    user, _ = await get_current_user(authorization)
    db = get_admin_client()

    org_id = (user.user_metadata or {}).get("org_id")
    out: dict = {}
    for provider in _LLM_PROVIDERS:
        key_name = f"{provider}_api_key"
        org_val = _fetch_key(db, "org_settings", key_name, org_id) if org_id else None
        platform_val = _fetch_key(db, "platform_settings", key_name)
        if org_val:
            out[provider] = {"masked": _mask(org_val), "scope": "org"}
        elif platform_val:
            out[provider] = {"masked": _mask(platform_val), "scope": "platform"}
        else:
            out[provider] = {"masked": None, "scope": None}
    return out


@router.put("")
async def salvar_credentials(
    body: CredentialsBody,
    authorization: Optional[str] = Header(None),
):
    """Upsert one or more provider keys.

    Routing:
      - platform_admin callers → writes to `platform_settings`
      - everyone else          → writes to their org's `org_settings` row
                                 (403 if they have no org_id)

    Null values are ignored (PUT only updates explicitly-set fields).
    """
    from fastapi import HTTPException

    user, _ = await get_current_user(authorization)
    db = get_admin_client()

    noctus_role = (user.user_metadata or {}).get("noctus_role")
    org_role = (user.user_metadata or {}).get("org_role")
    org_id = (user.user_metadata or {}).get("org_id")

    is_platform_admin = noctus_role == "admin"
    can_write_org = org_role in ("owner", "admin")

    if not is_platform_admin and not can_write_org:
        raise HTTPException(status_code=403, detail="Permissão insuficiente")
    if not is_platform_admin and not org_id:
        raise HTTPException(status_code=403, detail="Usuário sem org_id vinculado")

    pairs = [
        (provider, getattr(body, provider))
        for provider in _LLM_PROVIDERS
        if getattr(body, provider) is not None
    ]

    for provider, value in pairs:
        row = {"key": f"{provider}_api_key", "value": value, "is_secret": True}
        if is_platform_admin:
            db.table("platform_settings").upsert(row, on_conflict="key").execute()
        else:
            row["org_id"] = org_id
            db.table("org_settings").upsert(
                row, on_conflict="org_id,key"
            ).execute()

    return {"ok": True, "updated": [p for p, _ in pairs]}
