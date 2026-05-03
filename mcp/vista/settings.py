"""Vista MCP settings — per-tenant configuration.

Per `KB § INTEGRATIONS/vista.md` § 1 (Authentication) and PROJECT.md §3
Design Principle #5 ("The MCP server reads its per-tenant
`VISTA_BASE_URL` + `VISTA_API_KEY` from its own secrets store; never
inherits from this repo's `.env`"), this module owns Vista's auth
config independently of the showcase adapter.

Resolution order:
  1. Explicit constructor args to `VistaSettings(...)`
  2. Environment variables `VISTA_BASE_URL` + `VISTA_API_KEY`
  3. `.env` file in the same directory (dev convenience)

Both fields are optional at __init__ time (lenient construction —
the underlying VistaClient defers config-missing errors to request
time, per the FastAPI dep-factory pattern noted in vista.md §1).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional


def _load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


@dataclass(frozen=True)
class VistaSettings:
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


@lru_cache(maxsize=1)
def get_settings() -> VistaSettings:
    """Build VistaSettings from env + co-located .env (cached for the process).

    Env vars win over the dotfile. Call `get_settings.cache_clear()` if
    you need to re-read after process start (rare — the MCP server is
    long-lived).
    """
    here = Path(__file__).resolve().parent
    dot = _load_dotenv(here / ".env")
    return VistaSettings(
        base_url=os.environ.get("VISTA_BASE_URL") or dot.get("VISTA_BASE_URL"),
        api_key=os.environ.get("VISTA_API_KEY") or dot.get("VISTA_API_KEY"),
    )


__all__ = ["VistaSettings", "get_settings"]
