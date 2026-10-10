"""Esteira de reels endpoints (esteira-contract.md 5.1): ``/api/media-creation/esteira``.

Four routers, mounted in this order (``ROUTERS``):

1. ``stages_router`` — the seed ``pipeline_stages_router`` at ``/etapas`` (no admin gate, the same
   guard as SW's funil/processos stage editors).
2. ``hub_collection_router`` — the card hub's literal paths (``/posts/tags``,
   ``/posts/documentos/tipos``); MUST precede ``router``'s bare ``/posts/{id}``.
3. ``router`` — board, posts CRUD, ``mover-etapa``, headline/roteiro binding.
4. ``hub_entity_router`` — the card hub's ``/posts/{post_id}/...`` routes.

Auth ``get_current_user_org``; ``success_response`` envelope; a foreign id is a 404; coded refusals
are ``HTTPException(status, detail={"code", "detail", ...})``.
"""
import json
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import ValidationError

from noctusai_lib.domain.card_hub import CardHubContext, card_hub_routers
from noctusai_lib.domain.pipeline import PipelineContext, ensure_default_stages, pipeline_stages_router
from noctusai_lib.primitives.responses import success_response

from app.dependencies import coerce_org_uuid, get_admin_client, get_current_user_org
from app.modules.card_hub.deps import get_storage_backend
from app.modules.media_creation.esteira_config import CS_POST_HUB, ESTEIRA_PADRAO, PIPELINE_ESTEIRA
from app.modules.media_creation.schemas.esteira import (
    CAMPOS_NAO_EDITAVEIS,
    HeadlineBind,
    MoverEtapaRequest,
    PostCreate,
    PostUpdate,
    RoteiroBind,
)
from app.modules.media_creation.services.esteira_service import LIMITE_PADRAO, EsteiraError, EsteiraService

PREFIX = "/api/media-creation/esteira"

#: 🔴 THE APP REFUSES TO BOOT WITHOUT THESE in `app.main._MAX_BODY_PATH_OVERRIDES` (the card hub
#: mounts two `UploadFile` routes under the post). 30 MB, the same outer bound as the other card-hub
#: document surfaces; the hub's own business-policy limit (25 MB) stays under it.
MAX_BODY_PATH_OVERRIDES = {
    f"{PREFIX}/posts/*/documentos": 30 * 1024 * 1024,
    f"{PREFIX}/posts/*/checklist-extras/*/documento": 30 * 1024 * 1024,
}


def get_esteira_db() -> Any:
    """DI seam: the schema-pinned admin client (every query filters ``org_id`` itself)."""
    return get_admin_client()


def _org(auth) -> str:
    return str(coerce_org_uuid(auth[2]))


def _svc(auth, db) -> EsteiraService:
    return EsteiraService(db, _org(auth), str(auth[0].id))


def _raise(exc: EsteiraError):
    raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


# ── 1. stages (seed router) ─────────────────────────────────────────────────


def _stage_context(auth) -> PipelineContext:
    org_id = _org(auth)
    db = get_esteira_db()
    ensure_default_stages(db, PIPELINE_ESTEIRA, ESTEIRA_PADRAO, org_id=org_id)
    return PipelineContext(db=db, org_id=org_id, user_id=str(auth[0].id))


stages_router = pipeline_stages_router(
    PIPELINE_ESTEIRA,
    auth_dependency=get_current_user_org,
    resolve_context=_stage_context,
    success_response=success_response,
    prefix=f"{PREFIX}/etapas",
    tags=["Media Creation — Esteira (etapas)"],
)

# ── 2 / 4. card hub ─────────────────────────────────────────────────────────


def _hub_context(auth, db) -> CardHubContext:
    return CardHubContext(db=db, org_id=coerce_org_uuid(auth[2]), user_id=getattr(auth[0], "id", None))


hub_collection_router, hub_entity_router = card_hub_routers(
    CS_POST_HUB,
    auth_dependency=get_current_user_org,
    resolve_context=_hub_context,
    get_db=get_esteira_db,
    get_storage=get_storage_backend,
    prefix=f"{PREFIX}/posts",
    tags=["Media Creation — Esteira (card)"],
)

# ── 3. board + posts ────────────────────────────────────────────────────────

router = APIRouter(prefix=PREFIX, tags=["Media Creation — Esteira"])


@router.get("/board")
def obter_board(
    marca_id: Optional[str] = Query(None),
    busca: Optional[str] = Query(None, max_length=200),
    membro_id: Optional[str] = Query(None),
    incluir_arquivados: bool = Query(False),
    limite_por_etapa: int = Query(LIMITE_PADRAO, ge=1, le=500),
    auth=Depends(get_current_user_org),
    db=Depends(get_esteira_db),
):
    try:
        return success_response(
            _svc(auth, db).board(
                marca_id=marca_id,
                busca=busca,
                membro_id=membro_id,
                incluir_arquivados=incluir_arquivados,
                limite_por_etapa=limite_por_etapa,
            )
        )
    except EsteiraError as exc:
        _raise(exc)


@router.post("/posts", status_code=201)
def criar_post(body: PostCreate, auth=Depends(get_current_user_org), db=Depends(get_esteira_db)):
    try:
        return success_response(_svc(auth, db).criar(body))
    except EsteiraError as exc:
        _raise(exc)


@router.get("/posts/{post_id}")
def obter_post(post_id: str, auth=Depends(get_current_user_org), db=Depends(get_esteira_db)):
    try:
        return success_response(_svc(auth, db).detalhe(post_id))
    except EsteiraError as exc:
        _raise(exc)


@router.patch("/posts/{post_id}")
def atualizar_post(
    post_id: str,
    raw: dict = Body(...),
    auth=Depends(get_current_user_org),
    db=Depends(get_esteira_db),
):
    # Parsed by hand so the immutable columns answer the contract's `campo_nao_editavel`
    # (a plain extra="forbid" would answer a generic pydantic 422).
    proibidos = sorted(CAMPOS_NAO_EDITAVEIS & set(raw))
    if proibidos:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "campo_nao_editavel",
                "detail": "Estes campos não podem ser editados aqui: " + ", ".join(proibidos),
                "campos": proibidos,
            },
        )
    try:
        body = PostUpdate.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=json.loads(exc.json(include_url=False, include_context=False))) from exc
    patch = body.model_dump(exclude_unset=True, mode="json")
    try:
        return success_response(_svc(auth, db).atualizar(post_id, patch))
    except EsteiraError as exc:
        _raise(exc)


@router.delete("/posts/{post_id}", status_code=204)
def excluir_post(post_id: str, auth=Depends(get_current_user_org), db=Depends(get_esteira_db)):
    try:
        _svc(auth, db).excluir(post_id)
    except EsteiraError as exc:
        _raise(exc)


@router.post("/posts/{post_id}/mover-etapa")
def mover_etapa(
    post_id: str, body: MoverEtapaRequest, auth=Depends(get_current_user_org), db=Depends(get_esteira_db)
):
    try:
        return success_response(_svc(auth, db).mover(post_id, body))
    except EsteiraError as exc:
        _raise(exc)


@router.put("/posts/{post_id}/headline")
def vincular_headline(post_id: str, body: HeadlineBind, auth=Depends(get_current_user_org), db=Depends(get_esteira_db)):
    try:
        return success_response(_svc(auth, db).vincular_headline(post_id, body))
    except EsteiraError as exc:
        _raise(exc)


@router.delete("/posts/{post_id}/headline", status_code=204)
def desvincular_headline(post_id: str, auth=Depends(get_current_user_org), db=Depends(get_esteira_db)):
    try:
        _svc(auth, db).desvincular_headline(post_id)
    except EsteiraError as exc:
        _raise(exc)


@router.put("/posts/{post_id}/roteiro")
def vincular_roteiro(post_id: str, body: RoteiroBind, auth=Depends(get_current_user_org), db=Depends(get_esteira_db)):
    try:
        return success_response(_svc(auth, db).vincular_roteiro(post_id, str(body.roteiro_id)))
    except EsteiraError as exc:
        _raise(exc)


@router.delete("/posts/{post_id}/roteiro", status_code=204)
def desvincular_roteiro(post_id: str, auth=Depends(get_current_user_org), db=Depends(get_esteira_db)):
    try:
        _svc(auth, db).desvincular_roteiro(post_id)
    except EsteiraError as exc:
        _raise(exc)


#: Mount order matters (see the module docstring).
ROUTERS = [stages_router, hub_collection_router, router, hub_entity_router]
