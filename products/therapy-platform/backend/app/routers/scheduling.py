"""Scheduling router — candidate-slot generation + booking.

Per the pilot's §2 decisions: multi-clinic + solo, internal +
Google Calendar two-way (Fake fallback when credentials missing),
new `/api/scheduling/*` URL prefix to avoid collision with the
parallel `therapy-platform-wiring` agent's `/api/availability` and
`/api/appointments` surfaces.

Auth gates per §7 Q2 recommendation: therapist-initiated booking only
at MVP. Patient self-booking arrives in a follow-up project.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import settings
from app.dependencies import get_current_user, get_user_client, get_user_role
from app.responses import success_response
from app.services.scheduling import (
    book_appointment,
    generate_candidate_slots,
    reschedule_appointment,
    resolve_calendar_for_therapist,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scheduling", tags=["Scheduling"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CandidateSlotDTO(BaseModel):
    start_at: datetime
    end_at: datetime
    duration_minutes: int
    score: float = 0.0


class BookAppointmentBody(BaseModel):
    therapist_id: str = Field(..., description="UUID of the therapist")
    patient_id: str = Field(..., description="UUID of the patient")
    clinic_id: Optional[str] = Field(None, description="Optional clinic UUID")
    slot_start: datetime
    slot_end: datetime
    summary: str = "Sessão de terapia"


class RescheduleBody(BaseModel):
    slot_start: datetime
    slot_end: datetime


# ---------------------------------------------------------------------------
# Google Calendar OAuth (per-therapist; 7-day re-auth window)
# ---------------------------------------------------------------------------

_GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GCAL_SCOPES = "https://www.googleapis.com/auth/calendar"


def _build_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "scope": _GCAL_SCOPES,
        "state": state,
    }
    return f"{_GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/candidates")
async def list_candidates(
    therapist_id: str = Query(...),
    window_start: datetime = Query(...),
    window_end: datetime = Query(...),
    clinic_id: Optional[str] = Query(None),
    duration_minutes: int = Query(50, ge=15, le=240),
    authorization: Optional[str] = Header(None),
):
    """Return ranked candidate slots for the therapist within the
    requested window. Therapists query their own; admins / clinic
    admins may query any therapist."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)

    if role == "therapist":
        if user.id != therapist_id:
            raise HTTPException(
                status_code=403,
                detail="Therapists can only request their own candidate slots",
            )
    elif role not in ("platform_admin", "clinic_admin"):
        raise HTTPException(
            status_code=403,
            detail="Patient self-booking not enabled in MVP",
        )

    db = get_user_client(token)
    adapter, calendar_id = resolve_calendar_for_therapist(
        db=db,
        therapist_id=therapist_id,
        client_id=settings.therapy_google_client_id,
        client_secret=settings.therapy_google_client_secret,
    )
    slots = generate_candidate_slots(
        therapist_id=therapist_id,
        clinic_id=clinic_id,
        window_start=window_start,
        window_end=window_end,
        duration_minutes=duration_minutes,
        db=db,
        calendar_adapter=adapter,
        calendar_id=calendar_id,
    )
    payload = [
        CandidateSlotDTO(
            start_at=s.start_at,
            end_at=s.end_at,
            duration_minutes=s.duration_minutes,
            score=s.score,
        ).model_dump(mode="json")
        for s in slots
    ]
    return success_response(payload)


@router.post("/appointments")
async def book(
    body: BookAppointmentBody,
    authorization: Optional[str] = Header(None),
):
    """Book a confirmed slot. Writes the GCal event in the same call
    (best-effort; appointment row persisted regardless of GCal write
    success)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)

    if role == "therapist":
        if user.id != body.therapist_id:
            raise HTTPException(
                status_code=403,
                detail="Therapists can only book on their own calendar",
            )
    elif role not in ("platform_admin", "clinic_admin"):
        raise HTTPException(
            status_code=403,
            detail="Patient self-booking not enabled in MVP",
        )

    # LGPD: appointment metadata + GCal write = personal-data export.
    # Logged here as the boundary; the data subject is the patient.
    logger.info(
        "lgpd:gcal_export therapist=%s patient=%s slot=%s",
        body.therapist_id,
        body.patient_id,
        body.slot_start.isoformat(),
    )

    db = get_user_client(token)
    adapter, calendar_id = resolve_calendar_for_therapist(
        db=db,
        therapist_id=body.therapist_id,
        client_id=settings.therapy_google_client_id,
        client_secret=settings.therapy_google_client_secret,
    )
    appt = book_appointment(
        therapist_id=body.therapist_id,
        patient_id=body.patient_id,
        clinic_id=body.clinic_id,
        slot_start=body.slot_start,
        slot_end=body.slot_end,
        db=db,
        calendar_adapter=adapter,
        calendar_id=calendar_id,
        summary=body.summary,
    )
    return success_response(appt)


@router.get("/gcal/authorize")
async def gcal_authorize(
    therapist_id: str = Query(...),
    redirect_uri: str = Query(
        "http://localhost:5173/therapist/scheduling/gcal-callback",
        description="Frontend callback URL; must match a registered URI in Google Cloud Console",
    ),
    authorization: Optional[str] = Header(None),
):
    """Build the Google OAuth consent URL for the therapist + report
    whether re-authorization is needed (i.e. the stored token is older
    than 7 days OR no token exists)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role == "therapist" and user.id != therapist_id:
        raise HTTPException(
            status_code=403,
            detail="Therapists can only authorize their own calendar",
        )

    client_id = settings.therapy_google_client_id
    if not client_id:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth client not configured (THERAPY_GOOGLE_CLIENT_ID)",
        )

    db = get_user_client(token)
    fresh_resp = (
        db.table("therapist_profiles")
        .select("gcal_authorized_at, gcal_refresh_token_encrypted")
        .eq("user_id", therapist_id)
        .limit(1)
        .execute()
    )
    rows = getattr(fresh_resp, "data", None) or []
    needs_authorization = True
    if rows and rows[0].get("gcal_refresh_token_encrypted"):
        rpc = db.rpc(
            "gcal_authorization_is_fresh",
            {"authorized_at": rows[0].get("gcal_authorized_at")},
        ).execute()
        needs_authorization = not bool(getattr(rpc, "data", False))

    return success_response(
        {
            "authorize_url": _build_authorize_url(client_id, redirect_uri, therapist_id),
            "needs_authorization": needs_authorization,
        }
    )


@router.get("/gcal/callback")
async def gcal_callback(
    code: str = Query(...),
    state: str = Query(..., description="therapist_id round-tripped from authorize"),
    redirect_uri: str = Query(
        "http://localhost:5173/therapist/scheduling/gcal-callback",
    ),
    authorization: Optional[str] = Header(None),
):
    """Exchange OAuth code → refresh_token, encrypt + persist via the
    therapy.encrypt_gcal_token helper, set gcal_authorized_at = now().

    Calls Google's token endpoint via httpx; mocked in tests via
    `unittest.mock.patch.object(httpx.AsyncClient, "post", ...)`.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    therapist_id = state

    if role == "therapist" and user.id != therapist_id:
        raise HTTPException(
            status_code=403,
            detail="Therapists can only complete their own OAuth flow",
        )

    client_id = settings.therapy_google_client_id
    client_secret = settings.therapy_google_client_secret
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth client not configured",
        )

    async with httpx.AsyncClient(timeout=10.0) as http:
        token_resp = await http.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if token_resp.status_code >= 400:
        logger.warning(
            "Google token exchange failed (status=%s body=%s)",
            token_resp.status_code,
            token_resp.text[:500],
        )
        raise HTTPException(status_code=502, detail="Google token exchange failed")
    token_payload = token_resp.json()
    refresh_token = token_payload.get("refresh_token")
    if not refresh_token:
        # Google omits refresh_token if the user already consented and
        # the previous grant is still active. Force re-consent via
        # `prompt=consent` (already in authorize URL); surface a
        # clearer error if it still happens.
        raise HTTPException(
            status_code=502,
            detail="Google did not return refresh_token (revoke prior grant or set prompt=consent)",
        )

    db = get_user_client(token)
    encrypt_resp = db.rpc(
        "encrypt_gcal_token", {"token": refresh_token}
    ).execute()
    ciphertext = getattr(encrypt_resp, "data", None)
    if ciphertext is None:
        raise HTTPException(
            status_code=500,
            detail="Token encryption failed (vault key missing?)",
        )

    db.table("therapist_profiles").update(
        {
            "gcal_refresh_token_encrypted": ciphertext,
            "gcal_authorized_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("user_id", therapist_id).execute()

    return success_response(
        {"connected": True, "authorized_at": datetime.now(timezone.utc).isoformat()}
    )


@router.patch("/appointments/{appointment_id}")
async def reschedule(
    appointment_id: str,
    body: RescheduleBody,
    authorization: Optional[str] = Header(None),
):
    """Reschedule in-place: update DB times + update the GCal event via
    `CalendarAdapter.update_event` (preserves event_id; attendees see a
    move rather than a delete-and-new-invite)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)

    db = get_user_client(token)
    fetch = (
        db.table("appointments")
        .select("therapist_id, patient_id, clinic_id, status")
        .eq("id", appointment_id)
        .limit(1)
        .execute()
    )
    rows = getattr(fetch, "data", None) or []
    if not rows:
        raise HTTPException(status_code=404, detail="Appointment not found")
    original = rows[0]

    if role == "therapist" and user.id != original["therapist_id"]:
        raise HTTPException(
            status_code=403,
            detail="Therapists can only reschedule their own appointments",
        )
    if role not in ("therapist", "platform_admin", "clinic_admin"):
        raise HTTPException(
            status_code=403,
            detail="Patient self-rescheduling not enabled in MVP",
        )

    adapter, calendar_id = resolve_calendar_for_therapist(
        db=db,
        therapist_id=original["therapist_id"],
        client_id=settings.therapy_google_client_id,
        client_secret=settings.therapy_google_client_secret,
    )
    moved = reschedule_appointment(
        appointment_id=appointment_id,
        new_start=body.slot_start,
        new_end=body.slot_end,
        db=db,
        calendar_adapter=adapter,
        calendar_id=calendar_id,
    )
    return success_response(moved)
