"""Hostinger connector MCP settings — API auth config.

Hostinger's Developers API authenticates with a Bearer token that has
no external store (unlike `mcp/github`'s `gh` keyring), so the token
DOES live here — in the connector's own co-located `.env`
(`mcp/hostinger/.env`, gitignored), independent of the product/root
`.env` ("every connector owns its own auth store",
`KB § INTEGRATIONS/vista.md § 1`; this is vista's / n8n's exact shape).

Unlike vista/n8n there is no per-tenant `base_url` — Hostinger is a
single public API host — but `base_url` is kept off `env_map` with a
canonical default so tests / future regional hosts can override it.
`timeout_seconds` is likewise kept off `env_map` so it keeps its
dataclass default (vista's exact rule — every `env_map` field is passed
on every build, `None` when unset).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, make_get_settings

from .api import DEFAULT_BASE_URL, normalize_base_url


@dataclass(frozen=True)
class HostingerConnectorSettings(ConnectorSettings):
    """Frozen API config (a tool handler can't corrupt server state).

    - `api_token` — Hostinger Developers API token (`Authorization:
      Bearer <token>`). Secret.
    - `base_url`  — API host; defaults to the canonical Hostinger host.
      Off `env_map` (a single public API, not a per-tenant instance) but
      overridable in code for tests / future regional hosts.
    - `timeout_seconds` — HTTP timeout; pure default (off `env_map`).
    """

    api_token: Optional[str] = None
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 20.0

    @property
    def root(self) -> str:
        """The normalized API host (canonical default when unset)."""
        return normalize_base_url(self.base_url or "")

    @property
    def configured(self) -> bool:
        """True iff the API token is present. Reachability / auth validity
        is a separate runtime check
        (`hostinger.diagnostics.connection_status`)."""
        return bool(self.api_token)


# Env wins over the co-located `.env`; process-cached. `base_url` +
# `timeout_seconds` intentionally omitted from `env_map` so they keep
# their dataclass defaults (vista's exact rule — see module docstring).
get_settings = make_get_settings(
    HostingerConnectorSettings,
    dotenv_dir=Path(__file__).resolve().parent,
    env_map={
        "api_token": "HOSTINGER_API_TOKEN",
    },
)


__all__ = ["HostingerConnectorSettings", "get_settings"]
