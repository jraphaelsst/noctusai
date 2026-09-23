"""`SmtpEmailSender` — mocked at the `smtplib` socket boundary (the
external-service carve-out `test_email_digest.py` also uses; never a
monkeypatch of our own guard). Covers SSL/STARTTLS/none security modes,
attachment round-trip, generated `Message-ID`, threading-header
pass-through (R8), and error translation."""
from __future__ import annotations

import asyncio
import smtplib

import pytest

from noctusai_lib.integrations.email.config import SmtpConfig
from noctusai_lib.integrations.email.errors import EmailSendError
from noctusai_lib.integrations.email.smtp_adapter import SmtpEmailSender
from noctusai_lib.integrations.email.types import (
    Attachment,
    EmailSender,
    OutgoingEmail,
)


def _run(coro):
    return asyncio.run(coro)


class _FakeSmtpClient:
    """Mimics the smtplib context-manager API. Shared by SMTP and
    SMTP_SSL fakes — same shape `test_email_digest.py`'s fixture uses,
    extended with the `context=` kwarg + `from_addr`/`to_addrs` on
    `send_message` since `SmtpEmailSender` passes both explicitly
    (Bcc must never ride as a header, so recipients are addressed via
    the envelope, not by letting smtplib re-derive them from headers).
    """

    instances: list = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.starttls_called = False
        self.starttls_context = None
        self.login_args: tuple | None = None
        self.sent: list = []
        _FakeSmtpClient.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def starttls(self, context=None):
        self.starttls_called = True
        self.starttls_context = context

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, msg, from_addr=None, to_addrs=None):
        self.sent.append(msg)
        self.last_from_addr = from_addr
        self.last_to_addrs = to_addrs


@pytest.fixture(autouse=True)
def _reset_fake_smtp():
    _FakeSmtpClient.instances = []
    yield
    _FakeSmtpClient.instances = []


def _config(**overrides) -> SmtpConfig:
    base = dict(
        host="smtp.example.com",
        port=587,
        username="bot@example.com",
        password="sekret",
        security="starttls",
        from_email="bot@example.com",
        from_name="NoctusAI",
    )
    base.update(overrides)
    return SmtpConfig(**base)


class TestProtocolConformance:
    def test_satisfies_email_sender_protocol(self):
        assert isinstance(SmtpEmailSender(_config()), EmailSender)


class TestStarttlsPath:
    def test_sends_via_starttls_and_returns_message_id(self, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP", _FakeSmtpClient)
        sender = SmtpEmailSender(_config())

        sent = _run(sender.send(OutgoingEmail(
            to=["lead@example.com"], subject="Seu orçamento", html="<p>Oi</p>",
        )))

        assert len(_FakeSmtpClient.instances) == 1
        client = _FakeSmtpClient.instances[0]
        assert client.host == "smtp.example.com"
        assert client.port == 587
        assert client.starttls_called is True
        assert client.login_args == ("bot@example.com", "sekret")
        assert client.last_from_addr == "bot@example.com"
        assert client.last_to_addrs == ["lead@example.com"]

        msg = client.sent[0]
        assert msg["Subject"] == "Seu orçamento"
        assert msg["To"] == "lead@example.com"
        assert msg["From"] == "NoctusAI <bot@example.com>"
        assert msg["Message-ID"].endswith("@example.com>")
        assert sent.message_id == msg["Message-ID"]


class TestSslPath:
    def test_uses_smtp_ssl_no_starttls(self, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSmtpClient)

        def _boom(*_a, **_k):
            raise AssertionError("plain SMTP class must not be used in ssl mode")
        monkeypatch.setattr(smtplib, "SMTP", _boom)

        sender = SmtpEmailSender(_config(security="ssl", port=465))
        _run(sender.send(OutgoingEmail(to=["a@b.com"], subject="S")))

        client = _FakeSmtpClient.instances[0]
        assert client.port == 465
        assert client.starttls_called is False
        assert client.login_args == ("bot@example.com", "sekret")


class TestNoneSecurity:
    def test_skips_starttls(self, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP", _FakeSmtpClient)
        sender = SmtpEmailSender(_config(security="none"))
        _run(sender.send(OutgoingEmail(to=["a@b.com"], subject="S")))
        client = _FakeSmtpClient.instances[0]
        assert client.starttls_called is False


class TestMessageId:
    def test_generated_from_sender_domain_when_absent(self, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP", _FakeSmtpClient)
        sender = SmtpEmailSender(_config(from_email="orcamentos@igig.app"))
        sent = _run(sender.send(OutgoingEmail(to=["a@b.com"], subject="S")))
        assert sent.message_id.endswith("@igig.app>")

    def test_caller_supplied_message_id_is_honoured(self, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP", _FakeSmtpClient)
        sender = SmtpEmailSender(_config())
        sent = _run(sender.send(OutgoingEmail(
            to=["a@b.com"], subject="S", message_id="<pinned@example.com>",
        )))
        assert sent.message_id == "<pinned@example.com>"


class TestThreadingHeaders:
    def test_in_reply_to_and_references_pass_through_and_echo(self, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP", _FakeSmtpClient)
        sender = SmtpEmailSender(_config())
        sent = _run(sender.send(OutgoingEmail(
            to=["lead@example.com"],
            subject="Re: Seu orçamento",
            headers={
                "In-Reply-To": "<orig@igig.app>",
                "References": "<orig@igig.app> <mid@igig.app>",
            },
        )))
        client = _FakeSmtpClient.instances[0]
        msg = client.sent[0]
        assert msg["In-Reply-To"] == "<orig@igig.app>"
        assert msg["References"] == "<orig@igig.app> <mid@igig.app>"
        assert sent.in_reply_to == "<orig@igig.app>"
        assert sent.references == ("<orig@igig.app>", "<mid@igig.app>")


class TestAttachments:
    def test_attachment_round_trips_in_the_sent_message(self, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP", _FakeSmtpClient)
        sender = SmtpEmailSender(_config())
        pdf_bytes = b"%PDF-1.4 fake orcamento content"
        _run(sender.send(OutgoingEmail(
            to=["lead@example.com"],
            subject="Seu orçamento",
            html="<p>Segue em anexo</p>",
            attachments=[Attachment(
                filename="orcamento.pdf", content=pdf_bytes, mime_type="application/pdf",
            )],
        )))
        client = _FakeSmtpClient.instances[0]
        msg = client.sent[0]
        attachment_parts = [
            part for part in msg.iter_attachments()
        ]
        assert len(attachment_parts) == 1
        part = attachment_parts[0]
        assert part.get_filename() == "orcamento.pdf"
        assert part.get_content_type() == "application/pdf"
        assert part.get_payload(decode=True) == pdf_bytes

    def test_multiple_attachments_all_round_trip(self, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP", _FakeSmtpClient)
        sender = SmtpEmailSender(_config())
        _run(sender.send(OutgoingEmail(
            to=["lead@example.com"],
            subject="S",
            text="body",
            attachments=[
                Attachment("a.pdf", b"AAA", "application/pdf"),
                Attachment("b.txt", b"BBB", "text/plain"),
            ],
        )))
        client = _FakeSmtpClient.instances[0]
        msg = client.sent[0]
        filenames = {part.get_filename() for part in msg.iter_attachments()}
        assert filenames == {"a.pdf", "b.txt"}


class TestTextFallback:
    def test_html_only_gets_stripped_text_alternative(self, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP", _FakeSmtpClient)
        sender = SmtpEmailSender(_config())
        _run(sender.send(OutgoingEmail(
            to=["a@b.com"], subject="S", html="<p>Hello <b>world</b></p>",
        )))
        client = _FakeSmtpClient.instances[0]
        msg = client.sent[0]
        text_parts = [
            part.get_payload() for part in msg.iter_parts()
            if part.get_content_type() == "text/plain"
        ]
        joined = "".join(text_parts) if text_parts else msg.get_payload()
        assert "Hello" in joined
        assert "world" in joined
        assert "<" not in joined


class TestBcc:
    def test_bcc_reaches_envelope_but_never_a_header(self, monkeypatch):
        monkeypatch.setattr(smtplib, "SMTP", _FakeSmtpClient)
        sender = SmtpEmailSender(_config())
        _run(sender.send(OutgoingEmail(
            to=["a@b.com"], cc=["c@b.com"], bcc=["blind@b.com"], subject="S",
        )))
        client = _FakeSmtpClient.instances[0]
        assert client.last_to_addrs == ["a@b.com", "c@b.com", "blind@b.com"]
        msg = client.sent[0]
        assert msg["Bcc"] is None
        assert msg["Cc"] == "c@b.com"


class TestErrorTranslation:
    def test_no_recipients_raises_send_error(self):
        sender = SmtpEmailSender(_config())
        with pytest.raises(EmailSendError):
            _run(sender.send(OutgoingEmail(to=[], subject="S")))

    def test_auth_error_translates(self, monkeypatch):
        class _AuthFailClient(_FakeSmtpClient):
            def login(self, username, password):
                raise smtplib.SMTPAuthenticationError(535, b"bad creds")

        monkeypatch.setattr(smtplib, "SMTP", _AuthFailClient)
        sender = SmtpEmailSender(_config())
        with pytest.raises(EmailSendError) as exc_info:
            _run(sender.send(OutgoingEmail(to=["a@b.com"], subject="S")))
        assert "auth" in str(exc_info.value).lower()

    def test_recipients_refused_translates(self, monkeypatch):
        class _RefusedClient(_FakeSmtpClient):
            def send_message(self, msg, from_addr=None, to_addrs=None):
                raise smtplib.SMTPRecipientsRefused(
                    {"a@b.com": (550, b"no such user")}
                )

        monkeypatch.setattr(smtplib, "SMTP", _RefusedClient)
        sender = SmtpEmailSender(_config())
        with pytest.raises(EmailSendError) as exc_info:
            _run(sender.send(OutgoingEmail(to=["a@b.com"], subject="S")))
        assert "refused" in str(exc_info.value).lower()

    def test_oserror_translates_to_transport(self, monkeypatch):
        def _boom(*_a, **_k):
            raise OSError("conn refused")
        monkeypatch.setattr(smtplib, "SMTP", _boom)
        sender = SmtpEmailSender(_config())
        with pytest.raises(EmailSendError) as exc_info:
            _run(sender.send(OutgoingEmail(to=["a@b.com"], subject="S")))
        assert "transport" in str(exc_info.value).lower()
