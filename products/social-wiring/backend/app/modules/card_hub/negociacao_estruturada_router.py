"""`/api/clientes/{cliente_id}/negociacao/{parcelas,favorecidos,intermediarios}`
— migration 108's structured deal-terms surface.

A SEPARATE FILE, INCLUDED INTO `router.py`'s `router` WITH ONE LINE
---------------------------------------------------------------------
`card_hub/router.py` is one 1300+-line file with every other card_hub route
already in it. This module's `router` carries no prefix of its own —
`router.py` mounts it via `router.include_router(negociacao_estruturada_router)`
so every path here inherits `/api/clientes` and is registered exactly once,
in `app.modules.card_hub.register()`'s existing `ModuleRegistration`, with NO
change to `app/main.py`. Every path below continues the existing
`/{cliente_id}/negociacao` shape (already mounted by `router.py`'s own
`get_negociacao_route`/`patch_negociacao_route`), so none of them are a
literal 1-segment path and none of them can hit the `/tags`-vs-`/{cliente_id}`
route-ordering hazard `router.py`'s module docstring documents.

Auth is not re-tested here — `test_auth_boundary_negociacao_estruturada.py`
enumerates every route this module mounts and asserts a strict 401 on each
(the existing generic `test_auth_boundary.py` also covers them, once its id
placeholder map knows the new path params — see that file's diff).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.modules.card_hub import negociacao_estruturada_service as svc
from app.modules.card_hub.deps import get_card_hub_client
from app.modules.card_hub.schemas import (
    FavorecidoCreateBody,
    FavorecidoPatchBody,
    IntermediarioCreateBody,
    IntermediarioPatchBody,
    ParcelaCreateBody,
    ParcelaPatchBody,
    ParcelasDividirBody,
)

router = APIRouter()


def _auth_parts(auth):
    """Same two-liner `router.py::_auth_parts` — duplicated rather than
    imported to avoid a circular import (`router.py` imports THIS module to
    `include_router` it). Noted as a scoped-improvement: a shared
    `card_hub/auth.py` helper would remove the duplication for both call
    sites; not done here to keep this migration's footprint additive-only."""
    user, _token, raw_org = auth
    return user, coerce_org_uuid(raw_org)


# ─── the aggregate view ───────────────────────────────────────────────────


@router.get("/{cliente_id}/negociacao/estruturada")
async def get_negociacao_estruturada_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return svc.obter_estruturada(client, org_id, cliente_id)


# ─── parcelas ─────────────────────────────────────────────────────────────


@router.post("/{cliente_id}/negociacao/parcelas", status_code=201)
async def create_parcela_route(
    cliente_id: UUID,
    body: ParcelaCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    return svc.criar_parcela(
        client, org_id, cliente_id,
        valores=body.model_dump(), usuario_id=getattr(user, "id", None),
    )


@router.patch("/{cliente_id}/negociacao/parcelas/{parcela_id}")
async def patch_parcela_route(
    cliente_id: UUID,
    parcela_id: UUID,
    body: ParcelaPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    valores = {k: getattr(body, k) for k in body.model_fields_set}
    return svc.atualizar_parcela(
        client, org_id, cliente_id, parcela_id,
        valores=valores, usuario_id=getattr(user, "id", None),
    )


@router.delete("/{cliente_id}/negociacao/parcelas/{parcela_id}", status_code=204)
async def delete_parcela_route(
    cliente_id: UUID,
    parcela_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
):
    _user, org_id = _auth_parts(auth)
    svc.remover_parcela(client, org_id, cliente_id, parcela_id)


@router.post("/{cliente_id}/negociacao/parcelas/dividir-saldo", status_code=201)
async def dividir_saldo_route(
    cliente_id: UUID,
    body: ParcelasDividirBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    return svc.dividir_saldo_em_parcelas(
        client, org_id, cliente_id,
        num_parcelas=body.num_parcelas,
        tipo=body.tipo,
        forma_pagamento=body.forma_pagamento,
        favorecido_id=body.favorecido_id,
        vencimento_inicial=body.vencimento_inicial,
        usuario_id=getattr(user, "id", None),
    )


# ─── favorecidos ──────────────────────────────────────────────────────────


@router.post("/{cliente_id}/negociacao/favorecidos", status_code=201)
async def create_favorecido_route(
    cliente_id: UUID,
    body: FavorecidoCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    return svc.criar_favorecido(
        client, org_id, cliente_id,
        valores=body.model_dump(), usuario_id=getattr(user, "id", None),
    )


@router.patch("/{cliente_id}/negociacao/favorecidos/{favorecido_id}")
async def patch_favorecido_route(
    cliente_id: UUID,
    favorecido_id: UUID,
    body: FavorecidoPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    valores = {k: getattr(body, k) for k in body.model_fields_set}
    return svc.atualizar_favorecido(
        client, org_id, cliente_id, favorecido_id,
        valores=valores, usuario_id=getattr(user, "id", None),
    )


@router.delete("/{cliente_id}/negociacao/favorecidos/{favorecido_id}", status_code=204)
async def delete_favorecido_route(
    cliente_id: UUID,
    favorecido_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
):
    _user, org_id = _auth_parts(auth)
    svc.remover_favorecido(client, org_id, cliente_id, favorecido_id)


# ─── intermediários ───────────────────────────────────────────────────────


@router.post("/{cliente_id}/negociacao/intermediarios", status_code=201)
async def create_intermediario_route(
    cliente_id: UUID,
    body: IntermediarioCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    return svc.criar_intermediario(
        client, org_id, cliente_id,
        valores=body.model_dump(), usuario_id=getattr(user, "id", None),
    )


@router.patch("/{cliente_id}/negociacao/intermediarios/{intermediario_id}")
async def patch_intermediario_route(
    cliente_id: UUID,
    intermediario_id: UUID,
    body: IntermediarioPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    valores = {k: getattr(body, k) for k in body.model_fields_set}
    return svc.atualizar_intermediario(
        client, org_id, cliente_id, intermediario_id,
        valores=valores, usuario_id=getattr(user, "id", None),
    )


@router.delete(
    "/{cliente_id}/negociacao/intermediarios/{intermediario_id}", status_code=204
)
async def delete_intermediario_route(
    cliente_id: UUID,
    intermediario_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
):
    _user, org_id = _auth_parts(auth)
    svc.remover_intermediario(client, org_id, cliente_id, intermediario_id)


__all__ = ["router"]
