"""Tests for the email service."""
import pytest
from unittest.mock import MagicMock, patch

from app.services.email_service import (
    send_invitation_email,
    send_welcome_email,
    send_billing_alert,
    _send,
    FROM_EMAIL,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_resend(success=True):
    """Create a mock Resend module."""
    mock = MagicMock()
    if not success:
        mock.Emails.send.side_effect = Exception("Resend API error")
    return mock


# ---------------------------------------------------------------------------
# _send() tests
# ---------------------------------------------------------------------------


class TestSendInternal:
    """Tests for the internal _send() function."""

    def test_send_returns_false_when_no_provider(self):
        """_send() returns False when Resend is not configured."""
        with patch("app.services.email_service._get_resend", return_value=None):
            result = _send("user@example.com", "Subject", "<p>Body</p>")

        assert result is False

    def test_send_calls_resend_emails_send(self):
        """_send() calls Resend Emails.send with correct params."""
        mock_resend = _mock_resend()

        with patch("app.services.email_service._get_resend", return_value=mock_resend):
            result = _send("user@example.com", "Test Subject", "<p>Hello</p>")

        assert result is True
        mock_resend.Emails.send.assert_called_once_with({
            "from": FROM_EMAIL,
            "to": ["user@example.com"],
            "subject": "Test Subject",
            "html": "<p>Hello</p>",
        })

    def test_send_returns_false_on_exception(self):
        """_send() catches exceptions and returns False."""
        mock_resend = _mock_resend(success=False)

        with patch("app.services.email_service._get_resend", return_value=mock_resend):
            result = _send("user@example.com", "Subject", "<p>Body</p>")

        assert result is False


# ---------------------------------------------------------------------------
# _get_resend() tests
# ---------------------------------------------------------------------------


class TestGetResend:
    """Tests for the lazy Resend client initialization."""

    def test_returns_none_when_no_api_key(self):
        """_get_resend() returns None when RESEND_API_KEY is not set."""
        import app.services.email_service as mod
        mod._resend = None  # Reset cached state

        mock_settings = MagicMock()
        mock_settings.resend_api_key = None

        with (
            patch.dict("sys.modules", {"resend": MagicMock()}),
            patch("app.services.email_service.settings", mock_settings, create=True),
            patch("app.config.settings", mock_settings),
        ):
            result = mod._get_resend()

        assert result is None
        # Clean up
        mod._resend = None

    def test_returns_none_when_resend_not_installed(self):
        """_get_resend() returns None when resend package is missing."""
        import app.services.email_service as mod
        mod._resend = None  # Reset cached state

        with patch.dict("sys.modules", {"resend": None}):
            # Force re-import failure
            import builtins
            original_import = builtins.__import__

            def _mock_import(name, *args, **kwargs):
                if name == "resend":
                    raise ImportError("No module named 'resend'")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=_mock_import):
                result = mod._get_resend()

        assert result is None
        # Clean up
        mod._resend = None

    def test_caches_result(self):
        """_get_resend() caches the client after first call."""
        import app.services.email_service as mod
        sentinel = MagicMock()
        mod._resend = sentinel

        result = mod._get_resend()
        assert result is sentinel
        # Clean up
        mod._resend = None


# ---------------------------------------------------------------------------
# send_invitation_email() tests
# ---------------------------------------------------------------------------


class TestSendInvitationEmail:
    """Tests for the invitation email function."""

    def test_sends_invitation_email(self):
        """send_invitation_email() sends with correct subject and invite URL."""
        mock_resend = _mock_resend()

        with patch("app.services.email_service._get_resend", return_value=mock_resend):
            result = send_invitation_email(
                to="new@example.com",
                org_name="Acme Corp",
                invite_token="tok-abc",
                invited_by="John",
            )

        assert result is True
        call_args = mock_resend.Emails.send.call_args[0][0]
        assert call_args["to"] == ["new@example.com"]
        assert "Acme Corp" in call_args["subject"]
        assert "invite/tok-abc" in call_args["html"]
        assert "John" in call_args["html"]

    def test_uses_custom_base_url(self):
        """send_invitation_email() uses the provided base_url."""
        mock_resend = _mock_resend()

        with patch("app.services.email_service._get_resend", return_value=mock_resend):
            send_invitation_email(
                to="new@example.com",
                org_name="Acme",
                invite_token="tok-xyz",
                invited_by="Jane",
                base_url="https://app.noctusai.com",
            )

        call_args = mock_resend.Emails.send.call_args[0][0]
        assert "https://app.noctusai.com/invite/tok-xyz" in call_args["html"]

    def test_returns_false_when_not_configured(self):
        """send_invitation_email() returns False when Resend is not set up."""
        with patch("app.services.email_service._get_resend", return_value=None):
            result = send_invitation_email(
                to="new@example.com",
                org_name="Acme",
                invite_token="tok",
                invited_by="Admin",
            )

        assert result is False


# ---------------------------------------------------------------------------
# send_welcome_email() tests
# ---------------------------------------------------------------------------


class TestSendWelcomeEmail:
    """Tests for the welcome email function."""

    def test_sends_welcome_email(self):
        """send_welcome_email() sends with user name and org name."""
        mock_resend = _mock_resend()

        with patch("app.services.email_service._get_resend", return_value=mock_resend):
            result = send_welcome_email(
                to="user@example.com",
                user_name="Maria",
                org_name="StartupX",
            )

        assert result is True
        call_args = mock_resend.Emails.send.call_args[0][0]
        assert "Maria" in call_args["subject"]
        assert "StartupX" in call_args["html"]

    def test_returns_false_when_not_configured(self):
        """send_welcome_email() returns False without Resend."""
        with patch("app.services.email_service._get_resend", return_value=None):
            result = send_welcome_email("u@e.com", "User", "Org")

        assert result is False


# ---------------------------------------------------------------------------
# send_billing_alert() tests
# ---------------------------------------------------------------------------


class TestSendBillingAlert:
    """Tests for the billing alert email function."""

    def test_payment_failed_subject(self):
        """send_billing_alert() uses correct subject for payment_failed."""
        mock_resend = _mock_resend()

        with patch("app.services.email_service._get_resend", return_value=mock_resend):
            result = send_billing_alert(
                to="admin@example.com",
                event_type="invoice.payment_failed",
                org_name="CorpZ",
            )

        assert result is True
        call_args = mock_resend.Emails.send.call_args[0][0]
        assert "Falha no pagamento" in call_args["subject"]
        assert "CorpZ" in call_args["subject"]

    def test_subscription_deleted_subject(self):
        """send_billing_alert() uses correct subject for subscription deleted."""
        mock_resend = _mock_resend()

        with patch("app.services.email_service._get_resend", return_value=mock_resend):
            send_billing_alert(
                to="admin@example.com",
                event_type="customer.subscription.deleted",
                org_name="OrgY",
            )

        call_args = mock_resend.Emails.send.call_args[0][0]
        assert "cancelada" in call_args["subject"]

    def test_subscription_updated_subject(self):
        """send_billing_alert() uses correct subject for subscription updated."""
        mock_resend = _mock_resend()

        with patch("app.services.email_service._get_resend", return_value=mock_resend):
            send_billing_alert(
                to="admin@example.com",
                event_type="customer.subscription.updated",
                org_name="OrgW",
            )

        call_args = mock_resend.Emails.send.call_args[0][0]
        assert "atualizada" in call_args["subject"]

    def test_unknown_event_type_uses_fallback(self):
        """send_billing_alert() uses fallback subject for unknown event types."""
        mock_resend = _mock_resend()

        with patch("app.services.email_service._get_resend", return_value=mock_resend):
            send_billing_alert(
                to="admin@example.com",
                event_type="some.unknown.event",
                org_name="OrgV",
            )

        call_args = mock_resend.Emails.send.call_args[0][0]
        assert "Alerta de cobrança" in call_args["subject"]

    def test_returns_false_when_not_configured(self):
        """send_billing_alert() returns False without Resend."""
        with patch("app.services.email_service._get_resend", return_value=None):
            result = send_billing_alert("a@e.com", "invoice.payment_failed", "Org")

        assert result is False
