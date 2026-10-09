"""`/api/clientes/{cliente_id}/contratos/{contrato_id}/imobiliaria` — which
registered company (migration 215's `org_imobiliarias`) signs this contract.

Sibling of `contrato_testemunhas_router.py`, `include_router`'d into
`card_hub/router.py`. The 4-segment path ends in the literal `imobiliaria`,
distinct from every sibling at this depth. Auth is asserted strictly
(`== 401`) in `tests/modules/card_hub/test_auth_boundary_contrato_imobiliaria.py`.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends

from noctusai_lib.api import StrictHttpModel

from app.dependencies import get_current_user_org
from app.modules.card_hub import contrato_imobiliaria_service as service
from app.modules.card_hub import services as svc
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.deps import get_card_hub_client

router = APIRouter()


class DefinirImobiliariaBody(StrictHttpModel):
    #: `null` clears the stored choice (resolution then falls back to the
    #: "only active company" rule).
    imobiliaria_id: Optional[UUID] = None


@router.get("/{cliente_id}/contratos/{contrato_id}/imobiliaria")
async def get_contrato_imobiliaria_route(
    cliente_id: UUID,
    contrato_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    return service.obter(client, org_id, atendimento_id, contrato_id)


@router.put("/{cliente_id}/contratos/{contrato_id}/imobiliaria")
async def put_contrato_imobiliaria_route(
    cliente_id: UUID,
    contrato_id: UUID,
    body: DefinirImobiliariaBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    return service.definir(
        client, org_id, atendimento_id, contrato_id, imobiliaria_id=body.imobiliaria_id
    )
