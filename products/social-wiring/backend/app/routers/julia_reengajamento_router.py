"""Julia wave 4 -- Reengajamento routes (contract 6, page-map 59.0 a2 / 59.0b b2).

  GET  /api/julia/reengajamento/config                       org member
  PUT  /api/julia/reengajamento/config                       org admin
  GET  /api/julia/reengajamento/reguas                       org member
  POST /api/julia/reengajamento/reguas                       org admin
  GET  /api/julia/reengajamento/reguas/{id}                  org member
  PATCH/DELETE /api/julia/reengajamento/reguas/{id}          org admin
  POST /api/julia/reengajamento/reguas/{id}/ativar|desativar org admin   (409 regua_sem_tentativa)
  POST /api/julia/reengajamento/reguas/{id}/tentativas       org admin   (409 limite_tentativas)
  PATCH/DELETE .../reguas/{id}/tentativas/{tid}             org admin   (409 ultima_tentativa_ativa)

Envelope `{"data": ...}` (errors: `AppException` -> `{"error": {...}}`); request models are strict
(unknown field -> 422). The org is the session's selected org (auth tuple), never a body field.
"""
# No `from __future__ import annotations`: FastAPI resolves the body models from the real annotations.
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import Field, field_validator, model_validator

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.services import julia_reengajamento_service as svc

router = APIRouter(prefix="/api/julia/reengajamento", tags=["julia-reengajamento"])


def get_reengajamento_db() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


def _admin(auth: tuple, request: Request, context: str) -> UUID:
    require_org_admin_for(get_core_client(), auth, request, context)
    return coerce_org_uuid(auth[2])


class ConfigUpdate(StrictHttpModel):
    minutos_ativo: Optional[bool] = None
    minutos_intervalo: Optional[int] = None
    horas_ativo: Optional[bool] = None
    horas_intervalo: Optional[int] = None

    @field_validator("minutos_intervalo")
    @classmethod
    def _minutos(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in svc.MINUTOS_VALIDOS:
            raise ValueError("minutos_intervalo deve ser 5, 10, ..., 60")
        return v

    @field_validator("horas_intervalo")
    @classmethod
    def _horas(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in svc.HORAS_VALIDAS:
            raise ValueError("horas_intervalo deve ficar entre 1 e 11")
        return v


class ReguaCreate(StrictHttpModel):
    nome: str = Field(min_length=1, max_length=80)
    compra: bool = False
    aluguel: bool = False


class ReguaPatch(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=80)
    compra: Optional[bool] = None
    aluguel: Optional[bool] = None


class _Tentativa(StrictHttpModel):
    espera_unidade: Optional[Literal["minutos", "horas", "dias"]] = None
    texto: Optional[str] = Field(default=None, max_length=svc.TEXTO_MAX)
    template_id: Optional[UUID] = None
    ativa: Optional[bool] = None

    @field_validator("texto")
    @classmethod
    def _texto_nao_vazio(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("texto não pode ser vazio")
        return v


class TentativaCreate(_Tentativa):
    ordem: Optional[int] = Field(default=None, ge=1, le=svc.MAX_TENTATIVAS)
    espera_valor: int = Field(ge=1, le=999)

    @model_validator(mode="after")
    def _texto_xor_template(self) -> "TentativaCreate":
        if (self.texto is None) == (self.template_id is None):
            raise ValueError("informe texto OU template_id")
        return self


class TentativaPatch(_Tentativa):
    ordem: Optional[int] = Field(default=None, ge=1, le=svc.MAX_TENTATIVAS)
    espera_valor: Optional[int] = Field(default=None, ge=1, le=999)

    @model_validator(mode="after")
    def _um_so(self) -> "TentativaPatch":
        if self.texto is not None and self.template_id is not None:
            raise ValueError("informe texto OU template_id")
        return self


def _dump(m: StrictHttpModel) -> dict[str, Any]:
    return m.model_dump(mode="json", exclude_unset=True)


# ── config ──────────────────────────────────────────────────────────────────
@router.get("/config")
def get_config(auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_reengajamento_db)) -> dict[str, Any]:
    return {"data": svc.obter_config(db, coerce_org_uuid(auth[2]))}


@router.put("/config")
def put_config(
    body: ConfigUpdate, request: Request, auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_reengajamento_db),
) -> dict[str, Any]:
    org_id = _admin(auth, request, "julia reengajamento config")
    valores = {k: v for k, v in _dump(body).items() if v is not None}
    return {"data": svc.salvar_config(db, org_id, valores)}


# ── reguas ──────────────────────────────────────────────────────────────────
@router.get("/reguas")
def list_reguas(auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_reengajamento_db)) -> dict[str, Any]:
    return {"data": svc.listar_reguas(db, coerce_org_uuid(auth[2]))}


@router.post("/reguas", status_code=status.HTTP_201_CREATED)
def create_regua(
    body: ReguaCreate, request: Request, auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_reengajamento_db),
) -> dict[str, Any]:
    org_id = _admin(auth, request, "julia reengajamento regua")
    return {"data": svc.criar_regua(db, org_id, nome=body.nome, compra=body.compra, aluguel=body.aluguel)}


@router.get("/reguas/{regua_id}")
def get_regua(regua_id: UUID, auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_reengajamento_db)) -> dict[str, Any]:
    return {"data": svc.obter_regua(db, coerce_org_uuid(auth[2]), regua_id)}


@router.patch("/reguas/{regua_id}")
def patch_regua(
    regua_id: UUID, body: ReguaPatch, request: Request, auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_reengajamento_db),
) -> dict[str, Any]:
    org_id = _admin(auth, request, "julia reengajamento regua")
    return {"data": svc.atualizar_regua(db, org_id, regua_id, {k: v for k, v in _dump(body).items() if v is not None})}


@router.delete("/reguas/{regua_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_regua(
    regua_id: UUID, request: Request, auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_reengajamento_db),
) -> Response:
    svc.apagar_regua(db, _admin(auth, request, "julia reengajamento regua"), regua_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/reguas/{regua_id}/ativar")
def ativar(
    regua_id: UUID, request: Request, auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_reengajamento_db),
) -> dict[str, Any]:
    return {"data": svc.ativar_regua(db, _admin(auth, request, "julia reengajamento regua"), regua_id)}


@router.post("/reguas/{regua_id}/desativar")
def desativar(
    regua_id: UUID, request: Request, auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_reengajamento_db),
) -> dict[str, Any]:
    return {"data": svc.desativar_regua(db, _admin(auth, request, "julia reengajamento regua"), regua_id)}


# ── tentativas ──────────────────────────────────────────────────────────────
@router.post("/reguas/{regua_id}/tentativas", status_code=status.HTTP_201_CREATED)
def create_tentativa(
    regua_id: UUID, body: TentativaCreate, request: Request, auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_reengajamento_db),
) -> dict[str, Any]:
    org_id = _admin(auth, request, "julia reengajamento tentativa")
    return {"data": svc.criar_tentativa(db, org_id, regua_id, _dump(body))}


@router.patch("/reguas/{regua_id}/tentativas/{tid}")
def patch_tentativa(
    regua_id: UUID, tid: UUID, body: TentativaPatch, request: Request, auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_reengajamento_db),
) -> dict[str, Any]:
    org_id = _admin(auth, request, "julia reengajamento tentativa")
    return {"data": svc.atualizar_tentativa(db, org_id, regua_id, tid, {k: v for k, v in _dump(body).items() if v is not None})}


@router.delete("/reguas/{regua_id}/tentativas/{tid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tentativa(
    regua_id: UUID, tid: UUID, request: Request, auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_reengajamento_db),
) -> Response:
    svc.apagar_tentativa(db, _admin(auth, request, "julia reengajamento tentativa"), regua_id, tid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["get_reengajamento_db", "router"]
