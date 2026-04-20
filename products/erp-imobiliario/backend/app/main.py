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
)


def _startup():
    """Recover stuck items and schedule pending TJSP on startup."""
    from app.dependencies import get_admin_client
    admin_db = get_admin_client()
    recover_stuck_processando(admin_db)
    schedule_all_pending_tjsp(admin_db)


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
    ],
    version="0.2.0",
    limiter=limiter,
    lifespan_startup=_startup,
)
