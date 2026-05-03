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


# accept-with-rationale: "MCP settings shim ships its own local
# get_settings() factory (not in noctusai_lib)" in
# KB § PATTERNS/accept-with-rationale.md — lib intentionally exposes
# only the BaseAppSettings shape; per-product Settings is the documented
# pattern. MCP-scoped factory is the right granularity. Revisit when a
# 2nd non-product process needs the same singleton.
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


__all__ = ["Settings", "get_settings"]
