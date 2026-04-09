"""
LGPD Router — Data deletion endpoints per Brazilian data protection law.

Patients can request deletion of their own data.
Therapists can delete specific entities (sessions, observations) or all data.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from app.dependencies import get_current_user, get_admin_client, get_user_role
from app.responses import success_response
from app.schemas.settings import DataDeletionRequest
from app.services import lgpd_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/lgpd", tags=["LGPD"])


@router.post("/delete-my-data")
async def delete_my_data(
    body: DataDeletionRequest,
    authorization: Optional[str] = Header(None),
):
    """Patient requests deletion of all their data (LGPD).

    Requires exact confirmation text: 'CONFIRMAR EXCLUSAO'.
    Only patients can use this endpoint.
    """
    user, _ = await get_current_user(authorization)
    role = get_user_role(user)

    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem solicitar exclusão dos próprios dados")

    db = get_admin_client()
    result = await lgpd_service.delete_patient_data(patient_id=user.id, db=db)
    return success_response(result)


@router.post("/delete-data/{entity_type}/{entity_id}")
async def delete_therapist_data(
    entity_type: str,
    entity_id: str,
    authorization: Optional[str] = Header(None),
):
    """Therapist deletes specific data or all data.

    entity_type: session | observation | all
    entity_id: the specific record ID (ignored when entity_type='all')
    """
    user, _ = await get_current_user(authorization)
    role = get_user_role(user)

    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem usar este endpoint")

    if entity_type not in ("session", "observation", "all"):
        raise HTTPException(status_code=400, detail="Tipo deve ser 'session', 'observation' ou 'all'")

    db = get_admin_client()
    result = await lgpd_service.delete_therapist_data(
        therapist_id=user.id,
        entity_type=entity_type,
        entity_id=entity_id if entity_type != "all" else None,
        db=db,
    )
    return success_response(result)
