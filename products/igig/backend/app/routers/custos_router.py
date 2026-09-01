"""Custo/hora — funções e profissionais.

  GET    /api/custos/funcoes                  list roles + default rates
  POST   /api/custos/funcoes                  create a role
  PATCH  /api/custos/funcoes/{funcao_id}      edit name / default rate
  DELETE /api/custos/funcoes/{funcao_id}      delete a role
  GET    /api/custos/profissionais            list people + RESOLVED rate
  POST   /api/custos/profissionais            create a person
  PATCH  /api/custos/profissionais/{id}       edit role / override / ativo
  DELETE /api/custos/profissionais/{id}       delete a person

**Why this router exists.** Migration `008` shipped `funcao` + `profissional`
with RLS, repositories and ``custo_hora_efetivo`` — everything except an HTTP
boundary. Nothing above the repository layer could reach them, so the rate
table could never be filled, and the three features that read it all reported
zero: M1's calculadora ("preço sugerido é 0 e NÃO deve ser usado"), M5's BI de
eficiência (custo real), and M6's DRE (margem por conta). A zero that is
really "no input" reads as a real answer — exactly the silent-error shape the
platform forbids. This closes it.

Deleting a função is deliberately NOT cascading: `profissional.funcao_id` is
``ON DELETE SET NULL``, so people survive but fall back to their override.
Anyone left with neither is reported by ``custo_hora_indefinido`` rather than
silently costed at zero.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from noctusai_lib.integrations.persistence import RecordNotFound

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.repositories import Repositorios
from app.schemas.custos import (
    FuncaoCreate,
    FuncaoOut,
    FuncaoUpdate,
    ProfissionalCreate,
    ProfissionalOut,
    ProfissionalUpdate,
)
from app.store import get_repositorios

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/custos", tags=["custos"])


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


def _com_taxa(repos: Repositorios, org_id: str, row: dict) -> ProfissionalOut:
    """Attach the resolved rate to a profissional row.

    Resolution is delegated to ``custo_hora_efetivo`` rather than recomputed
    here — one definition, shared by M1/M5/M6. A person with neither an
    override nor a função raises there; that is reported as
    ``custo_hora_indefinido`` instead of being flattened to 0.0, because a
    zero rate and an unknown rate mean very different things to a DRE.
    """
    try:
        efetivo = repos.profissional.custo_hora_efetivo(
            org_id, str(row["id"]), funcoes=repos.funcao
        )
        return ProfissionalOut(**row, custo_hora_efetivo=efetivo)
    except ValueError:
        return ProfissionalOut(**row, custo_hora_efetivo=None, custo_hora_indefinido=True)


# ─── Funções ───────────────────────────────────────────────────────────────

@router.get("/funcoes", response_model=list[FuncaoOut])
async def listar_funcoes(
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[FuncaoOut]:
    org_id = _org(auth)
    return [FuncaoOut(**f) for f in repos.funcao.listar(org_id)]


@router.post("/funcoes", response_model=FuncaoOut, status_code=status.HTTP_201_CREATED)
async def criar_funcao(
    payload: FuncaoCreate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> FuncaoOut:
    org_id = _org(auth)
    row = repos.funcao.criar(org_id, payload.model_dump())
    logger.info("funcao criada org=%s id=%s", org_id, row.get("id"))
    return FuncaoOut(**row)


@router.patch("/funcoes/{funcao_id}", response_model=FuncaoOut)
async def atualizar_funcao(
    funcao_id: str,
    payload: FuncaoUpdate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> FuncaoOut:
    org_id = _org(auth)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        return FuncaoOut(**repos.funcao.atualizar(org_id, funcao_id, data))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Função não encontrada")


@router.delete("/funcoes/{funcao_id}", status_code=status.HTTP_200_OK)
async def remover_funcao(
    funcao_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> dict:
    org_id = _org(auth)
    if not repos.funcao.remover(org_id, funcao_id):
        raise HTTPException(status_code=404, detail="Função não encontrada")
    return {"ok": True}


# ─── Profissionais ─────────────────────────────────────────────────────────

@router.get("/profissionais", response_model=list[ProfissionalOut])
async def listar_profissionais(
    apenas_ativos: bool = Query(default=False),
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[ProfissionalOut]:
    org_id = _org(auth)
    linhas = (
        repos.profissional.ativos(org_id)
        if apenas_ativos
        else repos.profissional.listar(org_id)
    )
    return [_com_taxa(repos, org_id, p) for p in linhas]


@router.post(
    "/profissionais", response_model=ProfissionalOut, status_code=status.HTTP_201_CREATED
)
async def criar_profissional(
    payload: ProfissionalCreate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> ProfissionalOut:
    org_id = _org(auth)
    # exclude_unset, NOT exclude_none: `custo_hora_override=None` sent
    # explicitly means "inherit the função", and dropping it would silently
    # keep a stale override.
    row = repos.profissional.criar(org_id, payload.model_dump(exclude_unset=True))
    logger.info("profissional criado org=%s id=%s", org_id, row.get("id"))
    return _com_taxa(repos, org_id, row)


@router.patch("/profissionais/{profissional_id}", response_model=ProfissionalOut)
async def atualizar_profissional(
    profissional_id: str,
    payload: ProfissionalUpdate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> ProfissionalOut:
    org_id = _org(auth)
    # Same reasoning as create: clearing an override is a legitimate edit, so
    # an explicitly-sent null must survive into the update.
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = repos.profissional.atualizar(org_id, profissional_id, data)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")
    return _com_taxa(repos, org_id, row)


@router.delete("/profissionais/{profissional_id}", status_code=status.HTTP_200_OK)
async def remover_profissional(
    profissional_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> dict:
    org_id = _org(auth)
    if not repos.profissional.remover(org_id, profissional_id):
        raise HTTPException(status_code=404, detail="Profissional não encontrado")
    return {"ok": True}
