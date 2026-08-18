"""Live-call tools (`boards`, `lists`, `cards`, `checklists`, `labels`,
`actions`) against a STUBBED transport — never real network.

Two layers of test, matching the two-layer test seam documented in
`mcp/trello/client.py`:

1. Patch `trello.api.request_json` — proves the tool → `TrelloClient` →
   `api.request_json` wiring, output shaping, and error mapping.
2. Patch `_kit.transport.urlopen` — proves the ACTUAL wire shape: `key`
   and `token` really do go out as query params (not a header, unlike
   every other connector), and the URL/method are correct.

Configuration is exercised through REAL env vars (`monkeypatch.setenv` +
`get_settings.cache_clear()`), not a patched `get_settings` — `get_settings`
is one `lru_cache`-wrapped singleton object imported by name into several
modules (`client.py`, every `tools/*.py`); patching one module's copy of
the NAME would leave every other module's copy pointing at the original
unpatched function, since `from X import Y` binds a reference at import
time. Real env vars flow through the one shared singleton correctly
regardless of which module calls it — no risk of "patched the wrong
binding and silently exercised the unconfigured path".

Our own code (`TrelloClient`, `api.require_configured`) is never patched.
"""
from __future__ import annotations

import asyncio
import json
import urllib.parse
from unittest.mock import patch

import pytest

from trello import api, client, settings as settings_module
from trello.tools import actions, boards, cards, checklists, labels, lists
from trello.tools.diagnostics import probe


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    client.configure_client(None)
    for var in ("TRELLO_API_KEY", "TRELLO_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    settings_module.get_settings.cache_clear()
    yield
    client.configure_client(None)
    settings_module.get_settings.cache_clear()


@pytest.fixture()
def configured(monkeypatch):
    """Real env-backed credentials, flowing through the one shared
    `get_settings` singleton every module calls."""
    monkeypatch.setenv("TRELLO_API_KEY", "k")
    monkeypatch.setenv("TRELLO_TOKEN", "t")
    settings_module.get_settings.cache_clear()
    yield
    settings_module.get_settings.cache_clear()


# -- unconfigured: typed 424, never a fake success --------------------


@pytest.mark.parametrize(
    "handler,args,outcome_key",
    [
        (boards.boards_list, {}, "boards"),
        (lists.lists_list, {"board_id": "b1"}, "lists"),
        (cards.cards_list, {"board_id": "b1"}, "cards"),
        (cards.cards_get, {"card_id": "c1"}, "card"),
        (checklists.checklists_get, {"checklist_id": "cl1"}, "checklist"),
        (labels.labels_list, {"board_id": "b1"}, "labels"),
        (actions.actions_list, {"card_id": "c1"}, "actions"),
    ],
)
def test_every_read_tool_unconfigured_returns_424(handler, args, outcome_key):
    result = run(handler(args))
    assert result["error"]["status"] == 424
    empty = result[outcome_key]
    assert empty in ([], None)


# -- api.request_json layer ---------------------------------------------


def test_boards_list_forwards_to_the_client_and_shapes_output(configured):
    with patch.object(api, "request_json", return_value=[{"id": "b1", "name": "Board 1"}]):
        result = run(boards.boards_list({"member_id": "me"}))

    assert result["boards"] == [{"id": "b1", "name": "Board 1"}]
    assert result["error"] is None


def test_cards_list_requires_exactly_one_of_board_id_or_list_id():
    result = run(cards.cards_list({}))
    assert result["error"]["status"] is None
    assert "exactly one" in result["error"]["message"]

    result2 = run(cards.cards_list({"board_id": "b1", "list_id": "l1"}))
    assert "exactly one" in result2["error"]["message"]


def test_cards_get_maps_an_upstream_404_typed(configured):
    with patch.object(api, "request_json", side_effect=api.TrelloApiError("not found", status=404)):
        result = run(cards.cards_get({"card_id": "does-not-exist"}))

    assert result["card"] is None
    assert result["error"]["status"] == 404


def test_cards_create_refuses_without_confirm_then_creates_with_it(configured):
    refused = run(cards.cards_create({"id_list": "l1", "name": "New"}))
    assert refused["created"] is False
    assert refused["error"]["status"] == 412

    with patch.object(api, "request_json", return_value={"id": "c9", "name": "New"}):
        created = run(cards.cards_create({"id_list": "l1", "name": "New", "confirm": True}))

    assert created["created"] is True
    assert created["card"]["id"] == "c9"


def test_checklists_create_confirm_then_creates(configured):
    with patch.object(api, "request_json", return_value={"id": "cl1", "name": "Docs"}):
        result = run(checklists.checklists_create({
            "card_id": "c1", "name": "Docs", "confirm": True,
        }))

    assert result["created"] is True
    assert result["checklist"]["id"] == "cl1"


def test_cards_comment_add_confirm_then_posts(configured):
    with patch.object(api, "request_json", return_value={"id": "a1", "data": {"text": "hi"}}):
        result = run(cards.cards_comment_add({
            "card_id": "c1", "text": "hi", "confirm": True,
        }))

    assert result["added"] is True
    assert result["action"]["id"] == "a1"


def test_lists_list_and_labels_list_and_actions_list_forward_correctly(configured):
    with patch.object(api, "request_json", return_value=[{"id": "l1"}]):
        assert run(lists.lists_list({"board_id": "b1"}))["lists"] == [{"id": "l1"}]
    with patch.object(api, "request_json", return_value=[{"id": "lb1"}]):
        assert run(labels.labels_list({"board_id": "b1"}))["labels"] == [{"id": "lb1"}]
    with patch.object(api, "request_json", return_value=[{"id": "act1"}]):
        assert run(actions.actions_list({"card_id": "c1"}))["actions"] == [{"id": "act1"}]


# -- wire shape: key/token as QUERY PARAMS, not a header -----------------


class _FakeHttpResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_get_me_sends_key_and_token_as_query_params_not_a_header(configured):
    captured = {}

    def _fake_urlopen(request, timeout=None):
        captured["full_url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["method"] = request.get_method()
        return _FakeHttpResponse(json.dumps({"id": "m1", "username": "noctus"}).encode())

    with patch("_kit.transport.urlopen", _fake_urlopen):
        result = run(probe({}))

    assert result["probed"] is True
    assert result["member"]["username"] == "noctus"

    parsed = urllib.parse.urlparse(captured["full_url"])
    query = urllib.parse.parse_qs(parsed.query)
    assert query["key"] == ["k"]
    assert query["token"] == ["t"]
    assert captured["method"] == "GET"
    # NOT a header — Trello is the one connector in this repo that is not.
    assert "Authorization" not in captured["headers"]
    assert "X-Api-Key" not in captured["headers"]


def test_cards_update_sends_the_fields_as_query_params(configured):
    captured = {}

    def _fake_urlopen(request, timeout=None):
        captured["full_url"] = request.full_url
        return _FakeHttpResponse(json.dumps({"id": "c1", "name": "Renamed"}).encode())

    with patch("_kit.transport.urlopen", _fake_urlopen):
        result = run(cards.cards_update({
            "card_id": "c1", "fields": {"name": "Renamed"}, "confirm": True,
        }))

    assert result["updated"] is True
    parsed = urllib.parse.urlparse(captured["full_url"])
    query = urllib.parse.parse_qs(parsed.query)
    assert query["name"] == ["Renamed"]
    assert "/cards/c1" in parsed.path


def test_an_http_error_becomes_a_typed_trello_api_error(configured):
    import urllib.error

    def _fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "invalid key", {}, None)

    with patch("_kit.transport.urlopen", _fake_urlopen):
        result = run(probe({}))

    assert result["probed"] is True
    assert result["error"]["status"] == 401
    assert result["error"]["error_class"] == "TrelloApiError"
