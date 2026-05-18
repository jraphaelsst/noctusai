"""Google connector MCP server — stdio entry point.

Run:
    python mcp/google/server.py

Reads GOOGLE_API_KEY / GOOGLE_MAPS_API_KEY / GOOGLE_OAUTH_CLIENT_ID /
GOOGLE_OAUTH_CLIENT_SECRET / GOOGLE_OAUTH_REFRESH_TOKEN from env or
`mcp/google/.env`. The deferred-config rule (settings.py) means the
server starts cleanly with NO creds — read tools then resolve against
the seed-lib Fakes, OAuth-only write tools return a typed error.

The stdio bootstrap (sys.path trick, stderr logging, the Server +
list_tools + call_tool + run loop) is shared across every connector MCP
in `_kit.bootstrap` — this module just composes it.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Two sys.path inserts (order matters), both BEFORE the first import:
#
# 1. `mcp/`        — so `from _kit.X import ...` resolves (the shared
#    connector kit). The PyPI `mcp` package shadows our `mcp/` dir as a
#    namespace; importing `_kit` as a top-level package sidesteps that
#    (same trick as mcp/vista/server.py).
# 2. `mcp/google/` — so the connector's own `tools` / `settings` /
#    `types` resolve as TOP-LEVEL modules. Unlike vista, the package
#    name `google` collides with the PyPI `google.*` namespace package
#    (shipped by google-api-python-client / google-auth), so this
#    connector imports its modules flat (mcp/noctusai uses the same
#    self-dir-on-path strategy) rather than as a `google.` package.
_HERE = Path(__file__).resolve()

# 3. `seed/lib/backend` — resolve `noctusai_lib` from the seed IN THIS
#    TREE. A repo-wide editable install registers a `_EditableFinder`
#    MetaPathFinder that hard-pins `noctusai_lib` to whatever worktree it
#    was last installed from (possibly a *different*, now-stale
#    `agent-*` tree). `sys.meta_path` is consulted BEFORE `sys.path`, so
#    a plain insert can't override it — evict any editable finder whose
#    pinned path is OUTSIDE this tree + drop stale cached modules, then
#    prepend the in-tree seed. Pure import wiring (same category as the
#    `google`-namespace flat-import trick); touches no product code.
_SEED_BACKEND = str(_HERE.parents[2] / "seed" / "lib" / "backend")
for _finder in list(sys.meta_path):
    _m = getattr(_finder, "_mapping", None) or getattr(_finder, "MAPPING", None)
    if not isinstance(_m, dict):
        continue
    _p = _m.get("noctusai_lib")
    _ps = _p if isinstance(_p, str) else (
        _p[0] if isinstance(_p, (list, tuple)) and _p else None
    )
    if _ps and _SEED_BACKEND not in str(_ps):
        sys.meta_path.remove(_finder)
for _name in list(sys.modules):
    if _name == "noctusai_lib" or _name.startswith("noctusai_lib."):
        del sys.modules[_name]
sys.path.insert(0, _SEED_BACKEND)
sys.path.insert(0, str(_HERE.parents[1]))   # mcp/   → _kit
sys.path.insert(0, str(_HERE.parent))       # mcp/google/ → tools/settings/types

from _kit.bootstrap import configure_stderr_logging, run_stdio_server

# Route logs to stderr — stdio MCP uses stdout for JSON-RPC.
logger = configure_stderr_logging("google-mcp")

from tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("google", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
