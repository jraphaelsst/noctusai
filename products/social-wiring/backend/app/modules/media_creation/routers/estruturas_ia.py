"""Estruturas library -- AI draft from a video (estruturas-contract.md section 6.2, tier ``platform``; EST-5).

``POST /estruturas/a-partir-do-viral`` -> 201 ``{viral_id}``: a platform admin asks for a DRAFT Estrutura derived from a
library video. Same service as the automatic draft (:func:`estruturas_ia.criar_rascunho`); here ``origem='manual'``,
``ator_tipo='admin'``. 422 ``viral_sem_conteudo`` (no blueprint / transcript / caption), 409 ``viral_ja_tem_rascunho``
(a non-archived ``viral_auto`` already links it), 404 ``viral_nao_encontrado``. The call is rate-limited
(``DEFAULT_AI_RL``) and metered on the INGESTION org's LLM budget (never the caller's org). Returns the fresh
``EstruturaDetalhe`` with the admin fields. Included BEFORE the ``estruturas`` routers (static path under ``/estruturas``).

NOTE: no ``from __future__ import annotations`` -- slowapi's ``@limiter.limit`` wrapper makes FastAPI resolve string
annotations in slowapi's globals and would turn the body into a query parameter.
"""
import logging

from fastapi import Depends, Request

from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.rate_limit_policies import DEFAULT_AI_RL
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, require_platform_admin
from app.modules.media_creation.routers.estruturas import get_estruturas_storage, raise_http
from app.modules.media_creation.schemas.estruturas_ia import APartirDoViralBody
from app.modules.media_creation.services import estruturas_ia as ia
from app.modules.media_creation.services.estruturas_service import EstruturaError, EstruturasService, assinar_urls
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = make_router(
    tier="platform", guard=require_platform_admin, prefix="/api/media-creation/estruturas",
    tags=["Media Creation — Estruturas (admin)"],
)


def get_estruturas_ia_ports() -> ia.IaPorts:
    """DI seam of the derivation (production: the admin client, the registry-fed model call). Tests override it."""
    return ia.default_ports()


@router.post("/a-partir-do-viral", status_code=201)
@limiter.limit(DEFAULT_AI_RL)
async def a_partir_do_viral(
    request: Request,
    body: APartirDoViralBody,
    auth=Depends(require_platform_admin),
    ports: ia.IaPorts = Depends(get_estruturas_ia_ports),
    storage: StorageBackend = Depends(get_estruturas_storage),
):
    user_id = str(getattr(auth[0], "id", "") or "")
    try:
        criada = await ia.criar_rascunho(
            ports, str(body.viral_id), origem=ia.ORIGEM_MANUAL, ator_id=user_id or None, ator_tipo="admin",
        )
        detalhe = await run_blocking(
            EstruturasService(get_admin_client(), org_id=str(auth[2]), user_id=user_id, is_admin=True).detalhe, criada["id"],
        )
    except EstruturaError as exc:
        raise_http(exc)
    return success_response(await assinar_urls(detalhe, storage))
