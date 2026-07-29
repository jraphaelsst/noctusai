"""
ERP Imobiliario — FastAPI Backend (seed framework)

Entry point for the API server.
Run with: uvicorn app.main:app --reload --port 8001
"""
from noctusai_seed import create_product_app
from app.config import settings
from app.rate_limit import limiter
from app.services.certidoes_service import recover_stuck_processando, schedule_all_pending_tjsp

# Import ALL domain routers (team, notificacoes, health provided by framework)
from app.routers import (
    matching, condominios, ativos, clientes, metas, profiles,
    atividades, action_log, funil,
    comissoes, portais, whatsapp,
    financeiro, propostas, documentos,
    locacoes, vistorias, relatorios, distribuicao,
    marketing, agenda, dimob, ai, gamificacao,
    chaves, portal_externo, site_imoveis, campo, analise_credito, filiais,
    bi, contratos, assinaturas, portal_cliente, manutencao,
    seguros, impostos, banco, emails,
    whatsapp_webhook, meta_api,
    storage, pdf, jobs, recorrencia,
    certidoes, matriculas, configuracoes,
    equipes, meta_periodos, metas_empresa,
    regras_pontuacao, metas_configuracao,
    metas_equipe, meta_fechamentos, meta_rankings, metas_digest, meta_eventos,
    vista_showcase,
    negociacoes,
    negociacoes_venda, processos_venda, pipeline_stages,
)


def _startup():
    """Recover stuck items and schedule pending TJSP on startup."""
    from app.dependencies import get_admin_client
    admin_db = get_admin_client()
    recover_stuck_processando(admin_db)
    schedule_all_pending_tjsp(admin_db)


# `"auth"` in `standard_routers` below mounts `/api/auth/{login,me,logout}`
# + `/api/settings/api-tokens` via the seed's bare
# `noctusai_seed.routers._build_auth_router(deps, settings, product_name,
# version)` -> `create_auth_router(deps, settings)` (NO `api_token_resolver`
# / `legacy_jwt_resolver` overrides) — erp-httponly-cookie-session-2026-07
# roadmap, Slice 2. This is the SIMPLER of the two mount shapes
# `create_auth_router`'s docstring documents (contrast
# `products/social-wiring/backend/app/main.py`'s direct factory call),
# correct here because, unlike social-wiring on day one:
#   (a) ERP has no REAL `ApiTokenResolver` to inject — no `pk_*` bearer
#       consumer exists anywhere in ERP's backend yet; the bare default
#       `FakeApiTokenResolver()` (always-empty) costs nothing today.
#   (b) ERP has no existing bridge to keep working on THESE 5 new
#       endpoints specifically — the 61 pre-existing routers stay on
#       `Depends(get_current_user_org)` (raw Supabase JWT bearer),
#       completely unaffected by this mount; passing a
#       `legacy_jwt_resolver` here would only matter if a caller needed
#       `/api/auth/me`/`/logout`/the api-token endpoints to ALSO accept a
#       legacy JWT bearer, which no caller does yet.
#   (c) ERP's routers are a flat list (not social-wiring's per-module
#       `register()` seam), so `standard_routers=[...]` is the
#       least-surprise, most-conventional shape here.
# `deps` (built internally by `create_product_app` via
# `create_database_module(settings, schema="erp")` + `create_dependencies`)
# already exposes `get_admin_client()` (erp-schema-scoped — where
# `erp.api_tokens`, migration 040, lives) + `get_core_client()`
# (`public`-scoped — where `_require_org_admin` reads `noctus_users`),
# exactly the surface `create_auth_router` needs — no adapter shim required.
# See `app/dependencies.py`'s "Cookie-session auth infra" section for the
# SEC-6 per-request-RLS-client seam (`get_current_user_org_unified`), which
# this mount does NOT need (login/me/logout never build a per-request RLS
# client; the api-token endpoints use the service-role clients above).
app = create_product_app(
    name="ERP Imobiliario",
    schema="erp",
    settings=settings,
    routers=[
        ativos.router,
        clientes.router,
        metas.router,
        profiles.router,
        atividades.router,
        action_log.router,
        funil.router,
        # ORDER MATTERS: these must precede `processos_venda.router`, whose
        # `GET /{processo_id}` would otherwise match `/api/processos-venda/etapas`
        # and try to load a processo with the id "etapas". FastAPI resolves in
        # registration order, so the literal path has to be registered first.
        pipeline_stages.funil_stages_router,
        pipeline_stages.processos_stages_router,
        negociacoes_venda.router,
        processos_venda.router,
        matching.router,
        condominios.router,
        comissoes.router,
        portais.router,
        whatsapp.router,
        financeiro.router,
        propostas.router,
        documentos.router,
        locacoes.router,
        vistorias.router,
        relatorios.router,
        distribuicao.router,
        chaves.router,
        portal_externo.router,
        site_imoveis.router,
        campo.router,
        analise_credito.router,
        filiais.router,
        marketing.router,
        agenda.router,
        dimob.router,
        ai.router,
        gamificacao.router,
        bi.router,
        contratos.router,
        assinaturas.router,
        portal_cliente.router,
        manutencao.router,
        seguros.router,
        impostos.router,
        banco.router,
        emails.router,
        whatsapp_webhook.router,
        meta_api.router,
        storage.router,
        pdf.router,
        jobs.router,
        recorrencia.router,
        certidoes.router,
        matriculas.router,
        configuracoes.router,
        equipes.router,
        meta_periodos.router,
        metas_empresa.router,
        regras_pontuacao.router,
        metas_configuracao.router,
        metas_equipe.router,
        meta_fechamentos.router,
        meta_rankings.router,
        metas_digest.router,
        meta_eventos.router,
        vista_showcase.router,
        negociacoes.router,
    ],
    version="0.2.0",
    limiter=limiter,
    lifespan_startup=_startup,
    standard_routers=["health", "notificacoes", "team", "llm", "ai_outputs", "ai_feedback", "status_paginas", "auth"],
    consent_features="app.services.ai_consent_features",
)
