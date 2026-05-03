"""Settings shim for the MCP server.

For now the server reuses ``noctusai_lib.config.settings.BaseAppSettings``
so we keep a single ``.env`` source of truth across the repo. When this
MCP is extracted to its own NoctusAI repo, this module gets its own
``Settings`` class and the platform becomes one of N consumers reading
its own ``.env``.

Path constants — ``REPO_ROOT`` and ``PRODUCTS_DIR`` — also live here so
every tool module imports the same depth-independent definition.
Previously each module computed its own
``Path(__file__).resolve().parents[N]``, which broke when files moved
between directory levels (mcp-server-fastmcp-switch Phase 3 had to bump
18 modules from ``parents[3]`` to ``parents[5]``). The constants here
delegate to ``workspace.get_noctusai_home()`` — the canonical
marker-file-based resolver in ``mcp/noctusai/workspace.py`` — which
already handles primary-vs-seed-workspace resolution correctly. Any
module that needs the noc repo path imports ``REPO_ROOT`` from here
instead of computing its own.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from noctusai_lib.config.settings import BaseAppSettings

from workspace import get_noctusai_home


Settings = BaseAppSettings

REPO_ROOT: Path = get_noctusai_home()
PRODUCTS_DIR: Path = REPO_ROOT / "products"


# accept-with-rationale: "MCP settings shim ships its own local
# get_settings() factory (not in noctusai_lib)" in
# KB § PATTERNS/accept-with-rationale.md — lib intentionally exposes
# only the BaseAppSettings shape; per-product Settings is the documented
# pattern. MCP-scoped factory is the right granularity. Revisit when a
# 2nd non-product process needs the same singleton.
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


__all__ = ["Settings", "get_settings", "REPO_ROOT", "PRODUCTS_DIR"]
