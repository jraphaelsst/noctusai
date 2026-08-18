"""`trello.lists.*` — live READ. One network call per tool, through the
`client.get_client()` DI seam. Unconfigured ⇒ typed 424, never faked.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api, client
from ..types import ListsListInput, ListsListOutput


async def lists_list(args: dict) -> dict:
    inp = ListsListInput(**args)
    try:
        data = client.get_client().get_board_lists(inp.board_id)
    except api.TrelloApiError as e:
        return ListsListOutput(error=typed_error(e)).model_dump()
    return ListsListOutput(lists=data if isinstance(data, list) else []).model_dump()


HANDLERS = {"trello.lists.list": lists_list}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="trello.lists.list",
            description="Lists on a board. READ, ONE LIVE API CALL.",
            inputSchema=ListsListInput.model_json_schema(),
        ),
    ]


__all__ = ["HANDLERS", "register", "tool_descriptors"]
