"""`FakeEmailSender` — records sends, Protocol conformance, deterministic
ids, threading-header echo (R8's reply watcher depends on the echo
shape matching what the Real sender returns)."""
from __future__ import annotations

import asyncio

from noctusai_lib.integrations.email.fake_adapter import FakeEmailSender
from noctusai_lib.integrations.email.types import (
    Attachment,
    EmailSender,
    OutgoingEmail,
)


def _run(coro):
    return asyncio.run(coro)


class TestProtocolConformance:
    def test_satisfies_email_sender_protocol(self):
        assert isinstance(FakeEmailSender(), EmailSender)


class TestSend:
    def test_records_the_sent_email(self):
        sender = FakeEmailSender()
        email = OutgoingEmail(to=["a@b.com"], subject="Hi", text="body")
        _run(sender.send(email))
        assert sender.sent == [email]

    def test_deterministic_monotonic_ids(self):
        sender = FakeEmailSender()
        first = _run(sender.send(OutgoingEmail(to=["a@b.com"], subject="1")))
        second = _run(sender.send(OutgoingEmail(to=["a@b.com"], subject="2")))
        assert first.message_id == "<fake-1@fake.noctus.test>"
        assert second.message_id == "<fake-2@fake.noctus.test>"

    def test_caller_supplied_message_id_is_honoured(self):
        sender = FakeEmailSender()
        email = OutgoingEmail(
            to=["a@b.com"], subject="Hi", message_id="<custom@example.com>",
        )
        sent = _run(sender.send(email))
        assert sent.message_id == "<custom@example.com>"

    def test_attachments_round_trip_into_sent_record(self):
        sender = FakeEmailSender()
        attachment = Attachment(
            filename="orcamento.pdf", content=b"%PDF-1.4 fake", mime_type="application/pdf",
        )
        email = OutgoingEmail(
            to=["lead@example.com"], subject="Seu orçamento", attachments=[attachment],
        )
        _run(sender.send(email))
        assert sender.sent[0].attachments == [attachment]
        assert sender.sent[0].attachments[0].content == b"%PDF-1.4 fake"

    def test_threading_headers_echo_into_sent_email(self):
        sender = FakeEmailSender()
        email = OutgoingEmail(
            to=["lead@example.com"],
            subject="Re: Seu orçamento",
            headers={
                "In-Reply-To": "<orig@fake.noctus.test>",
                "References": "<orig@fake.noctus.test> <mid@fake.noctus.test>",
            },
        )
        sent = _run(sender.send(email))
        assert sent.in_reply_to == "<orig@fake.noctus.test>"
        assert sent.references == ("<orig@fake.noctus.test>", "<mid@fake.noctus.test>")

    def test_no_threading_headers_means_empty_references(self):
        sender = FakeEmailSender()
        sent = _run(sender.send(OutgoingEmail(to=["a@b.com"], subject="Hi")))
        assert sent.in_reply_to is None
        assert sent.references == ()
