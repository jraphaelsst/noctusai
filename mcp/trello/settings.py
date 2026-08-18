"""Trello connector settings — `key` + `token` query-param auth.

Trello's OpenAPI spec (`components.securitySchemes`, vendored at
`contract/swagger.v3.json`) declares BOTH `APIKey` and `APIToken` as
`type: apiKey, in: query` — unlike every other connector in this repo,
Trello authenticates via QUERY PARAMS (`?key=...&token=...`), never a
header. `client.py` is where that gets applied on every request.

Secrets live in this connector's own gitignored `mcp/trello/.env` —
every connector owns its auth store rather than inheriting the repo
`.env` (`KB § INTEGRATIONS/vista.md § 1`).

This connector is deliberately NOT backed by a `noctusai_lib.integrations`
seed adapter (see `mcp/trello/README.md` § Architecture) — no product
consumes Trello today, and a seed IO module would have to ship Fake+Real+
factory for a consumer that does not exist. The HTTP mechanics live in
`client.py`/`api.py`, composing `_kit.transport` directly, the same shape
`mcp/waha` and `mcp/hostinger` use.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, make_get_settings

#: Trello's fixed public API host. Not per-tenant — kept as a dataclass
#: default (off `env_map`) so tests / a future API-version bump can
#: override it without touching the environment.
DEFAULT_BASE_URL = "https://api.trello.com/1"


@dataclass(frozen=True)
class TrelloConnectorSettings(ConnectorSettings):
    """Frozen API config (a tool handler can't corrupt server state).

    - `api_key` / `token` — sent as `?key=...&token=...` on every
      authenticated call. Secret.
    - `base_url` / `timeout_seconds` — pure defaults, off `env_map`.
    """

    api_key: Optional[str] = None
    token: Optional[str] = None
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 20.0

    @property
    def configured(self) -> bool:
        """Both halves are required — Trello rejects a request carrying
        only one of `key`/`token`. Reachability / credential VALIDITY is
        a separate live question (`trello.diagnostics.probe`)."""
        return bool(self.api_key) and bool(self.token)


get_settings = make_get_settings(
    TrelloConnectorSettings,
    dotenv_dir=Path(__file__).resolve().parent,
    env_map={
        "api_key": "TRELLO_API_KEY",
        "token": "TRELLO_TOKEN",
    },
)


__all__ = ["DEFAULT_BASE_URL", "TrelloConnectorSettings", "get_settings"]
