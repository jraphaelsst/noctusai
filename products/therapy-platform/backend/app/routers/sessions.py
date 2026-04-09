"""
Sessions Router — Video session lifecycle management.

Endpoints for starting, pausing, resuming, ending, and reopening sessions.
AI pipeline is triggered in the background after session end.
"""
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query

from app.dependencies import (
    get_admin_client,
    get_current_user,
    get_user_client,
    get_user_role,
)
from app.responses import success_response
from app.schemas.session import SessionEndRequest, SessionPauseRequest, SessionStartRequest
from app.services import ai_pipeline, livekit_service, session_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


@router.post("/{appointment_id}/start")
async def start_session(
    appointment_id: str,
    body: SessionStartRequest,
    authorization: Optional[str] = Header(None),
):
    """Start a therapy session.

    Requires consent_given=True. Only the assigned therapist can start.
    Creates the LiveKit room and begins audio recording.
    """
    if not body.consent_given:
        raise HTTPException(
            status_code=400,
            detail="O consentimento para gravação é obrigatório para iniciar a sessão",
        )

    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem iniciar sessões")

    db = get_user_client(token)
    result = await session_service.start_session(appointment_id, user.id, db)
    return success_response(result)


@router.post("/{appointment_id}/pause")
async def pause_session(
    appointment_id: str,
    body: SessionPauseRequest = SessionPauseRequest(),
    authorization: Optional[str] = Header(None),
):
    """Pause a running session.

    Can be triggered manually or automatically on disconnect.
    Stops audio recording but does NOT trigger the AI pipeline.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem pausar sessões")

    db = get_user_client(token)
    result = await session_service.pause_session(
        appointment_id, user.id, body.reason, db,
    )
    return success_response(result)


@router.post("/{appointment_id}/resume")
async def resume_session(
    appointment_id: str,
    authorization: Optional[str] = Header(None),
):
    """Resume a paused session.

    Validates the access window is still open. Creates a new audio segment.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem retomar sessões")

    db = get_user_client(token)
    result = await session_service.resume_session(appointment_id, user.id, db)
    return success_response(result)


@router.post("/{appointment_id}/end")
async def end_session(
    appointment_id: str,
    background_tasks: BackgroundTasks,
    body: SessionEndRequest = SessionEndRequest(),
    authorization: Optional[str] = Header(None),
):
    """End a therapy session.

    Optionally accepts an initial observation from the therapist.
    Triggers the full AI pipeline (transcription + summaries + longitudinal)
    in the background — the response returns immediately.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem finalizar sessões")

    db = get_user_client(token)
    result = await session_service.end_session(appointment_id, user.id, db)

    # Trigger AI pipeline in background (uses admin client to bypass RLS)
    admin_db = get_admin_client()
    background_tasks.add_task(
        ai_pipeline.process_session_end,
        appointment_id=appointment_id,
        initial_observation=body.initial_observation,
        source="therapist_end",
        db=admin_db,
    )

    return success_response(result)


@router.post("/{appointment_id}/reopen")
async def reopen_session(
    appointment_id: str,
    authorization: Optional[str] = Header(None),
):
    """Reopen a session after auto-finalization.

    Only available within the reopen visibility window. Creates a new
    audio segment and restarts recording.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem reabrir sessões")

    db = get_user_client(token)
    result = await session_service.reopen_session(appointment_id, user.id, db)
    return success_response(result)


@router.get("/{appointment_id}/status")
async def get_session_status(
    appointment_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get current session state.

    Returns video room status, access window times, remaining time,
    and interruption history. Suitable for polling.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Authorization: involved party or admin
    role = get_user_role(user)
    if role not in ("platform_admin", "clinic_admin"):
        appt = (
            db.table("appointments")
            .select("therapist_id, patient_id")
            .eq("id", appointment_id)
            .execute()
        )
        from app.dependencies import first_or_none
        appointment = first_or_none(appt)
        if not appointment:
            raise HTTPException(status_code=404, detail="Agendamento não encontrado")
        if user.id not in (appointment["therapist_id"], appointment["patient_id"]):
            raise HTTPException(status_code=403, detail="Sem permissão para acessar esta sessão")

    result = await session_service.get_session_status(appointment_id, db)
    return success_response(result)


@router.get("/{appointment_id}/overtime")
async def get_overtime_info(
    appointment_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get overtime information with alert thresholds.

    Returns remaining minutes and which alert thresholds have been triggered.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    result = await session_service.get_overtime_info(appointment_id, db)
    return success_response(result)


@router.get("/{appointment_id}/token")
async def get_session_token(
    appointment_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get a LiveKit room token for joining the video call.

    Both therapist and patient can request a token. The token is valid
    for the session's LiveKit room.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    role = get_user_role(user)

    # Validate: user is involved in the appointment
    appt = (
        db.table("appointments")
        .select("therapist_id, patient_id")
        .eq("id", appointment_id)
        .execute()
    )
    from app.dependencies import first_or_none
    appointment = first_or_none(appt)
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    if user.id not in (appointment["therapist_id"], appointment["patient_id"]):
        raise HTTPException(status_code=403, detail="Sem permissão para acessar esta sessão")

    # Fetch video room
    vr = (
        db.table("video_rooms")
        .select("*")
        .eq("appointment_id", appointment_id)
        .execute()
    )
    video_room = first_or_none(vr)
    if not video_room:
        raise HTTPException(status_code=404, detail="Sala de vídeo não encontrada")

    if video_room["status"] not in ("active", "pending", "reopened"):
        raise HTTPException(
            status_code=400,
            detail="A sala de vídeo não está disponível no momento",
        )

    # Determine participant name
    participant_name = "Terapeuta" if role == "therapist" else "Paciente"

    lk_token = await livekit_service.generate_token(
        room_name=video_room["livekit_room_name"],
        participant_identity=user.id,
        participant_name=participant_name,
    )

    return success_response({
        "token": lk_token,
        "room_name": video_room["livekit_room_name"],
        "meeting_url": video_room["meeting_url"],
    })
