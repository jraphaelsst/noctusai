"""`trello.boards.*` — live READ. One network call per tool, through the
`client.get_client()` DI seam. Unconfigured ⇒ typed 424, never faked.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api, client
from ..types import BoardsListInput, BoardsListOutput


async def boards_list(args: dict) -> dict:
    inp = BoardsListInput(**args)
    try:
        data = client.get_client().get_member_boards(inp.member_id)
    except api.TrelloApiError as e:
        return BoardsListOutput(error=typed_error(e)).model_dump()
    return BoardsListOutput(boards=data if isinstance(data, list) else []).model_dump()


HANDLERS = {"trello.boards.list": boards_list}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="trello.boards.list",
            description="Boards a member belongs to. READ, ONE LIVE API CALL.",
            inputSchema=BoardsListInput.model_json_schema(),
        ),
    ]


__all__ = ["HANDLERS", "register", "tool_descriptors"]
