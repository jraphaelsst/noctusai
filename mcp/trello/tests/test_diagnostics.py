"""`trello.diagnostics.*` — configured-vs-not, and the one live probe."""
from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from trello import client, settings as settings_module
from trello.tools import diagnostics


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


def _configured(**overrides):
    base = settings_module.TrelloConnectorSettings(api_key="k", token="t")
    return replace(base, **overrides) if overrides else base


def test_connection_status_unconfigured_names_both_missing_vars():
    result = run(diagnostics.connection_status({}))

    assert result["ok"] is False
    assert result["configured"] is False
    assert "TRELLO_API_KEY" in result["next_step"]
    assert "TRELLO_TOKEN" in result["next_step"]


def test_connection_status_makes_no_api_call(monkeypatch):
    """If this were making a real call it would raise — no transport is
    patched, and no host is reachable from a unit test."""
    result = run(diagnostics.connection_status({}))
    assert result["ok"] is False  # would blow up before returning if it dialed out


def test_connection_status_reports_configured_when_credentials_exist(monkeypatch):
    monkeypatch.setattr(diagnostics, "get_settings", lambda: _configured())

    result = run(diagnostics.connection_status({}))

    assert result["ok"] is True
    assert result["has_api_key"] is True
    assert result["has_token"] is True
    assert result["next_step"] is None


def test_probe_unconfigured_returns_typed_424_not_a_fake_success():
    result = run(diagnostics.probe({}))

    assert result["probed"] is False
    assert result["member"] is None
    assert result["error"]["status"] == 424


class _FakeClient:
    def __init__(self, member=None, raises=None):
        self._member = member
        self._raises = raises

    def get_me(self):
        if self._raises is not None:
            raise self._raises
        return self._member


def test_probe_configured_returns_the_member(monkeypatch):
    monkeypatch.setattr(diagnostics, "get_settings", lambda: _configured())
    client.configure_client(_FakeClient(member={"id": "abc", "username": "noctus"}))

    result = run(diagnostics.probe({}))

    assert result["probed"] is True
    assert result["member"]["username"] == "noctus"
    assert result["error"] is None


def test_probe_surfaces_an_upstream_error_typed(monkeypatch):
    from trello import api

    monkeypatch.setattr(diagnostics, "get_settings", lambda: _configured())
    client.configure_client(_FakeClient(raises=api.TrelloApiError("bad key/token", status=401)))

    result = run(diagnostics.probe({}))

    assert result["probed"] is True
    assert result["member"] is None
    assert result["error"]["status"] == 401
