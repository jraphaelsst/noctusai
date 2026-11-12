"""``GET /api/studio/agents/{key}/prontidao`` -- what the DRAFT still owes before it can (and should) be published.

Same audience as reading the draft (``require_platform_content_admin``: a NoctusAI platform admin session or the
``studio:content-write`` token of the ``noctus.agents.content`` MCP tool) and audited like every definition read. Pure
read: it compiles the draft but stamps nothing. The same item list rides in every publish 409. See
``app.studio.prontidao`` and ``KB § GUIDES/agent-creation.md``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import (
    get_conformidade_store_dep,
    get_geracao_store_dep,
    get_skills_store_dep,
    require_platform_content_admin,
)
from app.routers.qualificacao_router import get_padrao_store_dep
from app.routers.studio_agents_router import (
    audit_definition_read,
    get_eval_gate_dep,
    get_eval_store_dep,
    get_knowledge_catalog_dep,
    get_consolidacao_store_dep,
    get_prontidao_controles_dep,
    get_studio_definition_store_dep,
    resolve_agent,
    resolve_draft,
)
from app.schemas.studio_prontidao import ProntidaoItemOut, ProntidaoOut
from app.studio.prontidao import avaliar
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(prefix="/api/studio", tags=["studio-prontidao"], include_in_schema=False)


@router.get("/agents/{key}/prontidao", response_model=ProntidaoOut)
def get_prontidao(
    key: str,
    ctx: AuthContext = Depends(require_platform_content_admin),
    store=Depends(get_studio_definition_store_dep),
    gate=Depends(get_eval_gate_dep),
    catalog=Depends(get_knowledge_catalog_dep),
    padroes=Depends(get_padrao_store_dep),
    skills=Depends(get_skills_store_dep),
    geracoes=Depends(get_geracao_store_dep),
    evals=Depends(get_eval_store_dep),
    controles=Depends(get_prontidao_controles_dep),
    conformidade=Depends(get_conformidade_store_dep),
    consolidacao=Depends(get_consolidacao_store_dep),
) -> ProntidaoOut:
    agent = resolve_agent(store, ctx.org_id, key)
    draft = resolve_draft(store, ctx.org_id, agent)
    audit_definition_read(store, ctx, agent, "prontidao", draft.id)
    p = avaliar(
        store=store, catalog=catalog, org_id=ctx.org_id, agent=agent, draft=draft, gate=gate, padroes=padroes,
        skills=skills, geracoes=geracoes, evals=evals, controles=controles,
        conformidade=conformidade, consolidacao=consolidacao,
    )
    return ProntidaoOut(
        agent_key=p.agent_key, version_id=p.version_id, hash=p.hash, pronto_para_publicar=p.pronto_para_publicar,
        bloqueantes=p.bloqueantes, avisos=p.avisos, itens=[ProntidaoItemOut(**i.to_dict()) for i in p.itens],
    )


__all__ = ["router"]
