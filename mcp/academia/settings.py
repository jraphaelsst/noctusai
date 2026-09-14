"""academia MCP settings — per-tenant configuration.

Per CONTRACT §B.0 / §C build step 1: the connector reads
`ACADEMIA_API_URL` + `ACADEMIA_API_TOKEN` from its own secrets store
(never this repo's `.env`), mirroring vista's "MCP reads its own
secrets store" design principle. The token is a personal `pk_` token
minted with `human_personal=true` (CONTRACT §B.0), or a product token
minted for the `agents` control plane.

Resolution order (the dotenv + env precedence machinery lives in
`_kit.settings`):
  1. Explicit constructor args to `AcademiaSettings(...)`
  2. Environment variables `ACADEMIA_API_URL` + `ACADEMIA_API_TOKEN`
  3. `.env` file in the same directory (dev convenience)

Both fields are optional at __init__ time (lenient construction — the
"not configured" state is a first-class, never-faked signal every tool
returns as `{"ok": false, "error": {"status": 0, "code":
"not_configured", ...}}`; the connector never crashes at import and
never falls back to a default URL)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, make_get_settings


@dataclass(frozen=True)
class AcademiaSettings(ConnectorSettings):
    """academia-de-reciclagem per-tenant config carrier.

    Frozen so accidental mutation in tool handlers can't corrupt server
    state."""

    api_url: Optional[str] = None
    api_token: Optional[str] = None
    timeout_seconds: float = 30.0

    @property
    def configured(self) -> bool:
        return bool(self.api_url) and bool(self.api_token)


# Env wins over the co-located .env; cached for the process. Call
# `get_settings.cache_clear()` to re-read after process start (rare —
# the MCP server is long-lived). `timeout_seconds` keeps its dataclass
# default (not env-mapped, matching vista's original).
get_settings = make_get_settings(
    AcademiaSettings,
    dotenv_dir=Path(__file__).resolve().parent,
    env_map={"api_url": "ACADEMIA_API_URL", "api_token": "ACADEMIA_API_TOKEN"},
)


__all__ = ["AcademiaSettings", "get_settings"]
