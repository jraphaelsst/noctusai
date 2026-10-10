"""Equipe endpoints (esteira-contract.md 5.2): ``/api/media-creation/equipe``.

Auth ``get_current_user_org``, ``success_response`` envelope, org-scoped (a foreign id is a 404).
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from noctusai_lib.primitives.responses import success_response

from app.dependencies import coerce_org_uuid, get_admin_client, get_current_user_org
from app.modules.media_creation.schemas.equipe import MembroCreate, MembroUpdate
from app.modules.media_creation.services.equipe_service import EquipeService
from app.modules.media_creation.services.esteira_service import EsteiraError

router = APIRouter(prefix="/api/media-creation/equipe", tags=["Media Creation — Equipe"])


def _svc(auth) -> EquipeService:
    user, _token, raw_org = auth
    return EquipeService(get_admin_client(), str(coerce_org_uuid(raw_org)), str(user.id))


def _raise(exc: EsteiraError):
    raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.get("")
def listar_equipe(incluir_inativos: bool = Query(False), auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).listar(incluir_inativos))
    except EsteiraError as exc:
        _raise(exc)


@router.post("", status_code=201)
def criar_membro(body: MembroCreate, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).criar(body))
    except EsteiraError as exc:
        _raise(exc)


@router.patch("/{membro_id}")
def atualizar_membro(membro_id: str, body: MembroUpdate, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).atualizar(membro_id, body))
    except EsteiraError as exc:
        _raise(exc)


@router.delete("/{membro_id}", status_code=204)
def excluir_membro(membro_id: str, auth=Depends(get_current_user_org)):
    try:
        _svc(auth).excluir(membro_id)
    except EsteiraError as exc:
        _raise(exc)
