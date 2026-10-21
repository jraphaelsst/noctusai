"""Julia > Equipe (staff of the org's WhatsApp lines; owner 2026-10-21: "staff will be set in-org ... if not in the staff list, it's
an incoming lead").

  GET    /api/julia/equipe-whatsapp               admin  {data:{items,papeis,operadores}}   (the org staff list)
  GET    /api/julia/equipe-whatsapp/usuarios      admin  {data:[{id,nome,org_role}]}        (org users that can be linked)
  POST   /api/julia/equipe-whatsapp               admin  {nome,papel,telefone?,user_id?}    {data: row}
  PATCH  /api/julia/equipe-whatsapp/{id}          admin  {nome?,papel?,telefone?,user_id?,ativo?}
  DELETE /api/julia/equipe-whatsapp/{id}          admin  (the person's next message is a lead)

Staff is a privilege (an operator role drives the One Chat agent from the person's number), so every route is an org-admin action.
Typed errors: 422 `papel_invalido` / `telefone_invalido` / `nome_invalido` / `identificacao_obrigatoria` / `usuario_fora_da_org`, 409
`telefone_ja_cadastrado` / `numero_bloqueado` / `ultimo_operador`, 404 `staff_nao_encontrado`.
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.services import julia_staff_service as staff

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/julia/equipe-whatsapp", tags=["julia-equipe-whatsapp"])


def get_equipe_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


def get_equipe_core() -> Any:
    """DI seam: the core client (org users)."""
    return get_core_client()


class StaffIn(StrictHttpModel):
    nome: str = Field(min_length=1, max_length=staff.NOME_MAX)
    papel: str = Field(max_length=20)
    telefone: Optional[str] = Field(default=None, max_length=40)
    user_id: Optional[UUID] = None


class StaffPatch(StrictHttpModel):
    nome: Optional[str] = Field(default=None, max_length=staff.NOME_MAX)
    papel: Optional[str] = Field(default=None, max_length=20)
    telefone: Optional[str] = Field(default=None, max_length=40)
    user_id: Optional[UUID] = None
    ativo: Optional[bool] = None


def _org(auth: tuple) -> UUID:
    return coerce_org_uuid(auth[2])


def _admin(auth: tuple, request: Optional[Request], core: Any, what: str) -> None:
    require_org_admin_for(core, auth, request, what)


@router.get("")
def listar(
    request: Request = None, auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_equipe_client),
    core: Any = Depends(get_equipe_core),
) -> dict[str, Any]:
    _admin(auth, request, core, "A lista da equipe")
    items = staff.listar(client, _org(auth))
    return {"data": {"items": items, "papeis": list(staff.PAPEIS), "operadores": list(staff.PAPEIS_OPERADOR)}}


@router.get("/usuarios")
def usuarios(
    request: Request = None, auth: tuple = Depends(get_current_user_org), core: Any = Depends(get_equipe_core),
) -> dict[str, Any]:
    _admin(auth, request, core, "A lista de usuários da equipe")
    rows = core.table("noctus_users").select("id, nome, org_role").eq("org_id", str(_org(auth))).execute().data or []
    return {"data": sorted(({"id": str(r["id"]), "nome": r.get("nome"), "org_role": r.get("org_role")} for r in rows),
                           key=lambda r: str(r["nome"] or "").lower())}


@router.post("", status_code=201)
def criar(
    corpo: StaffIn, request: Request = None, auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_equipe_client), core: Any = Depends(get_equipe_core),
) -> dict[str, Any]:
    _admin(auth, request, core, "O cadastro da equipe")
    row = staff.criar(client, core, _org(auth), str(auth[0].id), nome=corpo.nome, papel=corpo.papel, telefone=corpo.telefone,
                      user_id=str(corpo.user_id) if corpo.user_id else None)
    logger.info("julia: staff entry created org=%s role=%s", _org(auth), row.get("papel"))
    return {"data": row}


@router.patch("/{staff_id}")
def atualizar(
    staff_id: UUID, corpo: StaffPatch, request: Request = None, auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_equipe_client), core: Any = Depends(get_equipe_core),
) -> dict[str, Any]:
    _admin(auth, request, core, "A edição da equipe")
    campos = corpo.model_dump(mode="json", exclude_unset=True)
    return {"data": staff.atualizar(client, core, _org(auth), staff_id, campos)}


@router.delete("/{staff_id}", status_code=204)
def remover(
    staff_id: UUID, request: Request = None, auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_equipe_client), core: Any = Depends(get_equipe_core),
) -> None:
    _admin(auth, request, core, "A remoção da equipe")
    staff.remover(client, _org(auth), staff_id)
