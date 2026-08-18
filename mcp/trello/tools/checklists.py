"""`trello.checklists.*` — one READ, one WRITE (confirm-gated).

Through the `client.get_client()` DI seam. Unconfigured ⇒ typed 424,
never faked. `create` refuses without `confirm=true`, returning a typed
412 BEFORE any network call.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api, client
from ..types import (
    ChecklistsCreateInput,
    ChecklistsCreateOutput,
    ChecklistsGetInput,
    ChecklistsGetOutput,
)


async def checklists_get(args: dict) -> dict:
    inp = ChecklistsGetInput(**args)
    try:
        data = client.get_client().get_checklist(inp.checklist_id)
    except api.TrelloApiError as e:
        return ChecklistsGetOutput(error=typed_error(e)).model_dump()
    return ChecklistsGetOutput(checklist=data if isinstance(data, dict) else None).model_dump()


async def checklists_create(args: dict) -> dict:
    inp = ChecklistsCreateInput(**args)
    if not inp.confirm:
        return ChecklistsCreateOutput(
            created=False,
            error=typed_error(api.ConfirmationRequiredError(
                "trello.checklists.create",
                f"creates a real checklist named {inp.name!r} on card {inp.card_id}",
            )),
        ).model_dump()
    try:
        data = client.get_client().create_checklist(inp.card_id, inp.name)
    except api.TrelloApiError as e:
        return ChecklistsCreateOutput(created=False, error=typed_error(e)).model_dump()
    return ChecklistsCreateOutput(
        created=True, checklist=data if isinstance(data, dict) else None
    ).model_dump()


HANDLERS = {
    "trello.checklists.get": checklists_get,
    "trello.checklists.create": checklists_create,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="trello.checklists.get",
            description="One checklist (with its check items). READ, "
            "ONE LIVE API CALL.",
            inputSchema=ChecklistsGetInput.model_json_schema(),
        ),
        Tool(
            name="trello.checklists.create",
            description="Create a new checklist on a card. WRITE — "
            "confirm-gated (412), ONE LIVE API CALL when confirmed.",
            inputSchema=ChecklistsCreateInput.model_json_schema(),
        ),
    ]


__all__ = ["HANDLERS", "register", "tool_descriptors"]
