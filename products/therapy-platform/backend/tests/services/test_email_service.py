"""
Tests for the Email Service — Resend integration with dry-run fallback.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.services import email_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_settings():
    """Ensure resend_api_key is None by default for dry-run tests.

    Patching `settings.resend_api_key` is config substitution, not logic
    substitution — Settings is a pydantic model whose attributes are values.
    The alternative would be reloading the Settings object via env vars
    (heavier, equally test-only). Documented as the standard pattern.
    """
    with patch.object(email_service.settings, "resend_api_key", None):  # self-patch-ok: settings config knob (pydantic model field, not behavior)
        yield


# ---------------------------------------------------------------------------
# send_email (core)
# ---------------------------------------------------------------------------

class TestSendEmail:
    @pytest.mark.asyncio
    async def test_send_email_dry_run(self):
        """No API key → logs dry-run, returns True."""
        result = await email_service.send_email(
            to="test@example.com",
            subject="Test",
            html="<p>Test</p>",
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_send_email_with_resend(self):
        """With API key → calls Resend API."""
        mock_resend = MagicMock()
        mock_resend.Emails.send = MagicMock(return_value={"id": "email-123"})

        with patch.object(email_service.settings, "resend_api_key", "re_test_key"):  # self-patch-ok: settings config knob (pydantic model field, not behavior)
            with patch.dict("sys.modules", {"resend": mock_resend}):
                result = await email_service.send_email(
                    to="test@example.com",
                    subject="Test Subject",
                    html="<p>Hello</p>",
                )
        assert result is True


# ---------------------------------------------------------------------------
# Template functions
# ---------------------------------------------------------------------------

class TestRegistrationEmail:
    @pytest.mark.asyncio
    async def test_send_registration_email(self):
        result = await email_service.send_registration_email(
            email="novo@example.com",
            nome="João Silva",
            role="therapist",
        )
        assert result is True


class TestBookingConfirmation:
    @pytest.mark.asyncio
    async def test_send_booking_confirmation(self):
        result = await email_service.send_booking_confirmation(
            patient_email="paciente@example.com",
            therapist_name="Dra. Maria",
            scheduled_start="2026-04-10T14:00:00Z",
            meeting_link="https://meet.example.com/abc123",
        )
        assert result is True


class TestCancellationEmail:
    @pytest.mark.asyncio
    async def test_send_cancellation_charged(self):
        result = await email_service.send_cancellation_email(
            email="paciente@example.com",
            nome="João",
            scheduled_start="2026-04-10T14:00:00Z",
            charged=True,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_send_cancellation_free(self):
        result = await email_service.send_cancellation_email(
            email="paciente@example.com",
            nome="João",
            scheduled_start="2026-04-10T14:00:00Z",
            charged=False,
        )
        assert result is True


class TestRefundNotification:
    @pytest.mark.asyncio
    async def test_send_refund_approved(self):
        result = await email_service.send_refund_notification(
            email="paciente@example.com",
            nome="João",
            amount="150.00",
            approved=True,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_send_refund_denied(self):
        result = await email_service.send_refund_notification(
            email="paciente@example.com",
            nome="João",
            amount="150.00",
            approved=False,
            reason="Fora do prazo de reembolso",
        )
        assert result is True
