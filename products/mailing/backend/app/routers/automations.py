"""Automations router — CRUD, steps, enrollments."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from app.dependencies import get_current_user_org, get_org_id, get_admin_client
from app.schemas.automations import (
    AutomationCreate, AutomationUpdate, StepCreate, StepUpdate, StepReorder, EnrollContacts,
)
from app.services.automation_service import AutomationService
from noctusai_lib.primitives.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/automations", tags=["Automations"])


def _get_service(user) -> AutomationService:
    return AutomationService(get_admin_client(), get_org_id(user))


@router.get("")
async def list_automations(auth = Depends(get_current_user_org), status: Optional[str] = Query(None)):
    user, _, org_id = auth
    return success_response(_get_service(user).list_automations(status=status))


@router.post("")
async def create_automation(body: AutomationCreate, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    result = _get_service(user).create_automation(body.model_dump(), str(user.id))
    if not result:
        raise HTTPException(status_code=400, detail="Erro ao criar automacao")
    return success_response(result)


@router.get("/{automation_id}")
async def get_automation(automation_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    svc = _get_service(user)
    result = svc.get_automation(automation_id)
    if not result:
        raise HTTPException(status_code=404, detail="Automacao nao encontrada")
    result["steps"] = svc.list_steps(automation_id)
    return success_response(result)


@router.patch("/{automation_id}")
async def update_automation(automation_id: str, body: AutomationUpdate, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    result = _get_service(user).update_automation(automation_id, body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Automacao nao encontrada")
    return success_response(result)


@router.delete("/{automation_id}")
async def delete_automation(automation_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    if not _get_service(user).delete_automation(automation_id):
        raise HTTPException(status_code=400, detail="Apenas rascunhos podem ser excluidos")
    return {"ok": True, "message": "Automacao excluida"}


@router.post("/{automation_id}/activate")
async def activate(automation_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    result = _get_service(user).activate(automation_id)
    if not result:
        raise HTTPException(status_code=400, detail="Erro ao ativar")
    return success_response(result)


@router.post("/{automation_id}/pause")
async def pause(automation_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    result = _get_service(user).pause(automation_id)
    if not result:
        raise HTTPException(status_code=400, detail="Erro ao pausar")
    return success_response(result)


# -- Steps --

@router.get("/{automation_id}/steps")
async def list_steps(automation_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    return success_response(_get_service(user).list_steps(automation_id))


@router.post("/{automation_id}/steps")
async def add_step(automation_id: str, body: StepCreate, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    result = _get_service(user).add_step(automation_id, body.model_dump())
    if not result:
        raise HTTPException(status_code=400, detail="Erro ao adicionar step")
    return success_response(result)


@router.patch("/{automation_id}/steps/{step_id}")
async def update_step(automation_id: str, step_id: str, body: StepUpdate, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    result = _get_service(user).update_step(automation_id, step_id, body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Step nao encontrado")
    return success_response(result)


@router.delete("/{automation_id}/steps/{step_id}")
async def delete_step(automation_id: str, step_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    _get_service(user).delete_step(automation_id, step_id)
    return {"ok": True}


@router.post("/{automation_id}/steps/reorder")
async def reorder_steps(automation_id: str, body: StepReorder, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    result = _get_service(user).reorder_steps(automation_id, body.step_ids)
    return success_response(result)


# -- Enrollments --

@router.get("/{automation_id}/enrollments")
async def list_enrollments(automation_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    return success_response(_get_service(user).list_enrollments(automation_id))


@router.post("/{automation_id}/enroll")
async def enroll_contacts(automation_id: str, body: EnrollContacts, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    result = _get_service(user).enroll_contacts(automation_id, body.contact_ids)
    return success_response(result)
