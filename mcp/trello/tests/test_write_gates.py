"""Every WRITE tool refuses without `confirm=true` — proven by injecting
a client that raises on ANY call, so "gated" means "no side effect", not
"returned an error after the call already happened".
"""
from __future__ import annotations

import asyncio

import pytest

from trello import client
from trello.tools import all_handlers

WRITE_TOOLS = {
    "trello.cards.create",
    "trello.cards.update",
    "trello.cards.comment_add",
    "trello.checklists.create",
}

ARGS_BY_TOOL = {
    "trello.cards.create": {"id_list": "list1", "name": "New card"},
    "trello.cards.update": {"card_id": "card1", "fields": {"name": "Renamed"}},
    "trello.cards.comment_add": {"card_id": "card1", "text": "hi"},
    "trello.checklists.create": {"card_id": "card1", "name": "Checklist"},
}


def run(coro):
    return asyncio.run(coro)


class _ExplodingClient:
    def __getattr__(self, name):
        def _boom(*args, **kwargs):
            raise AssertionError(f"confirm gate did not stop the write ({name})")
        return _boom


@pytest.fixture(autouse=True)
def _isolate():
    client.configure_client(None)
    yield
    client.configure_client(None)


@pytest.mark.parametrize("tool_name", sorted(WRITE_TOOLS))
def test_every_write_tool_refuses_without_confirm(tool_name):
    client.configure_client(_ExplodingClient())
    handler = all_handlers()[tool_name]

    result = run(handler(ARGS_BY_TOOL[tool_name]))

    assert result["error"]["status"] == 412
    assert result["error"]["error_class"] == "ConfirmationRequiredError"


@pytest.mark.parametrize("tool_name", sorted(WRITE_TOOLS))
def test_every_write_tool_reports_the_falsy_outcome_key_without_confirm(tool_name):
    client.configure_client(_ExplodingClient())
    handler = all_handlers()[tool_name]
    outcome_key = {
        "trello.cards.create": "created",
        "trello.cards.update": "updated",
        "trello.cards.comment_add": "added",
        "trello.checklists.create": "created",
    }[tool_name]

    result = run(handler(ARGS_BY_TOOL[tool_name]))

    assert result[outcome_key] is False


def test_cards_update_rejects_an_unknown_field_before_the_confirm_gate():
    """A field name that could never succeed must not even reach 'are
    you sure?' — 422, not 412, and BEFORE any client call."""
    client.configure_client(_ExplodingClient())

    result = run(all_handlers()["trello.cards.update"]({
        "card_id": "card1", "fields": {"notAField": "x"}, "confirm": True,
    }))

    assert result["updated"] is False
    assert result["error"]["status"] == 422
    assert "notAField" in result["error"]["message"]


def test_cards_update_accepts_every_documented_writable_field_name():
    """Every name off the vendored PUT /cards/{id} param list must pass
    field validation (this only proves validation, not the network leg —
    confirm stays False so the exploding client never fires)."""
    from trello.tools.cards import _put_card_writable_fields

    client.configure_client(_ExplodingClient())
    for field_name in _put_card_writable_fields():
        result = run(all_handlers()["trello.cards.update"]({
            "card_id": "card1", "fields": {field_name: "x"},
        }))
        assert result["error"]["status"] == 412, field_name
