"""n8n connector MCP settings — per-tenant API config.

Unlike `mcp/github` (where `gh auth` owns the secret in a keyring),
n8n's public API authenticates with a bearer-style API key that has no
external store, so the key DOES live here — in the connector's own
co-located `.env` (`mcp/n8n/.env`, gitignored), independent of the
product/root `.env` ("every connector owns its own auth store",
`KB § INTEGRATIONS/vista.md § 1`; this is vista's exact base_url+api_key
shape).

The dotenv + env-precedence machinery lives in `_kit.settings`; this
module just declares the frozen carrier + the env map. `timeout_seconds`
is kept off `env_map` so it keeps its dataclass default (vista's exact
rule — every `env_map` field is passed on every build, `None` when
unset).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, make_get_settings

from .api import normalize_base_url


@dataclass(frozen=True)
class N8nConnectorSettings(ConnectorSettings):
    """Frozen per-tenant config (a tool handler can't corrupt server state).

    - `base_url` — instance root (`https://n8n.example.com`) or an
      already-`/api/v1`-suffixed URL; both normalize identically.
    - `api_key`  — n8n public-API key (header `X-N8N-API-KEY`). Secret.
    - `timeout_seconds` — HTTP timeout; pure default (off `env_map`).
    """

    base_url: Optional[str] = None
    api_key: Optional[str] = None
    timeout_seconds: float = 20.0

    @property
    def api_root(self) -> str:
        """The normalized `…/api/v1` root (empty when unset)."""
        return normalize_base_url(self.base_url or "")

    @property
    def configured(self) -> bool:
        """True iff both base_url + api_key are present. Reachability /
        auth validity is a separate runtime check
        (`n8n.diagnostics.connection_status`)."""
        return bool(self.base_url) and bool(self.api_key)


# Env wins over the co-located `.env`; process-cached. `timeout_seconds`
# intentionally omitted from `env_map` so it keeps its dataclass default
# (vista's exact rule — see module docstring).
get_settings = make_get_settings(
    N8nConnectorSettings,
    dotenv_dir=Path(__file__).resolve().parent,
    env_map={
        "base_url": "N8N_BASE_URL",
        "api_key": "N8N_API_KEY",
    },
)


__all__ = ["N8nConnectorSettings", "get_settings"]
