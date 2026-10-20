"""``/api/agents/catalogo`` -- the tiered agent catalogue (Julia v2 A-RT2; CONTRACT 0.4 visibility tiers).

* ORG tier (any org member): ``[{key, nome, papel, descricao_publica, runtime, capacidades: [rotulo]}]`` --
  display-level fields only. ``descricao_publica`` and the capability labels are DB rows
  (``catalogo_agentes`` / ``catalogo_capacidades``), never a tool description or a prompt line.
* PLATFORM-ADMIN tier: the same rows plus the active version's tool keys and the version list. The tool
  KEYS (not their descriptions) are definition metadata; reading them is audited like every definition read.

Which agents are listed is decided by data: an agent of the caller's org with a visible catalogue row.
Julia is the leads agent (SDR); One Chat is the separate operator agent (``runtime='external'``) -- both
are listed (owner, 2026-10-20). The response models are explicit allowlists.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.dependencies import get_agent_store_dep, require_member, require_platform_admin
from app.routers.studio_agents_router import audit_definition_read, get_studio_definition_store_dep
from app.stores.catalogo import CatalogoEntrada, CatalogoStore, get_catalogo_store
from app.stores.errors import NotFound
from app.studio.resolucao import resolve_agent_for_org
from app.studio.vazamento import chamador_e_admin_da_plataforma
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import AuthContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])

__all__ = ["router", "get_catalogo_store_dep", "CatalogoAgenteOut", "CatalogoAgenteAdminOut"]


def get_catalogo_store_dep() -> CatalogoStore:
    from app.config import settings

    return get_catalogo_store(settings)


class CatalogoAgenteOut(BaseModel):
    """What an ORG member sees. Display-level only: no instruction text, rule, weight or tool detail."""

    key: str
    nome: str
    papel: str
    descricao_publica: str
    runtime: str
    capacidades: list[str] = Field(default_factory=list)


class VersaoResumoOut(BaseModel):
    versao: int
    status: str


class CatalogoAgenteAdminOut(CatalogoAgenteOut):
    """Platform-admin tier: + the active version's tool keys and the version list."""

    # REQUIRED (no defaults): an org-tier row must never validate as this model and grow empty admin keys.
    ferramentas: list[str]
    versao_ativa: int | None
    versoes: list[VersaoResumoOut]


class CatalogoEntradaIn(StrictHttpModel):
    papel: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,31}$")
    descricao_publica: str = Field(min_length=1, max_length=600)
    capacidades: list[str] = Field(default_factory=list, max_length=20)
    ordem: int = 0
    visivel: bool = True


def _admin_extra(studio_store: Any, ctx: AuthContext, key: str) -> dict[str, Any]:
    """Tool keys + versions of the definition behind ``key`` for the caller's org; empty for an agent without
    studio versions (an external agent)."""
    vazio: dict[str, Any] = {"ferramentas": [], "versao_ativa": None, "versoes": []}
    try:
        r = resolve_agent_for_org(studio_store, ctx.org_id, key)
    except NotFound:
        return vazio
    versoes = studio_store.list_versions(r.definicao.org_id, r.definicao.id)
    ativa = r.versao
    ferramentas: list[str] = []
    if ativa is not None:
        ferramentas = sorted(f.ferramenta for f in studio_store.list_ferramentas(r.definicao.org_id, ativa.id) if f.ativo)
        audit_definition_read(studio_store, ctx, r.definicao, "catalogo", ativa.id)
    return {
        "ferramentas": ferramentas,
        "versao_ativa": ativa.versao if ativa is not None else None,
        "versoes": [{"versao": v.versao, "status": v.status} for v in versoes],
    }


@router.get("/catalogo", response_model=list[CatalogoAgenteAdminOut] | list[CatalogoAgenteOut])
async def listar_catalogo(
    ctx: AuthContext = Depends(require_member),
    agentes=Depends(get_agent_store_dep),
    catalogo: CatalogoStore = Depends(get_catalogo_store_dep),
    studio_store=Depends(get_studio_definition_store_dep),
) -> list[dict[str, Any]]:
    agentes.ensure_default_agents(ctx.org_id)
    entradas = {e.agent_key: e for e in catalogo.listar()}
    admin = chamador_e_admin_da_plataforma(ctx)
    out: list[dict[str, Any]] = []
    for rec in sorted(agentes.list(ctx.org_id), key=lambda a: (entradas[a.key].ordem if a.key in entradas else 0, a.key)):
        e = entradas.get(rec.key)
        if e is None:
            continue
        row: dict[str, Any] = {
            "key": rec.key, "nome": rec.nome, "papel": e.papel, "descricao_publica": e.descricao_publica,
            "runtime": rec.runtime, "capacidades": list(e.capacidades),
        }
        if admin:
            row.update(_admin_extra(studio_store, ctx, rec.key))
        out.append(row)
    return out


@router.put("/catalogo/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def salvar_entrada_catalogo(
    key: str,
    payload: CatalogoEntradaIn,
    ctx: AuthContext = Depends(require_platform_admin),
    catalogo: CatalogoStore = Depends(get_catalogo_store_dep),
) -> Response:
    """Platform admin: write one agent's catalogue row (role, public description, capability labels)."""
    if not key or len(key) > 64 or not key.replace("-", "").isalnum() or key != key.lower():
        raise HTTPException(status_code=422, detail={"detail": "Chave inválida.", "code": "invalid_field"})
    catalogo.salvar(
        CatalogoEntrada(
            agent_key=key, papel=payload.papel, descricao_publica=payload.descricao_publica,
            capacidades=tuple(c.strip() for c in payload.capacidades if c.strip()), ordem=payload.ordem,
            visivel=payload.visivel,
        ),
        updated_by=ctx.user_id if isinstance(ctx.user_id, UUID) else None,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
