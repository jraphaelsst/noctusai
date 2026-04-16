"""Email templates router — CRUD, preview, send test."""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from app.dependencies import get_current_user, get_org_id, get_admin_client
from app.schemas.templates import TemplateCreate, TemplateUpdate, TemplatePreviewRequest, TemplateSendTestRequest
from app.services.template_service import TemplateService
from noctusai_lib.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/templates", tags=["Templates"])


def _get_service(user) -> TemplateService:
    org_id = get_org_id(user)
    return TemplateService(get_admin_client(), org_id)


@router.get("")
async def list_templates(
    authorization: Optional[str] = Header(None),
    categoria: Optional[str] = Query(None),
):
    user, _ = await get_current_user(authorization)
    svc = _get_service(user)
    return success_response(svc.list_templates(categoria=categoria))


@router.post("")
async def create_template(body: TemplateCreate, authorization: Optional[str] = Header(None)):
    user, _ = await get_current_user(authorization)
    svc = _get_service(user)
    result = svc.create_template(body.model_dump())
    if not result:
        raise HTTPException(status_code=400, detail="Erro ao criar template")
    return success_response(result)


@router.get("/{template_id}")
async def get_template(template_id: str, authorization: Optional[str] = Header(None)):
    user, _ = await get_current_user(authorization)
    svc = _get_service(user)
    result = svc.get_template(template_id)
    if not result:
        raise HTTPException(status_code=404, detail="Template nao encontrado")
    return success_response(result)


@router.patch("/{template_id}")
async def update_template(template_id: str, body: TemplateUpdate, authorization: Optional[str] = Header(None)):
    user, _ = await get_current_user(authorization)
    svc = _get_service(user)
    data = body.model_dump(exclude_unset=True)
    result = svc.update_template(template_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Template nao encontrado")
    return success_response(result)


@router.delete("/{template_id}")
async def delete_template(template_id: str, authorization: Optional[str] = Header(None)):
    user, _ = await get_current_user(authorization)
    svc = _get_service(user)
    svc.delete_template(template_id)
    return {"ok": True, "message": "Template desativado"}


@router.post("/{template_id}/preview")
async def preview_template(
    template_id: str,
    body: TemplatePreviewRequest,
    authorization: Optional[str] = Header(None),
):
    user, _ = await get_current_user(authorization)
    svc = _get_service(user)
    result = svc.preview(template_id, body.variaveis)
    if not result:
        raise HTTPException(status_code=404, detail="Template nao encontrado")
    return success_response(result)
