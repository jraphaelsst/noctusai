"""
Tests for the AI Pipeline Service.

Covers: process_session_end (full pipeline, transcription failure,
session record creation failure, summary failure, longitudinal failures,
initial observation), on_observation_change, on_patient_note_change.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import MockSupabaseClient
from app.services import ai_pipeline


SAMPLE_APPOINTMENT = {
    "id": "appt-001",
    "therapist_id": "therapist-001",
    "patient_id": "patient-001",
    "scheduled_start": "2026-04-01T14:00:00-03:00",
    "scheduled_end": "2026-04-01T14:50:00-03:00",
    "status": "completed",
    "clinic_id": None,
}

SAMPLE_SESSION_RECORD = {
    "id": "sr-001",
    "appointment_id": "appt-001",
    "therapist_id": "therapist-001",
    "patient_id": "patient-001",
    "combined_transcript": "Transcrição completa.",
    "ai_generated_at": "2026-04-01T15:00:00-03:00",
}

SAMPLE_OBSERVATION = {
    "id": "obs-001",
    "session_record_id": "sr-001",
    "therapist_id": "therapist-001",
    "observation_text": "Paciente apresentou progresso.",
    "is_initial": True,
}


# ---------------------------------------------------------------------------
# process_session_end
# ---------------------------------------------------------------------------

class TestProcessSessionEnd:
    @pytest.mark.asyncio
    async def test_full_pipeline_success(self):
        """Happy path: all steps complete without errors."""
        db = MockSupabaseClient()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        db.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        db.set_table_data("session_observations", [SAMPLE_OBSERVATION])
        db.set_table_data("session_audio_segments", [])

        with (
            patch.object(
                ai_pipeline.transcription_service,
                "assemble_transcript",
                new_callable=AsyncMock,
                return_value="Transcrição completa.",
            ),
            patch.object(
                ai_pipeline.summary_service,
                "generate_session_summaries",
                new_callable=AsyncMock,
                return_value={"base": {"id": "sum-b"}, "clinical": {"id": "sum-c"}},
            ),
            patch.object(
                ai_pipeline.longitudinal_service,
                "generate_clinical_longitudinal",
                new_callable=AsyncMock,
                return_value={"id": "long-clinical"},
            ),
            patch.object(
                ai_pipeline.longitudinal_service,
                "generate_patient_longitudinal",
                new_callable=AsyncMock,
                return_value={"id": "long-patient"},
            ),
        ):
            result = await ai_pipeline.process_session_end(
                appointment_id="appt-001",
                initial_observation="Observação inicial.",
                source="manual",
                db=db,
            )

        assert "session_record" in result
        assert "summaries" in result
        assert "clinical_longitudinal" in result
        assert "patient_longitudinal" in result
        assert result["clinical_longitudinal"] == {"id": "long-clinical"}
        assert result["patient_longitudinal"] == {"id": "long-patient"}

    @pytest.mark.asyncio
    async def test_appointment_not_found(self):
        """Returns error when appointment does not exist."""
        db = MockSupabaseClient()
        db.set_table_data("appointments", [])

        result = await ai_pipeline.process_session_end(
            appointment_id="nonexistent",
            initial_observation=None,
            source="manual",
            db=db,
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_session_record_creation_fails(self):
        """Returns error when session record insert fails."""
        db = MockSupabaseClient()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        db.set_table_data("session_records", [])  # insert returns empty

        with patch.object(
            ai_pipeline.transcription_service,
            "assemble_transcript",
            new_callable=AsyncMock,
            return_value="Transcrição.",
        ):
            result = await ai_pipeline.process_session_end(
                appointment_id="appt-001",
                initial_observation=None,
                source="auto",
                db=db,
            )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_transcription_failure_produces_error_text(self):
        """Transcription failure is caught, pipeline continues with error text."""
        db = MockSupabaseClient()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        db.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        db.set_table_data("session_observations", [])
        db.set_table_data("session_audio_segments", [])

        with (
            patch.object(
                ai_pipeline.transcription_service,
                "assemble_transcript",
                new_callable=AsyncMock,
                side_effect=Exception("Transcription service unavailable"),
            ),
            patch.object(
                ai_pipeline.summary_service,
                "generate_session_summaries",
                new_callable=AsyncMock,
                return_value={"base": {}, "clinical": {}},
            ),
            patch.object(
                ai_pipeline.longitudinal_service,
                "generate_clinical_longitudinal",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                ai_pipeline.longitudinal_service,
                "generate_patient_longitudinal",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await ai_pipeline.process_session_end(
                appointment_id="appt-001",
                initial_observation=None,
                source="auto",
                db=db,
            )

        # Pipeline should still complete (error handled gracefully)
        assert "session_record" in result

    @pytest.mark.asyncio
    async def test_no_initial_observation(self):
        """Pipeline works without an initial observation."""
        db = MockSupabaseClient()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        db.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        db.set_table_data("session_audio_segments", [])

        with (
            patch.object(
                ai_pipeline.transcription_service,
                "assemble_transcript",
                new_callable=AsyncMock,
                return_value="Texto.",
            ),
            patch.object(
                ai_pipeline.summary_service,
                "generate_session_summaries",
                new_callable=AsyncMock,
                return_value={"base": {}, "clinical": {}},
            ),
            patch.object(
                ai_pipeline.longitudinal_service,
                "generate_clinical_longitudinal",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                ai_pipeline.longitudinal_service,
                "generate_patient_longitudinal",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await ai_pipeline.process_session_end(
                appointment_id="appt-001",
                initial_observation=None,
                source="manual",
                db=db,
            )

        assert "session_record" in result

    @pytest.mark.asyncio
    async def test_whitespace_only_observation_skipped(self):
        """Blank observation is treated as no observation."""
        db = MockSupabaseClient()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        db.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        db.set_table_data("session_audio_segments", [])

        with (
            patch.object(
                ai_pipeline.transcription_service,
                "assemble_transcript",
                new_callable=AsyncMock,
                return_value="Texto.",
            ),
            patch.object(
                ai_pipeline.summary_service,
                "generate_session_summaries",
                new_callable=AsyncMock,
                return_value={"base": {}, "clinical": {}},
            ),
            patch.object(
                ai_pipeline.longitudinal_service,
                "generate_clinical_longitudinal",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                ai_pipeline.longitudinal_service,
                "generate_patient_longitudinal",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await ai_pipeline.process_session_end(
                appointment_id="appt-001",
                initial_observation="   ",
                source="manual",
                db=db,
            )

        assert "session_record" in result

    @pytest.mark.asyncio
    async def test_summary_failure_caught(self):
        """Summary generation failure is caught, pipeline continues."""
        db = MockSupabaseClient()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        db.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        db.set_table_data("session_audio_segments", [])

        with (
            patch.object(
                ai_pipeline.transcription_service,
                "assemble_transcript",
                new_callable=AsyncMock,
                return_value="Texto.",
            ),
            patch.object(
                ai_pipeline.summary_service,
                "generate_session_summaries",
                new_callable=AsyncMock,
                side_effect=Exception("OpenAI rate limit"),
            ),
            patch.object(
                ai_pipeline.longitudinal_service,
                "generate_clinical_longitudinal",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                ai_pipeline.longitudinal_service,
                "generate_patient_longitudinal",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await ai_pipeline.process_session_end(
                appointment_id="appt-001",
                initial_observation=None,
                source="manual",
                db=db,
            )

        # Summaries should have error keys
        assert "error" in result["summaries"]["base"]
        assert "error" in result["summaries"]["clinical"]

    @pytest.mark.asyncio
    async def test_longitudinal_failure_caught(self):
        """Longitudinal failures are caught individually."""
        db = MockSupabaseClient()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        db.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        db.set_table_data("session_audio_segments", [])

        with (
            patch.object(
                ai_pipeline.transcription_service,
                "assemble_transcript",
                new_callable=AsyncMock,
                return_value="Texto.",
            ),
            patch.object(
                ai_pipeline.summary_service,
                "generate_session_summaries",
                new_callable=AsyncMock,
                return_value={"base": {}, "clinical": {}},
            ),
            patch.object(
                ai_pipeline.longitudinal_service,
                "generate_clinical_longitudinal",
                new_callable=AsyncMock,
                side_effect=Exception("Clinical longitudinal error"),
            ),
            patch.object(
                ai_pipeline.longitudinal_service,
                "generate_patient_longitudinal",
                new_callable=AsyncMock,
                side_effect=Exception("Patient longitudinal error"),
            ),
        ):
            result = await ai_pipeline.process_session_end(
                appointment_id="appt-001",
                initial_observation=None,
                source="manual",
                db=db,
            )

        assert result["clinical_longitudinal"] is None
        assert result["patient_longitudinal"] is None


# ---------------------------------------------------------------------------
# on_observation_change
# ---------------------------------------------------------------------------

class TestOnObservationChange:
    @pytest.mark.asyncio
    async def test_regenerates_clinical_summary_and_longitudinal(self):
        """Triggers Track 2 regeneration and clinical longitudinal."""
        db = MockSupabaseClient()
        db.set_table_data("session_records", [{
            "id": "sr-001",
            "patient_id": "patient-001",
            "therapist_id": "therapist-001",
        }])

        with (
            patch.object(
                ai_pipeline.summary_service,
                "regenerate_clinical_summary",
                new_callable=AsyncMock,
                return_value={"id": "sum-regen"},
            ),
            patch.object(
                ai_pipeline.longitudinal_service,
                "generate_clinical_longitudinal",
                new_callable=AsyncMock,
                return_value={"id": "long-regen"},
            ),
        ):
            result = await ai_pipeline.on_observation_change("sr-001", db)

        assert result["clinical_summary"] == {"id": "sum-regen"}
        assert result["clinical_longitudinal"] == {"id": "long-regen"}

    @pytest.mark.asyncio
    async def test_clinical_summary_failure_caught(self):
        """Clinical summary regeneration failure is caught."""
        db = MockSupabaseClient()
        db.set_table_data("session_records", [{
            "id": "sr-001",
            "patient_id": "patient-001",
            "therapist_id": "therapist-001",
        }])

        with (
            patch.object(
                ai_pipeline.summary_service,
                "regenerate_clinical_summary",
                new_callable=AsyncMock,
                side_effect=Exception("Summary error"),
            ),
            patch.object(
                ai_pipeline.longitudinal_service,
                "generate_clinical_longitudinal",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await ai_pipeline.on_observation_change("sr-001", db)

        assert "error" in result["clinical_summary"]

    @pytest.mark.asyncio
    async def test_session_record_not_found(self):
        """Skips longitudinal if session record not found."""
        db = MockSupabaseClient()
        db.set_table_data("session_records", [])

        with patch.object(
            ai_pipeline.summary_service,
            "regenerate_clinical_summary",
            new_callable=AsyncMock,
            return_value={"id": "sum-regen"},
        ):
            result = await ai_pipeline.on_observation_change("nonexistent", db)

        assert result["clinical_longitudinal"] is None


# ---------------------------------------------------------------------------
# on_patient_note_change
# ---------------------------------------------------------------------------

class TestOnPatientNoteChange:
    @pytest.mark.asyncio
    async def test_regenerates_patient_longitudinal(self):
        """Triggers patient longitudinal regeneration."""
        db = MockSupabaseClient()

        with patch.object(
            ai_pipeline.longitudinal_service,
            "generate_patient_longitudinal",
            new_callable=AsyncMock,
            return_value={"id": "long-patient-regen"},
        ):
            result = await ai_pipeline.on_patient_note_change(
                session_record_id="sr-001",
                patient_id="patient-001",
                therapist_id="therapist-001",
                db=db,
            )

        assert result["patient_longitudinal"] == {"id": "long-patient-regen"}

    @pytest.mark.asyncio
    async def test_patient_longitudinal_failure_caught(self):
        """Patient longitudinal failure is caught, returns error dict."""
        db = MockSupabaseClient()

        with patch.object(
            ai_pipeline.longitudinal_service,
            "generate_patient_longitudinal",
            new_callable=AsyncMock,
            side_effect=Exception("Longitudinal error"),
        ):
            result = await ai_pipeline.on_patient_note_change(
                session_record_id="sr-001",
                patient_id="patient-001",
                therapist_id="therapist-001",
                db=db,
            )

        assert "error" in result["patient_longitudinal"]
