"""
Tests for the Settings Router — platform settings, branding, therapist/patient prefs.

AI prompts are stored as `platform_settings` rows with `ai_prompt_*` keys;
admins edit them through the generic PATCH /platform endpoint, which is
exercised by `TestPlatformSettings::test_update_platform_setting`. The
prior dedicated /platform/ai-prompts* endpoints (referencing phantom
`ai_prompt_settings` / `ai_prompt_history` tables) were removed by
`therapy-platform-drift-sweep` on 2026-05-11.
"""
import pytest


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_PLATFORM_SETTINGS = [
    {"key": "global_commission_rate", "value": "15.0"},
    {"key": "app_name", "value": "NoctusAI Therapy"},
    {"key": "ai_prompt_base_summary", "value": "Resuma a sessao..."},
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
        # Includes ai_prompt_* keys (stored as platform_settings rows).
        assert len(data) == len(SAMPLE_PLATFORM_SETTINGS)
        keys = {row["key"] for row in data}
        assert "ai_prompt_base_summary" in keys

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
        # `prior` snapshot read (single row) then upsert response.
        admin_client._mock_supabase.set_table_data("platform_settings", [
            {"key": "global_commission_rate", "value": "15.0"},
        ])
        resp = admin_client.patch("/api/settings/platform", json={
            "key": "global_commission_rate",
            "value": "20.0",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["key"] == "global_commission_rate"

    def test_update_platform_setting_writes_history_row(self, admin_client):
        """Verify the history-row insert uses the canonical column shape
        (setting_key / old_value / new_value / changed_by_admin_id)."""
        admin_client._mock_supabase.set_table_data("platform_settings", [
            {"key": "global_commission_rate", "value": "15.0"},
        ])
        resp = admin_client.patch("/api/settings/platform", json={
            "key": "global_commission_rate",
            "value": "20.0",
        })
        assert resp.status_code == 200
        history_payloads = (
            admin_client._mock_supabase.table("platform_settings_history").inserted_payloads
        )
        assert len(history_payloads) == 1
        row = history_payloads[0]
        assert row["setting_key"] == "global_commission_rate"
        assert row["new_value"] == "20.0"
        assert "changed_by_admin_id" in row
        # Older legacy columns must NOT appear.
        assert "setting_type" not in row
        assert "changed_by" not in row

    def test_update_ai_prompt_via_platform_endpoint(self, admin_client):
        """AI prompts edit through the generic /platform PATCH — confirms
        the unified surface works for keys like `ai_prompt_base_summary`."""
        admin_client._mock_supabase.set_table_data("platform_settings", [
            {"key": "ai_prompt_base_summary", "value": "old prompt"},
        ])
        resp = admin_client.patch("/api/settings/platform", json={
            "key": "ai_prompt_base_summary",
            "value": "Novo prompt para resumo de sessao terapeutica.",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["key"] == "ai_prompt_base_summary"

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
