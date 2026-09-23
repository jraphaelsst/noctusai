"""`/api/clientes/{cliente_id}/contratos/{contrato_id}/{geracao,gerar,
proveniencia}` and `POST /api/clientes/{cliente_id}/contratos/gerar`
(start one) — F5.

A separate file, `include_router`'d into `card_hub/router.py`'s `router` with
one line (same layout `negociacao_estruturada_router.py` uses), so every path
inherits `/api/clientes` and registers once in card_hub's existing
`ModuleRegistration`. Both paths are 4 segments ending in a literal distinct
from `versoes`, so they cannot shadow or be shadowed by the contratos routes.
The 3-segment start route ends in the literal `gerar`; the only other
3-segment POST is `/{cliente_id}/contratos` itself, and `{contrato_id}` 3rd
segments are PATCH/DELETE only (and UUID-typed) — no overlap.

Auth is asserted strictly (`== 401`) in
`tests/modules/card_hub/test_auth_boundary_contrato_gerador.py`.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from app.dependencies import get_current_user_org
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.contrato_gerador import service, validacao_extracao
from app.modules.card_hub.contrato_gerador.carregador import carregar
from app.modules.card_hub.contrato_gerador.deps import (
    get_contrato_docx_adapter,
    get_politica_contrato,
)
from app.modules.card_hub.deps import get_card_hub_client, get_storage_backend
from app.modules.card_hub.proveniencia import linhagem

router = APIRouter()


class DecisaoValidacao(StrictHttpModel):
    chave: str = Field(min_length=1)
    decisao: validacao_extracao.Decisao


class DecisoesValidacaoBody(StrictHttpModel):
    decisoes: list[DecisaoValidacao] = Field(min_length=1)


class GerarContratoBody(StrictHttpModel):
    #: Dates the instrument. Absent falls back to the date stored on the
    #: contract (migration 114), then to today in São Paulo — see
    #: `service.data_assinatura`.
    assinatura_data: Optional[date] = None


@router.post("/{cliente_id}/contratos/gerar", status_code=201)
async def post_contrato_iniciar_route(
    cliente_id: UUID,
    response: Response,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
    politica=Depends(get_politica_contrato),
) -> dict:
    """The card's "Gerar contrato" button: creates the contract to generate
    (or CONTINUES a leftover one that never got a version) and returns
    `{contrato, geracao}` — see `service.iniciar`.

    201 for a brand-new draft (the decorator's default); 200 when an
    already-existing, still-unrendered draft was reused instead — same body
    shape either way, so the FE (`useContratos.ts`'s `iniciar` mutation,
    a plain `api.post` that only checks `response.ok`) needs no change."""
    user, org_id = auth_parts(auth)
    resultado = service.iniciar(
        client,
        org_id,
        cliente_id,
        usuario_id=getattr(user, "id", None),
        politica=politica,
    )
    if resultado.pop("_reaproveitado"):
        response.status_code = status.HTTP_200_OK
    return resultado


@router.get("/{cliente_id}/contratos/{contrato_id}/geracao")
async def get_contrato_geracao_route(
    cliente_id: UUID,
    contrato_id: UUID,
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
        usuario_id=getattr(user, "id", None),
        politica=politica,
    )


@router.get("/{cliente_id}/contratos/{contrato_id}/validacao-extracao")
async def get_validacao_extracao_route(
    cliente_id: UUID,
    contrato_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """Owner decision D2: every contract-feeding value a machine extracted
    and no human validated yet — for THIS contract's partes, imóvel,
    permuta imóveis and certidões — plus the open extraction `conflitos` on
    that data (read-only; decided on the conflict screens). Both empty =
    `gerar` may proceed. See `validacao_extracao`."""
    user, org_id = auth_parts(auth)
    usuario_id = getattr(user, "id", None)
    dados, _ = carregar(client, org_id, cliente_id, contrato_id, usuario_id=usuario_id)
    return validacao_extracao.situacao(client, org_id, dados, usuario_id=usuario_id)


@router.get("/{cliente_id}/contratos/{contrato_id}/proveniencia")
async def get_contrato_proveniencia_route(
    cliente_id: UUID,
    contrato_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """The card's "Proveniência" tab: every contract-feeding value's state
    (empty / machine-pending / confirmed / manual / conflicted), its source
    document, and — for the ones not yet filled — which document type(s)
    could still supply it (`fontes.FONTES`). Read-only; see
    `proveniencia.linhagem.linhagem_do_card`."""
    _user, org_id = auth_parts(auth)
    return linhagem.linhagem_do_card(client, org_id, cliente_id, contrato_id)


@router.post("/{cliente_id}/contratos/{contrato_id}/validacao-extracao/decisoes")
async def post_validacao_extracao_decisoes_route(
    cliente_id: UUID,
    contrato_id: UUID,
    body: DecisoesValidacaoBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    """Accept (stamp `confirmado_por/_em`) or reject (value + provenance →
    NULL) each named pending value; one `extracao_validacoes` ledger row per
    decision (migration 156). 409 `EXTRACAO_VALIDACAO_DESATUALIZADA` — and
    nothing written — when any `chave` is not currently pending. Returns
    `{aplicadas, pendentes, conflitos}` (what still blocks generation)."""
    user, org_id = auth_parts(auth)
    usuario_id = getattr(user, "id", None)
    dados, _ = carregar(client, org_id, cliente_id, contrato_id, usuario_id=usuario_id)
    return validacao_extracao.decidir(
        client,
        org_id,
        dados,
        contrato_id,
        [(d.chave, d.decisao) for d in body.decisoes],
        usuario_id=usuario_id,
    )


@router.post("/{cliente_id}/contratos/{contrato_id}/gerar", status_code=201)
async def post_contrato_gerar_route(
    cliente_id: UUID,
    contrato_id: UUID,
    body: Optional[GerarContratoBody] = None,
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
        assinatura=body.assinatura_data if body else None,
        usuario_id=getattr(user, "id", None),
        politica=politica,
    )


__all__ = ["DecisaoValidacao", "DecisoesValidacaoBody", "GerarContratoBody", "router"]
