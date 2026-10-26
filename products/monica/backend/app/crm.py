"""Monica's CRM vocabulary: the funnel (stages) and where leads come from (origins).

Both are DATA the leads organ takes (`LeadsConfig`) -- the columns are plain TEXT, so editing these lists never
needs a migration. Leads on a stage removed from here are not hidden: the board shows them under "Sem etapa".
"""
from __future__ import annotations

from noctusai_lib.domain.leads import LeadOrigin, LeadsConfig, LeadStage

LEADS_CONFIG = LeadsConfig(
    stages=[
        LeadStage("lead", "Lead"),
        LeadStage("atendimento", "Atendimento"),
        LeadStage("negociacao", "Negociação"),
        LeadStage("fechado", "Fechado"),
    ],
    origins=[
        LeadOrigin("whatsapp", "WhatsApp"),
        LeadOrigin("instagram", "Instagram"),
        LeadOrigin("indicacao", "Indicação"),
        LeadOrigin("outro", "Outro"),
    ],
    whatsapp_origin="whatsapp",
)
