"""HTTP surface for the condomínio master list.

Auth: `Depends(get_current_user_org)` (-> 401 without a token). Every write
that changes what an imóvel RESOLVES to, or the validation state, is admin-only
on the TRUSTED `public.noctus_users` row (`require_org_admin_for`) -- the same
gate imovel_hub uses for "Vincular imóveis". Editing descriptive attributes is
open to any org member.

ROUTE ORDER: literal `/sugerir` precedes `/{condominio_id}`.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from noctusai_lib.api.auth.session import require_org_admin_for

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org
from app.modules.condominios import service as svc
from app.modules.condominios.schemas import AliasBody, CondominioPatchBody, FundirBody, RenomearBody
from app.modules.imovel_hub.deps import get_imovel_hub_client

router = APIRouter(prefix="/api/condominios", tags=["condominios"])


def _parts(auth):
    user, _token, raw_org = auth
    return getattr(user, "id", None), coerce_org_uuid(raw_org)


def _admin(auth, request: Request, acao: str) -> None:
    require_org_admin_for(get_core_client(), auth, request, acao)


@router.get("")
def listar_route(
    status: Optional[str] = Query(default=None, pattern="^(sugerido|validado|descartado)$"),
    cidade: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    _, org_id = _parts(auth)
    return svc.listar(client, org_id, status=status, cidade=cidade, q=q)


@router.post("/sugerir")
def sugerir_route(
    request: Request,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    _admin(auth, request, "Gerar sugestões de condomínios")
    user_id, org_id = _parts(auth)
    return svc.sugerir(client, org_id, user_id)


@router.get("/{condominio_id}")
def obter_route(condominio_id: UUID, auth=Depends(get_current_user_org),
                client=Depends(get_imovel_hub_client)) -> dict:
    _, org_id = _parts(auth)
    return svc.obter(client, org_id, condominio_id)


@router.patch("/{condominio_id}")
def atualizar_route(condominio_id: UUID, body: CondominioPatchBody, auth=Depends(get_current_user_org),
                    client=Depends(get_imovel_hub_client)) -> dict:
    user_id, org_id = _parts(auth)
    return svc.atualizar(client, org_id, condominio_id, body.model_dump(exclude_unset=True), user_id)


def _acao(nome: str, rotulo: str, fn):
    def rota(condominio_id: UUID, request: Request, auth=Depends(get_current_user_org),
             client=Depends(get_imovel_hub_client)) -> dict:
        _admin(auth, request, rotulo)
        user_id, org_id = _parts(auth)
        return fn(client, org_id, condominio_id, user_id)

    rota.__name__ = nome
    return rota


router.post("/{condominio_id}/validar")(_acao("validar_route", "Validar condomínios", svc.validar))
router.post("/{condominio_id}/descartar")(_acao("descartar_route", "Descartar condomínios", svc.descartar))
router.post("/{condominio_id}/reabrir")(_acao("reabrir_route", "Reabrir condomínios", svc.reabrir))
router.post("/{condominio_id}/desfazer-fusao")(
    _acao("desfazer_fusao_route", "Desfazer fusão de condomínios", svc.desfazer_fusao)
)


@router.post("/{condominio_id}/renomear")
def renomear_route(condominio_id: UUID, body: RenomearBody, request: Request,
                   auth=Depends(get_current_user_org), client=Depends(get_imovel_hub_client)) -> dict:
    _admin(auth, request, "Renomear condomínios")
    user_id, org_id = _parts(auth)
    return svc.renomear(client, org_id, condominio_id, body.nome, user_id)


@router.post("/{condominio_id}/fundir")
def fundir_route(condominio_id: UUID, body: FundirBody, request: Request,
                 auth=Depends(get_current_user_org), client=Depends(get_imovel_hub_client)) -> dict:
    _admin(auth, request, "Fundir condomínios")
    user_id, org_id = _parts(auth)
    return svc.fundir(client, org_id, condominio_id, body.destino_id, user_id)


@router.post("/{condominio_id}/aliases")
def adicionar_alias_route(condominio_id: UUID, body: AliasBody, request: Request,
                          auth=Depends(get_current_user_org), client=Depends(get_imovel_hub_client)) -> dict:
    _admin(auth, request, "Alterar grafias de condomínios")
    user_id, org_id = _parts(auth)
    return svc.adicionar_alias(client, org_id, condominio_id, body.alias, user_id)


@router.delete("/{condominio_id}/aliases/{alias_id}")
def remover_alias_route(condominio_id: UUID, alias_id: UUID, request: Request,
                        auth=Depends(get_current_user_org), client=Depends(get_imovel_hub_client)) -> dict:
    _admin(auth, request, "Alterar grafias de condomínios")
    user_id, org_id = _parts(auth)
    return svc.remover_alias(client, org_id, condominio_id, alias_id, user_id)
