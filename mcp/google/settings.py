"""Google connector MCP settings — per-tenant Google API config.

Composes `_kit.settings` exactly like `mcp/vista/settings.py`. The
Google connector owns its own credential set independently of this
repo's product `.env` (the "MCP reads its own secrets store" design
principle, `KB § INTEGRATIONS/vista.md § 1` — generalized across every
connector by `_kit`).

Resolution order (machinery in `_kit.settings`, identical to vista):
  1. Explicit constructor args to `GoogleConnectorSettings(...)`
  2. Environment variables
  3. A co-located `mcp/google/.env` file (dev convenience) — env wins

Five fields, each optional at __init__ (lenient construction — the
deferred-config rule means the server starts cleanly with no creds and
tool calls then resolve against the lib Fakes / return a typed error):

- `api_key`              `GOOGLE_API_KEY`               — Drive read-only public + YouTube read.
- `maps_api_key`         `GOOGLE_MAPS_API_KEY`          — Routes API v2 (travel estimates).
- `oauth_client_id`      `GOOGLE_OAUTH_CLIENT_ID`       — OAuth client (Calendar write, YouTube upload).
- `oauth_client_secret`  `GOOGLE_OAUTH_CLIENT_SECRET`   — OAuth client secret.
- `oauth_refresh_token`  `GOOGLE_OAUTH_REFRESH_TOKEN`   — long-lived user-delegated refresh token.

`configured` is intentionally coarse (any creds present) — each tool
checks the *specific* slice of config it needs and degrades to the lib
Fake (read tools) or returns a typed error (OAuth-only write tools).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, make_get_settings


@dataclass(frozen=True)
class GoogleConnectorSettings(ConnectorSettings):
    """Google connector per-tenant config carrier.

    Frozen so a tool handler cannot corrupt shared server state by
    mutating config. To switch tenants at runtime, construct a fresh
    instance and pass it explicitly.
    """

    api_key: Optional[str] = None
    maps_api_key: Optional[str] = None
    oauth_client_id: Optional[str] = None
    oauth_client_secret: Optional[str] = None
    oauth_refresh_token: Optional[str] = None

    @property
    def configured(self) -> bool:
        """Coarse "anything configured" probe. Individual tools test
        the specific slice they need (`oauth_configured`,
        `maps_api_key`, `api_key`)."""
        return bool(
            self.api_key
            or self.maps_api_key
            or self.oauth_configured
        )

    @property
    def oauth_configured(self) -> bool:
        """The OAuth user-delegated trio — required for Calendar writes
        and YouTube upload. All three must be present."""
        return bool(
            self.oauth_client_id
            and self.oauth_client_secret
            and self.oauth_refresh_token
        )


# Env wins over the co-located .env; cached for the process. Call
# `get_settings.cache_clear()` to re-read after process start (rare —
# the MCP server is long-lived).
get_settings = make_get_settings(
    GoogleConnectorSettings,
    dotenv_dir=Path(__file__).resolve().parent,
    env_map={
        "api_key": "GOOGLE_API_KEY",
        "maps_api_key": "GOOGLE_MAPS_API_KEY",
        "oauth_client_id": "GOOGLE_OAUTH_CLIENT_ID",
        "oauth_client_secret": "GOOGLE_OAUTH_CLIENT_SECRET",
        "oauth_refresh_token": "GOOGLE_OAUTH_REFRESH_TOKEN",
    },
)


__all__ = ["GoogleConnectorSettings", "get_settings"]
