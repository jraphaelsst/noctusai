"""Tests for WahaClient identity-resolution methods.

Covers:
- get_contact: correct URL + params + return value for 200; empty dict on 4xx.
- get_lid_phone: correct URL; returns pn on 200; None on 404.
- list_lids: correct URL; returns list on 200; [] on 4xx.

Uses asyncio.run (NOT get_event_loop — deprecated in py3.10+, removed in 3.12).
httpx.AsyncClient patched via monkeypatch on httpx.AsyncClient.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from noctusai_lib.integrations.whatsapp.client import WahaClient


# ── Helpers ───────────────────────────────────────────────────────────────────


def _async_ctx(response: MagicMock) -> MagicMock:
    """Build an AsyncClient context-manager mock that returns `response`."""
    mock_client = MagicMock()
    # async context manager protocol
    aenter = AsyncMock(return_value=mock_client)
    mock_client.__aenter__ = aenter
    mock_client.__aexit__ = AsyncMock(return_value=False)
    # HTTP verb mocks
    mock_client.get = AsyncMock(return_value=response)
    mock_client.post = AsyncMock(return_value=response)
    return mock_client


def _make_async_response(
    status_code: int = 200,
    json_body: dict | list | None = None,
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body if json_body is not None else {}
    return response


# ── get_contact ───────────────────────────────────────────────────────────────


def test_get_contact_returns_dict_on_200(monkeypatch: pytest.MonkeyPatch) -> None:
    contact_data = {
        "id": "5511974693365@c.us",
        "lid": "33613018058989@lid",
        "name": "João Raphael",
        "phoneNumber": "5511974693365@s.whatsapp.net",
    }
    resp = _make_async_response(200, contact_data)
    ctx = _async_ctx(resp)
    monkeypatch.setattr("httpx.AsyncClient", lambda **_: ctx)

    client = WahaClient(base_url="https://waha.test", api_key="k", session="default")
    result = asyncio.run(client.get_contact("5511974693365@c.us"))

    assert result == contact_data
    ctx.get.assert_called_once()
    call_kwargs = ctx.get.call_args
    assert call_kwargs.args[0] == "/api/contacts"
    assert call_kwargs.kwargs["params"]["contactId"] == "5511974693365@c.us"
    assert call_kwargs.kwargs["params"]["session"] == "default"


def test_get_contact_returns_empty_dict_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _make_async_response(404)
    ctx = _async_ctx(resp)
    monkeypatch.setattr("httpx.AsyncClient", lambda **_: ctx)

    client = WahaClient(base_url="https://waha.test", api_key="k")
    result = asyncio.run(client.get_contact("unknown@c.us"))

    assert result == {}


def test_get_contact_lid_form_returns_pushname(monkeypatch: pytest.MonkeyPatch) -> None:
    contact_data = {"id": "33613018058989@lid", "pushname": "J. Raphael"}
    resp = _make_async_response(200, contact_data)
    ctx = _async_ctx(resp)
    monkeypatch.setattr("httpx.AsyncClient", lambda **_: ctx)

    client = WahaClient(base_url="https://waha.test", api_key="k", session="sess")
    result = asyncio.run(client.get_contact("33613018058989@lid"))

    assert result.get("pushname") == "J. Raphael"
    call_kwargs = ctx.get.call_args
    assert call_kwargs.kwargs["params"]["session"] == "sess"


# ── get_lid_phone ─────────────────────────────────────────────────────────────


def test_get_lid_phone_returns_pn_on_200(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _make_async_response(200, {"lid": "33613018058989@lid", "pn": "5511974693365@c.us"})
    ctx = _async_ctx(resp)
    monkeypatch.setattr("httpx.AsyncClient", lambda **_: ctx)

    client = WahaClient(base_url="https://waha.test", api_key="k", session="sess")
    result = asyncio.run(client.get_lid_phone("33613018058989@lid"))

    assert result == "5511974693365@c.us"
    call_kwargs = ctx.get.call_args
    assert "/sess/lids/33613018058989@lid" in call_kwargs.args[0]


def test_get_lid_phone_returns_none_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _make_async_response(404)
    ctx = _async_ctx(resp)
    monkeypatch.setattr("httpx.AsyncClient", lambda **_: ctx)

    client = WahaClient(base_url="https://waha.test", api_key="k")
    result = asyncio.run(client.get_lid_phone("unknownlid@lid"))

    assert result is None


def test_get_lid_phone_returns_none_on_500(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _make_async_response(500)
    ctx = _async_ctx(resp)
    monkeypatch.setattr("httpx.AsyncClient", lambda **_: ctx)

    client = WahaClient(base_url="https://waha.test", api_key="k")
    result = asyncio.run(client.get_lid_phone("lid@lid"))

    assert result is None


# ── list_lids ─────────────────────────────────────────────────────────────────


def test_list_lids_returns_list_on_200(monkeypatch: pytest.MonkeyPatch) -> None:
    lids_data = [
        {"lid": "33613018058989@lid", "pn": "5511974693365@c.us"},
        {"lid": "1099562024960@lid", "pn": "5511974693365@c.us"},
    ]
    resp = _make_async_response(200, lids_data)
    ctx = _async_ctx(resp)
    monkeypatch.setattr("httpx.AsyncClient", lambda **_: ctx)

    client = WahaClient(base_url="https://waha.test", api_key="k", session="default")
    result = asyncio.run(client.list_lids())

    assert len(result) == 2
    assert result[0]["lid"] == "33613018058989@lid"
    call_kwargs = ctx.get.call_args
    assert "/default/lids" in call_kwargs.args[0]


def test_list_lids_returns_empty_list_on_4xx(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _make_async_response(400)
    ctx = _async_ctx(resp)
    monkeypatch.setattr("httpx.AsyncClient", lambda **_: ctx)

    client = WahaClient(base_url="https://waha.test", api_key="k")
    result = asyncio.run(client.list_lids())

    assert result == []
