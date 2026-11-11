"""The four market CRM presets — TODAY'S stage values, unchanged.

Expand phase of the CRM vertical seed (roadmap crm-cms-erp-vertical-seeds-2026-11,
W1-3). Each preset reproduces what its canon ships today so a later slice can
migrate the canon onto it without a data change:

  real estate  social-wiring migration 060 `ensure_default_pipeline_stages`
  SaaS         core migration 107 + `app/noc_funnel.py`
  agencies     orbity 005_crm_core.sql `seed_default_lead_stages`
  clinics      monica `app/crm.py` LEADS_CONFIG

NOC-REMEDIATE[crm-preset-to-canon]: each preset moves to its canon's
`app/market/crm_preset.py` when that canon migrates (W3-S2 SW, W3-C1 core,
W7-O orbity, W2-4 monica) and is deleted here then — the seed ships only the
mechanics (`presets.py`) and a generic preset — 2026-11-08.

Deltas vs today (deliberate, listed so the migration slice can act on them):
  * roles are the canonical ones: core `novo` -> `entrada`; SW `qualificacao`
    gains `qualificado`; monica `negociacao` gains `proposta`;
  * orbity colors were hex; mapped to the nearest design token;
  * orbity `Perdido` (`is_lost`) is a LOST STATUS, not a stage; `Fechado`
    (`is_won`) carries `ganho`.
"""
from __future__ import annotations

from noctusai_lib.domain.activities.types import KIND_CALL, KIND_MEETING, KIND_TASK, KIND_VISIT
from noctusai_lib.domain.activities.types import ActivityTypeSpec as A

from .defaults import StageDefault as S
from .presets import (
    ROLE_ENTRADA,
    ROLE_FINAL,
    ROLE_GANHO,
    ROLE_PROPOSTA,
    ROLE_PROPOSTA_ACEITE,
    ROLE_QUALIFICADO,
    ROLE_CONTATADO,
    ROLE_VISITA,
    CrmPreset,
    LostReasonDefault as L,
    OriginDefault as O,
)

#: Generic fallback for a market with no preset yet (the plan's stub).
GENERIC_PRESET = CrmPreset(
    market="generic",
    pipelines={
        "funil": (
            S("novo", "Novo", "secondary", ROLE_ENTRADA),
            S("qualificado", "Qualificado", "warning", ROLE_QUALIFICADO),
            S("proposta", "Proposta", "primary", ROLE_PROPOSTA),
            S("ganho", "Ganho", "success", ROLE_GANHO),
        )
    },
    lost_reasons=(L("preco", "Achou caro"), L("sem_resposta", "Parou de responder"), L("outro", "Outro motivo", True)),
    lead_origins=(O("site", "Site"), O("indicacao", "Indicação"), O("outro", "Outro")),
)

REAL_ESTATE_PRESET = CrmPreset(
    market="real_estate",
    pipelines={
        "funil": (
            S("qualificacao", "Qualificação", "secondary", ROLE_QUALIFICADO),
            S("visitas", "Visitas", "warning", ROLE_VISITA),
            S("proposta_recebida", "Proposta Recebida", "primary", ROLE_PROPOSTA),
            S("negociacao", "Negociação", "muted"),
            S("proposta_decisao", "Proposta Aceita/Rejeitada", "success", ROLE_PROPOSTA_ACEITE),
        ),
        "processos_venda": (
            S("elaboracao_contrato", "Elaboração do Contrato", "secondary"),
            S("analise_partes", "Análise das Partes", "secondary"),
            S("revisao_contrato", "Revisão do Contrato", "warning"),
            S("assinatura", "Assinatura", "warning"),
            S("financiamento_escritura", "Financiamento & Escritura", "primary"),
            S("finalizacao", "Finalização", "primary"),
            S("entrega_chaves", "Entrega das Chaves", "success"),
            S("nota_fiscal", "Nota Fiscal", "success", ROLE_FINAL),
        ),
    },
    lost_reasons=(L("preco", "Achou caro"), L("sem_resposta", "Parou de responder"), L("outro", "Outro motivo", True)),
    lead_origins=(
        O("whatsapp", "WhatsApp"),
        O("meta_lead_ads", "Meta Lead Ads"),
        O("zap", "ZAP Imóveis"),
        O("vivareal", "VivaReal"),
        O("olx", "OLX"),
        O("imovelweb", "Imovelweb"),
        O("site", "Site"),
        O("placa", "Placa"),
        O("indicacao", "Indicação"),
    ),
    # erp-imobiliario `atividades.py` kinds + the L2 consumers the plan unfreezes after the activities organ:
    # chaves (custody log), manutenção, campo (§4 rows Chaves / Manutenção / Campo).
    activity_types=(
        A("tarefa", "Tarefa", KIND_TASK),
        A("ligacao", "Ligação", KIND_CALL),
        A("reuniao", "Reunião", KIND_MEETING),
        A("visita", "Visita", KIND_VISIT),
        A("chave_retirada", "Retirada de chave", KIND_TASK),
        A("chave_devolucao", "Devolução de chave", KIND_TASK),
        A("manutencao", "Manutenção", KIND_TASK),
        A("campo", "Trabalho de campo", KIND_VISIT),
    ),
)

SAAS_PRESET = CrmPreset(
    market="saas",
    pipelines={
        "funil_noc": (
            S("novo", "Novo", "secondary", ROLE_ENTRADA),
            S("contatado", "Contatado", "primary", ROLE_CONTATADO),
            S("qualificado", "Qualificado", "warning", ROLE_QUALIFICADO),
            S("proposta", "Proposta", "success", ROLE_PROPOSTA),
        )
    },
    # core noc_funnel.LOST_REASONS, verbatim
    lost_reasons=(
        L("preco", "Achou caro"),
        L("sem_orcamento", "Sem orçamento agora"),
        L("outra_solucao", "Escolheu outra solução"),
        L("sem_resposta", "Parou de responder"),
        L("fora_do_perfil", "Não é o nosso cliente (fora do perfil)"),
        L("produto_indisponivel", "O produto ainda não está disponível"),
        L("outro", "Outro motivo", True),
    ),
    lead_origins=(O("site", "Site"), O("indicacao", "Indicação"), O("outbound", "Outbound")),
)

AGENCY_PRESET = CrmPreset(
    market="agency",
    pipelines={
        "comercial": (
            S("novo", "Novo", "muted", ROLE_ENTRADA),
            S("contato", "Contato", "primary"),
            S("qualificado", "Qualificado", "success", ROLE_QUALIFICADO),
            S("proposta", "Proposta", "warning", ROLE_PROPOSTA),
            S("negociacao", "Negociação", "warning"),
            S("fechado", "Fechado", "success", ROLE_GANHO),
        )
    },
    lost_reasons=(L("preco", "Achou caro"), L("sem_resposta", "Parou de responder"), L("outro", "Outro motivo", True)),
    lead_origins=(
        O("meta_lead_ads", "Meta Lead Ads"),
        O("site", "Site"),
        O("indicacao", "Indicação"),
        O("whatsapp", "WhatsApp"),
    ),
)

CLINIC_PRESET = CrmPreset(
    market="clinic",
    pipelines={
        "leads": (
            S("lead", "Lead", "destructive", ROLE_ENTRADA),
            S("atendimento", "Atendimento", "warning"),
            S("negociacao", "Negociação", "warning", ROLE_PROPOSTA),
            S("fechado", "Fechado", "success", ROLE_GANHO),
        )
    },
    lost_reasons=(L("sem_resposta", "Parou de responder"), L("outro", "Outro motivo", True)),
    lead_origins=(
        O("whatsapp", "WhatsApp"),
        O("instagram", "Instagram"),
        O("indicacao", "Indicação"),
        O("outro", "Outro"),
    ),
)

MARKET_PRESETS = {
    p.market: p
    for p in (GENERIC_PRESET, REAL_ESTATE_PRESET, SAAS_PRESET, AGENCY_PRESET, CLINIC_PRESET)
}
