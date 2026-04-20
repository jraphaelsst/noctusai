"""
AI Pipeline — Orchestrator for transcription, summary, and longitudinal analysis.

Ties together:
  1. Transcription (audio → text)
  2. Session record creation (combined transcript)
  3. Summary generation (Track 1 + Track 2)
  4. Longitudinal regeneration (clinical + patient)
  5. Audio retention management (24h expiry)

All operations are async and designed to run as FastAPI BackgroundTasks.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from app.dependencies import first_or_none
from app.services import (
    longitudinal_service,
    summary_service,
    transcription_service,
)
from app.services.session_service import _now_sp

logger = logging.getLogger(__name__)

AUDIO_RETENTION_HOURS = 24


def _resolve_clinic_id(db: Any, therapist_id: str) -> Optional[str]:
    """Fetch the `clinic_id` for a therapist profile.

    Independent therapists have `clinic_id IS NULL` — returns None, which
    the lib treats as "no Tier 1 key, fall through to platform/env".
    """
    try:
        result = (
            db.table("therapist_profiles")
            .select("clinic_id")
            .eq("user_id", therapist_id)
            .execute()
        )
        row = first_or_none(result)
        return row.get("clinic_id") if row else None
    except Exception as exc:
        logger.warning("Could not resolve clinic_id for therapist %s: %s", therapist_id, exc)
        return None


# ---------------------------------------------------------------------------
# Main Pipeline: Process Session End
# ---------------------------------------------------------------------------

async def process_session_end(
    appointment_id: str,
    initial_observation: Optional[str],
    source: str,
    db: Any,
) -> Dict:
    """Full AI pipeline triggered after a session ends.

    Steps:
    1. Assemble transcript from all audio segments
    2. Create session_record with combined transcript
    3. If initial_observation provided, create session_observations entry
    4. Generate both summary tracks
    5. Trigger clinical longitudinal regeneration
    6. Trigger patient longitudinal regeneration
    7. Set audio download expiry (24h)
    8. Set ai_generated_at on session_record
    """
    logger.info("AI pipeline started for appointment %s (source=%s)", appointment_id, source)

    # Fetch appointment for patient_id and therapist_id
    appt_result = (
        db.table("appointments")
        .select("*")
        .eq("id", appointment_id)
        .execute()
    )
    appointment = first_or_none(appt_result)
    if not appointment:
        logger.error("Appointment %s not found during AI pipeline", appointment_id)
        return {"error": "Agendamento não encontrado"}

    patient_id = appointment["patient_id"]
    therapist_id = appointment["therapist_id"]

    # Resolve the clinic_id for this session. Therapist profiles store
    # `clinic_id` (NULL for independent therapists). The clinic_id flows
    # into every lib call as `org_id` so the 3-tier credential chain picks
    # up the clinic's own provider key before falling back to the platform
    # default or env.
    clinic_id = _resolve_clinic_id(db, therapist_id)

    # Step 1: Assemble transcript
    logger.info("Step 1: Assembling transcript for %s", appointment_id)
    try:
        transcript = await transcription_service.assemble_transcript(
            appointment_id, db, clinic_id=clinic_id,
        )
    except Exception as e:
        logger.error("Transcription failed for %s: %s", appointment_id, e)
        transcript = f"[Erro na transcrição: {e}]"

    # Step 2: Create session record
    logger.info("Step 2: Creating session record for %s", appointment_id)
    now_iso = _now_sp().isoformat()
    session_record_data = {
        "appointment_id": appointment_id,
        "therapist_id": therapist_id,
        "patient_id": patient_id,
        "combined_transcript": transcript,
        "ai_generated_at": now_iso,
    }
    sr_result = db.table("session_records").insert(session_record_data).execute()
    session_record = first_or_none(sr_result)
    if not session_record:
        logger.error("Failed to create session record for %s", appointment_id)
        return {"error": "Erro ao criar registro de sessão"}

    session_record_id = session_record["id"]

    # Step 3: Create initial observation if provided
    observations: list[Dict] = []
    if initial_observation and initial_observation.strip():
        logger.info("Step 3: Creating initial observation for %s", session_record_id)
        obs_data = {
            "session_record_id": session_record_id,
            "therapist_id": therapist_id,
            "observation_text": initial_observation.strip(),
            "is_initial": True,
        }
        obs_result = db.table("session_observations").insert(obs_data).execute()
        obs = first_or_none(obs_result)
        if obs:
            observations.append(obs)

    # Step 4: Generate both summary tracks
    logger.info("Step 4: Generating summaries for %s", session_record_id)
    try:
        summaries = await summary_service.generate_session_summaries(
            session_record_id=session_record_id,
            transcript=transcript,
            observations=observations,
            source=source,
            org_ai_config=None,
            db=db,
            clinic_id=clinic_id,
        )
    except Exception as e:
        logger.error("Summary generation failed for %s: %s", session_record_id, e)
        summaries = {"base": {"error": str(e)}, "clinical": {"error": str(e)}}

    # Step 5: Trigger clinical longitudinal regeneration
    logger.info("Step 5: Regenerating clinical longitudinal for patient %s", patient_id)
    clinical_longitudinal = None
    try:
        clinical_longitudinal = await longitudinal_service.generate_clinical_longitudinal(
            patient_id=patient_id,
            therapist_id=therapist_id,
            db=db,
            clinic_id=clinic_id,
        )
    except Exception as e:
        logger.error("Clinical longitudinal failed: %s", e)

    # Step 6: Trigger patient longitudinal regeneration
    logger.info("Step 6: Regenerating patient longitudinal for patient %s", patient_id)
    patient_longitudinal = None
    try:
        patient_longitudinal = await longitudinal_service.generate_patient_longitudinal(
            patient_id=patient_id,
            therapist_id=therapist_id,
            db=db,
            clinic_id=clinic_id,
        )
    except Exception as e:
        logger.error("Patient longitudinal failed: %s", e)

    # Step 7: Set audio download expiry (24h from now)
    logger.info("Step 7: Setting audio expiry for %s", appointment_id)
    expiry = (_now_sp() + timedelta(hours=AUDIO_RETENTION_HOURS)).isoformat()
    db.table("session_audio_segments").update({
        "download_expires_at": expiry,
    }).eq("appointment_id", appointment_id).execute()

    logger.info("AI pipeline completed for appointment %s", appointment_id)

    return {
        "session_record": session_record,
        "summaries": summaries,
        "clinical_longitudinal": clinical_longitudinal,
        "patient_longitudinal": patient_longitudinal,
    }


# ---------------------------------------------------------------------------
# Observation Change Handler
# ---------------------------------------------------------------------------

async def on_observation_change(session_record_id: str, db: Any) -> Dict:
    """Triggered when an observation is added, edited, or deleted.

    Regenerates:
    - Clinical summary (Track 2 only)
    - Clinical longitudinal

    Does NOT affect Track 1 or patient longitudinal.
    """
    logger.info("Observation change for session_record %s", session_record_id)

    # Fetch session record for patient/therapist IDs first — we need the
    # therapist_id to resolve clinic_id before any LLM call.
    sr_result = (
        db.table("session_records")
        .select("patient_id, therapist_id")
        .eq("id", session_record_id)
        .execute()
    )
    sr = first_or_none(sr_result)
    clinic_id = _resolve_clinic_id(db, sr["therapist_id"]) if sr else None

    # Regenerate clinical summary
    try:
        clinical_summary = await summary_service.regenerate_clinical_summary(
            session_record_id, db, clinic_id=clinic_id,
        )
    except Exception as e:
        logger.error("Clinical summary regeneration failed: %s", e)
        clinical_summary = {"error": str(e)}

    clinical_longitudinal = None
    if sr:
        try:
            clinical_longitudinal = await longitudinal_service.generate_clinical_longitudinal(
                patient_id=sr["patient_id"],
                therapist_id=sr["therapist_id"],
                db=db,
                clinic_id=clinic_id,
            )
        except Exception as e:
            logger.error("Clinical longitudinal regeneration failed: %s", e)

    return {
        "clinical_summary": clinical_summary,
        "clinical_longitudinal": clinical_longitudinal,
    }


# ---------------------------------------------------------------------------
# Patient Note Change Handler
# ---------------------------------------------------------------------------

async def on_patient_note_change(
    session_record_id: str,
    patient_id: str,
    therapist_id: str,
    db: Any,
) -> Dict:
    """Triggered when a patient adds, edits, or deletes a personal note.

    Regenerates patient longitudinal only.
    Does NOT affect clinical summary or clinical longitudinal.
    """
    logger.info(
        "Patient note change for session_record %s, patient %s",
        session_record_id,
        patient_id,
    )

    clinic_id = _resolve_clinic_id(db, therapist_id)
    try:
        patient_longitudinal = await longitudinal_service.generate_patient_longitudinal(
            patient_id=patient_id,
            therapist_id=therapist_id,
            db=db,
            clinic_id=clinic_id,
        )
    except Exception as e:
        logger.error("Patient longitudinal regeneration failed: %s", e)
        patient_longitudinal = {"error": str(e)}

    return {"patient_longitudinal": patient_longitudinal}
