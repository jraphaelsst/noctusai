"""Client onboarding by interview -- the staff surface (owner decision 2026-11-17).

``GET  /api/studio/plataforma/agents/{key}/products/{product}/orgs/{org_id}/onboarding``          the checklist + progress
``POST .../onboarding/importar``   ``{"texto": "..."}`` -> pre-filled answers to CONFIRM (never a write)
``POST .../onboarding/conversa``  start the interview: a conversation of ``onboarding-imob`` bound to the company
``POST .../onboarding/aplicar``    ``{"respostas": {"<item n>": value}}`` -> ONE apply step, per-item report

Same two conditions as the staff org-specs route (platform admin + a live grant whose editor is ``plataforma``;
``plataforma_org_specs_router._alvo``), and the spec writes land in :func:`aplicar_org_specs` -- one write path, one
audit. The interviewer agent (``onboarding-imob``) conducts the conversation; these routes are what it, and the Studio
"Onboarding" tab, call. After apply the owner is pointed to evaluation mode (``modo_avaliacao``) for a dry
conversation BEFORE go-live; nothing here turns an agent on.

The interviewer's own tools (``progresso_onboarding`` / ``registrar_resposta`` / ``importar_configuracao`` /
``revisar_e_aplicar``, ``app.onboarding.ferramentas``) are the conversational twin of these routes: same checklist, same
apply step (``app.onboarding.servico``), plus the append-only event ledger the GET below folds for the live progress.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import Depends
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth.session import AuthContext
from pydantic import BaseModel, Field

from app.dependencies import get_conversation_store_dep, get_grant_store_dep, get_onboarding_store_dep, require_platform_admin
from app.grants.store import GrantStore
from app.onboarding import aplicar as ap
from app.onboarding.servico import aplicar_na_org, valores_armazenados
from app.onboarding.entrevista import ABERTO, RESPONDIDO, estado_dos_itens
from app.onboarding.checklist import CHECKLIST, ordem_entrevista
from app.onboarding.importar import MAX_ENTRADA, importar
from app.onboarding.sw_settings import SwSettingsPort, get_sw_settings
from app.routers.plataforma_org_specs_router import _BASE, _alvo
from app.routers.studio_agents_router import get_studio_definition_store_dep, http_error
from app.routers.studio_conteudo_router import get_spec_validacao_dep, ler_org_specs
from app.stores.errors import NotFound
from app.stores.onboarding_sessoes import OnboardingStore
from app.studio.especificacoes_service import ConfigValidacao

logger = logging.getLogger(__name__)

router = make_router(tier="platform", guard=require_platform_admin, tags=["onboarding"])

#: Where the owner goes after an apply: a dry conversation in evaluation mode, then the go-live decision (a human act).
PROXIMO_PASSO = "modo_avaliacao"
#: The interviewer is a studio agent of the STAFF org (the platform org); the conversation is its.
ENTREVISTADOR = "onboarding-imob"


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
    #: What the live interview says about the item (``respondido`` / ``pendente`` / ``proposto`` / ``recusado`` / ``aberto``);
    #: ``None`` when no interview exists for this company.
    entrevista: str | None = None


class SessaoOut(BaseModel):
    id: UUID
    conversation_id: UUID
    criada_em: datetime
    #: Event count of the ledger: the tab polls this + the items, so a new answer shows without a reload.
    eventos: int
    resumo_apresentado: bool
    aplicada: bool


class OnboardingOut(BaseModel):
    agent_key: str
    operacoes: list[str]
    itens: list[ItemOut]
    progresso: dict[str, Any]
    proximo_passo: str = PROXIMO_PASSO
    sessao: SessaoOut | None = None


class ConversaOut(BaseModel):
    sessao_id: UUID
    conversation_id: UUID
    agent_key: str


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


@router.get(f"{_BASE}/{{org_id}}/onboarding", response_model=OnboardingOut)
def get_onboarding(
    key: str, product: str, org_id: UUID,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
    grants: GrantStore = Depends(get_grant_store_dep),
    config: ConfigValidacao = Depends(get_spec_validacao_dep),
    onboarding: OnboardingStore = Depends(get_onboarding_store_dep),
) -> OnboardingOut:
    alvo, _ = _alvo(store, grants, ctx, key, product, org_id)
    valores = valores_armazenados(ler_org_specs(store, alvo, key, config))
    sessao = onboarding.ultima_sessao(org_id, key, product)
    eventos = onboarding.eventos(sessao.id) if sessao else []
    estados = estado_dos_itens(eventos)
    ops = ap.operacoes_de(valores.get("operacoes_atendidas"))
    if estados.get(9, {}).get("estado") == RESPONDIDO:
        ops = ops | ap.operacoes_de(estados[9]["valor"])
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
        if sessao is not None:
            est = estados.get(i.n, {}).get("estado", ABERTO)
            if est == RESPONDIDO:
                respondidos[i.n] = True
        itens.append(ItemOut(
            n=i.n, bloco=i.bloco, nivel=i.nivel, titulo=i.titulo, pergunta=i.pergunta, destino=f"{d.kind}:{d.alvo}",
            padrao=i.padrao, quando=list(i.quando), estado=estado,
            entrevista=estados.get(i.n, {}).get("estado", ABERTO) if sessao is not None else None,
        ))
    return OnboardingOut(
        agent_key=key, operacoes=sorted(ops), itens=itens, progresso=ap.progresso(ops or None, respondidos),
        sessao=None if sessao is None else SessaoOut(
            id=sessao.id, conversation_id=sessao.conversation_id, criada_em=sessao.created_at, eventos=len(eventos),
            resumo_apresentado=any(e.event_type == "resumo_apresentado" for e in eventos),
            aplicada=any(e.event_type == "aplicacao_executada" for e in eventos),
        ),
    )


@router.post(f"{_BASE}/{{org_id}}/onboarding/conversa", response_model=ConversaOut, status_code=201)
def post_conversa(
    key: str, product: str, org_id: UUID,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep),
    grants: GrantStore = Depends(get_grant_store_dep),
    conversas=Depends(get_conversation_store_dep),
    onboarding: OnboardingStore = Depends(get_onboarding_store_dep),
) -> ConversaOut:
    """Start the interview of ``org_id``: one conversation of the interviewer agent in the STAFF's own org, bound to the
    company. The staff then talks to it where Studio chats run (``/api/conversations/{id}/messages``)."""
    _, grant = _alvo(store, grants, ctx, key, product, org_id)  # the same gate as every other onboarding route
    try:
        agente = store.get_agent(ctx.org_id, ENTREVISTADOR)
    except NotFound as exc:
        raise http_error(409, "entrevistador_nao_configurado", "O agente entrevistador (onboarding-imob) não existe nesta organização.") from exc
    if not agente.ativo:
        raise http_error(409, "entrevistador_desligado", "O agente entrevistador está desligado.")
    ativa = store.get_active_version(agente.org_id, agente.id)
    if ativa is None:
        raise http_error(409, "entrevistador_sem_versao", "O agente entrevistador não tem versão publicada.")
    conversa = conversas.create(ctx.org_id, agente.id, ctx.user_id, titulo=f"Onboarding {product}", version_id=ativa.id)
    sessao = onboarding.criar_sessao(
        ctx.org_id, conversa.id, alvo_org_id=org_id, agent_key=key, product=product, grant_id=grant.id, created_by=ctx.user_id,
    )
    logger.info("onboarding.conversa org=%s agent=%s sessao=%s", org_id, key, sessao.id)
    return ConversaOut(sessao_id=sessao.id, conversation_id=conversa.id, agent_key=ENTREVISTADOR)


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
    rel = aplicar_na_org(
        store=store, grants=grants, ctx=ctx, key=key, product=product, org_id=org_id, respostas=payload.respostas,
        importados=frozenset(payload.importados), confirmados=frozenset(payload.confirmados), config=config, sw=sw,
    )
    logger.info("onboarding.aplicar org=%s agent=%s aplicados=%d recusados=%d", org_id, key, rel.aplicados, rel.recusados)
    return RelatorioOut(
        itens=[ItemRelatorioOut(**vars(i)) for i in rel.itens], aplicados=rel.aplicados, recusados=rel.recusados,
        obrigatorios_faltando=rel.obrigatorios_faltando,
    )
