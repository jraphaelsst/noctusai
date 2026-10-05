from __future__ import annotations

import pytest

from telegram import settings as m


@pytest.fixture(autouse=True)
def _clear():
    m.get_settings.cache_clear()
    yield
    m.get_settings.cache_clear()


def test_configured_requires_both_and_numeric_id():
    assert m.TelegramConnectorSettings().configured is False
    assert m.TelegramConnectorSettings(api_id="123").configured is False
    assert m.TelegramConnectorSettings(api_hash="h").configured is False
    assert m.TelegramConnectorSettings(api_id="abc", api_hash="h").configured is False
    assert m.TelegramConnectorSettings(api_id="123", api_hash="h").configured is True


def test_env_wins_and_session_defaults_live_in_gitignored_session_dir(monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_ID", "42")
    monkeypatch.setenv("TELEGRAM_API_HASH", "x")
    s = m.get_settings()
    assert s.configured
    assert s.session_file.endswith("mcp/telegram/.session/noctus.session")
    assert s.exports_dir.endswith("mcp/telegram/.exports")
