"""The unified agent surface (agents-unified CONTRACT §2-§4): the model schema, the listing and the per-agent painel.

* ``GET /api/studio/modelo`` -- the agent model (page sections; for platform admins also the 7 content areas with
  their fields and the creation-wizard steps), derived from the canonical Julia v2 model (``app.studio.modelo``).
* ``GET /api/agents/painel`` -- ONE card per agent of the caller's org (legado, platform instances, org Studio agents).
* ``GET /api/agents/{key}/painel`` -- one card (the page header), 404 for a key the org does not have.
* ``GET /api/agents/{key}/painel/interno`` -- the agent's internals (version, draft, content completeness):
  NoctusAI superadmin only; everyone else gets **404, not 403** (D31), and every read is audited.

Which agents exist and which sections each shows is decided by DATA (``definition_mode`` / ``definition_scope`` /
``conteudo_modo`` / ``kind`` / ``runtime``), never by an agent key.
"""
from __future__ import annotations

import logging
from typing import Any

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies import (
    ADMIN_ROLES,
    get_agent_store_dep,
    get_core_client,
    get_skills_store_dep,
    get_social_wiring_client_dep,
    require_member,
)
from app.routers.agents_router import _one_chat_state
from app.routers.catalogo_router import get_catalogo_store_dep
from app.routers.studio_agents_router import audit_definition_read, get_studio_definition_store_dep
from app.schemas.agente_painel import AgenteInternoOut, AgenteModeloOut, AgentePainelOut, AgentesPainelOut
from app.studio.modelo import FatosAgente, construir_modelo, origem_de, secoes_para
from app.studio.plataforma import ensure_instancias
from app.studio.vazamento import chamador_e_admin_da_plataforma
from noctusai_lib.api.auth.session import AuthContext, resolve_org_role_for

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agentes"])

__all__ = ["router", "tier_do_chamador"]

_NAO_ENCONTRADO = {"detail": "Agente não encontrado.", "code": "agent_not_found"}


def tier_do_chamador(ctx: AuthContext, request: Request | None) -> str:
    """``plataforma`` (``noctus_users.role == 'admin'``) > ``org_admin`` (owner/admin of the selected org) >
    ``membro``. Trusted-DB reads only; an unreadable platform role is NOT platform (fail closed)."""
    if chamador_e_admin_da_plataforma(ctx):
        return "plataforma"
    if resolve_org_role_for(get_core_client(), ctx, request) in ADMIN_ROLES:
        return "org_admin"
    return "membro"


class _Linha:
    """One agent of the org seen through both views of ``agents.agents``: the legacy store's row (``legado``) and/or
    the Studio store's row (every column). In production both read the same table; a key only one side knows is
    still that one agent."""

    def __init__(self, legado: Any | None, studio: Any | None) -> None:
        self.legado, self.studio = legado, studio
        base = studio or legado
        self.key: str = base.key
        self.nome: str = base.nome
        self.ativo: bool = bool(base.ativo)
        self.runtime: str = base.runtime
        self.owner_product: str | None = base.owner_product

    @property
    def fatos(self) -> FatosAgente:
        s = self.studio
        if s is None:
            return FatosAgente(origem="legado", runtime=self.runtime)
        return FatosAgente(
            origem=origem_de(s.definition_mode, s.definition_scope), conteudo_modo=s.conteudo_modo, kind=s.kind,
            runtime=s.runtime, usa_canais=s.usa_canais,
        )


def _linhas(ctx: AuthContext, agentes: Any, studio_store: Any) -> list[_Linha]:
    agentes.ensure_default_agents(ctx.org_id)
    ensure_instancias(ctx.org_id, studio_store=studio_store)
    legados = {a.key: a for a in agentes.list(ctx.org_id)}
    studios = {a.key: a for a in studio_store.list_agents(ctx.org_id)}
    return [_Linha(legados.get(k), studios.get(k)) for k in sorted(legados.keys() | studios.keys())]


def _linha(ctx: AuthContext, agentes: Any, studio_store: Any, key: str) -> _Linha:
    linha = next((li for li in _linhas(ctx, agentes, studio_store) if li.key == key), None)
    if linha is None:
        raise HTTPException(status_code=404, detail=_NAO_ENCONTRADO)
    return linha


async def _cartao(linha: _Linha, tier: str, catalogo: dict[str, Any], social_wiring_client: Any) -> AgentePainelOut:
    fatos = linha.fatos
    entrada = catalogo.get(linha.key)
    estado_externo, aviso, ativo = None, None, linha.ativo
    if fatos.origem == "legado" and linha.runtime == "external" and linha.legado is not None:
        # An external agent's on/off truth is its owning product's (One Chat -> social-wiring auto-reply).
        estado_externo, aviso = await _one_chat_state(linha.legado, social_wiring_client)
        if estado_externo is not None:
            ativo = estado_externo.auto_reply_enabled
    descricao = entrada.descricao_publica if entrada else getattr(linha.studio, "descricao", None)
    return AgentePainelOut(
        key=linha.key, nome=linha.nome, descricao=descricao, papel=entrada.papel if entrada else None,
        capacidades=list(entrada.capacidades) if entrada else [], origem=fatos.origem, tipo=fatos.kind,
        runtime=linha.runtime, owner_product=linha.owner_product, usa_canais=fatos.usa_canais, ativo=ativo,
        estado_externo=estado_externo, aviso=aviso, secoes=secoes_para(fatos, tier),
        pode_alternar=fatos.origem == "legado" and tier in ("org_admin", "plataforma"),
    )


@router.get("/api/studio/modelo", response_model=AgenteModeloOut)
async def get_modelo(request: Request, ctx: AuthContext = Depends(require_member)) -> dict[str, Any]:
    tier = await anyio.to_thread.run_sync(lambda: tier_do_chamador(ctx, request))
    return construir_modelo(tier)


@router.get("/api/agents/painel", response_model=AgentesPainelOut)
async def listar_painel(
    request: Request,
    ctx: AuthContext = Depends(require_member),
    agentes=Depends(get_agent_store_dep),
    studio_store=Depends(get_studio_definition_store_dep),
    catalogo_store=Depends(get_catalogo_store_dep),
    social_wiring_client=Depends(get_social_wiring_client_dep),
) -> AgentesPainelOut:
    def _ler():
        return (
            _linhas(ctx, agentes, studio_store), tier_do_chamador(ctx, request),
            {e.agent_key: e for e in catalogo_store.listar()},
        )

    linhas, tier, catalogo = await anyio.to_thread.run_sync(_ler)
    items = [await _cartao(li, tier, catalogo, social_wiring_client) for li in linhas]
    return AgentesPainelOut(items=items, total=len(items))


@router.get("/api/agents/{key}/painel", response_model=AgentePainelOut)
async def obter_painel(
    key: str,
    request: Request,
    ctx: AuthContext = Depends(require_member),
    agentes=Depends(get_agent_store_dep),
    studio_store=Depends(get_studio_definition_store_dep),
    catalogo_store=Depends(get_catalogo_store_dep),
    social_wiring_client=Depends(get_social_wiring_client_dep),
) -> AgentePainelOut:
    def _ler():
        return (
            _linha(ctx, agentes, studio_store, key), tier_do_chamador(ctx, request),
            {e.agent_key: e for e in catalogo_store.listar()},
        )

    linha, tier, catalogo = await anyio.to_thread.run_sync(_ler)
    return await _cartao(linha, tier, catalogo, social_wiring_client)


@router.get("/api/agents/{key}/painel/interno", response_model=AgenteInternoOut)
def obter_interno(
    key: str,
    request: Request,
    ctx: AuthContext = Depends(require_member),
    agentes=Depends(get_agent_store_dep),
    studio_store=Depends(get_studio_definition_store_dep),
    skills=Depends(get_skills_store_dep),
) -> AgenteInternoOut:
    # D31: an agent's internals exist only for NoctusAI superadmins -- for anyone else the route answers exactly
    # like an unknown agent (404, never 403: a 403 would confirm what is behind it).
    if tier_do_chamador(ctx, request) != "plataforma":
        raise HTTPException(status_code=404, detail=_NAO_ENCONTRADO)
    linha = _linha(ctx, agentes, studio_store, key)
    s = linha.studio
    if s is None:
        return AgenteInternoOut(
            key=linha.key, origem="legado", definition_scope="org", conteudo_modo="legado", versao_ativa=None,
            tem_rascunho=False, publicacao_limiar=None, conteudo_status=None,
        )
    from app.studio.geracao import conteudo_status

    definicao = s
    if s.definition_scope == "instancia" and s.definition_agent_id is not None:
        definicao = studio_store.get_agent_by_id(s.definition_agent_id)
    versao_ativa = tem_rascunho = None
    if s.definition_mode == "studio":
        ativa = studio_store.get_active_version(definicao.org_id, definicao.id)
        versao_ativa = ativa.versao if ativa else None
        tem_rascunho = s.definition_scope != "instancia" and studio_store.get_draft(definicao.org_id, definicao.id) is not None
    audit_definition_read(studio_store, ctx, s, "painel_interno")
    return AgenteInternoOut(
        key=s.key, origem=linha.fatos.origem, definition_scope=s.definition_scope, conteudo_modo=s.conteudo_modo,
        versao_ativa=versao_ativa, tem_rascunho=bool(tem_rascunho), publicacao_limiar=s.publicacao_limiar,
        conteudo_status=conteudo_status(studio_store, skills, s),
    )

