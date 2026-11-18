"""Client onboarding by interview -- the staff surface (owner decision 2026-11-17).

``GET  /api/studio/plataforma/agents/{key}/products/{product}/orgs/{org_id}/onboarding``          the checklist + progress
``POST .../onboarding/importar``   ``{"texto": "..."}`` -> pre-filled answers to CONFIRM (never a write)
``POST .../onboarding/aplicar``    ``{"respostas": {"<item n>": value}}`` -> ONE apply step, per-item report

Same two conditions as the staff org-specs route (platform admin + a live grant whose editor is ``plataforma``;
``plataforma_org_specs_router._alvo``), and the spec writes land in :func:`aplicar_org_specs` -- one write path, one
audit. The interviewer agent (``onboarding-imob``) conducts the conversation; these routes are what it, and the Studio
"Onboarding" tab, call. After apply the owner is pointed to evaluation mode (``modo_avaliacao``) for a dry
conversation BEFORE go-live; nothing here turns an agent on.

NOC-REMEDIATE[onboarding-interviewer-tools]: the three operations below are not yet exposed as TOOLS of the `onboarding-imob`
agent (progresso / importar / aplicar); only the Studio tab calls them. Destination: the next agents slice, "onboarding
interviewer as a live chatbot" -- 2026-11-17
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import Depends
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth.session import AuthContext
from pydantic import BaseModel, Field

from app.dependencies import get_grant_store_dep, require_platform_admin
from app.grants.store import GrantStore
from app.onboarding import aplicar as ap
from app.onboarding.checklist import CHECKLIST, ordem_entrevista
from app.onboarding.importar import MAX_ENTRADA, importar
from app.onboarding.sw_settings import SwSettingsPort, get_sw_settings
from app.routers.plataforma_org_specs_router import _BASE, _alvo
from app.routers.studio_agents_router import get_studio_definition_store_dep, http_error
from app.routers.studio_conteudo_router import aplicar_org_specs, get_spec_validacao_dep, ler_org_specs
from app.studio.especificacoes_service import ConfigValidacao

logger = logging.getLogger(__name__)

router = make_router(tier="platform", guard=require_platform_admin, tags=["onboarding"])

#: Where the owner goes after an apply: a dry conversation in evaluation mode, then the go-live decision (a human act).
PROXIMO_PASSO = "modo_avaliacao"


def get_sw_settings_dep() -> SwSettingsPort:
    """DI seam: the social-wiring settings port (tests override with the Fake)."""
    return get_sw_settings()


class ItemOut(BaseModel):
    n: int
    bloco: str
    nivel: str
    titulo: str
    pergunta: str
    destino: str
    padrao: str | None = None
    quando: list[str] = []
    #: ``preenchido`` / ``vazio`` for spec-backed items; ``fora_do_agents`` when the answer lives in SW or is a human step.
    estado: str


class OnboardingOut(BaseModel):
    agent_key: str
    operacoes: list[str]
    itens: list[ItemOut]
    progresso: dict[str, Any]
    proximo_passo: str = PROXIMO_PASSO


class ImportarIn(StrictHttpModel):
    texto: str = Field(max_length=MAX_ENTRADA)


class RespostaOut(BaseModel):
    n: int
    valor: Any
    fonte: str
    origem: str
    confirmado: bool


class ImportacaoOut(BaseModel):
    preenchidas: list[RespostaOut]
    nao_reconhecidas: list[str]
    conflitos: list[str]


class AplicarIn(StrictHttpModel):
    respostas: dict[int, Any] = Field(max_length=len(CHECKLIST))
    #: items whose value came from an import, and those of them somebody explicitly confirmed. An imported item that
    #: is not confirmed is NOT written (reported ``pendente_confirmacao``).
    importados: list[int] = Field(default_factory=list, max_length=len(CHECKLIST))
    confirmados: list[int] = Field(default_factory=list, max_length=len(CHECKLIST))


class ItemRelatorioOut(BaseModel):
    n: int
    titulo: str
    estado: str
    codigo: str | None = None
    motivo: str | None = None
    destino: str
    rota: str | None = None
    corpo: dict[str, Any] | None = None


class RelatorioOut(BaseModel):
    itens: list[ItemRelatorioOut]
    aplicados: int
    recusados: int
    obrigatorios_faltando: list[int]
    proximo_passo: str = PROXIMO_PASSO


def _valores(out) -> dict[str, str]:
    return {v.chave: v.valor for v in out.valores}


@router.get(f"{_BASE}/{{org_id}}/onboarding", response_model=OnboardingOut)
def get_onboarding(
    key: str, product: str, org_id: UUID,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
    grants: GrantStore = Depends(get_grant_store_dep),
    config: ConfigValidacao = Depends(get_spec_validacao_dep),
) -> OnboardingOut:
    alvo, _ = _alvo(store, grants, ctx, key, product, org_id)
    valores = _valores(ler_org_specs(store, alvo, key, config))
    ops = ap.operacoes_de(valores.get("operacoes_atendidas"))
    respondidos: dict[int, Any] = {}
    itens: list[ItemOut] = []
    for i in ordem_entrevista(ops or None):
        d = i.destino
        if d.kind == "spec":
            cheio = bool((valores.get(d.alvo) or "").strip())
            respondidos[i.n] = cheio or None
            estado = "preenchido" if cheio else "vazio"
        else:
            estado = "fora_do_agents"
        itens.append(ItemOut(
            n=i.n, bloco=i.bloco, nivel=i.nivel, titulo=i.titulo, pergunta=i.pergunta, destino=f"{d.kind}:{d.alvo}",
            padrao=i.padrao, quando=list(i.quando), estado=estado,
        ))
    return OnboardingOut(agent_key=key, operacoes=sorted(ops), itens=itens, progresso=ap.progresso(ops or None, respondidos))


@router.post(f"{_BASE}/{{org_id}}/onboarding/importar", response_model=ImportacaoOut)
def post_importar(
    key: str, product: str, org_id: UUID, payload: ImportarIn,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
    grants: GrantStore = Depends(get_grant_store_dep),
) -> ImportacaoOut:
    _alvo(store, grants, ctx, key, product, org_id)  # same gate as the write: no probing of ungranted orgs
    res = importar(payload.texto)
    return ImportacaoOut(
        preenchidas=[RespostaOut(n=r.n, valor=r.valor, fonte=r.fonte, origem=r.origem, confirmado=r.confirmado)
                     for r in res.preenchidas],
        nao_reconhecidas=res.nao_reconhecidas, conflitos=res.conflitos,
    )


@router.post(f"{_BASE}/{{org_id}}/onboarding/aplicar", response_model=RelatorioOut)
def post_aplicar(
    key: str, product: str, org_id: UUID, payload: AplicarIn,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
    grants: GrantStore = Depends(get_grant_store_dep),
    config: ConfigValidacao = Depends(get_spec_validacao_dep),
    sw: SwSettingsPort = Depends(get_sw_settings_dep),
) -> RelatorioOut:
    alvo, grant = _alvo(store, grants, ctx, key, product, org_id)
    atual = ler_org_specs(store, alvo, key, config)
    if not atual.declaradas:
        raise http_error(409, "definicao_sem_especificacoes", "A definição ainda não declara especificações da organização.")
    origem = {
        "origem": "plataforma_onboarding", "produto": product, "grant_id": str(grant.id), "org_alvo": str(org_id),
        "ator_plataforma": str(ctx.user_id),
    }
    rel = ap.aplicar(
        payload.respostas, org_id=org_id, declaradas={d.chave: d.tipo for d in atual.declaradas}, armazenados=_valores(atual),
        nao_confirmados=frozenset(payload.importados) - frozenset(payload.confirmados),
        config=config, gravar_specs=lambda v: aplicar_org_specs(store, alvo, key, v, config, origem=origem), sw=sw,
        ator=ctx.user_id, grant_id=grant.id,
    )
    logger.info("onboarding.aplicar org=%s agent=%s aplicados=%d recusados=%d", org_id, key, rel.aplicados, rel.recusados)
    return RelatorioOut(
        itens=[ItemRelatorioOut(**vars(i)) for i in rel.itens], aplicados=rel.aplicados, recusados=rel.recusados,
        obrigatorios_faltando=rel.obrigatorios_faltando,
    )
