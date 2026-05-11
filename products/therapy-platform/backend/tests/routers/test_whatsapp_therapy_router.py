"""
Tests for the WhatsApp Therapy Router.

Covers: send message, send reminder, message history,
configure reminders, list reminder configs, and auth/permission checks.
"""
import pytest

SAMPLE_MESSAGE_LOG = {
    "id": "msg-001",
    "appointment_id": "appt-001",
    "destinatario_telefone": "5511999998888",
    "tipo": "mensagem",
    "conteudo": "Olá, como você está?",
    "status": "enviado",
    "created_at": "2026-04-01T10:00:00Z",
}

SAMPLE_REMINDER_CONFIG = {
    "id": "rc-001",
    "therapist_id": "test-user-123",
    "antecedencia_horas": 24,
    "is_active": True,
}


class TestSendMessage:
    """POST /api/whatsapp/enviar"""

    def test_send_message(self, client):
        """Therapist sends a WhatsApp message."""
        client._mock_supabase.set_table_data("whatsapp_messages", [SAMPLE_MESSAGE_LOG])
        client._mock_supabase.set_table_data("patient_profiles", [
            {"user_id": "patient-001", "phone": "5511999998888", "nome": "João"},
        ])
        resp = client.post("/api/whatsapp/enviar", json={
            "patient_id": "patient-001",
            "message": "Olá, como você está?",
        })
        assert resp.status_code == 200

    def test_send_message_patient_forbidden(self, patient_client):
        """Patient cannot send WhatsApp messages."""
        resp = patient_client.post("/api/whatsapp/enviar", json={
            "patient_id": "patient-001",
            "message": "Teste",
        })
        assert resp.status_code == 403

    def test_send_message_401(self, client):
        """No auth returns 401.

        Body MUST be a complete + valid `WhatsAppSendCreate` so the
        request reaches the auth dependency (otherwise Pydantic 422
        short-circuits before auth fires).
        """
        resp = client._tc.post("/api/whatsapp/enviar", json={
            "patient_id": "patient-001",
            "message": "Teste",
        })
        assert resp.status_code == 401


class TestSendReminder:
    """POST /api/whatsapp/lembrete"""

    def test_send_reminder(self, client):
        """Therapist sends an appointment reminder."""
        client._mock_supabase.set_table_data("whatsapp_messages", [SAMPLE_MESSAGE_LOG])
        client._mock_supabase.set_table_data("patient_profiles", [
            {"user_id": "patient-001", "phone": "5511999998888", "nome": "João"},
        ])
        client._mock_supabase.set_table_data("appointments", [
            {"id": "appt-001", "patient_id": "patient-001", "scheduled_start": "2026-04-10T09:00:00Z"},
        ])
        resp = client.post("/api/whatsapp/lembrete", json={
            "appointment_id": "appt-001",
        })
        assert resp.status_code == 200

    def test_send_reminder_patient_forbidden(self, patient_client):
        """Patient cannot send reminders."""
        resp = patient_client.post("/api/whatsapp/lembrete", json={
            "appointment_id": "appt-001",
        })
        assert resp.status_code == 403


class TestMessageHistory:
    """GET /api/whatsapp/historico"""

    def test_message_history(self, client):
        """Therapist views message history."""
        client._mock_supabase.set_table_data("whatsapp_messages", [SAMPLE_MESSAGE_LOG])
        resp = client.get("/api/whatsapp/historico")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_message_history_with_patient_filter(self, client):
        """Therapist filters history by patient."""
        client._mock_supabase.set_table_data("whatsapp_messages", [SAMPLE_MESSAGE_LOG])
        resp = client.get("/api/whatsapp/historico", params={"patient_id": "patient-001"})
        assert resp.status_code == 200

    def test_message_history_patient_forbidden(self, patient_client):
        """Patient cannot view message history."""
        resp = patient_client.get("/api/whatsapp/historico")
        assert resp.status_code == 403

    def test_message_history_admin_allowed(self, admin_client):
        """Platform admin can view message history."""
        admin_client._mock_supabase.set_table_data("whatsapp_messages", [SAMPLE_MESSAGE_LOG])
        resp = admin_client.get("/api/whatsapp/historico")
        assert resp.status_code == 200


class TestConfigureReminders:
    """POST /api/whatsapp/configurar-lembretes"""

    def test_configure_reminders(self, client):
        """Therapist configures reminders."""
        client._mock_supabase.set_table_data("reminder_schedules", [SAMPLE_REMINDER_CONFIG])
        resp = client.post("/api/whatsapp/configurar-lembretes", json={
            "antecedencia_horas": 24,
            "is_active": True,
        })
        assert resp.status_code == 200

    def test_configure_reminders_patient_forbidden(self, patient_client):
        """Patient cannot configure reminders."""
        resp = patient_client.post("/api/whatsapp/configurar-lembretes", json={
            "antecedencia_horas": 24,
        })
        assert resp.status_code == 403


class TestListReminderConfigs:
    """GET /api/whatsapp/lembretes"""

    def test_list_reminder_configs(self, client):
        """Therapist lists their reminder configs."""
        client._mock_supabase.set_table_data("reminder_schedules", [SAMPLE_REMINDER_CONFIG])
        resp = client.get("/api/whatsapp/lembretes")
        assert resp.status_code == 200

    def test_list_reminder_configs_patient_forbidden(self, patient_client):
        """Patient cannot list reminder configs."""
        resp = patient_client.get("/api/whatsapp/lembretes")
        assert resp.status_code == 403
