"""OpenAI connector MCP server — stdio entry point.

Run:
    python mcp/openai/server.py

Reads `OPENAI_API_KEY` from env or `mcp/openai/.env`. Composes the shared
`_kit` bootstrap (same as github / vista / meta / google connectors): the
stdio sys.path trick, in-tree seed pin, stderr logging, Server + list_tools
+ call_tool + run loop.

Tool surface:
- openai.embed                          — text → vector (text-embedding-3-small)
- openai.chat                           — text → text (gpt-4o-mini)
- openai.vision                         — image + question → text (gpt-4o)
- openai.transcribe                     — audio file → text (whisper-1)
- openai.search.kb                      — semantic search over the KB
- openai.search.code                    — semantic search over the codebase
- openai.diagnostics.connection_status  — never-faked READY/UNCONFIGURED signal

Why this server exists: the noctusai MCP exposes embeddings as `noctus.dev.
kb_search` etc, but the underlying OpenAI capabilities (chat, vision,
transcription, image generation) had no MCP surface — agents couldn't send
audio to transcribe or images to analyze. This connector closes that gap.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from openai_mcp.X import ...` AND `from _kit.X
# import ...` resolve cleanly. The PyPI `mcp` package shadows our `mcp/`
# dir as a namespace, so we import this connector package as top-level
# `openai_mcp` and the shared kit as top-level `_kit` — same trick as
# `mcp/github/server.py`. This bare insert MUST precede the first
# `_kit` / `openai_mcp` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, run_stdio_server

# Route logs to stderr — stdio MCP uses stdout for JSON-RPC.
logger = configure_stderr_logging("openai-mcp")

from openai_mcp.tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("openai", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
