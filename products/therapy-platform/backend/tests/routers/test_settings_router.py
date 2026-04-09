"""
Tests for the Settings Router — platform settings, AI prompts, branding, therapist/patient prefs.
"""
import pytest


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_PLATFORM_SETTINGS = [
    {"key": "global_commission_rate", "value": "15.0"},
    {"key": "app_name", "value": "NoctusAI Therapy"},
]

SAMPLE_AI_PROMPT = {
    "prompt_key": "session_summary",
    "prompt_text": "Resuma a sessão terapêutica com foco nos pontos-chave discutidos.",
    "updated_by": "test-user-123",
}

SAMPLE_AI_PROMPT_HISTORY = [
    {
        "prompt_key": "session_summary",
        "prompt_text": "Versão anterior do prompt de resumo.",
        "changed_by": "test-user-123",
        "created_at": "2026-03-01T10:00:00Z",
    },
    {
        "prompt_key": "session_summary",
        "prompt_text": "Versão mais antiga.",
        "changed_by": "test-user-123",
        "created_at": "2026-02-01T10:00:00Z",
    },
]

SAMPLE_THERAPIST_SETTINGS = {
    "user_id": "test-user-123",
    "bank_name": "Banco do Brasil",
    "bank_agency": "1234",
    "bank_account": "56789-0",
    "pix_key": "terapeuta@email.com",
}

SAMPLE_CLINIC_BRANDING = {
    "clinic_id": "test-clinic-123",
    "primary_color": "#1e40af",
    "secondary_color": "#3b82f6",
    "logo_url": "https://cdn.example.com/logo.png",
    "favicon_url": None,
}

SAMPLE_PATIENT_SETTINGS = {
    "user_id": "test-user-123",
    "phone": "+5511999999999",
    "photo_url": "https://cdn.example.com/photo.jpg",
    "notification_preferences": {"email": True, "push": False},
}


# ---------------------------------------------------------------------------
# Platform Settings (Admin only)
# ---------------------------------------------------------------------------

class TestPlatformSettings:
    def test_get_platform_settings_as_admin(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "platform_settings", SAMPLE_PLATFORM_SETTINGS,
        )
        resp = admin_client.get("/api/settings/platform")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2

    def test_get_platform_settings_as_therapist_forbidden(self, client):
        resp = client.get("/api/settings/platform")
        assert resp.status_code == 403

    def test_get_platform_settings_as_patient_forbidden(self, patient_client):
        resp = patient_client.get("/api/settings/platform")
        assert resp.status_code == 403

    def test_get_platform_settings_no_auth(self, client):
        resp = client._tc.get("/api/settings/platform")
        assert resp.status_code == 401

    def test_update_platform_setting(self, admin_client):
        admin_client._mock_supabase.set_table_data("platform_settings", [
            {"key": "global_commission_rate", "value": "20.0"},
        ])
        admin_client._mock_supabase.set_table_data("settings_history", [
            {"setting_type": "platform", "setting_key": "global_commission_rate"},
        ])
        resp = admin_client.patch("/api/settings/platform", json={
            "key": "global_commission_rate",
            "value": "20.0",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["key"] == "global_commission_rate"

    def test_update_platform_setting_as_therapist_forbidden(self, client):
        resp = client.patch("/api/settings/platform", json={
            "key": "global_commission_rate",
            "value": "20.0",
        })
        assert resp.status_code == 403

    def test_update_platform_setting_no_auth(self, client):
        resp = client._tc.patch(
            "/api/settings/platform",
            json={"key": "test", "value": "val"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# AI Prompts (Admin only)
# ---------------------------------------------------------------------------

class TestAIPrompts:
    def test_get_ai_prompts_as_admin(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "ai_prompt_settings", [SAMPLE_AI_PROMPT],
        )
        resp = admin_client.get("/api/settings/platform/ai-prompts")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["prompt_key"] == "session_summary"

    def test_get_ai_prompts_as_therapist_forbidden(self, client):
        resp = client.get("/api/settings/platform/ai-prompts")
        assert resp.status_code == 403

    def test_update_ai_prompt(self, admin_client):
        admin_client._mock_supabase.set_table_data("ai_prompt_settings", [
            SAMPLE_AI_PROMPT,
        ])
        admin_client._mock_supabase.set_table_data("ai_prompt_history", [
            {"prompt_key": "session_summary", "prompt_text": SAMPLE_AI_PROMPT["prompt_text"]},
        ])
        resp = admin_client.patch("/api/settings/platform/ai-prompts", json={
            "prompt_key": "session_summary",
            "prompt_text": "Novo prompt atualizado para resumo de sessão terapêutica.",
        })
        assert resp.status_code == 200

    def test_update_ai_prompt_too_short(self, admin_client):
        resp = admin_client.patch("/api/settings/platform/ai-prompts", json={
            "prompt_key": "session_summary",
            "prompt_text": "Curto",
        })
        assert resp.status_code == 422

    def test_get_ai_prompt_history(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "ai_prompt_history", SAMPLE_AI_PROMPT_HISTORY,
        )
        resp = admin_client.get(
            "/api/settings/platform/ai-prompts/history",
            params={"prompt_key": "session_summary"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2

    def test_get_ai_prompt_history_no_auth(self, client):
        resp = client._tc.get(
            "/api/settings/platform/ai-prompts/history",
            params={"prompt_key": "session_summary"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Therapist Settings
# ---------------------------------------------------------------------------

class TestTherapistSettings:
    def test_get_therapist_settings(self, client):
        client._mock_supabase.set_table_data(
            "therapist_settings", [SAMPLE_THERAPIST_SETTINGS],
        )
        resp = client.get("/api/settings/therapist")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["bank_name"] == "Banco do Brasil"

    def test_get_therapist_settings_empty(self, client):
        client._mock_supabase.set_table_data("therapist_settings", [])
        resp = client.get("/api/settings/therapist")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_id"] == "test-user-123"

    def test_update_therapist_settings(self, client):
        client._mock_supabase.set_table_data("therapist_settings", [
            {**SAMPLE_THERAPIST_SETTINGS, "pix_key": "nova-chave@email.com"},
        ])
        resp = client.patch("/api/settings/therapist", json={
            "pix_key": "nova-chave@email.com",
        })
        assert resp.status_code == 200

    def test_get_therapist_settings_as_patient_forbidden(self, patient_client):
        resp = patient_client.get("/api/settings/therapist")
        assert resp.status_code == 403

    def test_update_therapist_settings_no_auth(self, client):
        resp = client._tc.patch(
            "/api/settings/therapist",
            json={"bank_name": "Itaú"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Clinic Branding
# ---------------------------------------------------------------------------

class TestClinicBranding:
    def test_get_clinic_branding(self, clinic_admin_client):
        clinic_admin_client._mock_supabase.set_table_data(
            "clinic_branding", [SAMPLE_CLINIC_BRANDING],
        )
        resp = clinic_admin_client.get("/api/settings/clinic/branding")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["primary_color"] == "#1e40af"

    def test_update_clinic_branding(self, clinic_admin_client):
        clinic_admin_client._mock_supabase.set_table_data("clinic_branding", [
            {**SAMPLE_CLINIC_BRANDING, "primary_color": "#dc2626"},
        ])
        resp = clinic_admin_client.patch("/api/settings/clinic/branding", json={
            "primary_color": "#dc2626",
        })
        assert resp.status_code == 200

    def test_get_clinic_branding_as_therapist_forbidden(self, client):
        resp = client.get("/api/settings/clinic/branding")
        assert resp.status_code == 403

    def test_update_clinic_branding_no_auth(self, client):
        resp = client._tc.patch(
            "/api/settings/clinic/branding",
            json={"primary_color": "#000000"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Patient Settings
# ---------------------------------------------------------------------------

class TestPatientSettings:
    def test_get_patient_settings(self, patient_client):
        patient_client._mock_supabase.set_table_data("patient_profiles", [
            SAMPLE_PATIENT_SETTINGS,
        ])
        resp = patient_client.get("/api/settings/patient")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["phone"] == "+5511999999999"

    def test_update_patient_settings(self, patient_client):
        patient_client._mock_supabase.set_table_data("patient_profiles", [
            {**SAMPLE_PATIENT_SETTINGS, "phone": "+5511888888888"},
        ])
        resp = patient_client.patch("/api/settings/patient", json={
            "phone": "+5511888888888",
        })
        assert resp.status_code == 200

    def test_get_patient_settings_as_therapist_forbidden(self, client):
        resp = client.get("/api/settings/patient")
        assert resp.status_code == 403

    def test_update_patient_settings_no_auth(self, client):
        resp = client._tc.patch(
            "/api/settings/patient",
            json={"phone": "+5511999999999"},
        )
        assert resp.status_code == 401
