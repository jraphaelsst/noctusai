"""The imóvel's published YouTube video -- manual set / edit / clear (`imovel_video_youtube_service`, migration 371).

  GET    /api/imoveis/{codigo}/video-youtube   org member  {data: ImovelVideoYoutube | null}
  PUT    /api/imoveis/{codigo}/video-youtube   org member  {youtube: <URL or 11-char id>, motivo?} -> {data: ImovelVideoYoutube}
  DELETE /api/imoveis/{codigo}/video-youtube   org member  ?motivo= -> {data: the removed ImovelVideoYoutube | null}

ImovelVideoYoutube = {codigo, youtube_video_id, youtube_url, origem: julia|manual|vista, upload_job_id, definido_por, criado_em,
atualizado_em}. A PUT is `origem = manual` with REPLACE semantics (the previous video stays in the imóvel history); when the org's
Vista-edit switch is on, Vista's `VideoDestaque` is set too, with the motivo written into ObsVenda. Strict 401 without a session,
404 unknown código (PUT/DELETE), 422 an invalid link / a Short. Access tier: org (any member of the imóvel's org).
"""
# No `from __future__ import annotations`: FastAPI body models are resolved from the signature.
from typing import Any, Optional

from fastapi import Depends, Query
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.modules.imovel_hub.deps import get_imovel_hub_client
from app.services import imovel_video_youtube_service as svc_mod

router = make_router(tier="org", guard=get_current_user_org, prefix="/api/imoveis", tags=["imoveis-video-youtube"])

MOTIVO_PADRAO_DEFINIR = "vídeo do YouTube do imóvel definido manualmente no NoctusAI"
MOTIVO_PADRAO_REMOVER = "vídeo do YouTube do imóvel removido manualmente no NoctusAI"


def get_imovel_video_youtube_service(client: Any = Depends(get_imovel_hub_client)) -> svc_mod.ImovelVideoYoutubeService:
    """DI seam: the service over the scoped client (tests override with one built on Fakes)."""
    return svc_mod.build_imovel_video_youtube_service(client)


class VideoYoutubeIn(StrictHttpModel):
    youtube: str = Field(min_length=1, max_length=500)
    motivo: Optional[str] = Field(default=None, max_length=300)


def _uid(auth: tuple) -> Optional[str]:
    user = auth[0]
    uid = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    return str(uid) if uid else None


def _invalido(exc: svc_mod.VideoYoutubeInvalido) -> AppException:
    return AppException("video_youtube_invalido", str(exc), status_code=422)


@router.get("/{codigo}/video-youtube")
def obter(codigo: str, auth: tuple = Depends(get_current_user_org),
          svc: svc_mod.ImovelVideoYoutubeService = Depends(get_imovel_video_youtube_service)) -> dict[str, Any]:
    video = svc.obter(coerce_org_uuid(auth[2]), codigo)
    return {"data": video.para_api() if video else None}


@router.put("/{codigo}/video-youtube")
def definir(codigo: str, corpo: VideoYoutubeIn, auth: tuple = Depends(get_current_user_org),
            svc: svc_mod.ImovelVideoYoutubeService = Depends(get_imovel_video_youtube_service)) -> dict[str, Any]:
    try:
        video = svc.definir(coerce_org_uuid(auth[2]), codigo, youtube_video_id=corpo.youtube, origem="manual",
                            motivo=(corpo.motivo or "").strip() or MOTIVO_PADRAO_DEFINIR, definido_por=_uid(auth))
    except svc_mod.VideoYoutubeInvalido as exc:
        raise _invalido(exc) from exc
    return {"data": video.para_api()}


@router.delete("/{codigo}/video-youtube")
def remover(codigo: str, motivo: Optional[str] = Query(None, max_length=300), auth: tuple = Depends(get_current_user_org),
            svc: svc_mod.ImovelVideoYoutubeService = Depends(get_imovel_video_youtube_service)) -> dict[str, Any]:
    try:
        video = svc.remover(coerce_org_uuid(auth[2]), codigo, motivo=(motivo or "").strip() or MOTIVO_PADRAO_REMOVER, definido_por=_uid(auth))
    except svc_mod.VideoYoutubeInvalido as exc:
        raise _invalido(exc) from exc
    return {"data": video.para_api() if video else None}


__all__ = ["router", "get_imovel_video_youtube_service"]
