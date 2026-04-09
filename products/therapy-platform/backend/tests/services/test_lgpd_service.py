"""
Tests for the LGPD Service — data deletion per Brazilian data protection law.
"""
import pytest
from unittest.mock import patch

from tests.conftest import MockSupabaseClient
from app.services import lgpd_service


@pytest.fixture(autouse=True)
def _mock_log_action():
    """Suppress log_action calls (it uses admin client)."""
    with patch("app.services.lgpd_service.log_action"):
        yield


# ---------------------------------------------------------------------------
# Patient Data Deletion
# ---------------------------------------------------------------------------

class TestDeletePatientData:
    @pytest.mark.asyncio
    async def test_delete_patient_data(self):
        db = MockSupabaseClient()
        db.set_table_data("wallets", [{"id": "wallet-001", "user_id": "patient-001"}])
        db.set_table_data("wallet_movements", [])
        db.set_table_data("messages", [])
        db.set_table_data("conversation_participants", [])
        db.set_table_data("patient_longitudinal_analyses", [])
        db.set_table_data("patient_session_notes", [])
        db.set_table_data("patient_profiles", [])

        result = await lgpd_service.delete_patient_data("patient-001", db)

        assert "patient_profiles" in result["deleted_tables"]
        assert "wallets" in result["deleted_tables"]
        assert "messages" in result["deleted_tables"]
        assert len(result["deleted_tables"]) == 7

    @pytest.mark.asyncio
    async def test_delete_patient_data_keeps_therapist_data(self):
        db = MockSupabaseClient()
        db.set_table_data("wallets", [])
        db.set_table_data("wallet_movements", [])
        db.set_table_data("messages", [])
        db.set_table_data("conversation_participants", [])
        db.set_table_data("patient_longitudinal_analyses", [])
        db.set_table_data("patient_session_notes", [])
        db.set_table_data("patient_profiles", [])

        result = await lgpd_service.delete_patient_data("patient-001", db)

        assert "session_records" in result["kept_tables"]
        assert "session_observations" in result["kept_tables"]
        assert "session_summary_versions" in result["kept_tables"]

    @pytest.mark.asyncio
    async def test_delete_patient_data_with_wallet(self):
        db = MockSupabaseClient()
        db.set_table_data("wallets", [
            {"id": "wallet-001", "user_id": "patient-001"},
            {"id": "wallet-002", "user_id": "patient-001"},
        ])
        db.set_table_data("wallet_movements", [])
        db.set_table_data("messages", [])
        db.set_table_data("conversation_participants", [])
        db.set_table_data("patient_longitudinal_analyses", [])
        db.set_table_data("patient_session_notes", [])
        db.set_table_data("patient_profiles", [])

        result = await lgpd_service.delete_patient_data("patient-001", db)
        assert "wallet_movements" in result["deleted_tables"]
        assert "wallets" in result["deleted_tables"]


# ---------------------------------------------------------------------------
# Therapist Data Deletion
# ---------------------------------------------------------------------------

class TestDeleteTherapistSession:
    @pytest.mark.asyncio
    async def test_delete_session(self):
        db = MockSupabaseClient()
        db.set_table_data("session_records", [
            {"id": "session-001", "therapist_id": "therapist-001"},
        ])
        db.set_table_data("session_observations", [])
        db.set_table_data("session_summary_versions", [])

        result = await lgpd_service.delete_therapist_data(
            "therapist-001", "session", "session-001", db,
        )
        assert "session_records" in result["deleted"]
        assert "session_observations" in result["deleted"]
        assert "session_summary_versions" in result["deleted"]

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("session_records", [])

        with pytest.raises(Exception) as exc_info:
            await lgpd_service.delete_therapist_data(
                "therapist-001", "session", "nonexistent", db,
            )
        assert exc_info.value.status_code == 404


class TestDeleteTherapistObservation:
    @pytest.mark.asyncio
    async def test_delete_observation(self):
        db = MockSupabaseClient()
        db.set_table_data("session_observations", [
            {"id": "obs-001", "therapist_id": "therapist-001"},
        ])

        result = await lgpd_service.delete_therapist_data(
            "therapist-001", "observation", "obs-001", db,
        )
        assert "session_observations" in result["deleted"]

    @pytest.mark.asyncio
    async def test_delete_observation_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("session_observations", [])

        with pytest.raises(Exception) as exc_info:
            await lgpd_service.delete_therapist_data(
                "therapist-001", "observation", "nonexistent", db,
            )
        assert exc_info.value.status_code == 404


class TestDeleteTherapistAll:
    @pytest.mark.asyncio
    async def test_delete_all(self):
        db = MockSupabaseClient()
        db.set_table_data("session_summary_versions", [])
        db.set_table_data("session_observations", [])
        db.set_table_data("session_records", [])
        db.set_table_data("messages", [])
        db.set_table_data("conversation_participants", [])
        db.set_table_data("wallets", [{"id": "w-001", "user_id": "therapist-001"}])
        db.set_table_data("wallet_movements", [])
        db.set_table_data("therapist_settings", [])
        db.set_table_data("therapist_profiles", [])

        result = await lgpd_service.delete_therapist_data(
            "therapist-001", "all", None, db,
        )
        assert "therapist_profiles" in result["deleted"]
        assert "session_records" in result["deleted"]
        assert "wallets" in result["deleted"]
        assert len(result["deleted"]) == 9

    @pytest.mark.asyncio
    async def test_delete_invalid_entity_type(self):
        db = MockSupabaseClient()
        with pytest.raises(Exception) as exc_info:
            await lgpd_service.delete_therapist_data(
                "therapist-001", "invalid", None, db,
            )
        assert exc_info.value.status_code == 400
