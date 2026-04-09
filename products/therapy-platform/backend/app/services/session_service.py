"""
Session Service — Lifecycle management for video therapy sessions.

Orchestrates start, pause, resume, end, auto-finalization, and reopen
of sessions. Delegates to LiveKit for room/recording operations.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import HTTPException

from app.dependencies import first_or_none
from app.services import livekit_service

logger = logging.getLogger(__name__)

SP_TZ = timezone(timedelta(hours=-3))


# ---------------------------------------------------------------------------
# Platform settings helpers
# ---------------------------------------------------------------------------

def _get_setting(db: Any, key: str, default: str) -> str:
    """Read a value from therapy.platform_settings."""
    result = (
        db.table("platform_settings")
        .select("value")
        .eq("key", key)
        .execute()
    )
    row = first_or_none(result)
    return row["value"] if row else default


def _get_reopen_visibility_minutes(db: Any) -> int:
    return int(_get_setting(db, "reopen_visibility_minutes", "30"))


def _get_reopen_duration_minutes(db: Any) -> int:
    return int(_get_setting(db, "reopen_duration_minutes", "15"))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_sp() -> datetime:
    return datetime.now(SP_TZ)


def _parse_dt(value: str) -> datetime:
    """Parse ISO datetime string to timezone-aware datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _get_video_room(appointment_id: str, db: Any) -> Dict:
    """Fetch video_room for an appointment. Raises 404 if not found."""
    result = (
        db.table("video_rooms")
        .select("*")
        .eq("appointment_id", appointment_id)
        .execute()
    )
    room = first_or_none(result)
    if not room:
        raise HTTPException(
            status_code=404,
            detail="Sala de vídeo não encontrada para este agendamento",
        )
    return room


async def _get_appointment(appointment_id: str, db: Any) -> Dict:
    """Fetch appointment. Raises 404 if not found."""
    result = (
        db.table("appointments")
        .select("*")
        .eq("id", appointment_id)
        .execute()
    )
    appt = first_or_none(result)
    if not appt:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    return appt


def _validate_therapist(user_id: str, appointment: Dict) -> None:
    """Ensure the user is the therapist for this appointment."""
    if appointment.get("therapist_id") != user_id:
        raise HTTPException(
            status_code=403,
            detail="Apenas o terapeuta responsável pode executar esta ação",
        )


def _validate_access_window(room: Dict) -> None:
    """Ensure current time is within the access window."""
    now = _now_sp()
    accessible_from = _parse_dt(room["accessible_from"])
    accessible_until = _parse_dt(room["accessible_until"])
    if now < accessible_from:
        raise HTTPException(
            status_code=400,
            detail="A sessão ainda não está acessível. Aguarde o horário de início.",
        )
    if now > accessible_until:
        raise HTTPException(
            status_code=400,
            detail="A janela de acesso desta sessão já expirou",
        )


# ---------------------------------------------------------------------------
# Start Session
# ---------------------------------------------------------------------------

async def start_session(appointment_id: str, user_id: str, db: Any) -> Dict:
    """Start a therapy session.

    Validates therapist ownership, appointment status, and access window.
    Creates first audio segment and starts LiveKit recording.
    """
    appointment = await _get_appointment(appointment_id, db)
    _validate_therapist(user_id, appointment)

    if appointment["status"] != "waiting":
        raise HTTPException(
            status_code=400,
            detail=f"Agendamento com status '{appointment['status']}' não pode ser iniciado",
        )

    room = await _get_video_room(appointment_id, db)
    _validate_access_window(room)

    now = _now_sp().isoformat()

    # Update video room to active
    db.table("video_rooms").update({
        "status": "active",
        "session_started_at": now,
    }).eq("id", room["id"]).execute()

    # Create LiveKit room
    lk_room = await livekit_service.create_room(room["livekit_room_name"])

    # Create first audio segment
    segment_data = {
        "appointment_id": appointment_id,
        "segment_number": 1,
        "segment_type": "initial",
        "started_at": now,
    }
    seg_result = db.table("session_audio_segments").insert(segment_data).execute()
    segment = first_or_none(seg_result)

    # Start recording
    rec_info = {}
    if segment:
        rec_info = await livekit_service.start_recording(
            room["livekit_room_name"],
            segment["id"],
        )
        if rec_info.get("recording_id"):
            db.table("session_audio_segments").update({
                "recording_id": rec_info["recording_id"],
            }).eq("id", segment["id"]).execute()

    # Update appointment status
    db.table("appointments").update({
        "status": "in_progress",
    }).eq("id", appointment_id).execute()

    # Generate token for therapist
    token = await livekit_service.generate_token(
        room["livekit_room_name"],
        participant_identity=user_id,
        participant_name="Terapeuta",
    )

    return {
        "appointment_id": appointment_id,
        "video_room_id": room["id"],
        "livekit_room_name": room["livekit_room_name"],
        "meeting_url": room["meeting_url"],
        "token": token,
        "session_started_at": now,
        "livekit_room": lk_room,
        "recording": rec_info,
    }


# ---------------------------------------------------------------------------
# Pause Session
# ---------------------------------------------------------------------------

async def pause_session(
    appointment_id: str,
    user_id: str,
    reason: Optional[str],
    db: Any,
) -> Dict:
    """Pause a running session.

    Stops current audio recording and logs an interruption event.
    Does NOT trigger the AI pipeline.
    """
    appointment = await _get_appointment(appointment_id, db)
    _validate_therapist(user_id, appointment)

    room = await _get_video_room(appointment_id, db)
    if room["status"] != "active":
        raise HTTPException(
            status_code=400,
            detail="Sessão não está ativa para ser pausada",
        )

    now = _now_sp().isoformat()
    total_pauses = (room.get("total_pauses") or 0) + 1

    # Update video room
    db.table("video_rooms").update({
        "status": "paused",
        "last_paused_at": now,
        "total_pauses": total_pauses,
    }).eq("id", room["id"]).execute()

    # Stop current audio segment
    current_seg = (
        db.table("session_audio_segments")
        .select("*")
        .eq("appointment_id", appointment_id)
        .is_("ended_at", "null")
        .order("segment_number", desc=True)
        .execute()
    )
    active_segment = first_or_none(current_seg)
    if active_segment:
        db.table("session_audio_segments").update({
            "ended_at": now,
        }).eq("id", active_segment["id"]).execute()

        # Stop LiveKit recording
        if active_segment.get("recording_id"):
            await livekit_service.stop_recording(active_segment["recording_id"])

    # Log interruption
    db.table("session_interruptions").insert({
        "appointment_id": appointment_id,
        "event_type": "pause",
        "triggered_by": user_id,
        "reason": reason,
        "occurred_at": now,
    }).execute()

    return {
        "appointment_id": appointment_id,
        "status": "paused",
        "paused_at": now,
        "total_pauses": total_pauses,
    }


# ---------------------------------------------------------------------------
# Resume Session
# ---------------------------------------------------------------------------

async def resume_session(appointment_id: str, user_id: str, db: Any) -> Dict:
    """Resume a paused session.

    Creates a new audio segment and restarts recording.
    """
    appointment = await _get_appointment(appointment_id, db)
    _validate_therapist(user_id, appointment)

    room = await _get_video_room(appointment_id, db)
    if room["status"] != "paused":
        raise HTTPException(
            status_code=400,
            detail="Sessão não está pausada para ser retomada",
        )
    _validate_access_window(room)

    now = _now_sp().isoformat()

    # Update video room
    db.table("video_rooms").update({
        "status": "active",
        "last_resumed_at": now,
    }).eq("id", room["id"]).execute()

    # Count existing segments to determine new segment_number
    existing_segs = (
        db.table("session_audio_segments")
        .select("segment_number")
        .eq("appointment_id", appointment_id)
        .order("segment_number", desc=True)
        .execute()
    )
    last_seg = first_or_none(existing_segs)
    next_number = (last_seg["segment_number"] + 1) if last_seg else 1

    # Create new audio segment
    segment_data = {
        "appointment_id": appointment_id,
        "segment_number": next_number,
        "segment_type": "resumed",
        "started_at": now,
    }
    seg_result = db.table("session_audio_segments").insert(segment_data).execute()
    segment = first_or_none(seg_result)

    # Start new recording
    rec_info = {}
    if segment:
        rec_info = await livekit_service.start_recording(
            room["livekit_room_name"],
            segment["id"],
        )
        if rec_info.get("recording_id"):
            db.table("session_audio_segments").update({
                "recording_id": rec_info["recording_id"],
            }).eq("id", segment["id"]).execute()

    # Log resume event
    db.table("session_interruptions").insert({
        "appointment_id": appointment_id,
        "event_type": "resume",
        "triggered_by": user_id,
        "occurred_at": now,
    }).execute()

    return {
        "appointment_id": appointment_id,
        "status": "active",
        "resumed_at": now,
        "segment_number": next_number,
        "recording": rec_info,
    }


# ---------------------------------------------------------------------------
# End Session
# ---------------------------------------------------------------------------

async def end_session(appointment_id: str, user_id: str, db: Any) -> Dict:
    """End a therapy session.

    Stops recording and marks the appointment as completed.
    Does NOT trigger the AI pipeline — that happens after the therapist
    submits or dismisses the observation popup.
    """
    appointment = await _get_appointment(appointment_id, db)
    _validate_therapist(user_id, appointment)

    room = await _get_video_room(appointment_id, db)
    if room["status"] not in ("active", "paused", "reopened"):
        raise HTTPException(
            status_code=400,
            detail="Sessão não está em andamento para ser finalizada",
        )

    now = _now_sp().isoformat()

    # Update video room
    db.table("video_rooms").update({
        "status": "closed",
        "session_ended_at": now,
    }).eq("id", room["id"]).execute()

    # Stop active audio segment
    current_seg = (
        db.table("session_audio_segments")
        .select("*")
        .eq("appointment_id", appointment_id)
        .is_("ended_at", "null")
        .order("segment_number", desc=True)
        .execute()
    )
    active_segment = first_or_none(current_seg)
    if active_segment:
        db.table("session_audio_segments").update({
            "ended_at": now,
        }).eq("id", active_segment["id"]).execute()

        if active_segment.get("recording_id"):
            await livekit_service.stop_recording(active_segment["recording_id"])

    # Update appointment
    db.table("appointments").update({
        "status": "completed",
        "ended_at": now,
    }).eq("id", appointment_id).execute()

    # Log end event
    db.table("session_interruptions").insert({
        "appointment_id": appointment_id,
        "event_type": "end",
        "triggered_by": user_id,
        "occurred_at": now,
    }).execute()

    # Close LiveKit room
    await livekit_service.close_room(room["livekit_room_name"])

    return {
        "appointment_id": appointment_id,
        "status": "completed",
        "ended_at": now,
    }


# ---------------------------------------------------------------------------
# Auto-Finalize Session
# ---------------------------------------------------------------------------

async def auto_finalize_session(appointment_id: str, db: Any) -> Dict:
    """Auto-finalize a session when the access window expires while paused.

    Called by a background job. Sets reopen_button_visible_until so
    the therapist can still reopen if needed.
    """
    room = await _get_video_room(appointment_id, db)
    if room["status"] not in ("paused", "active"):
        logger.info(
            "Skipping auto-finalize for appointment %s — room status is '%s'",
            appointment_id,
            room["status"],
        )
        return {"appointment_id": appointment_id, "skipped": True}

    now = _now_sp()
    now_iso = now.isoformat()
    reopen_visibility = _get_reopen_visibility_minutes(db)
    reopen_until = (now + timedelta(minutes=reopen_visibility)).isoformat()

    # Stop active audio segment if any
    current_seg = (
        db.table("session_audio_segments")
        .select("*")
        .eq("appointment_id", appointment_id)
        .is_("ended_at", "null")
        .order("segment_number", desc=True)
        .execute()
    )
    active_segment = first_or_none(current_seg)
    if active_segment:
        db.table("session_audio_segments").update({
            "ended_at": now_iso,
        }).eq("id", active_segment["id"]).execute()
        if active_segment.get("recording_id"):
            await livekit_service.stop_recording(active_segment["recording_id"])

    # Update video room
    db.table("video_rooms").update({
        "status": "auto_finalized",
        "auto_finalized_at": now_iso,
        "reopen_button_visible_until": reopen_until,
    }).eq("id", room["id"]).execute()

    # Update appointment
    db.table("appointments").update({
        "status": "completed",
        "ended_at": now_iso,
    }).eq("id", appointment_id).execute()

    # Close LiveKit room
    await livekit_service.close_room(room["livekit_room_name"])

    # Log auto-finalization
    db.table("session_interruptions").insert({
        "appointment_id": appointment_id,
        "event_type": "auto_finalize",
        "occurred_at": now_iso,
    }).execute()

    return {
        "appointment_id": appointment_id,
        "status": "auto_finalized",
        "auto_finalized_at": now_iso,
        "reopen_button_visible_until": reopen_until,
    }


# ---------------------------------------------------------------------------
# Reopen Session
# ---------------------------------------------------------------------------

async def reopen_session(appointment_id: str, user_id: str, db: Any) -> Dict:
    """Reopen a session after auto-finalization.

    Only allowed if the therapist clicks "Reopen" within the visibility window.
    """
    appointment = await _get_appointment(appointment_id, db)
    _validate_therapist(user_id, appointment)

    room = await _get_video_room(appointment_id, db)
    if room["status"] != "auto_finalized":
        raise HTTPException(
            status_code=400,
            detail="Sessão não foi auto-finalizada — não pode ser reaberta",
        )

    now = _now_sp()
    visible_until = _parse_dt(room["reopen_button_visible_until"])
    if now > visible_until:
        raise HTTPException(
            status_code=400,
            detail="O prazo para reabrir a sessão expirou",
        )

    now_iso = now.isoformat()
    reopen_duration = _get_reopen_duration_minutes(db)
    reopen_count = (room.get("reopen_count") or 0) + 1
    reopen_until = (now + timedelta(minutes=reopen_duration)).isoformat()

    # Update video room
    db.table("video_rooms").update({
        "status": "reopened",
        "last_reopened_at": now_iso,
        "reopen_count": reopen_count,
        "reopen_until": reopen_until,
    }).eq("id", room["id"]).execute()

    # Update appointment back to in_progress
    db.table("appointments").update({
        "status": "in_progress",
    }).eq("id", appointment_id).execute()

    # Create LiveKit room again
    lk_room = await livekit_service.create_room(room["livekit_room_name"])

    # Count existing segments
    existing_segs = (
        db.table("session_audio_segments")
        .select("segment_number")
        .eq("appointment_id", appointment_id)
        .order("segment_number", desc=True)
        .execute()
    )
    last_seg = first_or_none(existing_segs)
    next_number = (last_seg["segment_number"] + 1) if last_seg else 1

    # Create new audio segment
    segment_data = {
        "appointment_id": appointment_id,
        "segment_number": next_number,
        "segment_type": "reopened",
        "started_at": now_iso,
    }
    seg_result = db.table("session_audio_segments").insert(segment_data).execute()
    segment = first_or_none(seg_result)

    # Start recording
    rec_info = {}
    if segment:
        rec_info = await livekit_service.start_recording(
            room["livekit_room_name"],
            segment["id"],
        )
        if rec_info.get("recording_id"):
            db.table("session_audio_segments").update({
                "recording_id": rec_info["recording_id"],
            }).eq("id", segment["id"]).execute()

    # Log reopen event
    db.table("session_interruptions").insert({
        "appointment_id": appointment_id,
        "event_type": "reopen",
        "triggered_by": user_id,
        "occurred_at": now_iso,
    }).execute()

    # Generate token for therapist
    token = await livekit_service.generate_token(
        room["livekit_room_name"],
        participant_identity=user_id,
        participant_name="Terapeuta",
    )

    return {
        "appointment_id": appointment_id,
        "status": "reopened",
        "reopened_at": now_iso,
        "reopen_until": reopen_until,
        "reopen_count": reopen_count,
        "token": token,
        "livekit_room": lk_room,
        "recording": rec_info,
    }


# ---------------------------------------------------------------------------
# Session Status
# ---------------------------------------------------------------------------

async def get_session_status(appointment_id: str, db: Any) -> Dict:
    """Get the full session state including timing and interruption history."""
    appointment = await _get_appointment(appointment_id, db)
    room = await _get_video_room(appointment_id, db)

    # Fetch interruption history
    interruptions = (
        db.table("session_interruptions")
        .select("*")
        .eq("appointment_id", appointment_id)
        .order("occurred_at")
        .execute()
    )

    now = _now_sp()
    accessible_until = _parse_dt(room["accessible_until"])
    remaining_seconds = max(0, (accessible_until - now).total_seconds())

    return {
        "appointment_id": appointment_id,
        "appointment_status": appointment["status"],
        "video_room_status": room["status"],
        "accessible_from": room["accessible_from"],
        "accessible_until": room["accessible_until"],
        "session_started_at": room.get("session_started_at"),
        "session_ended_at": room.get("session_ended_at"),
        "total_pauses": room.get("total_pauses") or 0,
        "reopen_count": room.get("reopen_count") or 0,
        "remaining_seconds": int(remaining_seconds),
        "reopen_button_visible_until": room.get("reopen_button_visible_until"),
        "interruptions": interruptions.data or [],
    }


# ---------------------------------------------------------------------------
# Overtime Info
# ---------------------------------------------------------------------------

_ALERT_THRESHOLDS = [30, 15, 10, 5, 2, 1]


async def get_overtime_info(appointment_id: str, db: Any) -> Dict:
    """Get overtime information with alert thresholds."""
    room = await _get_video_room(appointment_id, db)

    now = _now_sp()
    accessible_until = _parse_dt(room["accessible_until"])
    remaining_seconds = max(0, (accessible_until - now).total_seconds())
    remaining_minutes = remaining_seconds / 60

    alerts = [
        {"threshold_minutes": t, "triggered": remaining_minutes <= t}
        for t in _ALERT_THRESHOLDS
    ]

    return {
        "appointment_id": appointment_id,
        "accessible_until": room["accessible_until"],
        "remaining_seconds": int(remaining_seconds),
        "remaining_minutes": round(remaining_minutes, 1),
        "alerts": alerts,
    }
