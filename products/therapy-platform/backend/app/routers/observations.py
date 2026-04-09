"""
Observations Router — Therapist observations on sessions.

CRUD for session observations. Each mutation triggers clinical summary
regeneration (Track 2) in the background, with a 30-second debounce.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from app.dependencies import (
    first_or_none,
    get_admin_client,
    get_current_user,
    get_user_client,
    get_user_role,
)
from app.responses import success_response
from app.schemas.session import ObservationCreate, ObservationUpdate
from app.services import ai_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/observations", tags=["Observations"])

SP_TZ = timezone(timedelta(hours=-3))

_DEBOUNCE_SECONDS = 30


def _should_regenerate(session_record_id: str, db) -> bool:
    """Check if enough time has passed since the last clinical summary version.

    Returns False if the last version was created < 30 seconds ago (debounce).
    """
    result = (
        db.table("session_summary_versions")
        .select("created_at")
        .eq("session_record_id", session_record_id)
        .eq("track", "clinical")
        .order("created_at", desc=True)
        .execute()
    )
    latest = first_or_none(result)
    if not latest or not latest.get("created_at"):
        return True

    try:
        last_created = datetime.fromisoformat(
            latest["created_at"].replace("Z", "+00:00")
        )
        now = datetime.now(SP_TZ)
        return (now - last_created).total_seconds() >= _DEBOUNCE_SECONDS
    except (ValueError, TypeError):
        return True


@router.post("")
async def create_observation(
    body: ObservationCreate,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
):
    """Create a therapist observation for a session.

    Triggers clinical summary regeneration in the background.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem criar observações")

    db = get_user_client(token)

    # Verify session record exists and belongs to this therapist
    sr = (
        db.table("session_records")
        .select("id, therapist_id")
        .eq("id", body.session_record_id)
        .execute()
    )
    record = first_or_none(sr)
    if not record:
        raise HTTPException(status_code=404, detail="Registro de sessão não encontrado")
    if record["therapist_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para este registro de sessão")

    # Create observation
    obs_data = {
        "session_record_id": body.session_record_id,
        "therapist_id": user.id,
        "observation_text": body.observation_text,
        "is_initial": False,
    }
    result = db.table("session_observations").insert(obs_data).execute()
    observation = first_or_none(result)
    if not observation:
        raise HTTPException(status_code=500, detail="Erro ao criar observação")

    # Trigger regeneration with debounce
    admin_db = get_admin_client()
    if _should_regenerate(body.session_record_id, admin_db):
        background_tasks.add_task(
            ai_pipeline.on_observation_change,
            session_record_id=body.session_record_id,
            db=admin_db,
        )

    return success_response(observation)


@router.get("/session/{session_record_id}")
async def list_observations(
    session_record_id: str,
    authorization: Optional[str] = Header(None),
):
    """List all observations for a session (ordered by created_at).

    Therapist and clinic_admin can view. Patient cannot.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role not in ("therapist", "clinic_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar observações")

    db = get_user_client(token)

    # Verify access: therapist must own the session, clinic_admin must be affiliated
    if role == "therapist":
        sr = (
            db.table("session_records")
            .select("therapist_id")
            .eq("id", session_record_id)
            .execute()
        )
        record = first_or_none(sr)
        if not record:
            raise HTTPException(status_code=404, detail="Registro de sessão não encontrado")
        if record["therapist_id"] != user.id:
            raise HTTPException(status_code=403, detail="Sem permissão para este registro de sessão")

    result = (
        db.table("session_observations")
        .select("*")
        .eq("session_record_id", session_record_id)
        .is_("deleted_at", "null")
        .order("created_at")
        .execute()
    )
    return success_response(result.data or [])


@router.patch("/{observation_id}")
async def update_observation(
    observation_id: str,
    body: ObservationUpdate,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
):
    """Update an observation's text.

    Triggers clinical summary regeneration in the background.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem editar observações")

    db = get_user_client(token)

    # Verify ownership
    obs = (
        db.table("session_observations")
        .select("*")
        .eq("id", observation_id)
        .is_("deleted_at", "null")
        .execute()
    )
    observation = first_or_none(obs)
    if not observation:
        raise HTTPException(status_code=404, detail="Observação não encontrada")
    if observation["therapist_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para editar esta observação")

    # Update
    result = (
        db.table("session_observations")
        .update({"observation_text": body.observation_text})
        .eq("id", observation_id)
        .execute()
    )
    updated = first_or_none(result)

    # Trigger regeneration with debounce
    session_record_id = observation["session_record_id"]
    admin_db = get_admin_client()
    if _should_regenerate(session_record_id, admin_db):
        background_tasks.add_task(
            ai_pipeline.on_observation_change,
            session_record_id=session_record_id,
            db=admin_db,
        )

    return success_response(updated or {**observation, "observation_text": body.observation_text})


@router.delete("/{observation_id}")
async def delete_observation(
    observation_id: str,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
):
    """Soft-delete an observation (set deleted_at).

    Triggers clinical summary regeneration in the background.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem excluir observações")

    db = get_user_client(token)

    # Verify existence and ownership
    obs = (
        db.table("session_observations")
        .select("*")
        .eq("id", observation_id)
        .is_("deleted_at", "null")
        .execute()
    )
    observation = first_or_none(obs)
    if not observation:
        raise HTTPException(status_code=404, detail="Observação não encontrada")
    if observation["therapist_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para excluir esta observação")

    # Soft delete
    now = datetime.now(SP_TZ).isoformat()
    db.table("session_observations").update({
        "deleted_at": now,
    }).eq("id", observation_id).execute()

    # Trigger regeneration with debounce
    session_record_id = observation["session_record_id"]
    admin_db = get_admin_client()
    if _should_regenerate(session_record_id, admin_db):
        background_tasks.add_task(
            ai_pipeline.on_observation_change,
            session_record_id=session_record_id,
            db=admin_db,
        )

    from app.responses import ok_response
    return ok_response("Observação excluída com sucesso")
