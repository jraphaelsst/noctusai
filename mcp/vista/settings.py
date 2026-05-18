"""Vista MCP settings — per-tenant configuration.

Per `KB § INTEGRATIONS/vista.md` § 1 (Authentication) and PROJECT.md §3
Design Principle #5 ("The MCP server reads its per-tenant
`VISTA_BASE_URL` + `VISTA_API_KEY` from its own secrets store; never
inherits from this repo's `.env`"), this module owns Vista's auth
config independently of the showcase adapter.

Resolution order (the dotenv + env precedence machinery now lives in
`_kit.settings` — vista composes it, identical behavior):
  1. Explicit constructor args to `VistaSettings(...)`
  2. Environment variables `VISTA_BASE_URL` + `VISTA_API_KEY`
  3. `.env` file in the same directory (dev convenience)

Both fields are optional at __init__ time (lenient construction —
the underlying VistaClient defers config-missing errors to request
time, per the FastAPI dep-factory pattern noted in vista.md §1).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, make_get_settings


@dataclass(frozen=True)
class VistaSettings(ConnectorSettings):
    """Vista per-tenant config carrier.

    Frozen so accidental mutation in tool handlers can't corrupt server
    state. To switch tenants at runtime, construct a new VistaSettings
    and pass it into the client/calibration explicitly.
    """

    base_url: Optional[str] = None
    api_key: Optional[str] = None
    timeout_seconds: float = 15.0

    @property
    def configured(self) -> bool:
        return bool(self.base_url) and bool(self.api_key)


# Env wins over the co-located .env; cached for the process. Call
# `get_settings.cache_clear()` to re-read after process start (rare —
# the MCP server is long-lived). `timeout_seconds` keeps its dataclass
# default (not env-mapped — vista's original never read it from env).
get_settings = make_get_settings(
    VistaSettings,
    dotenv_dir=Path(__file__).resolve().parent,
    env_map={"base_url": "VISTA_BASE_URL", "api_key": "VISTA_API_KEY"},
)


__all__ = ["VistaSettings", "get_settings"]
