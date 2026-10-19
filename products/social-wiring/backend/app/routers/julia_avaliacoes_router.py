"""Lais > Avaliacoes no Google (wave 13, contract 15).

  GET /api/lais/avaliacoes?mes=YYYY-MM    org member -> {data: {mes, pedidos_enviados, novas_avaliacoes,
                                          distribuicao: {"1".."5"}, media, total, ultimas: [{autor, data, nota,
                                          texto, link}], configurado: {review_url, gbp}}}
  GET /api/lais/avaliacoes/config         org member -> {data: {google_review_url, gbp_location_id, capi_ativo, capi_pixel_id}}
  PUT /api/lais/avaliacoes/config         org admin  (partial: only the sent keys change; null clears)

`mes` defaults to the current month (America/Sao_Paulo); malformed -> 422 `mes_invalido`. The GET refreshes the
Google Business Profile cache first (best effort, at most every 15 min; `configurado.gbp` is false until the owner
connects the Business Profile). A7: `pedidos_enviados` counts only the asks to contatos the caller owns; admins the
whole org. 422 `config_invalida` for a non-https link / non-numeric pixel.
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
import logging
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.services import lais_acesso, lais_avaliacoes_service as svc, lais_painel_service
from app.services.lais_reviews_provider import NaoConfiguradoReviews, ReviewsProvider, make_reviews_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lais/avaliacoes", tags=["lais-avaliacoes"])

svc.registrar()  # binds the review-ask hook on every episode close


def get_avaliacoes_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


def get_reviews_provider_factory() -> Callable[[str], ReviewsProvider]:
    """DI seam: `org_id -> ReviewsProvider`. NOC-REMEDIATE[lais-gbp-real] lives in `make_reviews_provider`."""
    return lambda org_id: make_reviews_provider(org_id)


class ConfigIn(StrictHttpModel):
    google_review_url: Optional[str] = Field(default=None, max_length=500)
    gbp_location_id: Optional[str] = Field(default=None, max_length=200)
    capi_ativo: Optional[bool] = None
    capi_pixel_id: Optional[str] = Field(default=None, max_length=20)


@router.get("")
async def avaliacoes(
    mes: Optional[str] = None,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_avaliacoes_client),
    provider_factory: Callable[[str], ReviewsProvider] = Depends(get_reviews_provider_factory),
) -> dict[str, Any]:
    mes = lais_painel_service.validar_mes(mes)
    org = coerce_org_uuid(auth[2])
    provider = provider_factory(str(org))
    sync = await svc.sincronizar(client, org, provider)
    ctx = lais_acesso.contexto(auth, request)
    dados = svc.painel(client, ctx, mes=mes, gbp_configurado=not isinstance(provider, NaoConfiguradoReviews) and sync["estado"] != "nao_configurado")
    return {"data": dados}


@router.get("/config")
def get_config(auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_avaliacoes_client)) -> dict[str, Any]:
    return {"data": svc.obter_config(client, coerce_org_uuid(auth[2]))}


@router.put("/config")
def put_config(
    corpo: ConfigIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_avaliacoes_client),
) -> dict[str, Any]:
    require_org_admin_for(get_core_client(), auth, request, "A configuração de avaliações")
    valores = {k: getattr(corpo, k) for k in corpo.model_fields_set}
    return {"data": svc.salvar_config(client, coerce_org_uuid(auth[2]), valores)}
