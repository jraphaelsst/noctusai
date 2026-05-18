"""Connector-MCP shared settings base.

Generalized from `mcp/vista/settings.py`. Every connector MCP owns its
per-tenant auth config independently of this repo's product `.env` (the
"MCP reads its own secrets store" design principle, `KB § INTEGRATIONS/
vista.md § 1`).

Resolution order, identical to vista's original:
  1. Explicit constructor args to the settings subclass
  2. Environment variables
  3. A co-located `.env` file (dev convenience) — env wins over the dotfile

`_load_dotenv` is moved here **verbatim-equivalent** to vista's original
(same parse: skip blank / `#`-comment / no-`=` lines; strip surrounding
quotes). Subclasses stay frozen dataclasses so a tool handler cannot
corrupt server state by mutating shared config.

A connector defines its own frozen dataclass extending `ConnectorSettings`
plus a cached factory built with `make_get_settings(...)`:

    @dataclass(frozen=True)
    class VistaSettings(ConnectorSettings):
        base_url: Optional[str] = None
        api_key: Optional[str] = None
        timeout_seconds: float = 15.0

        @property
        def configured(self) -> bool:
            return bool(self.base_url) and bool(self.api_key)

    get_settings = make_get_settings(
        VistaSettings,
        dotenv_dir=Path(__file__).resolve().parent,
        env_map={"base_url": "VISTA_BASE_URL", "api_key": "VISTA_API_KEY"},
    )
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Mapping, Type, TypeVar


def _load_dotenv(path: Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE `.env` file. Verbatim-equivalent to the
    original `mcp/vista/settings.py._load_dotenv` — do not "improve" the
    parse without re-baselining every connector's settings test."""
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
class ConnectorSettings:
    """Marker base for per-connector frozen-dataclass settings carriers.

    Holds no fields itself — vendor settings differ (base_url/api_key for
    vista; OAuth token chains for Meta/Google). It exists so `isinstance`
    / typing can talk about "a connector settings object" and so the
    shared dotenv + cached-factory machinery has a single bound.
    """


S = TypeVar("S", bound=ConnectorSettings)


def make_get_settings(
    settings_cls: Type[S],
    *,
    dotenv_dir: Path,
    env_map: Mapping[str, str],
) -> Callable[[], S]:
    """Build a process-cached `get_settings()` for a connector.

    - `settings_cls`  — the connector's frozen `ConnectorSettings` subclass.
    - `dotenv_dir`    — directory holding the co-located `.env` (the
                        connector passes `Path(__file__).resolve().parent`).
    - `env_map`       — {settings_kwarg: ENV_VAR_NAME}. For each pair the
                        value is `os.environ.get(ENV) or dotenv.get(ENV)`
                        (env wins over the dotfile — vista's exact rule).

    Returns an `lru_cache(maxsize=1)`-wrapped callable mirroring vista's
    original `get_settings`; `.cache_clear()` re-reads after process start.
    """

    @lru_cache(maxsize=1)
    def get_settings() -> S:
        dot = _load_dotenv(dotenv_dir / ".env")
        kwargs = {
            kwarg: (os.environ.get(env_name) or dot.get(env_name))
            for kwarg, env_name in env_map.items()
        }
        return settings_cls(**kwargs)

    return get_settings


__all__ = ["ConnectorSettings", "make_get_settings", "_load_dotenv"]
