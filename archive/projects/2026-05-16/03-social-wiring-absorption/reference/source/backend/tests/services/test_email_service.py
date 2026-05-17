"""Tests for email_service — construction guards + SMTP-mocked send paths."""
from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from app.services.email_service import (
    EmailNotConfigured,
    EmailService,
    EmailServiceError,
    _strip_html,
)


def _make() -> EmailService:
    return EmailService(
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_user="bot@example.com",
        smtp_password="sekret",
    )


class TestConstruction:
    def test_missing_user_raises(self):
        with pytest.raises(EmailNotConfigured):
            EmailService(
                smtp_host="x", smtp_port=465, smtp_user="", smtp_password="p",
            )

    def test_missing_password_raises(self):
        with pytest.raises(EmailNotConfigured):
            EmailService(
                smtp_host="x", smtp_port=465, smtp_user="u", smtp_password="",
            )

    def test_full_creds_pass(self):
        svc = _make()
        assert svc.smtp_user == "bot@example.com"


class TestSendEmail:
    @pytest.mark.asyncio
    async def test_happy_path_sends_via_smtp_ssl(self):
        svc = _make()
        smtp_mock = MagicMock()
        smtp_ctx = MagicMock()
        smtp_ctx.__enter__.return_value = smtp_mock
        smtp_ctx.__exit__.return_value = False

        with patch.object(smtplib, "SMTP_SSL", return_value=smtp_ctx) as smtp_cls:
            await svc.send_email(
                to="user@example.com",
                subject="Hello",
                html_body="<p>Hi</p>",
                text_body="Hi",
            )

        smtp_cls.assert_called_once()
        smtp_mock.login.assert_called_once_with("bot@example.com", "sekret")
        smtp_mock.send_message.assert_called_once()
        sent_msg = smtp_mock.send_message.call_args[0][0]
        assert sent_msg["From"] == "bot@example.com"
        assert sent_msg["To"] == "user@example.com"
        assert sent_msg["Subject"] == "Hello"

    @pytest.mark.asyncio
    async def test_auth_error_translates(self):
        svc = _make()
        with patch.object(smtplib, "SMTP_SSL") as smtp_cls:
            smtp_ctx = MagicMock()
            smtp_mock = MagicMock()
            smtp_mock.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad")
            smtp_ctx.__enter__.return_value = smtp_mock
            smtp_ctx.__exit__.return_value = False
            smtp_cls.return_value = smtp_ctx

            with pytest.raises(EmailServiceError) as exc_info:
                await svc.send_email(
                    to="u@example.com", subject="s", html_body="<p>h</p>",
                )
            assert "auth" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_recipients_refused_translates(self):
        svc = _make()
        with patch.object(smtplib, "SMTP_SSL") as smtp_cls:
            smtp_ctx = MagicMock()
            smtp_mock = MagicMock()
            smtp_mock.send_message.side_effect = smtplib.SMTPRecipientsRefused(
                {"u@example.com": (550, b"no such user")}
            )
            smtp_ctx.__enter__.return_value = smtp_mock
            smtp_ctx.__exit__.return_value = False
            smtp_cls.return_value = smtp_ctx

            with pytest.raises(EmailServiceError) as exc_info:
                await svc.send_email(
                    to="u@example.com", subject="s", html_body="<p>h</p>",
                )
            assert "refused" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_oserror_translates_to_transport(self):
        svc = _make()
        with patch.object(smtplib, "SMTP_SSL", side_effect=OSError("conn refused")):
            with pytest.raises(EmailServiceError) as exc_info:
                await svc.send_email(
                    to="u@example.com", subject="s", html_body="<p>h</p>",
                )
            assert "transport" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_default_text_body_strips_html(self):
        """When text_body is omitted, the html is stripped to a plaintext
        fallback so non-HTML clients still see the message."""
        svc = _make()
        with patch.object(smtplib, "SMTP_SSL") as smtp_cls:
            smtp_ctx = MagicMock()
            smtp_mock = MagicMock()
            smtp_ctx.__enter__.return_value = smtp_mock
            smtp_ctx.__exit__.return_value = False
            smtp_cls.return_value = smtp_ctx

            await svc.send_email(
                to="u@example.com",
                subject="s",
                html_body="<p>Hello <b>world</b></p>",
            )
        sent_msg = smtp_mock.send_message.call_args[0][0]
        # The plaintext alternative is the FIRST set_content call.
        # The HTML alternative is the SECOND. Walk parts for the text/plain.
        text_parts = [
            part.get_payload() for part in sent_msg.iter_parts()
            if part.get_content_type() == "text/plain"
        ]
        # Stripped HTML should yield "Hello world"
        joined = "".join(text_parts) if text_parts else sent_msg.get_payload()
        assert "Hello" in joined
        assert "world" in joined
        assert "<" not in joined


class TestStripHtml:
    def test_strips_tags(self):
        assert _strip_html("<p>Hi</p>") == "Hi"

    def test_collapses_whitespace(self):
        assert _strip_html("<p>foo</p>\n\n  <p>bar</p>") == "foo bar"

    def test_empty_input(self):
        assert _strip_html("") == ""
