"""Meta connector MCP settings — per-tenant configuration.

Owns the Meta-family auth/config independently of any consuming
product's `.env` (same isolation rule vista follows — `KB §
INTEGRATIONS/vista.md` § 1 generalized). The dotenv + env precedence
machinery lives in `_kit.settings`; this module just declares the
frozen carrier + the env map.

Resolution order per field (machinery in `_kit.settings`):
  1. Environment variable
  2. Co-located `mcp/meta/.env`
  3. Dataclass default (fields NOT listed in `env_map`)

All fields optional at __init__ time — lenient construction so the
server boots with no creds; the seed factories (`get_whatsapp_client`)
then return a Fake and tools still answer (deferred-config rule).

Field provenance (per the Wave-2 brief):
- `meta_system_user_token` / `meta_app_id` / `meta_app_secret` are read
  and carried for the Facebook/Instagram/diagnostics surface. That
  surface is NOT shipped this wave (the `noctusai_lib.integrations.meta`
  Graph-API package does not exist — see `mcp/meta/README.md`); the
  fields are declared now so the env contract is stable for Wave 3+.
- `waha_base_url` / `waha_api_key` back the SHIPPED `meta.whatsapp.*`
  tools via `noctusai_lib.integrations.whatsapp.get_whatsapp_client`.
- `waha_external_base_url` is carried for tunnel/webhook URL emission.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, make_get_settings


@dataclass(frozen=True)
class MetaConnectorSettings(ConnectorSettings):
    """Meta-family per-tenant config carrier.

    Frozen so a tool handler can't accidentally corrupt server state.
    To switch tenants at runtime, build a new instance and pass it
    explicitly into the relevant seed factory.
    """

    # --- Meta Graph API (Facebook/Instagram/diagnostics — NOT shipped this wave)
    meta_system_user_token: Optional[str] = None
    meta_app_id: Optional[str] = None
    meta_app_secret: Optional[str] = None

    # --- WAHA / WhatsApp (the shipped slice)
    waha_base_url: Optional[str] = None
    waha_api_key: Optional[str] = None
    waha_external_base_url: Optional[str] = None

    @property
    def configured(self) -> bool:
        """True when the WhatsApp slice can talk to a real WAHA server.

        The Graph-API surface has its own (currently dormant) gate; the
        WhatsApp slice is the only shipped surface so `configured`
        tracks it. `get_whatsapp_client` uses presence of `waha_base_url`
        as the real-vs-Fake signal, so this mirrors that exactly.
        """
        return bool(self.waha_base_url)


# Env wins over the co-located `.env`; process-cached. `get_settings.
# cache_clear()` to re-read (rare — the MCP server is long-lived).
get_settings = make_get_settings(
    MetaConnectorSettings,
    dotenv_dir=Path(__file__).resolve().parent,
    env_map={
        "meta_system_user_token": "META_SYSTEM_USER_TOKEN",
        "meta_app_id": "META_APP_ID",
        "meta_app_secret": "META_APP_SECRET",
        "waha_base_url": "WAHA_BASE_URL",
        "waha_api_key": "WAHA_API_KEY",
        "waha_external_base_url": "WAHA_EXTERNAL_BASE_URL",
    },
)


__all__ = ["MetaConnectorSettings", "get_settings"]
