"""Leads-lite -- a WhatsApp-fed funnel of people, as an L1 seed organ.

One lead = a person who reached out (usually by WhatsApp) and where they are in the funnel. Stages and origins
are DATA the product supplies (`LeadsConfig`); a lead is fully CRUD-able; the card order inside a stage is
fractional (`domain.pipeline.ordering`) so a drag is one write. Formalizes three divergent product copies
(social-wiring `leads`, orbity `leads`, igig `lead`) -- KB § PATTERNS/backend/leads-organ.md.

Mount it from a product:

    config = LeadsConfig(
        stages=[LeadStage("lead", "Lead"), LeadStage("atendimento", "Atendimento"), ...],
        origins=[LeadOrigin("whatsapp", "WhatsApp"), LeadOrigin("instagram", "Instagram"), ...],
    )
    sql = leads_migration("monica")                                    # -> migrations/0NN_leads.sql
    store = build_leads_store(admin_client, schema="monica")
    service = LeadsService(store, config)
    app.include_router(create_leads_router(store_factory=lambda: store, get_current_user_org=auth, config=config))
    inbox_router = create_whatsapp_inbox_router(..., on_new_chat=service.upsert_from_whatsapp)
"""
from .config import LeadOrigin, LeadsConfig, LeadStage, Stage
from .errors import LeadConflictError, LeadsError
from .guards import leads_guard_probes
from .router import create_leads_router
from .service import ORPHAN_LABEL, ORPHAN_STAGE, LeadsService, WhatsAppChatLike, present
from .sql import LEADS_MIGRATION_HEADER, leads_migration, leads_table_ddl
from .store import FakeLeadsStore, LeadFilters, LeadsStore, parse_search
from .supabase_store import SupabaseLeadsStore, build_leads_store

__all__ = [
    "FakeLeadsStore",
    "LEADS_MIGRATION_HEADER",
    "LeadConflictError",
    "LeadFilters",
    "LeadOrigin",
    "LeadStage",
    "LeadsConfig",
    "LeadsError",
    "LeadsService",
    "LeadsStore",
    "ORPHAN_LABEL",
    "ORPHAN_STAGE",
    "Stage",
    "SupabaseLeadsStore",
    "WhatsAppChatLike",
    "build_leads_store",
    "create_leads_router",
    "leads_guard_probes",
    "leads_migration",
    "leads_table_ddl",
    "parse_search",
    "present",
]
