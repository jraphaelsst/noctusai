"""Julia "Vídeos Prontos" -- the submissions of the editor's WhatsApp group (project julia-videos-prontos-youtube, S2).

  GET  /api/julia/videos-prontos              org member   newest first (`?limite=`, 1..200, default 50)
  POST /api/julia/videos-prontos/{id}/retry   org member   retry the FAILED videos of a `parcial` / `falhou`
                                                           submission now (404 nao_encontrada, 409 nao_retentavel)

Envelope `{"data": ...}` (errors: `AppException` -> `{"error": {...}}`). The org is the session's selected org (auth
tuple), never a parameter; a submission of another org is a 404.
"""
# No `from __future__ import annotations`: FastAPI resolves the parameters from the real annotations.
from typing import Any
from uuid import UUID

from fastapi import Depends, Query

from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.services import julia_videos_prontos_service as svc

router = make_router(tier="org", guard=get_current_user_org, prefix="/api/julia/videos-prontos",
                     tags=["julia-videos-prontos"])


def get_videos_prontos_service() -> svc.JuliaVideosProntosService:
    """DI seam: the production service (tests override)."""
    return svc.build_service()


@router.get("")
def listar(
    limite: int = Query(50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
    service: svc.JuliaVideosProntosService = Depends(get_videos_prontos_service),
) -> dict[str, Any]:
    return {"data": service.listar(coerce_org_uuid(auth[2]), limite)}


@router.post("/{submissao_id}/retry", status_code=202)
async def retry(
    submissao_id: UUID,
    auth: tuple = Depends(get_current_user_org),
    service: svc.JuliaVideosProntosService = Depends(get_videos_prontos_service),
) -> dict[str, Any]:
    try:
        out = await service.solicitar_retry(coerce_org_uuid(auth[2]), submissao_id, ator_id=str(auth[0].id))
    except svc.SubmissaoNaoEncontrada as exc:
        raise AppException("nao_encontrada", "Submissão não encontrada.", status_code=404) from exc
    except svc.RetryRecusado as exc:
        raise AppException("nao_retentavel", "Só dá para tentar de novo uma submissão que falhou (total ou em parte).",
                           status_code=409) from exc
    return {"data": out}
