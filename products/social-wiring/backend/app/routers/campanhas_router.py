"""Campanhas router — /api/campanhas.

Endpoints:
    POST /api/campanhas/solicitacoes            → request a campaign for an imóvel
    GET  /api/campanhas/solicitacoes            → the queue
    GET  /api/campanhas/solicitacoes/{codigo}   → pending request for one imóvel

Auth: ``Depends(get_current_user_org)`` on every route, no exceptions.
Reads go through the admin client with an explicit `org_id` filter —
defense in depth on top of RLS, same shape as `imoveis_router`.

Scope is the "solicitar campanha" signal only (user: "keep it simple for
later refinement"). Campaign CRUD proper is deliberately not here yet.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
)
from app.services.campanhas_service import (
    CampanhaError,
    ImovelDesconhecido,
    SolicitacaoDuplicada,
    build_campanhas_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/campanhas", tags=["campanhas"])


class SolicitacaoIn(BaseModel):
    codigo: str = Field(..., min_length=1, description="Código do imóvel, ex. ONE10640.")
    justificativa: Optional[str] = Field(
        None, max_length=2000,
        description="Por que este imóvel merece tráfego pago.",
    )


class SolicitacaoOut(BaseModel):
    id: Optional[str] = None
    imovel_ref_id: Optional[str] = None
    status: str = "pendente"
    justificativa: Optional[str] = None
    solicitado_em: Optional[str] = None


@router.post(
    "/solicitacoes",
    response_model=SolicitacaoOut,
    status_code=status.HTTP_201_CREATED,
)
async def criar_solicitacao(
    payload: SolicitacaoIn,
    auth=Depends(get_current_user_org),
    db=Depends(get_admin_client),
) -> SolicitacaoOut:
    """Signal that an imóvel deserves paid traffic."""
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    svc = build_campanhas_service(db)
    try:
        created = svc.solicitar(
            org_id,
            payload.codigo,
            justificativa=payload.justificativa,
            solicitado_por=getattr(user, "id", None),
        )
    except ImovelDesconhecido as exc:
        # 404, not 400: the request is well-formed, the imóvel is the thing
        # that does not exist.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Imóvel não encontrado no catálogo: {exc}",
        ) from exc
    except SolicitacaoDuplicada as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe uma solicitação pendente para {exc}.",
        ) from exc
    except CampanhaError as exc:
        logger.error("solicitação failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível registrar a solicitação.",
        ) from exc

    return SolicitacaoOut(**{
        k: v for k, v in created.items() if k in SolicitacaoOut.model_fields
    })


@router.get("/solicitacoes")
async def listar_solicitacoes(
    situacao: Optional[str] = Query(
        None, description="pendente | aprovada | recusada | convertida",
    ),
    auth=Depends(get_current_user_org),
    db=Depends(get_admin_client),
) -> list[dict]:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return build_campanhas_service(db).listar_solicitacoes(org_id, status=situacao)


# Declared LAST: `/{codigo}` would otherwise shadow the collection route
# above, since FastAPI matches in declaration order and a bare path segment
# is a valid código. Same ordering rule `imoveis_router` documents.
@router.get("/solicitacoes/{codigo}")
async def solicitacao_do_imovel(
    codigo: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_admin_client),
) -> dict:
    """The pending request for one imóvel, or `{}`.

    `{}` rather than 404: "no pending request" is the NORMAL state of every
    imóvel, and a 404 would make the button's own state-check look like an
    error in the logs.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    found = build_campanhas_service(db).solicitacao_do_imovel(org_id, codigo)
    return found or {}
