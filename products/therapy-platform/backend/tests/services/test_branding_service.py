"""
Tests for the Branding Service — clinic and platform branding.
"""
import pytest

from tests.conftest import MockSupabaseClient
from app.services import branding_service


# ---------------------------------------------------------------------------
# Clinic Branding
# ---------------------------------------------------------------------------

class TestGetClinicBranding:
    @pytest.mark.asyncio
    async def test_get_clinic_branding_exists(self):
        db = MockSupabaseClient()
        db.set_table_data("clinic_branding", [{
            "clinic_id": "clinic-001",
            "primary_color": "#1e40af",
            "secondary_color": "#3b82f6",
            "logo_url": "https://cdn.example.com/logo.png",
            "favicon_url": None,
        }])
        result = await branding_service.get_clinic_branding("clinic-001", db)
        assert result["primary_color"] == "#1e40af"
        assert result["clinic_id"] == "clinic-001"

    @pytest.mark.asyncio
    async def test_get_clinic_branding_defaults(self):
        db = MockSupabaseClient()
        db.set_table_data("clinic_branding", [])
        result = await branding_service.get_clinic_branding("clinic-new", db)
        assert result["clinic_id"] == "clinic-new"
        assert result["primary_color"] == "#6366f1"  # default


class TestUpdateClinicBranding:
    @pytest.mark.asyncio
    async def test_update_clinic_branding(self):
        db = MockSupabaseClient()
        db.set_table_data("clinic_branding", [{
            "clinic_id": "clinic-001",
            "primary_color": "#dc2626",
            "secondary_color": "#3b82f6",
        }])
        result = await branding_service.update_clinic_branding(
            "clinic-001",
            {"primary_color": "#dc2626"},
            db,
        )
        assert result["clinic_id"] == "clinic-001"


# ---------------------------------------------------------------------------
# Platform Branding
# ---------------------------------------------------------------------------

class TestGetPlatformBranding:
    @pytest.mark.asyncio
    async def test_get_platform_branding(self):
        db = MockSupabaseClient()
        db.set_table_data("platform_settings", [
            {"key": "app_name", "value": "Minha Clínica"},
        ])
        result = await branding_service.get_platform_branding(db)
        assert result["app_name"] == "Minha Clínica"
        # Defaults for keys not in DB
        assert result["primary_color"] == "#6366f1"

    @pytest.mark.asyncio
    async def test_get_platform_branding_empty(self):
        db = MockSupabaseClient()
        db.set_table_data("platform_settings", [])
        result = await branding_service.get_platform_branding(db)
        assert result["app_name"] == "NoctusAI Therapy"
