"""Behaviour tests through the DI seam (`client.configure_client`) — no network."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from datetime import datetime, timezone

import pytest

from telegram import client, settings as settings_module
from telegram.tools import all_handlers, messages


def run(coro):
    return asyncio.run(coro)


class _Exploding:
    def __getattr__(self, name):
        async def _boom(*a, **k):
            raise AssertionError(f"confirm gate did not stop the write ({name})")
        return _boom


class FakeGateway:
    def __init__(self, pages=None):
        self.pages = list(pages or [])
        self.disconnected = 0
        self.sent = []

    async def disconnect(self):
        self.disconnected += 1

    async def is_authorized(self):
        return True

    async def get_me(self):
        return {"id": 1, "username": "me", "name": "Me"}

    async def list_dialogs(self, *, limit, query):
        return [{"id": 5, "title": "T", "type": "group", "unread": 0, "username": None}]

    async def fetch_messages(self, chat, *, limit, offset_id=0, min_id=0, reverse=False, search=None):
        if search:
            return [{"id": 1, "text": search}]
        item = self.pages.pop(0) if self.pages else []
        if isinstance(item, Exception):
            raise item
        return item

    async def send_message(self, chat, text):
        self.sent.append((chat, text))
        return {"id": 9, "date": None}


def _unconfigured(monkeypatch):
    """The dev checkout may carry a real gitignored .env, which env-clearing
    cannot hide (dotenv fallback) — hand the two settings readers an empty
    config instead. Config accessor only; no guard is touched."""
    from telegram.tools import diagnostics
    empty = settings_module.TelegramConnectorSettings()
    monkeypatch.setattr(client, "get_settings", lambda: empty)
    monkeypatch.setattr(diagnostics, "get_settings", lambda: empty)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    client.configure_client(None)
    monkeypatch.setenv("TELEGRAM_EXPORTS_DIR", str(tmp_path / "exports"))
    settings_module.get_settings.cache_clear()
    yield
    client.configure_client(None)
    settings_module.get_settings.cache_clear()


@pytest.mark.parametrize("tool,args", [
    ("telegram.messages.send", {"chat": "@x", "text": "hi"}),
    ("telegram.media.download", {"chat": "@x", "message_ids": [1], "out_dir": "/tmp/x"}),
])
def test_write_tools_refuse_with_412_before_touching_the_client(tool, args):
    client.configure_client(_Exploding())
    r = run(all_handlers()[tool](args))
    assert r["error"]["status"] == 412
    assert r["error"]["error_class"] == "ConfirmationRequiredError"


def test_media_download_caps_ids_at_20():
    with pytest.raises(Exception):
        run(all_handlers()["telegram.media.download"](
            {"chat": "@x", "message_ids": list(range(21)), "out_dir": "/tmp/x", "confirm": True}))


def test_send_with_confirm_calls_gateway_and_disconnects():
    gw = FakeGateway()
    client.configure_client(gw)
    r = run(all_handlers()["telegram.messages.send"]({"chat": "@x", "text": "hi", "confirm": True}))
    assert r["sent"] is True and gw.sent == [("@x", "hi")] and gw.disconnected == 1


def test_unconfigured_read_is_typed_424(monkeypatch):
    _unconfigured(monkeypatch)
    r = run(all_handlers()["telegram.dialogs.list"]({}))
    assert r["error"]["status"] == 424


def test_connection_status_unconfigured_names_vars(monkeypatch):
    _unconfigured(monkeypatch)
    r = run(all_handlers()["telegram.diagnostics.connection_status"]({}))
    assert r["ok"] is False and "TELEGRAM_API_ID" in r["next_step"]


def test_me_has_no_phone_key():
    client.configure_client(FakeGateway())
    r = run(all_handlers()["telegram.diagnostics.me"]({}))
    assert "phone" not in json.dumps(r).lower()


def test_unknown_argument_is_rejected():
    with pytest.raises(Exception):
        run(all_handlers()["telegram.dialogs.list"]({"bogus": 1}))


def test_shape_message_extracts_hashtags_and_media():
    f = SimpleNamespace(name="a.pdf", size=10, mime_type="application/pdf", duration=None)
    m = SimpleNamespace(
        id=3, date=datetime(2026, 1, 1, tzinfo=timezone.utc), sender_id=7, sender=None,
        message="hello #tag1 #tag2", reply_to=SimpleNamespace(reply_to_msg_id=2),
        media=object(), file=f, document=True,
    )
    out = client.shape_message(m)
    assert out["hashtags"] == ["#tag1", "#tag2"]
    assert out["reply_to"] == 2
    assert out["media"] == {"type": "document", "file_name": "a.pdf", "size": 10,
                            "mime_type": "application/pdf", "duration": None}


def test_parse_chat():
    assert client.parse_chat("-100123") == -100123
    assert client.parse_chat("@user") == "@user"


class FloodWaitError(Exception):
    def __init__(self, seconds):
        super().__init__("flood")
        self.seconds = seconds


def test_export_paginates_writes_ndjson_and_sleeps_bounded_on_floodwait(tmp_path):
    pages = [
        [{"id": 30, "date": "d", "sender": None, "text": "c", "media": None},
         {"id": 20, "date": "d", "sender": None, "text": "b", "media": None}],
        FloodWaitError(9999),
        [{"id": 10, "date": "d", "sender": None, "text": "a",
          "media": {"type": "photo", "file_name": None}}],
        [],
    ]
    gw = FakeGateway(pages)
    client.configure_client(gw)
    slept = []

    async def fake_sleep(s):
        slept.append(s)

    r = run(messages.messages_export({"chat": "@x", "markdown": True}, sleep=fake_sleep))
    assert r["count"] == 3
    assert slept == [120]  # bounded by max_flood_wait_seconds, not 9999
    lines = open(r["path"]).read().splitlines()
    assert [json.loads(l)["id"] for l in lines] == [30, 20, 10]
    assert str(tmp_path / "exports") in r["path"]
    assert open(r["markdown_path"]).read().count("\n") == 3
