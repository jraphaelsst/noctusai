"""Lais > Equipes (wave 11, contract section 13). Distribution data lives in SW; Julia only consumes it.

  GET    /api/lais/equipes                              -> {data:[{id, nome, atende_apos_julia, modo funil|julia,
                                                          manter_ultimo, membros:[{user_id, nome, ativo, ordem}]}]}
  POST   /api/lais/equipes                              admin {nome, atende_apos_julia?, modo?, manter_ultimo?} -> 201
  GET    /api/lais/equipes/{id}
  PATCH  /api/lais/equipes/{id}                         admin (any of the POST fields)
  DELETE /api/lais/equipes/{id}                         admin -> 204
  POST   /api/lais/equipes/{id}/membros                 admin {user_id, ativo?} -> 201 (the team)
  PATCH  /api/lais/equipes/{id}/membros/{user_id}       admin {ativo}
  DELETE /api/lais/equipes/{id}/membros/{user_id}       admin -> 204
  PUT    /api/lais/equipes/{id}/membros/ordem           admin {ordem:[user_id,...]} (exactly the current members)
  GET    /api/lais/equipes/{id}/metricas?mes=YYYY-MM    -> {data:{membros:[{user_id, nome, ultimo_acesso, tpr_medio_s,
                                                          tpr_amostras, conversas, distribuicao, distribuicao_pct}], ...}}

Writes are org owner/admin only (403); reads are any org member. Every route is 401 without a session.
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.services import lais_equipes_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lais/equipes", tags=["lais-equipes"])

_QUEM = "As equipes"


def get_equipes_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


class EquipeIn(StrictHttpModel):
    nome: str = Field(min_length=1, max_length=60)
    atende_apos_julia: bool = True
    modo: Literal["funil", "julia"] = "funil"
    manter_ultimo: bool = True


class EquipePatch(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=60)
    atende_apos_julia: Optional[bool] = None
    modo: Optional[Literal["funil", "julia"]] = None
    manter_ultimo: Optional[bool] = None


class MembroIn(StrictHttpModel):
    user_id: UUID
    ativo: bool = True


class MembroPatch(StrictHttpModel):
    ativo: bool


class OrdemIn(StrictHttpModel):
    ordem: list[UUID] = Field(max_length=200)


def _org(auth: tuple) -> UUID:
    return coerce_org_uuid(auth[2])


def _admin(auth: tuple, request: Optional[Request]) -> UUID:
    require_org_admin_for(get_core_client(), auth, request, _QUEM)
    return _org(auth)


@router.get("")
def listar(auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_equipes_client)) -> dict[str, Any]:
    return {"data": svc.listar(client, get_core_client(), _org(auth))}


@router.post("", status_code=201)
def criar(corpo: EquipeIn, request: Request = None, auth: tuple = Depends(get_current_user_org),
          client: Any = Depends(get_equipes_client)) -> dict[str, Any]:
    org = _admin(auth, request)
    return {"data": svc.criar(client, get_core_client(), org, nome=corpo.nome, atende_apos_julia=corpo.atende_apos_julia,
                              modo=corpo.modo, manter_ultimo=corpo.manter_ultimo)}


@router.get("/{equipe_id}")
def obter(equipe_id: UUID, auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_equipes_client)) -> dict[str, Any]:
    return {"data": svc.obter(client, get_core_client(), _org(auth), equipe_id)}


@router.patch("/{equipe_id}")
def atualizar(equipe_id: UUID, corpo: EquipePatch, request: Request = None, auth: tuple = Depends(get_current_user_org),
              client: Any = Depends(get_equipes_client)) -> dict[str, Any]:
    org = _admin(auth, request)
    campos = {k: getattr(corpo, k) for k in corpo.model_fields_set}
    return {"data": svc.atualizar(client, get_core_client(), org, equipe_id, campos)}


@router.delete("/{equipe_id}", status_code=204)
def excluir(equipe_id: UUID, request: Request = None, auth: tuple = Depends(get_current_user_org),
            client: Any = Depends(get_equipes_client)) -> Response:
    svc.excluir(client, _admin(auth, request), equipe_id)
    return Response(status_code=204)


# `/membros/ordem` is declared BEFORE `/membros/{user_id}` so the literal segment is not read as a user id.
@router.put("/{equipe_id}/membros/ordem")
def ordenar(equipe_id: UUID, corpo: OrdemIn, request: Request = None, auth: tuple = Depends(get_current_user_org),
            client: Any = Depends(get_equipes_client)) -> dict[str, Any]:
    org = _admin(auth, request)
    return {"data": svc.ordenar_membros(client, get_core_client(), org, equipe_id, [str(u) for u in corpo.ordem])}


@router.post("/{equipe_id}/membros", status_code=201)
def adicionar_membro(equipe_id: UUID, corpo: MembroIn, request: Request = None, auth: tuple = Depends(get_current_user_org),
                     client: Any = Depends(get_equipes_client)) -> dict[str, Any]:
    org = _admin(auth, request)
    return {"data": svc.adicionar_membro(client, get_core_client(), org, equipe_id, corpo.user_id, ativo=corpo.ativo)}


@router.patch("/{equipe_id}/membros/{user_id}")
def atualizar_membro(equipe_id: UUID, user_id: UUID, corpo: MembroPatch, request: Request = None,
                     auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_equipes_client)) -> dict[str, Any]:
    org = _admin(auth, request)
    return {"data": svc.atualizar_membro(client, get_core_client(), org, equipe_id, user_id, ativo=corpo.ativo)}


@router.delete("/{equipe_id}/membros/{user_id}", status_code=204)
def remover_membro(equipe_id: UUID, user_id: UUID, request: Request = None, auth: tuple = Depends(get_current_user_org),
                   client: Any = Depends(get_equipes_client)) -> Response:
    svc.remover_membro(client, _admin(auth, request), equipe_id, user_id)
    return Response(status_code=204)


@router.get("/{equipe_id}/metricas")
def metricas(equipe_id: UUID, mes: Optional[str] = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
             auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_equipes_client)) -> dict[str, Any]:
    mes = mes or datetime.now(timezone.utc).strftime("%Y-%m")
    return {"data": svc.metricas(client, get_core_client(), _org(auth), equipe_id, mes)}
