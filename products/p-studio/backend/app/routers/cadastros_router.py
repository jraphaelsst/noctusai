"""Rotas dos quatro cadastros: clientes, imóveis, serviços, equipamentos.

Todos têm a mesma forma de CRUD, então a rota é gerada por uma fábrica em vez
de repetida quatro vezes. O que muda por cadastro — prefixo, service, schemas —
é declarado na tabela no fim do arquivo.

Cada cadastro ganha `?incluir_inativos=true` na listagem porque o DELETE é
soft: sem isso não haveria como reativar o que foi desativado por engano.
"""
from typing import Type

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.dependencies import CurrentUser, get_current_user
from app.schemas.catalogo import (
    EquipamentoCreate,
    EquipamentoOut,
    EquipamentoUpdate,
    ServicoCreate,
    ServicoOut,
    ServicoUpdate,
)
from app.schemas.clientes import ClienteCreate, ClienteOut, ClienteUpdate
from app.schemas.imoveis import ImovelCreate, ImovelOut, ImovelUpdate
from app.services.base import CrudService, somente_preenchidos
from app.services.cadastros_service import (
    ClientesService,
    EquipamentosService,
    ImoveisService,
    ServicosService,
)


def montar_router(
    *,
    prefixo: str,
    tag: str,
    service_cls: Type[CrudService],
    create_schema: Type[BaseModel],
    update_schema: Type[BaseModel],
    out_schema: Type[BaseModel],
) -> APIRouter:
    router = APIRouter(prefix=f"/api/{prefixo}", tags=[tag])

    def service(user: CurrentUser) -> CrudService:
        return service_cls(user.db, user.org_id)

    @router.get("", response_model=list[out_schema])
    def listar(
        incluir_inativos: bool = Query(default=False),
        user: CurrentUser = Depends(get_current_user),
    ):
        return service(user).listar(incluir_inativos=incluir_inativos)

    @router.post("", response_model=out_schema, status_code=201)
    def criar(payload: create_schema, user: CurrentUser = Depends(get_current_user)):  # type: ignore[valid-type]
        return service(user).criar(payload.model_dump(mode="json"))

    @router.get("/{item_id}", response_model=out_schema)
    def obter(item_id: str, user: CurrentUser = Depends(get_current_user)):
        return service(user).obter(item_id)

    @router.patch("/{item_id}", response_model=out_schema)
    def atualizar(
        item_id: str,
        payload: update_schema,  # type: ignore[valid-type]
        user: CurrentUser = Depends(get_current_user),
    ):
        return service(user).atualizar(item_id, somente_preenchidos(payload))

    @router.delete("/{item_id}", status_code=204)
    def excluir(item_id: str, user: CurrentUser = Depends(get_current_user)):
        service(user).excluir(item_id)
        return None

    return router


clientes_router = montar_router(
    prefixo="clientes",
    tag="clientes",
    service_cls=ClientesService,
    create_schema=ClienteCreate,
    update_schema=ClienteUpdate,
    out_schema=ClienteOut,
)

imoveis_router = montar_router(
    prefixo="imoveis",
    tag="imoveis",
    service_cls=ImoveisService,
    create_schema=ImovelCreate,
    update_schema=ImovelUpdate,
    out_schema=ImovelOut,
)

servicos_router = montar_router(
    prefixo="servicos",
    tag="servicos",
    service_cls=ServicosService,
    create_schema=ServicoCreate,
    update_schema=ServicoUpdate,
    out_schema=ServicoOut,
)

equipamentos_router = montar_router(
    prefixo="equipamentos",
    tag="equipamentos",
    service_cls=EquipamentosService,
    create_schema=EquipamentoCreate,
    update_schema=EquipamentoUpdate,
    out_schema=EquipamentoOut,
)
