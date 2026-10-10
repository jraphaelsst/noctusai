"""Treinamentos (geracao-contract.md §4.2, endpoints 4-6 + ``/treinamentos/admin``).

Reads: any authenticated user. Writes: platform admins only (``require_platform_admin``).
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response

from noctusai_lib.primitives.responses import success_response

from app.dependencies import (
    get_admin_client,
    get_current_user_org,
    get_platform_admin_check,
    require_platform_admin,
)
from app.modules.media_creation.schemas.perfil_criacao import TreinamentoCreate, TreinamentoUpdate
from app.modules.media_creation.services.treinamentos_service import TreinamentoError, TreinamentosService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media-creation/treinamentos", tags=["Media Creation — Treinamentos"])


def _svc(auth) -> TreinamentosService:
    return TreinamentosService(get_admin_client(), str(auth[0].id))


def _raise(exc: TreinamentoError):
    raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.get("")
async def listar_treinamentos(auth=Depends(get_current_user_org), is_admin=Depends(get_platform_admin_check)):
    """Members see the active lessons; a platform admin also sees the inactive ones (``ativo: false``)."""
    return success_response(_svc(auth).listar(incluir_inativos=bool(is_admin(str(auth[0].id)))))


@router.get("/admin")
async def treinamentos_admin(auth=Depends(get_current_user_org), is_admin=Depends(get_platform_admin_check)):
    """Whether the caller may edit (drives the FE edit controls; the writes enforce it themselves)."""
    return success_response({"is_admin": bool(is_admin(str(auth[0].id)))})


@router.post("", status_code=201)
async def criar_treinamento(body: TreinamentoCreate, auth=Depends(require_platform_admin)):
    try:
        return success_response(_svc(auth).criar(**body.model_dump()))
    except TreinamentoError as exc:
        _raise(exc)


@router.put("/{treinamento_id}")
async def atualizar_treinamento(
    treinamento_id: uuid.UUID, body: TreinamentoUpdate, auth=Depends(require_platform_admin),
):
    patch = {k: getattr(body, k) for k in body.model_fields_set}
    # null is meaningful only for video_url (clears it); null on a NOT NULL column is a client error.
    nulos = [k for k, v in patch.items() if v is None and k != "video_url"]
    if nulos:
        raise HTTPException(status_code=422, detail=f"Valor nulo não permitido: {', '.join(sorted(nulos))}")
    try:
        return success_response(_svc(auth).atualizar(str(treinamento_id), patch))
    except TreinamentoError as exc:
        _raise(exc)


@router.delete("/{treinamento_id}", status_code=204)
async def excluir_treinamento(treinamento_id: uuid.UUID, auth=Depends(require_platform_admin)):
    try:
        _svc(auth).excluir(str(treinamento_id))
    except TreinamentoError as exc:
        _raise(exc)
    return Response(status_code=204)
