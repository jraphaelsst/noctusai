"""Fake parity + real adapter (httpx.MockTransport) + rate limiting + token hygiene."""
from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest

from noctusai_lib.integrations import rate_limit
from noctusai_lib.integrations.telegram import (
    DELETE_WINDOW_SECONDS, FakeTelegramClient, HttpxTelegramClient, TelegramAuthError, TelegramBadRequestError,
    TelegramClient, TelegramForbiddenError, TelegramMessageNotDeletableError, TelegramMessageNotModifiedError,
    TelegramNotConfiguredError, TelegramNotFoundError, TelegramRateLimitedError, TelegramUnreachableError,
    make_telegram_client, verify_bot_channel_admin,
)
from noctusai_lib.integrations.telegram.redact import mask_token, redact

TOKEN = "123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq"
CH = -1001234567890


def run(coro):
    return asyncio.run(coro)


# ---------------- factory ----------------
def test_factory_refuses_without_token_never_silent_fake():
    with pytest.raises(TelegramNotConfiguredError):
        make_telegram_client(None)
    with pytest.raises(TelegramNotConfiguredError):
        make_telegram_client("")


def test_factory_fake_only_by_explicit_opt_in_and_real_when_configured():
    assert isinstance(make_telegram_client(None, allow_fake=True), FakeTelegramClient)
    real = make_telegram_client(TOKEN, line="l1")
    assert isinstance(real, HttpxTelegramClient)
    assert isinstance(real, TelegramClient) and isinstance(FakeTelegramClient(), TelegramClient)


# ---------------- Fake behaviour (parity with the Real error contract) ----------------
def _fake(now=None):
    f = FakeTelegramClient(now=now or (lambda: 1_000_000.0))
    f.add_channel(CH, "Ofertas", username="ofertas", members=42)
    return f


def test_fake_send_edit_delete_roundtrip():
    f = _fake()
    m = run(f.send_message(CH, "<b>oi</b>"))
    assert m.message_id == 1 and m.chat_id == CH
    run(f.edit_message_text(CH, m.message_id, "<b>tchau</b>"))
    assert f.sent[0].text == "<b>tchau</b>"
    with pytest.raises(TelegramMessageNotModifiedError):
        run(f.edit_message_text(CH, m.message_id, "<b>tchau</b>"))
    assert run(f.delete_message(CH, m.message_id)) is True
    with pytest.raises(TelegramNotFoundError):
        run(f.delete_message(CH, m.message_id))


def test_fake_delete_after_48h_is_typed_error():
    t = [1_000_000.0]
    f = _fake(now=lambda: t[0])
    m = run(f.send_message(CH, "x"))
    t[0] += DELETE_WINDOW_SECONDS + 1
    with pytest.raises(TelegramMessageNotDeletableError):
        run(f.delete_message(CH, m.message_id))
    run(f.edit_message_text(CH, m.message_id, "EXPIRADO"))  # tombstone edit still works


def test_fake_limits_and_permissions():
    f = _fake()
    with pytest.raises(TelegramBadRequestError):
        run(f.send_message(CH, "x" * 4097))
    with pytest.raises(TelegramBadRequestError):
        run(f.send_photo(CH, "http://i/x.jpg", caption="x" * 1025))
    with pytest.raises(TelegramNotFoundError):
        run(f.send_message(999, "x"))
    f.add_channel(7, "ro", can_post=False)
    with pytest.raises(TelegramForbiddenError):
        run(f.send_message(7, "x"))
    assert run(f.get_chat_member_count("@ofertas")) == 42


def test_fake_webhook_rules_and_auth_failure():
    f = _fake()
    with pytest.raises(TelegramBadRequestError):
        run(f.set_webhook("https://x/h", secret_token="bad token!"))
    with pytest.raises(TelegramBadRequestError):
        run(f.set_webhook("http://x/h", secret_token="ok_token-1"))
    run(f.set_webhook("https://x/h", secret_token="ok_token-1"))
    info = run(f.get_webhook_info())
    assert info.url == "https://x/h" and "channel_post" in info.allowed_updates
    run(f.delete_webhook())
    assert run(f.get_webhook_info()).url == ""
    f.token_valid = False
    with pytest.raises(TelegramAuthError):
        run(f.get_me())


def test_verify_bot_channel_admin_verdicts():
    f = _fake()
    assert run(verify_bot_channel_admin(f, CH)).ok
    f.add_channel(8, "nao-admin", bot_status="member", can_post=False)
    assert run(verify_bot_channel_admin(f, 8)).reason == "bot_not_admin"
    f.add_group(9)
    assert run(verify_bot_channel_admin(f, 9)).reason == "not_a_channel"
    assert run(verify_bot_channel_admin(f, 12345)).reason == "chat_not_found"


# ---------------- Real adapter over MockTransport ----------------
def _real(handler, line="l1"):
    return HttpxTelegramClient(TOKEN, line=line, transport=httpx.MockTransport(handler))


def _ok(result):
    return httpx.Response(200, json={"ok": True, "result": result})


def test_real_send_message_wire_shape_html_and_preview_toggle():
    seen = {}

    def handler(req: httpx.Request):
        seen["path"] = req.url.path
        seen["body"] = json.loads(req.content)
        return _ok({"message_id": 77, "chat": {"id": CH}, "date": 5})

    sent = run(_real(handler).send_message(CH, "<b>x</b>", disable_web_page_preview=True))
    assert seen["path"] == f"/bot{TOKEN}/sendMessage"
    assert seen["body"]["parse_mode"] == "HTML"
    assert seen["body"]["link_preview_options"] == {"is_disabled": True}
    assert (sent.message_id, sent.chat_id) == (77, CH)


def test_real_maps_errors_to_typed():
    def mk(code, desc, params=None):
        return lambda req: httpx.Response(code, json={"ok": False, "error_code": code, "description": desc,
                                                       **({"parameters": params} if params else {})})
    cases = [
        (401, "Unauthorized", TelegramAuthError),
        (403, "Forbidden: bot was kicked from the channel chat", TelegramForbiddenError),
        (400, "Bad Request: chat not found", TelegramNotFoundError),
        (400, "Bad Request: message can't be deleted for everyone", TelegramMessageNotDeletableError),
        (400, "Bad Request: message is not modified: specified new message content", TelegramMessageNotModifiedError),
        (400, "Bad Request: can't parse entities", TelegramBadRequestError),
        (502, "Bad Gateway", TelegramUnreachableError),
    ]
    for code, desc, exc in cases:
        with pytest.raises(exc):
            run(_real(mk(code, desc)).delete_message(CH, 1))


def test_real_transport_failure_is_unreachable_and_not_retried():
    calls = []

    def handler(req):
        calls.append(1)
        raise httpx.ConnectTimeout("timeout talking to https://api.telegram.org/bot" + TOKEN + "/sendMessage")

    with pytest.raises(TelegramUnreachableError) as ei:
        run(_real(handler).send_message(CH, "x"))
    assert len(calls) == 1  # unknown write outcome: never blind-retried
    assert TOKEN not in str(ei.value) and TOKEN not in repr(ei.value)


def test_real_429_honours_retry_after_then_succeeds(virtual_clock):
    n = {"c": 0}

    def handler(req):
        n["c"] += 1
        if n["c"] == 1:
            return httpx.Response(429, json={"ok": False, "error_code": 429, "description": "Too Many Requests: retry after 7",
                                             "parameters": {"retry_after": 7}})
        return _ok({"message_id": 1, "chat": {"id": CH}, "date": 1})

    t0 = virtual_clock.monotonic()
    run(_real(handler).send_message(CH, "x"))
    assert n["c"] == 2
    assert virtual_clock.monotonic() - t0 >= 7  # waited the vendor's hint, not our own guess


def test_real_429_persistent_gives_up_typed_with_retry_after():
    def handler(req):
        return httpx.Response(429, json={"ok": False, "error_code": 429, "description": "Too Many Requests",
                                         "parameters": {"retry_after": 1}})

    with pytest.raises(TelegramRateLimitedError) as ei:
        run(_real(handler).send_message(CH, "x"))
    assert ei.value.retry_after == 1


def test_real_429_beyond_inline_max_becomes_retry_later():
    def handler(req):
        return httpx.Response(429, json={"ok": False, "error_code": 429, "description": "flood",
                                         "parameters": {"retry_after": 99999}})

    with pytest.raises(rate_limit.RetryLater):
        run(_real(handler).send_message(CH, "x"))


# ---------------- rate buckets ----------------
def test_calls_go_through_global_and_per_chat_buckets_and_pace(virtual_clock):
    f = FakeTelegramClient(line="L")
    f.add_channel(CH, "c")
    t0 = virtual_clock.monotonic()
    for i in range(5):  # per-chat burst is 3 @ 0.33/s -> the 4th/5th must wait
        run(f.send_message(CH, f"m{i}"))
    assert virtual_clock.monotonic() - t0 > 3.0
    assert f"telegram_chat:L:{CH}" in rate_limit._async_registry._buckets
    assert "telegram" in rate_limit._async_registry._buckets
    cfg = rate_limit._overrides
    assert cfg["telegram"].rate_per_sec == 25.0
    assert cfg[f"telegram_chat:L:{CH}"].rate_per_sec == 0.33 and cfg[f"telegram_chat:L:{CH}"].burst == 3.0


def test_reads_without_chat_use_only_global_bucket():
    f = FakeTelegramClient(line="L2")
    run(f.get_me())
    assert not any(k.startswith("telegram_chat:") for k in rate_limit._async_registry._buckets)


# ---------------- token hygiene ----------------
def test_token_never_in_repr_logs_or_masks(caplog):
    caplog.set_level(logging.DEBUG)
    c = _real(lambda r: _ok({"id": 1, "is_bot": True, "username": "b"}))
    run(c.get_me())
    assert TOKEN not in repr(c)
    assert TOKEN not in caplog.text
    assert TOKEN not in redact(f"POST https://api.telegram.org/bot{TOKEN}/getMe")
    assert mask_token(TOKEN).endswith(TOKEN[-4:]) and TOKEN[:-4] not in mask_token(TOKEN)
