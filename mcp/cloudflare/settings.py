"""Cloudflare connector MCP settings — API auth config.

Cloudflare's API v4 authenticates with a scoped Bearer token that has
no external store (unlike `mcp/github`'s `gh` keyring), so the token
DOES live here — in the connector's own co-located `.env`
(`mcp/cloudflare/.env`, gitignored), independent of the product/root
`.env` ("every connector owns its own auth store",
`KB § INTEGRATIONS/vista.md § 1`; this is vista's / n8n's / hostinger's
exact shape).

`account_id` is read here too — the Cloudflare Tunnel (cfd_tunnel)
endpoints are **account-scoped** (`/accounts/{account_id}/cfd_tunnel`),
so the tunnel tools need it. It is NOT a secret (it's the public account
identifier from `accounts.list`), but it co-locates with the token for
operational simplicity. Tools that need it but lack it surface a typed
never-faked error rather than building a malformed path.

Unlike vista/n8n there is no per-tenant `base_url` — Cloudflare is a
single public API host — but `base_url` is kept off `env_map` with a
canonical default so tests can override it. `timeout_seconds` is
likewise kept off `env_map` so it keeps its dataclass default (vista's
exact rule — every `env_map` field is passed on every build, `None`
when unset).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, make_get_settings

from .api import DEFAULT_BASE_URL, normalize_base_url


@dataclass(frozen=True)
class CloudflareConnectorSettings(ConnectorSettings):
    """Frozen API config (a tool handler can't corrupt server state).

    - `api_token`  — Cloudflare API v4 scoped token (`Authorization:
      Bearer <token>`). Secret.
    - `account_id` — Cloudflare account id; needed for the account-scoped
      tunnel endpoints. NOT a secret (the public account identifier).
    - `base_url`   — API host; defaults to the canonical Cloudflare v4
      base. Off `env_map` (a single public API) but overridable in code
      for tests.
    - `timeout_seconds` — HTTP timeout; pure default (off `env_map`).
    """

    api_token: Optional[str] = None
    account_id: Optional[str] = None
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 20.0

    @property
    def root(self) -> str:
        """The normalized API base (canonical default when unset)."""
        return normalize_base_url(self.base_url or "")

    @property
    def configured(self) -> bool:
        """True iff the API token is present. Reachability / auth validity
        is a separate runtime check
        (`cloudflare.diagnostics.connection_status`). `account_id` is not
        part of configured-ness — zone/DNS tools work without it; only the
        account-scoped tunnel tools require it (they surface a typed error
        when it is missing)."""
        return bool(self.api_token)


# Env wins over the co-located `.env`; process-cached. `base_url` +
# `timeout_seconds` intentionally omitted from `env_map` so they keep
# their dataclass defaults (vista's exact rule — see module docstring).
get_settings = make_get_settings(
    CloudflareConnectorSettings,
    dotenv_dir=Path(__file__).resolve().parent,
    env_map={
        "api_token": "CLOUDFLARE_API_TOKEN",
        "account_id": "CLOUDFLARE_ACCOUNT_ID",
    },
)


__all__ = ["CloudflareConnectorSettings", "get_settings"]
