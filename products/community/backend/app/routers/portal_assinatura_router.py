"""Member portal — subscription cancel. projects/ninho-vazio/CONTRACT.md
§Member portal, `POST /api/portal/assinatura/cancelar` (slice BE-B).

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

from fastapi import APIRouter, Depends

from app.dependencies import actor_uuid, get_admin_client, get_membro_context, http_error
from app.schemas.cobranca import AssinaturaPortal, CancelarAssinaturaPortalRequest
from app.services.assinaturas_service import (
    AssinaturasService,
    AssinaturasServiceError,
    CancelamentoGatewayFalhou,
)
from app.services.ciclo_assinatura import gateway_estrito

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portal/assinatura", tags=["portal"])

SEM_ASSINATURA = "Você não tem assinatura ativa."
FALHA_GATEWAY = "Não foi possível cancelar no gateway. Tente novamente."


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
