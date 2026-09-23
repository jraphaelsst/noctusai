"""`send_test` — the "Testar envio" zero-effort default."""
from __future__ import annotations

import asyncio

from noctusai_lib.integrations.email.convenience import send_test
from noctusai_lib.integrations.email.fake_adapter import FakeEmailSender


def _run(coro):
    return asyncio.run(coro)


class TestSendTest:
    def test_sends_a_minimal_round_trip_email(self):
        sender = FakeEmailSender()
        sent = _run(send_test(sender, to="owner@example.com"))
        assert sent.message_id.startswith("<fake-")
        assert len(sender.sent) == 1
        recorded = sender.sent[0]
        assert recorded.to == ["owner@example.com"]
        assert recorded.subject == "Teste de envio"
        assert recorded.html is not None
        assert recorded.text is not None

    def test_custom_subject_and_from_label_are_honoured(self):
        sender = FakeEmailSender()
        _run(send_test(
            sender, to="owner@example.com", subject="[igig] Teste SMTP",
            from_label="igig",
        ))
        recorded = sender.sent[0]
        assert recorded.subject == "[igig] Teste SMTP"
        assert "igig" in recorded.text
        assert "igig" in recorded.html
