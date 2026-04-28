"""LGPD Service — Data deletion per Brazilian data protection law.

Patient deletion removes patient-side data ONLY; therapist clinical data
(session_records, session_observations, session_summary_versions) is preserved
as the therapist's professional records.

Therapist deletion can target specific entities or everything.

**Rewritten 2026-04-22 (compliance-audit-reconciliation Phase 2)** to fix the
silent-fail chain in the prior implementation, which filtered several tables
by columns that don't exist in the live schema (verified via Supabase MCP):

  - `session_records`, `session_summary_versions`, `session_observations` have
    NO `therapist_id` column and NO `session_id` column. Therapist ownership
    chains indirectly through `appointments.therapist_id`.
  - `messages.sender_id` → actual column is `sender_user_id`.
  - `conversation_participants.user_id` → actual column is `participant_id`.
  - `wallets.user_id` → actual columns are `owner_id` + `owner_type`.
  - `therapist_settings.user_id` → actual column is `therapist_id`.

All those filters matched zero rows silently (Supabase returns success with
0 rows affected when a filter column doesn't exist), so the prior endpoint
reported deletion success while the data persisted — a textbook LGPD rights-
handling compliance failure per `KB § 01-PHILOSOPHY.md § No silent errors`.

This rewrite uses a dependency-graph deletion pattern: resolve IDs at each
level (appointments → session_records → summaries/observations), then delete
via `.in_()` filters on those IDs.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.dependencies import log_action

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dependency-graph helpers — resolve IDs without assuming non-existent columns.
# ---------------------------------------------------------------------------

def _appointment_ids_for_therapist(db: Any, therapist_id: str) -> List[str]:
    """Return appointment IDs owned by a therapist."""
    result = (
        db.table("appointments")
        .select("id")
        .eq("therapist_id", therapist_id)
        .execute()
    )
    return [row["id"] for row in (result.data or [])]


def _session_record_ids_for_appointments(db: Any, appointment_ids: List[str]) -> List[str]:
    """Return session_record IDs whose appointments are in the given list."""
    if not appointment_ids:
        return []
    result = (
        db.table("session_records")
        .select("id")
        .in_("appointment_id", appointment_ids)
        .execute()
    )
    return [row["id"] for row in (result.data or [])]


def _video_room_ids_for_appointments(db: Any, appointment_ids: List[str]) -> List[str]:
    """Return video_room IDs whose appointments are in the given list."""
    if not appointment_ids:
        return []
    result = (
        db.table("video_rooms")
        .select("id")
        .in_("appointment_id", appointment_ids)
        .execute()
    )
    return [row["id"] for row in (result.data or [])]


def _session_record_appointment(db: Any, session_record_id: str) -> Optional[Dict]:
    """Fetch a session_record's appointment details (id + therapist_id) via join
    through session_records → appointments."""
    sr_result = (
        db.table("session_records")
        .select("id, appointment_id")
        .eq("id", session_record_id)
        .execute()
    )
    sr = (sr_result.data or [None])[0]
    if not sr:
        return None
    appt_result = (
        db.table("appointments")
        .select("id, therapist_id")
        .eq("id", sr["appointment_id"])
        .execute()
    )
    return (appt_result.data or [None])[0]


# ---------------------------------------------------------------------------
# Patient data deletion
# ---------------------------------------------------------------------------

async def delete_patient_data(patient_id: str, db: Any) -> Dict:
    """Delete all patient-owned data per LGPD request.

    Deletes:
        - messages sent by patient (filtered by sender_user_id + sender_type)
        - conversation_participants (participant_id + participant_type='user')
        - wallets (owner_id + owner_type='patient') + their wallet_movements
        - patient_longitudinal_analyses (patient_id)
        - patient_session_notes (patient_id)
        - patient_profiles (user_id)

    Keeps (therapist clinical data):
        - session_records, session_observations, session_summary_versions
          — these are the therapist's professional records; the patient can
          delete their OWN notes/analyses but the therapist's session memory
          is preserved per clinical-record retention requirements.
    """
    deleted_tables: List[str] = []

    # Messages sent by the patient.
    # `messages` has `sender_user_id` + `sender_type`; a patient is sender_type='user'.
    # Filtering by sender_user_id alone would also catch messages from therapists
    # with the same user_id (impossible in practice but narrow it for safety).
    db.table("messages").delete().eq("sender_user_id", patient_id).eq("sender_type", "user").execute()
    deleted_tables.append("messages")

    # Conversation participations. `conversation_participants.participant_id`
    # + `participant_type='user'` — both patients and therapists register as
    # 'user' here; the participant_id narrows it to this patient.
    db.table("conversation_participants").delete().eq("participant_id", patient_id).eq("participant_type", "user").execute()
    deleted_tables.append("conversation_participants")

    # Wallet movements (via the patient's wallets).
    # `wallets` is keyed by (owner_id, owner_type) with owner_type='patient'.
    wallet_result = (
        db.table("wallets")
        .select("id")
        .eq("owner_id", patient_id)
        .eq("owner_type", "patient")
        .execute()
    )
    for wallet in wallet_result.data or []:
        db.table("wallet_movements").delete().eq("wallet_id", wallet["id"]).execute()
    deleted_tables.append("wallet_movements")

    # The patient's wallets themselves.
    db.table("wallets").delete().eq("owner_id", patient_id).eq("owner_type", "patient").execute()
    deleted_tables.append("wallets")

    # Patient-facing longitudinal analyses.
    db.table("patient_longitudinal_analyses").delete().eq("patient_id", patient_id).execute()
    deleted_tables.append("patient_longitudinal_analyses")

    # Patient's own session notes.
    db.table("patient_session_notes").delete().eq("patient_id", patient_id).execute()
    deleted_tables.append("patient_session_notes")

    # Patient profile. `patient_profiles` is keyed by `user_id`.
    db.table("patient_profiles").delete().eq("user_id", patient_id).execute()
    deleted_tables.append("patient_profiles")

    kept_tables = [
        "session_records",
        "session_observations",
        "session_summary_versions",
    ]

    log_action(
        user_id=patient_id,
        tipo_acao="lgpd_delete",
        tipo_entidade="patient",
        entidade_id=patient_id,
        descricao="Exclusão de dados do paciente via LGPD",
        detalhes={"deleted_tables": deleted_tables, "kept_tables": kept_tables},
    )

    logger.info("LGPD patient data deleted: patient_id=%s tables=%s", patient_id, deleted_tables)
    return {"deleted_tables": deleted_tables, "kept_tables": kept_tables}


# ---------------------------------------------------------------------------
# Therapist data deletion
# ---------------------------------------------------------------------------

async def delete_therapist_data(
    therapist_id: str,
    entity_type: str,
    entity_id: Optional[str],
    db: Any,
) -> Dict:
    """Delete therapist-owned data — all or specific entities.

    entity_type:
        - "all": full therapist wipe (profile, settings, wallet, all sessions
          they ran + summaries + observations + audio_segments + interruptions,
          longitudinal analyses authored by them, messages/conversations).
        - "session": deletes a specific session_record + its dependents
          (summaries, observations). Verified to belong to this therapist
          via the appointments chain.
        - "observation": deletes a specific observation. Verified to belong
          to a session_record owned (via appointments) by this therapist.
    """
    deleted: List[str] = []

    if entity_type == "all":
        # Resolve the ownership graph once, up front.
        appointment_ids = _appointment_ids_for_therapist(db, therapist_id)
        session_record_ids = _session_record_ids_for_appointments(db, appointment_ids)
        video_room_ids = _video_room_ids_for_appointments(db, appointment_ids)

        # Deepest dependents first (summaries + observations link via session_record_id).
        if session_record_ids:
            db.table("session_summary_versions").delete().in_("session_record_id", session_record_ids).execute()
            deleted.append("session_summary_versions")

            db.table("session_observations").delete().in_("session_record_id", session_record_ids).execute()
            deleted.append("session_observations")

        # Audio + interruption artifacts link to video_rooms (not session_records).
        if video_room_ids:
            db.table("session_audio_segments").delete().in_("video_room_id", video_room_ids).execute()
            deleted.append("session_audio_segments")

            db.table("session_interruptions").delete().in_("video_room_id", video_room_ids).execute()
            deleted.append("session_interruptions")

        # Session records themselves.
        if appointment_ids:
            db.table("session_records").delete().in_("appointment_id", appointment_ids).execute()
            deleted.append("session_records")

        # Longitudinal analyses authored by this therapist (about patients).
        # clinical_longitudinal_analyses + patient_longitudinal_analyses both
        # have a direct `therapist_id` column per live-schema verification.
        db.table("clinical_longitudinal_analyses").delete().eq("therapist_id", therapist_id).execute()
        deleted.append("clinical_longitudinal_analyses")

        db.table("patient_longitudinal_analyses").delete().eq("therapist_id", therapist_id).execute()
        deleted.append("patient_longitudinal_analyses")

        # Messages the therapist sent (sender_type='user', sender_user_id=them).
        db.table("messages").delete().eq("sender_user_id", therapist_id).eq("sender_type", "user").execute()
        deleted.append("messages")

        # Conversation memberships.
        db.table("conversation_participants").delete().eq("participant_id", therapist_id).eq("participant_type", "user").execute()
        deleted.append("conversation_participants")

        # Wallet movements + wallets. `wallets` is keyed by (owner_id, owner_type='therapist').
        wallet_result = (
            db.table("wallets")
            .select("id")
            .eq("owner_id", therapist_id)
            .eq("owner_type", "therapist")
            .execute()
        )
        for wallet in wallet_result.data or []:
            db.table("wallet_movements").delete().eq("wallet_id", wallet["id"]).execute()
        deleted.append("wallet_movements")

        db.table("wallets").delete().eq("owner_id", therapist_id).eq("owner_type", "therapist").execute()
        deleted.append("wallets")

        # Therapist settings. The table is keyed by `therapist_id` directly.
        db.table("therapist_settings").delete().eq("therapist_id", therapist_id).execute()
        deleted.append("therapist_settings")

        # Therapist profile (keyed by user_id).
        db.table("therapist_profiles").delete().eq("user_id", therapist_id).execute()
        deleted.append("therapist_profiles")

    elif entity_type == "session":
        if not entity_id:
            raise HTTPException(status_code=400, detail="entity_id é obrigatório para exclusão de sessão")

        # Verify session belongs to therapist via session_records → appointments.
        appt = _session_record_appointment(db, entity_id)
        if not appt or appt.get("therapist_id") != therapist_id:
            raise HTTPException(status_code=404, detail="Sessão não encontrada ou não pertence ao terapeuta")

        # Dependents first (correct column name: session_record_id).
        db.table("session_summary_versions").delete().eq("session_record_id", entity_id).execute()
        deleted.append("session_summary_versions")

        db.table("session_observations").delete().eq("session_record_id", entity_id).execute()
        deleted.append("session_observations")

        db.table("session_records").delete().eq("id", entity_id).execute()
        deleted.append("session_records")

    elif entity_type == "observation":
        if not entity_id:
            raise HTTPException(status_code=400, detail="entity_id é obrigatório para exclusão de observação")

        # Fetch observation → its session_record → its appointment → therapist.
        obs_result = (
            db.table("session_observations")
            .select("id, session_record_id")
            .eq("id", entity_id)
            .execute()
        )
        obs = (obs_result.data or [None])[0]
        if not obs:
            raise HTTPException(status_code=404, detail="Observação não encontrada")

        appt = _session_record_appointment(db, obs["session_record_id"])
        if not appt or appt.get("therapist_id") != therapist_id:
            raise HTTPException(status_code=404, detail="Observação não pertence ao terapeuta")

        db.table("session_observations").delete().eq("id", entity_id).execute()
        deleted.append("session_observations")

    else:
        raise HTTPException(
            status_code=400,
            detail="Tipo de entidade inválido. Use 'all', 'session' ou 'observation'",
        )

    log_action(
        user_id=therapist_id,
        tipo_acao="lgpd_delete",
        tipo_entidade="therapist",
        entidade_id=entity_id or therapist_id,
        descricao=f"Exclusão de dados do terapeuta via LGPD: {entity_type}",
        detalhes={"deleted": deleted, "entity_type": entity_type, "entity_id": entity_id},
    )

    logger.info(
        "LGPD therapist data deleted: therapist_id=%s type=%s entity_id=%s deleted=%s",
        therapist_id, entity_type, entity_id, deleted,
    )
    return {"deleted": deleted, "entity_type": entity_type, "entity_id": entity_id}
