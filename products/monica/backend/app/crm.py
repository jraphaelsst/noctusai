"""Monica's CRM vocabulary: the funnel (stages), where leads come from (origins), and the patients organ's config.

Both stages and origins are DATA the leads organ takes (`LeadsConfig`) -- the columns are plain TEXT, so editing
these lists never needs a migration. Leads on a stage removed from here are not hidden: the board shows them under
"Sem etapa". Each stage carries a colour + a short tag (the badge the UI shows on a lead): a lead not yet talked to
is "Lead", one in conversation or negotiation is "Em atendimento", a closed one is "Paciente".

A lead entering `fechado` becomes a patient (`ClientsService.ensure_from_lead`, idempotent on the lead) through the
leads organ's generic `on_stage_entered` hook. A conversion failure is logged and surfaced on the lead payload by the
leads organ (`stage_hook_error`); it never rolls the lead move back.
"""
from __future__ import annotations

import logging

from noctusai_lib.domain.clients import ClientsConfig, ClientsService, build_clients_store
from noctusai_lib.domain.leads import LeadOrigin, LeadsConfig, LeadStage

logger = logging.getLogger(__name__)

#: the stage whose entry turns a lead into a patient
CONVERSION_STAGE = "fechado"

CLIENTS_CONFIG = ClientsConfig(
    noun_singular="Paciente",
    noun_plural="Pacientes",
    timezone="America/Sao_Paulo",
)


def convert_closed_lead(org_id: str, lead: dict, stage: str) -> None:
    """`LeadsConfig.on_stage_entered`: a lead entering `CONVERSION_STAGE` becomes a patient (once)."""
    if stage != CONVERSION_STAGE:
        return
    from app.dependencies import get_admin_client  # late: the hook runs per request, after app wiring

    client, created = ClientsService(build_clients_store(get_admin_client(), CLIENTS_CONFIG), CLIENTS_CONFIG).ensure_from_lead(
        org_id, lead
    )
    if created:
        logger.info("crm: lead %s converted into patient %s", lead.get("id"), client.get("id"))


LEADS_CONFIG = LeadsConfig(
    stages=[
        LeadStage("lead", "Lead", "destructive", "Lead"),
        LeadStage("atendimento", "Atendimento", "warning", "Em atendimento"),
        LeadStage("negociacao", "Negociação", "warning", "Em atendimento"),
        LeadStage(CONVERSION_STAGE, "Fechado", "success", "Paciente"),
    ],
    origins=[
        LeadOrigin("whatsapp", "WhatsApp"),
        LeadOrigin("instagram", "Instagram"),
        LeadOrigin("indicacao", "Indicação"),
        LeadOrigin("outro", "Outro"),
    ],
    whatsapp_origin="whatsapp",
    on_stage_entered=convert_closed_lead,
)
