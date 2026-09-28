"""Member portal — subscription change + cancel. projects/ninho-vazio/
CONTRACT.md §Member portal: `POST /api/portal/assinatura` (troca de plano)
and `POST /api/portal/assinatura/cancelar` (slice BE-B).

Auth is `get_membro_context` (403 for staff / non-members). A member has
SELECT-only RLS on their own `assinaturas` and no write on
`membro_eventos`, so after resolving THEIR subscription (the service is
scoped by `org_id` + `membro_id` from the context row, never from the
request) the write runs on the service-role client.

The gateway call uses the STRICT factory: a missing Asaas key is a 502,
never a Fake "cancelled" that leaves the member being charged.
"""
from __future__ import annotations

import functools
import logging

from fastapi import APIRouter, Depends, status

from app.dependencies import actor_uuid, get_admin_client, get_membro_context, http_error
from app.schemas.checkout import CheckoutOut
from app.schemas.cobranca import (
    AssinaturaPortal,
    CancelarAssinaturaPortalRequest,
    TrocaPlanoPortalRequest,
)
from app.services.assinaturas_service import (
    AssinaturasService,
    AssinaturasServiceError,
    CancelamentoGatewayFalhou,
)
from app.services.checkout_service import CheckoutService, CheckoutServiceError
from app.services.ciclo_assinatura import gateway_estrito

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portal/assinatura", tags=["portal"])

SEM_ASSINATURA = "Você não tem assinatura ativa."
FALHA_GATEWAY = "Não foi possível cancelar no gateway. Tente novamente."


@router.post("", response_model=CheckoutOut, status_code=status.HTTP_201_CREATED)
async def trocar_meu_plano(
    payload: TrocaPlanoPortalRequest,
    ctx: tuple = Depends(get_membro_context),
) -> CheckoutOut:
    """Troca de plano (CONTRACT.md §Member portal): open a paid
    subscription for the CALLER's own membro row — same gateway path and
    response shape as `POST /api/checkout`, without its anonymous-caller
    rules (A2), which exist because that route cannot know who is asking."""
    user, _token, org_id, membro = ctx
    service = CheckoutService(get_admin_client(), org_id=org_id)
    try:
        result = await service.trocar_plano(
            membro=membro, plano_id=payload.plano_id, metodo=payload.metodo,
            cpf_cnpj=payload.cpf_cnpj, autor_id=actor_uuid(user),
        )
    except CheckoutServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return CheckoutOut(**result)


@router.post("/cancelar", response_model=AssinaturaPortal)
async def cancelar_minha_assinatura(
    payload: CancelarAssinaturaPortalRequest,
    ctx: tuple = Depends(get_membro_context),
) -> AssinaturaPortal:
    user, _token, org_id, membro = ctx
    service = AssinaturasService(
        get_admin_client(), org_id=org_id,
        gateway_factory=functools.partial(gateway_estrito, org_id=str(org_id)),
    )
    atual = service.assinatura_em_cobranca(membro_id=membro["id"])
    if atual is None:
        raise http_error(404, SEM_ASSINATURA)
    try:
        row = await service.cancelar(
            assinatura_id=atual["id"], motivo=payload.motivo,
            solicitado_por="membro", autor_id=actor_uuid(user),
        )
    except CancelamentoGatewayFalhou as exc:
        raise http_error(502, FALHA_GATEWAY) from exc
    except AssinaturasServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return AssinaturaPortal.from_row(row)
