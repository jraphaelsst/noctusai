"""
Tests for the AI Pipeline Service.

Covers: process_session_end (full pipeline, transcription failure,
session record creation failure, summary failure, longitudinal failures,
initial observation), on_observation_change, on_patient_note_change.

Patient-consent guards: tests exercise the REAL `consent.require(...)`
path — no patching of our own guard. Consent state is controlled by
seeding `ai_consent` rows into the mock Supabase via `_db_with_grants(...)`.
Revoked tests pass `revoked=[...]`. The catalog is populated at conftest
load time via the `from app.main import app` module-level import (which
triggers `create_product_app(consent_features=...)` in the framework).
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.services import ai_pipeline
from app.services.ai_pipeline import _PipelineHooks
from tests.conftest import MockSupabaseClient, MockSupabaseResponse


THERAPY_FEATURES = ("therapy.session_summary", "therapy.longitudinal_narrative")


def _hooks(
    *,
    transcribe=None,
    summarize=None,
    regenerate_clinical_summary=None,
    longitudinal_clinical=None,
    longitudinal_patient=None,
):
    """Build a `_PipelineHooks` for testing.

    Each kwarg overrides one helper; the rest fall back to silent AsyncMocks
    that return `None`. This is the DI pattern from `KB § PATTERNS/testing.md
    § "No self-monkeypatching" Pattern 1` — tests inject fakes via the kwarg,
    production paths omit `hooks=` and resolve to `_DEFAULT_HOOKS` (real
    services). Zero `patch.object` of our own code.
    """
    return _PipelineHooks(
        transcribe=transcribe or AsyncMock(return_value=""),
        summarize=summarize or AsyncMock(return_value={"base": {}, "clinical": {}}),
        regenerate_clinical_summary=regenerate_clinical_summary or AsyncMock(return_value=None),
        longitudinal_clinical=longitudinal_clinical or AsyncMock(return_value=None),
        longitudinal_patient=longitudinal_patient or AsyncMock(return_value=None),
    )


def _db_with_grants(*, patient_id: str = "patient-001", revoked=None) -> MockSupabaseClient:
    """Return a MockSupabaseClient with `ai_consent` rows for the patient.

    Both therapy features default to granted. Pass `revoked=[<feature_key>, ...]`
    to mark specific features as revoked. The seeded rows exercise the real
    `noctusai_lib.ai.consent.is_granted(...)` path — no patching.
    """
    revoked_set = set(revoked or [])
    rows = []
    for feature in THERAPY_FEATURES:
        is_granted = feature not in revoked_set
        rows.append({
            "user_id": patient_id,
            "feature_key": feature,
            "granted": is_granted,
            "granted_at": "2026-04-27T00:00:00Z" if is_granted else None,
            "revoked_at": None if is_granted else "2026-04-27T00:00:00Z",
        })
    db = MockSupabaseClient()
    db.set_table_data("ai_consent", rows)
    return db


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
    "combined_transcript_text": "Transcrição completa.",
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
        """Happy path: all steps complete without errors.

        DI shape: pass a `_PipelineHooks` with AsyncMock fakes for each
        helper. The orchestrator's real call sequence runs end-to-end (real
        consent guard, real DB writes) — only the per-step LLM/transcription
        calls are short-circuited.
        """
        db = _db_with_grants()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        db.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        db.set_table_data("session_observations", [SAMPLE_OBSERVATION])
        db.set_table_data("session_audio_segments", [])

        hooks = _hooks(
            transcribe=AsyncMock(return_value="Transcrição completa."),
            summarize=AsyncMock(return_value={"base": {"id": "sum-b"}, "clinical": {"id": "sum-c"}}),
            longitudinal_clinical=AsyncMock(return_value={"id": "long-clinical"}),
            longitudinal_patient=AsyncMock(return_value={"id": "long-patient"}),
        )

        result = await ai_pipeline.process_session_end(
            appointment_id="appt-001",
            initial_observation="Observação inicial.",
            source="manual",
            db=db,
            hooks=hooks,
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
        db = _db_with_grants()
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
        db = _db_with_grants()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        # Simulate insert failure: queue an empty response on the table.
        db.set_sequential_responses("session_records", [MockSupabaseResponse(data=[])])

        hooks = _hooks(transcribe=AsyncMock(return_value="Transcrição."))

        result = await ai_pipeline.process_session_end(
            appointment_id="appt-001",
            initial_observation=None,
            source="auto",
            db=db,
            hooks=hooks,
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_transcription_failure_produces_error_text(self):
        """Transcription failure is caught, pipeline continues with error text.

        DI shape: only `transcribe` raises; the other helpers default to
        silent AsyncMocks. Tests the orchestrator's exception-handling path
        without patching anything we own.
        """
        db = _db_with_grants()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        db.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        db.set_table_data("session_observations", [])
        db.set_table_data("session_audio_segments", [])

        hooks = _hooks(
            transcribe=AsyncMock(side_effect=Exception("Transcription service unavailable")),
            summarize=AsyncMock(return_value={"base": {}, "clinical": {}}),
        )

        result = await ai_pipeline.process_session_end(
            appointment_id="appt-001",
            initial_observation=None,
            source="auto",
            db=db,
            hooks=hooks,
        )

        # Pipeline should still complete (error handled gracefully)
        assert "session_record" in result

    @pytest.mark.asyncio
    async def test_no_initial_observation(self):
        """Pipeline works without an initial observation."""
        db = _db_with_grants()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        db.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        db.set_table_data("session_audio_segments", [])

        hooks = _hooks(transcribe=AsyncMock(return_value="Texto."))

        result = await ai_pipeline.process_session_end(
            appointment_id="appt-001",
            initial_observation=None,
            source="manual",
            db=db,
            hooks=hooks,
        )

        assert "session_record" in result

    @pytest.mark.asyncio
    async def test_whitespace_only_observation_skipped(self):
        """Blank observation is treated as no observation."""
        db = _db_with_grants()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        db.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        db.set_table_data("session_audio_segments", [])

        hooks = _hooks(transcribe=AsyncMock(return_value="Texto."))

        result = await ai_pipeline.process_session_end(
            appointment_id="appt-001",
            initial_observation="   ",
            source="manual",
            db=db,
            hooks=hooks,
        )

        assert "session_record" in result

    @pytest.mark.asyncio
    async def test_summary_failure_caught(self):
        """Summary generation failure is caught, pipeline continues."""
        db = _db_with_grants()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        db.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        db.set_table_data("session_audio_segments", [])

        hooks = _hooks(
            transcribe=AsyncMock(return_value="Texto."),
            summarize=AsyncMock(side_effect=Exception("OpenAI rate limit")),
        )

        result = await ai_pipeline.process_session_end(
            appointment_id="appt-001",
            initial_observation=None,
            source="manual",
            db=db,
            hooks=hooks,
        )

        # Summaries should have error keys
        assert "error" in result["summaries"]["base"]
        assert "error" in result["summaries"]["clinical"]

    @pytest.mark.asyncio
    async def test_longitudinal_failure_caught(self):
        """Longitudinal failures are caught individually."""
        db = _db_with_grants()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        db.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        db.set_table_data("session_audio_segments", [])

        hooks = _hooks(
            transcribe=AsyncMock(return_value="Texto."),
            summarize=AsyncMock(return_value={"base": {}, "clinical": {}}),
            longitudinal_clinical=AsyncMock(side_effect=Exception("Clinical longitudinal error")),
            longitudinal_patient=AsyncMock(side_effect=Exception("Patient longitudinal error")),
        )

        result = await ai_pipeline.process_session_end(
            appointment_id="appt-001",
            initial_observation=None,
            source="manual",
            db=db,
            hooks=hooks,
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
        db = _db_with_grants()
        db.set_table_data("session_records", [{
            "id": "sr-001",
            "patient_id": "patient-001",
            "therapist_id": "therapist-001",
        }])

        hooks = _hooks(
            regenerate_clinical_summary=AsyncMock(return_value={"id": "sum-regen"}),
            longitudinal_clinical=AsyncMock(return_value={"id": "long-regen"}),
        )

        result = await ai_pipeline.on_observation_change("sr-001", db, hooks=hooks)

        assert result["clinical_summary"] == {"id": "sum-regen"}
        assert result["clinical_longitudinal"] == {"id": "long-regen"}

    @pytest.mark.asyncio
    async def test_clinical_summary_failure_caught(self):
        """Clinical summary regeneration failure is caught."""
        db = _db_with_grants()
        db.set_table_data("session_records", [{
            "id": "sr-001",
            "patient_id": "patient-001",
            "therapist_id": "therapist-001",
        }])

        hooks = _hooks(
            regenerate_clinical_summary=AsyncMock(side_effect=Exception("Summary error")),
        )

        result = await ai_pipeline.on_observation_change("sr-001", db, hooks=hooks)

        assert "error" in result["clinical_summary"]

    @pytest.mark.asyncio
    async def test_session_record_not_found(self):
        """Skips longitudinal if session record not found."""
        db = _db_with_grants()
        db.set_table_data("session_records", [])

        hooks = _hooks(
            regenerate_clinical_summary=AsyncMock(return_value={"id": "sum-regen"}),
        )

        result = await ai_pipeline.on_observation_change("nonexistent", db, hooks=hooks)

        assert result["clinical_longitudinal"] is None


# ---------------------------------------------------------------------------
# on_patient_note_change
# ---------------------------------------------------------------------------

class TestOnPatientNoteChange:
    @pytest.mark.asyncio
    async def test_regenerates_patient_longitudinal(self):
        """Triggers patient longitudinal regeneration."""
        db = _db_with_grants()

        hooks = _hooks(
            longitudinal_patient=AsyncMock(return_value={"id": "long-patient-regen"}),
        )

        result = await ai_pipeline.on_patient_note_change(
            session_record_id="sr-001",
            patient_id="patient-001",
            therapist_id="therapist-001",
            db=db,
            hooks=hooks,
        )

        assert result["patient_longitudinal"] == {"id": "long-patient-regen"}

    @pytest.mark.asyncio
    async def test_patient_longitudinal_failure_caught(self):
        """Patient longitudinal failure is caught, returns error dict."""
        db = _db_with_grants()

        hooks = _hooks(
            longitudinal_patient=AsyncMock(side_effect=Exception("Longitudinal error")),
        )

        result = await ai_pipeline.on_patient_note_change(
            session_record_id="sr-001",
            patient_id="patient-001",
            therapist_id="therapist-001",
            db=db,
            hooks=hooks,
        )

        assert "error" in result["patient_longitudinal"]


# ---------------------------------------------------------------------------
# Patient consent guards (therapy-consent-guard-wiring 2026-04-27)
# ---------------------------------------------------------------------------


class TestPatientConsentGuards:
    """LGPD Art. 11 — patient consent gates clinical AI in `ai_pipeline`.

    No patching of `ai_pipeline.require` — these tests exercise the REAL
    consent guard. Revoked state is established by seeding `ai_consent`
    rows with `granted=False` via `_db_with_grants(revoked=[...])`. The
    notification side-effect lands in the SAME mock_sb because we pass
    `core_db=db` (proper DI; production callers default to
    `get_core_client()`).

    Skip-and-notify contract verified per test: AI service mocks are
    `assert_not_awaited()`, the result dict carries the `skipped` marker,
    and a row appears in `core_db._tables["notifications"]`.
    """

    @staticmethod
    def _captured_notifications(db) -> list:
        """Return rows inserted into the mock's `notifications` table.

        Reads `MockRequestBuilder.inserted_payloads` — the public capture
        attribute on the seed-lib mock. No patching of the production
        helper required.
        """
        builder = db._tables.get("notifications")
        if builder is None:
            return []
        return list(builder.inserted_payloads)

    @pytest.mark.asyncio
    async def test_session_summary_consent_revoked_skips_summary_and_notifies(self):
        """Patient revoked `therapy.session_summary` → summary skipped, longitudinal still runs.

        DI shape: each helper is an AsyncMock on the `_PipelineHooks` instance,
        so `hooks.summarize.assert_not_awaited()` proves the consent guard
        short-circuited before the LLM call. Production guard runs for real.
        """
        db = _db_with_grants(revoked=["therapy.session_summary"])
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        db.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        db.set_table_data("session_audio_segments", [])
        db.set_table_data("notifications", [])

        hooks = _hooks(
            transcribe=AsyncMock(return_value="Texto."),
            summarize=AsyncMock(),  # tracked: assert_not_awaited() below
            longitudinal_clinical=AsyncMock(return_value={"id": "long-clinical"}),
            longitudinal_patient=AsyncMock(return_value={"id": "long-patient"}),
        )

        result = await ai_pipeline.process_session_end(
            appointment_id="appt-001",
            initial_observation=None,
            source="manual",
            db=db,
            core_db=db,
            hooks=hooks,
        )

        # Summary AI was never called — real consent guard short-circuited.
        hooks.summarize.assert_not_awaited()
        # Skip marker is present.
        assert result["summaries"]["base"]["skipped"] == "patient_consent_missing"
        assert result["summaries"]["clinical"]["skipped"] == "patient_consent_missing"
        # Longitudinal still ran (only the summary feature was revoked).
        assert result["clinical_longitudinal"] == {"id": "long-clinical"}
        assert result["patient_longitudinal"] == {"id": "long-patient"}
        # Therapist notification filed via the real helper.
        notifs = TestPatientConsentGuards._captured_notifications(db)
        assert len(notifs) == 1
        assert notifs[0]["user_id"] == "therapist-001"
        assert notifs[0]["type"] == "ai_skipped_consent"
        assert notifs[0]["metadata"]["feature_key"] == "therapy.session_summary"

    @pytest.mark.asyncio
    async def test_longitudinal_consent_revoked_skips_both_steps_5_and_6(self):
        """Patient revoked `therapy.longitudinal_narrative` → both clinical + patient longitudinals skipped."""
        db = _db_with_grants(revoked=["therapy.longitudinal_narrative"])
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        db.set_table_data("session_records", [SAMPLE_SESSION_RECORD])
        db.set_table_data("session_audio_segments", [])
        db.set_table_data("notifications", [])

        hooks = _hooks(
            transcribe=AsyncMock(return_value="Texto."),
            summarize=AsyncMock(return_value={"base": {"id": "sum-b"}, "clinical": {"id": "sum-c"}}),
            longitudinal_clinical=AsyncMock(),  # tracked: assert_not_awaited()
            longitudinal_patient=AsyncMock(),   # tracked: assert_not_awaited()
        )

        result = await ai_pipeline.process_session_end(
            appointment_id="appt-001",
            initial_observation=None,
            source="manual",
            db=db,
            core_db=db,
            hooks=hooks,
        )

        # Summary still ran.
        assert result["summaries"]["base"] == {"id": "sum-b"}
        # Both longitudinal calls were skipped — real consent guard short-circuited.
        hooks.longitudinal_clinical.assert_not_awaited()
        hooks.longitudinal_patient.assert_not_awaited()
        assert result["clinical_longitudinal"] is None
        assert result["patient_longitudinal"] is None
        # ONE notification fired (single guard covers both steps).
        notifs = TestPatientConsentGuards._captured_notifications(db)
        assert len(notifs) == 1
        assert notifs[0]["metadata"]["feature_key"] == "therapy.longitudinal_narrative"

    @pytest.mark.asyncio
    async def test_on_observation_change_consent_revoked_skips_both(self):
        """Observation-change handler skips when patient revoked both features."""
        db = _db_with_grants(revoked=list(THERAPY_FEATURES))
        db.set_table_data("session_records", [{
            "id": "sr-001",
            "patient_id": "patient-001",
            "therapist_id": "therapist-001",
        }])
        db.set_table_data("notifications", [])

        hooks = _hooks(
            regenerate_clinical_summary=AsyncMock(),  # tracked: assert_not_awaited()
            longitudinal_clinical=AsyncMock(),         # tracked: assert_not_awaited()
        )

        result = await ai_pipeline.on_observation_change("sr-001", db, core_db=db, hooks=hooks)

        hooks.regenerate_clinical_summary.assert_not_awaited()
        hooks.longitudinal_clinical.assert_not_awaited()
        assert result["clinical_summary"] == {"skipped": "patient_consent_missing"}
        assert result["clinical_longitudinal"] is None
        # One notification per feature (summary + longitudinal).
        notifs = TestPatientConsentGuards._captured_notifications(db)
        assert len(notifs) == 2
        feature_keys = {n["metadata"]["feature_key"] for n in notifs}
        assert feature_keys == set(THERAPY_FEATURES)

    @pytest.mark.asyncio
    async def test_on_patient_note_change_consent_revoked_skips(self):
        """Patient-note-change handler skips when patient revoked longitudinal."""
        db = _db_with_grants(revoked=["therapy.longitudinal_narrative"])
        db.set_table_data("notifications", [])

        hooks = _hooks(
            longitudinal_patient=AsyncMock(),  # tracked: assert_not_awaited()
        )

        result = await ai_pipeline.on_patient_note_change(
            session_record_id="sr-001",
            patient_id="patient-001",
            therapist_id="therapist-001",
            db=db,
            core_db=db,
            hooks=hooks,
        )

        hooks.longitudinal_patient.assert_not_awaited()
        assert result["patient_longitudinal"] == {"skipped": "patient_consent_missing"}
        notifs = TestPatientConsentGuards._captured_notifications(db)
        assert len(notifs) == 1
        assert notifs[0]["metadata"]["feature_key"] == "therapy.longitudinal_narrative"
