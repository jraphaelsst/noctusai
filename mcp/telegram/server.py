"""Telegram connector MCP server — stdio entry point.

Run:
    mcp/noctusai/.venv/bin/python mcp/telegram/server.py

Telegram user-account client over MTProto (Telethon). Config from env or
`mcp/telegram/.env`; the login session is created once, interactively, by
`mcp/telegram/login.py` (MCP tools never accept codes or passwords).
Starts cleanly with no config; credentialed tools return a typed 424.

Tools (8): telegram.diagnostics.{connection_status,me} · telegram.dialogs.list
· telegram.messages.{list,search,export} · telegram.media.download (confirm)
· telegram.messages.send (confirm).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Bare insert FIRST: PyPI `mcp` shadows our `mcp/` dir (see _kit/README.md).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, prepare_sys_path, run_stdio_server

prepare_sys_path(__file__)

logger = configure_stderr_logging("telegram-mcp")

from telegram.tools import all_descriptors, all_handlers

_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()


async def _main():
    await run_stdio_server("telegram", _DESCRIPTORS, _HANDLERS, logger)


if __name__ == "__main__":
    asyncio.run(_main())
