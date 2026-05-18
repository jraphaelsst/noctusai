"""Meta connector MCP server — stdio entry point.

Run:
    python mcp/meta/server.py

Reads its per-tenant config from env or `mcp/meta/.env` (see
settings.py). The seed factory deferred-config rule means the server
starts cleanly with no creds — `meta.whatsapp.*` tools then run against
`FakeWahaClient` and still answer deterministically.

Tool surface:
- meta.whatsapp.send_text          — outbound, confirm-gated (412 if unconfirmed)
- meta.whatsapp.parse_inbound      — pure WAHA-payload parse
- meta.facebook.list_pages         — Pages the identity manages (read-only)
- meta.facebook.list_page_posts    — posts authored by a Page (read-only)
- meta.facebook.post_insights      — per-post insight metrics (read-only)
- meta.instagram.list_accounts     — IG Business accounts (read-only)
- meta.instagram.list_media        — media for an IG account (read-only)
- meta.instagram.media_insights    — per-media insight metrics (read-only)
- meta.diagnostics.connection_status — adapter introspection (auth_mode)
- meta.diagnostics.discover_scopes — OAuth scope resolution

The Facebook/Instagram/diagnostics leaves wrap
`noctusai_lib.integrations.meta` (present post social-wiring
absorption). READ-ONLY v1 — the seed `MetaAdapter` Protocol has no
write methods (Meta App Review gates the write scopes); no
posting/ads tools are exposed.

The stdio bootstrap (sys.path trick, stderr logging, Server +
list_tools + call_tool + run loop) is shared across every connector MCP
in `_kit.bootstrap` — this module just composes it.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from meta.X import ...` AND `from _kit.X
# import ...` resolve cleanly. The PyPI `mcp` package shadows our `mcp/`
# dir as a namespace, so we import this connector package as top-level
# `meta` and the shared kit as top-level `_kit` — same trick as
# `mcp/vista/server.py`. This bare insert MUST precede the first
# `_kit` / `meta` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, run_stdio_server

# Route logs to stderr — stdio MCP uses stdout for JSON-RPC.
logger = configure_stderr_logging("meta-mcp")

from meta.tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("meta", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
