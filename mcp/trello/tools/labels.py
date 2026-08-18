"""`trello.labels.*` — live READ. One network call per tool, through the
`client.get_client()` DI seam. Unconfigured ⇒ typed 424, never faked.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api, client
from ..types import LabelsListInput, LabelsListOutput


async def labels_list(args: dict) -> dict:
    inp = LabelsListInput(**args)
    try:
        data = client.get_client().get_board_labels(inp.board_id)
    except api.TrelloApiError as e:
        return LabelsListOutput(error=typed_error(e)).model_dump()
    return LabelsListOutput(labels=data if isinstance(data, list) else []).model_dump()


HANDLERS = {"trello.labels.list": labels_list}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="trello.labels.list",
            description="Labels defined on a board. READ, ONE LIVE API CALL.",
            inputSchema=LabelsListInput.model_json_schema(),
        ),
    ]


__all__ = ["HANDLERS", "register", "tool_descriptors"]
