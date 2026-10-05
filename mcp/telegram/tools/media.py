"""`telegram.media.download` — media bytes for explicit message ids only.

Writes large files to disk, so it is confirm-gated (typed 412 before any
Telegram call). Refuses a destination inside the session directory.
"""
from __future__ import annotations

from pathlib import Path

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import client
from ..settings import SESSION_DIR
from ..types import MediaDownloadInput
from ._run import run_with_gateway


async def media_download(args: dict) -> dict:
    inp = MediaDownloadInput(**args)
    if not inp.confirm:
        return {
            "downloaded": False,
            "error": typed_error(client.ConfirmationRequiredError(
                "telegram.media.download",
                f"downloads media of {len(inp.message_ids)} message(s) to {inp.out_dir}",
            )),
        }
    out = Path(inp.out_dir).expanduser().resolve()
    if out == SESSION_DIR.resolve() or SESSION_DIR.resolve() in out.parents:
        return {"downloaded": False, "error": typed_error(client.TelegramApiError(
            "out_dir may not be inside the session directory.", status=422))}
    out.mkdir(parents=True, exist_ok=True)

    async def _go(gw):
        files = await gw.download_media(inp.chat, inp.message_ids, str(out))
        return {"downloaded": True, "files": files}

    return await run_with_gateway(_go, downloaded=False)


HANDLERS = {"telegram.media.download": media_download}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(name="telegram.media.download",
             description="Download media for explicit message_ids (max 20) into out_dir. WRITE "
             "(writes files to disk) — confirm-gated: typed 412 without confirm=true.",
             inputSchema=MediaDownloadInput.model_json_schema()),
    ]


__all__ = ["HANDLERS", "register", "tool_descriptors"]
