"""
Session Journal Router — Session history, summaries, audio access.

Role-filtered access:
  - Therapist: sees Track 2 (clinical) + observations + version history
  - Patient: sees Track 1 (base) + personal notes only
  - Clinic Admin: sees Track 2 for affiliated sessions
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import (
    first_or_none,
    get_clinic_id_for_user,
    get_current_user,
    get_user_client,
    get_user_role,
)
from app.responses import paginated_response, success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/journal", tags=["Session Journal"])

SP_TZ = timezone(timedelta(hours=-3))


def _track_for_role(role: str) -> str:
    """Determine which summary track a role should see."""
    if role in ("therapist", "clinic_admin", "platform_admin"):
        return "clinical"
    return "base"


@router.get("/sessions")
async def list_completed_sessions(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    patient_id: Optional[str] = Query(None),
):
    """List completed sessions for the current user.

    Therapists see their patients' sessions. Patients see their own.
    Returns session_record + latest summary for the appropriate track.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    role = get_user_role(user)

    # Build filters for appointments
    query = (
        db.table("appointments")
        .select("id", count="exact")
        .eq("status", "completed")
        .order("scheduled_start", desc=True)
    )

    if role == "patient":
        query = query.eq("patient_id", user.id)
    elif role == "therapist":
        query = query.eq("therapist_id", user.id)
        if patient_id:
            query = query.eq("patient_id", patient_id)
    elif role == "clinic_admin":
        clinic_id = get_clinic_id_for_user(user)
        if clinic_id:
            query = query.eq("clinic_id", clinic_id)
        if patient_id:
            query = query.eq("patient_id", patient_id)
    # platform_admin: no scope restriction
    elif role == "platform_admin" and patient_id:
        query = query.eq("patient_id", patient_id)

    from app.responses import calculate_pagination
    page, page_size, offset = calculate_pagination(page, page_size)
    result = query.range(offset, offset + page_size - 1).execute()
    appointments = result.data or []
    total = result.count or 0

    if not appointments:
        return paginated_response([], 0, page, page_size)

    appointment_ids = [a["id"] for a in appointments]
    track = _track_for_role(role)

    # Fetch session records
    sr_result = (
        db.table("session_records")
        .select("*")
        .in_("appointment_id", appointment_ids)
        .execute()
    )
    records_by_appt = {r["appointment_id"]: r for r in (sr_result.data or [])}

    # Fetch latest summary version per session record for the appropriate track
    record_ids = [r["id"] for r in (sr_result.data or [])]
    summaries_by_record: dict = {}
    if record_ids:
        sum_result = (
            db.table("session_summary_versions")
            .select("*")
            .in_("session_record_id", record_ids)
            .eq("track", track)
            .order("version_number", desc=True)
            .execute()
        )
        for s in (sum_result.data or []):
            if s["session_record_id"] not in summaries_by_record:
                summaries_by_record[s["session_record_id"]] = s

    # Assemble response
    sessions = []
    for appt in appointments:
        record = records_by_appt.get(appt["id"])
        entry = {
            "appointment": appt,
            "session_record": record,
            "latest_summary": summaries_by_record.get(record["id"]) if record else None,
        }
        sessions.append(entry)

    return paginated_response(sessions, total, page, page_size)


@router.get("/sessions/{session_record_id}")
async def get_session_detail(
    session_record_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get full session detail.

    Therapist: Track 2 clinical summary + observation history + version history.
    Patient: Track 1 base summary + personal notes only.
    Clinic admin: Track 2 for affiliated sessions.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    role = get_user_role(user)

    # Fetch session record
    sr_result = (
        db.table("session_records")
        .select("*")
        .eq("id", session_record_id)
        .execute()
    )
    record = first_or_none(sr_result)
    if not record:
        raise HTTPException(status_code=404, detail="Registro de sessão não encontrado")

    # Authorization check
    if role == "patient" and record["patient_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para acessar esta sessão")
    elif role == "therapist" and record["therapist_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para acessar esta sessão")

    track = _track_for_role(role)

    # Fetch latest summary for the appropriate track
    sum_result = (
        db.table("session_summary_versions")
        .select("*")
        .eq("session_record_id", session_record_id)
        .eq("track", track)
        .order("version_number", desc=True)
        .execute()
    )
    latest_summary = first_or_none(sum_result)

    response: dict = {
        "session_record": record,
        "latest_summary": latest_summary,
        "track": track,
    }

    # Therapist/admin: include observations + version history
    if role in ("therapist", "clinic_admin", "platform_admin"):
        obs_result = (
            db.table("session_observations")
            .select("*")
            .eq("session_record_id", session_record_id)
            .is_("deleted_at", "null")
            .order("created_at")
            .execute()
        )
        response["observations"] = obs_result.data or []

        versions_result = (
            db.table("session_summary_versions")
            .select("*")
            .eq("session_record_id", session_record_id)
            .eq("track", "clinical")
            .order("version_number", desc=True)
            .execute()
        )
        response["summary_versions"] = versions_result.data or []

    # Patient: include personal notes
    if role == "patient":
        notes_result = (
            db.table("patient_session_notes")
            .select("*")
            .eq("session_record_id", session_record_id)
            .eq("patient_id", user.id)
            .order("created_at")
            .execute()
        )
        response["patient_notes"] = notes_result.data or []

    # Fetch appointment for context
    appt_result = (
        db.table("appointments")
        .select("*")
        .eq("id", record["appointment_id"])
        .execute()
    )
    response["appointment"] = first_or_none(appt_result)

    return success_response(response)


@router.get("/sessions/{session_record_id}/versions")
async def list_summary_versions(
    session_record_id: str,
    authorization: Optional[str] = Header(None),
):
    """List all summary versions for a session.

    Role-filtered: patient sees Track 1 only, therapist sees Track 2.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    role = get_user_role(user)

    # Verify access
    sr = (
        db.table("session_records")
        .select("patient_id, therapist_id")
        .eq("id", session_record_id)
        .execute()
    )
    record = first_or_none(sr)
    if not record:
        raise HTTPException(status_code=404, detail="Registro de sessão não encontrado")

    if role == "patient" and record["patient_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão")
    elif role == "therapist" and record["therapist_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão")

    track = _track_for_role(role)

    result = (
        db.table("session_summary_versions")
        .select("*")
        .eq("session_record_id", session_record_id)
        .eq("track", track)
        .order("version_number", desc=True)
        .execute()
    )
    return success_response(result.data or [])


@router.get("/sessions/{session_record_id}/audio")
async def get_session_audio(
    session_record_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get audio download links for a session.

    Audio is available for 24 hours after session end. After that,
    the audio files are deleted and only the transcript remains.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    role = get_user_role(user)

    # Verify access
    sr = (
        db.table("session_records")
        .select("appointment_id, patient_id, therapist_id")
        .eq("id", session_record_id)
        .execute()
    )
    record = first_or_none(sr)
    if not record:
        raise HTTPException(status_code=404, detail="Registro de sessão não encontrado")

    if role not in ("platform_admin", "clinic_admin"):
        if user.id not in (record["patient_id"], record["therapist_id"]):
            raise HTTPException(status_code=403, detail="Sem permissão para acessar o áudio")

    # Fetch audio segments
    segments = (
        db.table("session_audio_segments")
        .select("*")
        .eq("appointment_id", record["appointment_id"])
        .order("segment_number")
        .execute()
    )

    now = datetime.now(SP_TZ)
    audio_segments = []
    for seg in (segments.data or []):
        expires_at = seg.get("download_expires_at")
        is_expired = True
        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                is_expired = now > exp_dt
            except (ValueError, TypeError):
                pass

        audio_segments.append({
            "segment_number": seg.get("segment_number"),
            "segment_type": seg.get("segment_type"),
            "started_at": seg.get("started_at"),
            "ended_at": seg.get("ended_at"),
            "audio_url": seg.get("audio_url") if not is_expired else None,
            "is_expired": is_expired,
            "download_expires_at": expires_at,
        })

    return success_response({
        "session_record_id": session_record_id,
        "segments": audio_segments,
    })
