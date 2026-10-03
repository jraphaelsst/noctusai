"""`/api/clientes/{cliente_id}/contratos/{contrato_id}/aditivos[...]` —
aditivos (migration 190).

`include_router`'d into `card_hub/router.py`'s `router` with one line (the
`contrato_gerador/router.py` layout), so every path inherits `/api/clientes`
and the card_hub `ModuleRegistration`. Every path's 4th segment is the
literal `aditivos` — distinct from `versoes`/`geracao`/`gerar`/… — so
nothing here shadows or is shadowed by the contract routes.

Auth is asserted strictly (`== 401`) in
`tests/modules/card_hub/test_auth_boundary_contrato_aditivo.py` (and by the
card_hub route-enumerating sweep). The docx adapter and the policy come in
through the contract generator's own DI seams (`contrato_gerador.deps`) —
tests override them via `app.dependency_overrides`, never a patch.

Contract: `products/social-wiring/projects/contrato-aditivos-CONTRACT.md`.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from noctusai_lib.api.auth.session import is_org_admin

from app.dependencies import get_core_client, get_current_user_org
from app.modules.card_hub import contratos_service as contratos_svc
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.contrato_aditivo import service, store
from app.modules.card_hub.contrato_aditivo.schemas import (
    AditivoCreateBody,
    AditivoPatchBody,
    GerarAditivoBody,
)
from app.modules.card_hub.contrato_gerador.deps import (
    get_contrato_docx_adapter,
    get_politica_contrato,
)
from app.modules.card_hub.deps import get_card_hub_client, get_storage_backend

router = APIRouter()

_BASE = "/{cliente_id}/contratos/{contrato_id}/aditivos"


@router.get(_BASE)
async def get_aditivos_route(
    cliente_id: UUID,
    contrato_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return store.listar(client, org_id, cliente_id, contrato_id)


@router.post(_BASE, status_code=201)
async def post_aditivo_route(
    cliente_id: UUID,
    contrato_id: UUID,
    body: AditivoCreateBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """409 `CONTRATO_ORIGINAL_NAO_ASSINADO` unless the original is
    `assinado` or carries an `assinatura_data` (and is not cancelado)."""
    user, org_id = auth_parts(auth)
    return store.criar(
        client,
        org_id,
        cliente_id,
        contrato_id,
        estilo=body.estilo,
        alteracoes=body.alteracoes,
        parcelas=[p.model_dump() for p in body.parcelas],
        assinatura_data=body.assinatura_data,
        modalidade_assinatura=body.modalidade_assinatura,
        usuario_id=getattr(user, "id", None),
    )


@router.patch(_BASE + "/{aditivo_id}")
async def patch_aditivo_route(
    cliente_id: UUID,
    contrato_id: UUID,
    aditivo_id: UUID,
    body: AditivoPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """409 `ADITIVO_CONGELADO` for a content change on an assinado/cancelado
    aditivo; 409 `CONTRATO_AGUARDANDO_REVISAO_JURIDICA` for a jump to
    enviado_assinatura/assinado while the current version awaits review."""
    user, org_id = auth_parts(auth)
    valores: dict = {}
    for campo in body.model_fields_set:
        if campo == "alteracoes":
            valores[campo] = body.alteracoes
        elif campo == "parcelas":
            valores[campo] = [p.model_dump() for p in body.parcelas] if body.parcelas is not None else None
        else:
            valores[campo] = getattr(body, campo)
    return store.atualizar(
        client,
        org_id,
        cliente_id,
        contrato_id,
        aditivo_id,
        valores=valores,
        usuario_id=getattr(user, "id", None),
    )


@router.get(_BASE + "/{aditivo_id}/geracao")
async def get_aditivo_geracao_route(
    cliente_id: UUID,
    contrato_id: UUID,
    aditivo_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    politica=Depends(get_politica_contrato),
) -> dict:
    user, org_id = auth_parts(auth)
    return service.obter_geracao(
        client,
        org_id,
        cliente_id,
        contrato_id,
        aditivo_id,
        usuario_id=getattr(user, "id", None),
        politica=politica,
    )


@router.post(_BASE + "/{aditivo_id}/gerar", status_code=201)
async def post_aditivo_gerar_route(
    cliente_id: UUID,
    contrato_id: UUID,
    aditivo_id: UUID,
    body: Optional[GerarAditivoBody] = None,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
    adapter=Depends(get_contrato_docx_adapter),
    politica=Depends(get_politica_contrato),
) -> dict:
    user, org_id = auth_parts(auth)
    return await service.gerar(
        client,
        storage,
        adapter,
        org_id,
        cliente_id,
        contrato_id,
        aditivo_id,
        assinatura=body.assinatura_data if body else None,
        usuario_id=getattr(user, "id", None),
        politica=politica,
    )


@router.get(_BASE + "/{aditivo_id}/versoes")
async def get_aditivo_versoes_route(
    cliente_id: UUID,
    contrato_id: UUID,
    aditivo_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    store.contexto_contrato(client, org_id, cliente_id, contrato_id)
    aditivo = store.saida(client, org_id, store.exigir_aditivo(client, org_id, contrato_id, aditivo_id))
    return {"versoes": aditivo["versoes"]}


@router.get(_BASE + "/{aditivo_id}/versoes/{versao_id}/url")
async def get_aditivo_versao_url_route(
    cliente_id: UUID,
    contrato_id: UUID,
    aditivo_id: UUID,
    versao_id: UUID,
    intent: str = Query("view"),
    formato: str = Query("pdf"),
    impressao: bool = Query(False),
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
) -> dict:
    """`impressao=true` is refused (409 `CONTRATO_AGUARDANDO_REVISAO_JURIDICA`)
    while the version awaits the legal review; a plain view is not."""
    user, org_id = auth_parts(auth)
    store.contexto_contrato(client, org_id, cliente_id, contrato_id)
    store.exigir_aditivo(client, org_id, contrato_id, aditivo_id)
    if impressao:
        contratos_svc.exigir_revisao_juridica(
            store.VERSOES_STORE.exigir(client, org_id, aditivo_id, versao_id)
        )
    return await contratos_svc.url_artefato_versao(
        store.VERSOES_STORE,
        client,
        storage,
        org_id,
        aditivo_id,
        versao_id,
        usuario_id=getattr(user, "id", None),
        intent=intent,
        formato=formato,
    )


@router.post(_BASE + "/{aditivo_id}/versoes/{versao_id}/revisao-juridica")
async def post_aditivo_revisao_juridica_route(
    cliente_id: UUID,
    contrato_id: UUID,
    aditivo_id: UUID,
    versao_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """"Aprovar revisão jurídica" of an aditivo version — ADMIN/OWNER ONLY,
    on the TRUSTED `noctus_users.org_role` row (`is_org_admin`), the same
    bar as the contract's review. Returns the aditivo."""
    user, org_id = auth_parts(auth)
    usuario_id = getattr(user, "id", None)
    if not is_org_admin(get_core_client(), usuario_id):
        raise HTTPException(
            status_code=403,
            detail="Aprovar a revisão jurídica do aditivo é restrito a administradores.",
        )
    store.contexto_contrato(client, org_id, cliente_id, contrato_id)
    store.exigir_aditivo(client, org_id, contrato_id, aditivo_id)
    store.aprovar_revisao(client, org_id, aditivo_id, versao_id, usuario_id=usuario_id)
    return store.saida(client, org_id, store.exigir_aditivo(client, org_id, contrato_id, aditivo_id))


__all__ = ["router"]
