"""NoctusAI MCP Server — platform dev toolkit.

Builds a ``FastMCP`` instance, registers every tool under
``mcp/noctusai/tools/``, and runs over stdio.

Run: ``python mcp/noctusai/server.py`` (or ``python -m mcp.noctusai.server``).

Switch to HTTP/SSE transport later by replacing ``server.run("stdio")``
with the appropriate FastMCP transport call — no tool code changes needed.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Configure platform-standard logging BEFORE importing any tools/* module.
# MCP server uses stdio: stdout is the JSON-RPC channel and any non-JSON
# byte corrupts it, so we route logs to stderr via `use_stderr=True`.
try:
    from noctusai_lib.logging_config import auto_configure_for_cli
    auto_configure_for_cli("noctusai-mcp-server", use_stderr=True)
except ImportError as exc:
    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stderr,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logging.getLogger(__name__).warning(
        "server: noctusai_lib not installed (%s); using basicConfig fallback. "
        "Run `pip install -e seed/backend/lib` from the repo root to fix.",
        exc,
    )

from mcp.server.fastmcp import FastMCP

from tools import register_all


def build_server() -> FastMCP:
    server = FastMCP(
        name="noctusai",
        instructions=(
            "NoctusAI platform dev toolkit. Tools are namespaced "
            "<vendor_or_namespace>.<service>.<action> (e.g. `noctus.dev.validate`, "
            "`noctus.dev.review`). Legacy flat names (`noctusai_<action>`) are "
            "registered as aliases until consumers migrate. Call "
            "`noctusai_agent_context` first when starting a fresh session."
        ),
    )
    register_all(server)
    return server


def run() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    run()
