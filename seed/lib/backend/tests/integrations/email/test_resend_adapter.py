"""ResendEmailSender — Real EmailSender over Resend (P1b, 2026-10-10)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from noctusai_lib.integrations.email import (
    Attachment, EmailNotConfigured, EmailSendError, OutgoingEmail, ResendConfig,
    ResendEmailSender, make_email_sender,
)


def _http(status=200, body=None, raises=None):
    calls = []

    class Client:
        def __init__(self, *_a, **_k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None, timeout=None):
            if raises:
                raise raises
            calls.append({"url": url, "json": json, "headers": headers})
            return SimpleNamespace(status_code=status, json=lambda: body if body is not None else {"id": "re_123"}, text="err")

    return Client, calls


def _sender(**kw):
    client, calls = _http(**kw)
    return ResendEmailSender(ResendConfig(api_key="re_key", from_email="a@x.com", from_name="X"),
                             http_client_factory=client), calls


def test_send_posts_the_payload_and_returns_resend_id():
    sender, calls = _sender()
    sent = asyncio.run(sender.send(OutgoingEmail(
        to=["b@y.com"], subject="Oi", html="<p>x</p>", headers={"References": "<a> <b>"},
        attachments=[Attachment("f.pdf", b"%PDF")])))
    assert sent.message_id == "re_123" and sent.references == ("<a>", "<b>")
    (call,) = calls
    assert call["json"]["from"] == "X <a@x.com>" and call["json"]["to"] == ["b@y.com"]
    assert call["json"]["attachments"][0]["filename"] == "f.pdf"
    assert call["headers"]["Authorization"] == "Bearer re_key"


@pytest.mark.parametrize("kw", [{"status": 422}, {"raises": OSError("down")}, {"body": {}}])
def test_failures_raise_never_swallow(kw):
    sender, _ = _sender(**kw)
    with pytest.raises(EmailSendError):
        asyncio.run(sender.send(OutgoingEmail(to=["b@y.com"], subject="s", text="t")))


def test_config_refuses_incomplete_and_factory_selects_resend():
    with pytest.raises(EmailNotConfigured):
        ResendConfig(api_key="", from_email="a@x.com")
    assert isinstance(make_email_sender(ResendConfig(api_key="k", from_email="a@x.com")), ResendEmailSender)
