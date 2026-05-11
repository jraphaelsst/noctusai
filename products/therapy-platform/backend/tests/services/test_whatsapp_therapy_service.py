"""
Tests for the WhatsApp Therapy Service.

Covers: message formatting, send_via_waha (mock httpx),
send_reminder workflow, log_message.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import MockSupabaseClient
from app.services import whatsapp_therapy_service


SAMPLE_APPOINTMENT = {
    "id": "appt-001",
    "patient_id": "patient-001",
    "scheduled_start": "2026-04-10T09:00:00Z",
}

SAMPLE_PATIENT = {
    "user_id": "patient-001",
    "phone": "5511999998888",
    "nome": "João Silva",
}


# ---------------------------------------------------------------------------
# Message Formatting
# ---------------------------------------------------------------------------

class TestFormatReminderMessage:
    def test_format_with_valid_date(self):
        msg = whatsapp_therapy_service._format_reminder_message(SAMPLE_APPOINTMENT)
        assert "2026-04-10" in msg
        assert "09:00" in msg
        assert "Lembrete" in msg

    def test_format_with_short_date(self):
        appt = {"scheduled_start": "2026-04-10"}
        msg = whatsapp_therapy_service._format_reminder_message(appt)
        assert "2026-04-10" in msg

    def test_format_with_empty_date(self):
        appt = {"scheduled_start": ""}
        msg = whatsapp_therapy_service._format_reminder_message(appt)
        assert "Lembrete" in msg


# ---------------------------------------------------------------------------
# WAHA Integration
# ---------------------------------------------------------------------------

class TestSendViaWaha:
    """Therapy's `send_via_waha` delegates HTTP transport to the seed
    `noctusai_lib.integrations.whatsapp.WahaClient`. Tests patch `httpx.AsyncClient`
    at the seed-lib import site (external integration boundary) — never the
    product's `send_via_waha` itself, per the no-monkey-patching rule."""

    @pytest.mark.asyncio
    async def test_send_success(self):
        from noctusai_lib.integrations.whatsapp import client as waha_client_module

        captured_post: dict = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"id": "msg-123", "status": "sent"}

        async def fake_post(path, json=None, headers=None):
            captured_post["path"] = path
            captured_post["json"] = json
            captured_post["headers"] = headers
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = fake_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(
            waha_client_module.httpx, "AsyncClient", lambda **_: mock_client,
        ):
            result = await whatsapp_therapy_service.send_via_waha(
                waha_url="http://localhost:3000",
                session_name="default",
                phone="5511999998888",
                message="Olá!",
            )
            # Status + body assertions (status-code-assertion-rule analog).
            assert result["status"] == "sent"
            assert result["id"] == "msg-123"
            assert captured_post["path"] == "/api/sendText"
            assert captured_post["json"] == {
                "session": "default",
                "chatId": "5511999998888@c.us",
                "text": "Olá!",
            }

    @pytest.mark.asyncio
    async def test_send_api_error(self):
        import httpx
        from noctusai_lib.integrations.whatsapp import client as waha_client_module

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "500 Internal Server Error", request=MagicMock(), response=mock_response,
            ),
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(
            waha_client_module.httpx, "AsyncClient", lambda **_: mock_client,
        ):
            with pytest.raises(ValueError, match="Erro ao enviar mensagem via WAHA"):
                await whatsapp_therapy_service.send_via_waha(
                    waha_url="http://localhost:3000",
                    session_name="default",
                    phone="5511999998888",
                    message="Olá!",
                )


# ---------------------------------------------------------------------------
# Send Reminder
# ---------------------------------------------------------------------------

class TestSendReminder:
    @pytest.mark.asyncio
    async def test_send_reminder_dry_run(self):
        """Without WAHA URL, performs dry run."""
        db = MockSupabaseClient()
        db.set_table_data("patient_profiles", [SAMPLE_PATIENT])
        db.set_table_data("whatsapp_messages", [{"id": "msg-001"}])
        result = await whatsapp_therapy_service.send_reminder(
            appointment=SAMPLE_APPOINTMENT,
            db=db,
            waha_url=None,
        )
        assert result["status"] == "dry_run"
        assert result["phone"] == "5511999998888"

    @pytest.mark.asyncio
    async def test_send_reminder_no_phone(self):
        """Patient without phone returns skipped."""
        db = MockSupabaseClient()
        no_phone = {**SAMPLE_PATIENT, "phone": None}
        db.set_table_data("patient_profiles", [no_phone])
        result = await whatsapp_therapy_service.send_reminder(
            appointment=SAMPLE_APPOINTMENT,
            db=db,
        )
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_send_reminder_no_patient(self):
        """Appointment without patient_id raises error."""
        db = MockSupabaseClient()
        appt = {"id": "appt-001"}
        with pytest.raises(ValueError, match="Agendamento sem paciente"):
            await whatsapp_therapy_service.send_reminder(
                appointment=appt,
                db=db,
            )


# ---------------------------------------------------------------------------
# Log Message
# ---------------------------------------------------------------------------

class TestLogMessage:
    @pytest.mark.asyncio
    async def test_log_message(self):
        db = MockSupabaseClient()
        db.set_table_data("whatsapp_messages", [{"id": "msg-001"}])
        result = await whatsapp_therapy_service.log_message(
            data={
                "appointment_id": "appt-001",
                "destinatario_telefone": "5511999998888",
                "tipo": "lembrete",
                "conteudo": "Olá!",
                "status": "enviado",
            },
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_log_message_error_returns_none(self):
        """Logging errors should not raise, just return None."""
        db = MockSupabaseClient()
        # Simulate DB error by making table raise
        original_table = db.table

        def broken_table(name):
            if name == "whatsapp_messages":
                raise Exception("DB error")
            return original_table(name)

        db.table = broken_table
        result = await whatsapp_therapy_service.log_message(
            data={"tipo": "lembrete"},
            db=db,
        )
        assert result is None
