"""`/api/clientes/{cliente_id}/contratos/{contrato_id}/testemunhas` — which
of the org's registered witnesses (migration 168's `org_testemunhas`
registry) sign this contract, and in what order.

A separate file, `include_router`'d into `card_hub/router.py`'s `router`
with one line — same layout `assinatura_router.py` uses. The 4-segment path
ends in the literal `testemunhas`, distinct from every sibling route at this
depth (`geracao`, `gerar`, `assinatura`, `assinatura-fisica`,
`proveniencia`), so no route-ordering hazard with this module's other
routers.

Auth is asserted strictly (`== 401`) in
`tests/modules/card_hub/test_auth_boundary_contrato_testemunhas.py`.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from app.modules.card_hub import contrato_testemunhas_service as service
from app.modules.card_hub import services as svc
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.deps import get_card_hub_client
from app.dependencies import get_current_user_org

router = APIRouter()


class DefinirTestemunhasBody(StrictHttpModel):
    #: Ordered — print/selection order. `[]` clears the selection.
    testemunha_ids: list[UUID] = Field(default_factory=list)


@router.get("/{cliente_id}/contratos/{contrato_id}/testemunhas")
async def get_contrato_testemunhas_route(
    cliente_id: UUID,
    contrato_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """The contract's currently-selected witnesses, in print order."""
    _user, org_id = auth_parts(auth)
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    return service.listar(client, org_id, atendimento_id, contrato_id)


@router.put("/{cliente_id}/contratos/{contrato_id}/testemunhas")
async def put_contrato_testemunhas_route(
    cliente_id: UUID,
    contrato_id: UUID,
    body: DefinirTestemunhasBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """Replace the contract's witness selection wholesale — see
    `contrato_testemunhas_service.definir`."""
    user, org_id = auth_parts(auth)
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    return service.definir(
        client,
        org_id,
        atendimento_id,
        contrato_id,
        testemunha_ids=body.testemunha_ids,
        usuario_id=getattr(user, "id", None),
    )
