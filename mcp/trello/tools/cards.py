"""`trello.cards.*` — reads (list, get) and confirm-gated writes (create,
update, comment_add). Through the `client.get_client()` DI seam.
Unconfigured ⇒ typed 424, never faked; every write refuses without
`confirm=true`, returning a typed 412 BEFORE any network call.

`cards.update`'s `fields` keys are validated against the vendored spec's
own `PUT /cards/{id}` parameter list (`..spec.find_operation`) — an
unknown key is rejected with a typed 422 before the confirm check even
runs, so a typo'd field name never reaches "are you sure?" for a request
that could never have succeeded.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api, client, spec
from ..types import (
    CardsCommentAddInput,
    CardsCommentAddOutput,
    CardsCreateInput,
    CardsCreateOutput,
    CardsGetInput,
    CardsGetOutput,
    CardsListInput,
    CardsListOutput,
    CardsUpdateInput,
    CardsUpdateOutput,
)


def _put_card_writable_fields() -> set[str]:
    op = spec.find_operation(method="PUT", path="/cards/{id}") or {}
    return {p.get("name") for p in op.get("parameters", [])}


# ── reads ────────────────────────────────────────────────────────────


async def cards_list(args: dict) -> dict:
    inp = CardsListInput(**args)
    if bool(inp.board_id) == bool(inp.list_id):
        return CardsListOutput(
            error={
                "error_class": "ValueError",
                "message": "Provide exactly one of board_id or list_id.",
                "status": None,
            }
        ).model_dump()
    try:
        c = client.get_client()
        data = c.get_board_cards(inp.board_id) if inp.board_id else c.get_list_cards(inp.list_id)
    except api.TrelloApiError as e:
        return CardsListOutput(error=typed_error(e)).model_dump()
    return CardsListOutput(cards=data if isinstance(data, list) else []).model_dump()


async def cards_get(args: dict) -> dict:
    inp = CardsGetInput(**args)
    try:
        data = client.get_client().get_card(inp.card_id, include=inp.include)
    except api.TrelloApiError as e:
        return CardsGetOutput(error=typed_error(e)).model_dump()
    return CardsGetOutput(card=data if isinstance(data, dict) else None).model_dump()


# ── writes ───────────────────────────────────────────────────────────


async def cards_create(args: dict) -> dict:
    inp = CardsCreateInput(**args)
    if not inp.confirm:
        return CardsCreateOutput(
            created=False,
            error=typed_error(api.ConfirmationRequiredError(
                "trello.cards.create", f"creates a real card named {inp.name!r}"
            )),
        ).model_dump()
    try:
        data = client.get_client().create_card(
            id_list=inp.id_list, name=inp.name, desc=inp.desc, due=inp.due,
            id_members=inp.id_members, id_labels=inp.id_labels,
        )
    except api.TrelloApiError as e:
        return CardsCreateOutput(created=False, error=typed_error(e)).model_dump()
    return CardsCreateOutput(created=True, card=data if isinstance(data, dict) else None).model_dump()


async def cards_update(args: dict) -> dict:
    inp = CardsUpdateInput(**args)
    writable = _put_card_writable_fields()
    unknown = sorted(set(inp.fields) - writable)
    if unknown:
        return CardsUpdateOutput(
            updated=False,
            error={
                "error_class": "ValueError",
                "message": f"Unknown field(s) for PUT /cards/{{id}}: {unknown}. "
                "Call trello.contract.card_surface for the exact writable list.",
                "status": 422,
            },
        ).model_dump()
    if not inp.confirm:
        return CardsUpdateOutput(
            updated=False,
            error=typed_error(api.ConfirmationRequiredError(
                "trello.cards.update",
                f"mutates card {inp.card_id}: {sorted(inp.fields)}",
            )),
        ).model_dump()
    try:
        data = client.get_client().update_card(inp.card_id, **inp.fields)
    except api.TrelloApiError as e:
        return CardsUpdateOutput(updated=False, error=typed_error(e)).model_dump()
    return CardsUpdateOutput(updated=True, card=data if isinstance(data, dict) else None).model_dump()


async def cards_comment_add(args: dict) -> dict:
    inp = CardsCommentAddInput(**args)
    if not inp.confirm:
        return CardsCommentAddOutput(
            added=False,
            error=typed_error(api.ConfirmationRequiredError(
                "trello.cards.comment_add", f"posts a real comment on card {inp.card_id}"
            )),
        ).model_dump()
    try:
        data = client.get_client().add_comment(inp.card_id, inp.text)
    except api.TrelloApiError as e:
        return CardsCommentAddOutput(added=False, error=typed_error(e)).model_dump()
    return CardsCommentAddOutput(
        added=True, action=data if isinstance(data, dict) else None
    ).model_dump()


HANDLERS = {
    "trello.cards.list": cards_list,
    "trello.cards.get": cards_get,
    "trello.cards.create": cards_create,
    "trello.cards.update": cards_update,
    "trello.cards.comment_add": cards_comment_add,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="trello.cards.list",
            description="Cards on a board OR a list (exactly one of "
            "board_id/list_id). READ, ONE LIVE API CALL.",
            inputSchema=CardsListInput.model_json_schema(),
        ),
        Tool(
            name="trello.cards.get",
            description="One card, optionally with nested attachments/"
            "checklists/members/actions expanded via `include`. READ, "
            "ONE LIVE API CALL.",
            inputSchema=CardsGetInput.model_json_schema(),
        ),
        Tool(
            name="trello.cards.create",
            description="Create a new card on a list. WRITE — confirm-"
            "gated (412), ONE LIVE API CALL when confirmed.",
            inputSchema=CardsCreateInput.model_json_schema(),
        ),
        Tool(
            name="trello.cards.update",
            description="Update fields on an existing card. `fields` "
            "keys must be from PUT /cards/{id}'s documented writable "
            "list (an unknown key is rejected, 422, before the confirm "
            "check). WRITE — confirm-gated (412), ONE LIVE API CALL "
            "when confirmed.",
            inputSchema=CardsUpdateInput.model_json_schema(),
        ),
        Tool(
            name="trello.cards.comment_add",
            description="Post a comment on a card. WRITE — confirm-"
            "gated (412), ONE LIVE API CALL when confirmed.",
            inputSchema=CardsCommentAddInput.model_json_schema(),
        ),
    ]


__all__ = ["HANDLERS", "register", "tool_descriptors"]
