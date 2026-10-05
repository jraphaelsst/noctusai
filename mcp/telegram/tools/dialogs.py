"""`telegram.dialogs.list` — chats the account is in. READ."""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from ..types import DialogsListInput
from ._run import run_with_gateway


async def dialogs_list(args: dict) -> dict:
    inp = DialogsListInput(**args)

    async def _go(gw):
        rows = await gw.list_dialogs(limit=inp.limit, query=inp.query)
        return {"dialogs": rows, "count": len(rows)}

    return await run_with_gateway(_go, dialogs=[], count=0)


HANDLERS = {"telegram.dialogs.list": dialogs_list}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="telegram.dialogs.list",
            description="List dialogs (id, title, type user/group/channel, unread, "
            "username), optional title filter. READ.",
            inputSchema=DialogsListInput.model_json_schema(),
        ),
    ]


__all__ = ["HANDLERS", "register", "tool_descriptors"]
