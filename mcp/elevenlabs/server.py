"""ElevenLabs connector MCP server — stdio entry point.

Run:  python mcp/elevenlabs/server.py

Config from env or `mcp/elevenlabs/.env` (see settings.py). Boots cleanly
with no key — tools then return a typed 424 (never faked).

Tools: elevenlabs.user.usage · elevenlabs.model.list · elevenlabs.voice.{list,get}
(READ) · elevenlabs.tts.synthesize · elevenlabs.voice.clone_instant ·
elevenlabs.voice.delete (WRITE, confirm-gated 412).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# `mcp/` on sys.path BEFORE the first `_kit`/`elevenlabs` import: ours must win
# over the PyPI `elevenlabs` SDK / `mcp` packages (same trick as mcp/waha).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, run_stdio_server

logger = configure_stderr_logging("elevenlabs-mcp")

from elevenlabs.tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("elevenlabs", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
