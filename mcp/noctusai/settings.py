"""Settings shim for the MCP server.

For now the server reuses ``noctusai_lib.config.settings.BaseAppSettings``
so we keep a single ``.env`` source of truth across the repo. When this
MCP is extracted to its own NoctusAI repo, this module gets its own
``Settings`` class and the platform becomes one of N consumers reading
its own ``.env``.
"""

from __future__ import annotations

from functools import lru_cache

from noctusai_lib.config.settings import BaseAppSettings


Settings = BaseAppSettings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


__all__ = ["Settings", "get_settings"]
