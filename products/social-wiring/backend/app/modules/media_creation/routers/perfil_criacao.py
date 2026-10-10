"""Meu Perfil + taxonomias (geracao-contract.md §4.1, endpoints 1-3)."""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException

from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.schemas.perfil_criacao import PerfilCriacaoUpdate
from app.modules.media_creation.services.perfil_service import PerfilError, PerfilService, taxonomias

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media-creation", tags=["Media Creation — Meu Perfil"])


def perfil_service(auth) -> PerfilService:
    user, _, org_id = auth
    return PerfilService(get_admin_client(), org_id, str(user.id))


def raise_http(exc: PerfilError):
    raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.get("/taxonomias")
async def get_taxonomias(auth=Depends(get_current_user_org)):
    return success_response(taxonomias())


@router.get("/perfil")
async def get_perfil(marca_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(perfil_service(auth).get(str(marca_id)))
    except PerfilError as exc:
        raise_http(exc)


@router.put("/perfil")
async def put_perfil(body: PerfilCriacaoUpdate, auth=Depends(get_current_user_org)):
    try:
        fields = {k: getattr(body, k) for k in body.model_fields_set if k != "marca_id"}
        return success_response(perfil_service(auth).save(str(body.marca_id), **fields))
    except PerfilError as exc:
        raise_http(exc)
