"""CoreStudio publication targets: ``/api/media-creation/cs-posts/{post_id}/publicacoes``.

Creating a target is checked against the rede x formato x assets matrix (``post_formatos``): an invalid one is a 422
whose ``code`` names the first reason (``motivos`` lists all).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from noctusai_lib.primitives.responses import success_response

from app.dependencies import coerce_org_uuid, get_admin_client, get_current_user_org
from app.modules.media_creation.schemas.post_publicacoes import PublicacaoAtualizar, PublicacaoCriar
from app.modules.media_creation.services.post_assets_service import PostAssetError
from app.modules.media_creation.services.post_publicacoes_service import PostPublicacoesService

router = APIRouter(prefix="/api/media-creation/cs-posts", tags=["Media Creation — Post publicações"])


def get_post_publicacoes_db() -> Any:
    return get_admin_client()


def _svc(auth, db) -> PostPublicacoesService:
    return PostPublicacoesService(db, str(coerce_org_uuid(auth[2])), str(auth[0].id))


@router.get("/{post_id}/publicacoes")
def listar_publicacoes(post_id: str, auth=Depends(get_current_user_org), db=Depends(get_post_publicacoes_db)):
    try:
        return success_response(_svc(auth, db).listar(post_id))
    except PostAssetError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)


@router.post("/{post_id}/publicacoes", status_code=201)
def criar_publicacao(post_id: str, body: PublicacaoCriar, auth=Depends(get_current_user_org), db=Depends(get_post_publicacoes_db)):
    try:
        return success_response(_svc(auth, db).criar(
            post_id, rede=body.rede, formato=body.formato, conta_id=body.conta_id, publicar_em=body.publicar_em,
        ))
    except PostAssetError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)


@router.patch("/{post_id}/publicacoes/{pub_id}")
def atualizar_publicacao(
    post_id: str, pub_id: str, body: PublicacaoAtualizar, auth=Depends(get_current_user_org), db=Depends(get_post_publicacoes_db),
):
    try:
        return success_response(_svc(auth, db).atualizar(post_id, pub_id, publicar_em=body.publicar_em, status=body.status))
    except PostAssetError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)
