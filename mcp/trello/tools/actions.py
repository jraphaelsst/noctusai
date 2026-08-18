"""`trello.actions.*` — live READ. A card's comment/activity thread —
the concrete substrate behind the "Comentários e atividade" row of
`trello.contract.capability_map`. One network call, through the
`client.get_client()` DI seam. Unconfigured ⇒ typed 424, never faked.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api, client
from ..types import ActionsListInput, ActionsListOutput


async def actions_list(args: dict) -> dict:
    inp = ActionsListInput(**args)
    try:
        data = client.get_client().get_card_actions(inp.card_id, filter_=inp.filter)
    except api.TrelloApiError as e:
        return ActionsListOutput(error=typed_error(e)).model_dump()
    return ActionsListOutput(actions=data if isinstance(data, list) else []).model_dump()


HANDLERS = {"trello.actions.list": actions_list}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="trello.actions.list",
            description="A card's comment/activity thread (Trello Actions). "
            "READ, ONE LIVE API CALL. Optional `filter` (e.g. 'commentCard').",
            inputSchema=ActionsListInput.model_json_schema(),
        ),
    ]


__all__ = ["HANDLERS", "register", "tool_descriptors"]
