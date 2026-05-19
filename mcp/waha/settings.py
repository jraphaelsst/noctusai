"""WAHA connector MCP settings — per-tenant API config.

Same base_url+api_key shape as `mcp/n8n` / `mcp/vista`. WAHA's
`X-Api-Key` has no external store, so the key lives in the connector's
own co-located `.env` (`mcp/waha/.env`, gitignored), independent of the
product/root `.env` ("every connector owns its own auth store",
`KB § INTEGRATIONS/vista.md § 1`).

`default_session` (the WAHA session name, almost always `"default"`)
and `timeout_seconds` are kept off `env_map` so they keep their
dataclass defaults — vista's exact rule (every `env_map` field is
passed on every build, `None` when unset).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, make_get_settings

from .api import normalize_base_url


@dataclass(frozen=True)
class WahaConnectorSettings(ConnectorSettings):
    """Frozen per-tenant config (a tool handler can't corrupt server state).

    - `base_url` — WAHA instance root (`https://waha.example.com`).
    - `api_key`  — WAHA `X-Api-Key`. Secret.
    - `default_session` — session name when a tool omits it (`"default"`).
    - `timeout_seconds` — HTTP timeout; pure default (off `env_map`).
    """

    base_url: Optional[str] = None
    api_key: Optional[str] = None
    default_session: str = "default"
    timeout_seconds: float = 20.0

    @property
    def root(self) -> str:
        """The normalized instance root (empty when unset)."""
        return normalize_base_url(self.base_url or "")

    @property
    def configured(self) -> bool:
        """True iff both base_url + api_key are present. Reachability /
        auth validity is a separate runtime check
        (`waha.diagnostics.connection_status`)."""
        return bool(self.base_url) and bool(self.api_key)


# Env wins over the co-located `.env`; process-cached. `default_session`
# + `timeout_seconds` intentionally omitted from `env_map` so they keep
# their dataclass defaults (vista's exact rule — see module docstring).
get_settings = make_get_settings(
    WahaConnectorSettings,
    dotenv_dir=Path(__file__).resolve().parent,
    env_map={
        "base_url": "WAHA_BASE_URL",
        "api_key": "WAHA_API_KEY",
    },
)


__all__ = ["WahaConnectorSettings", "get_settings"]
