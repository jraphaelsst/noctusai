"""
Monica -- CRM of Monica Tangerino's psychoanalysis practice (future ERP).

Run with: uvicorn app.main:app --reload --port 8020

Everything domain-shaped is a SEED organ mounted here, no product-local re-implementation:

* leads (`mount_leads`)            -- funnel + list, stages/origins from `app/crm.py`
* WhatsApp connections + inbox     -- `app/routers/whatsapp_router.py` (QR lines, conversations, webhook);
                                       each new inbound number becomes a lead, every message refreshes its card
* contexto                         -- `app/routers/contexto_router.py`, proxy to the agents org specs
* finance (`mount_finance`)        -- the future ERP side (hidden behind `status_pagina`)
* clients (`mount_clients`)        -- patients: sessions, weekly slots, charges booked into finance, manual
                                       payments; a lead entering `fechado` becomes a patient (`app/crm.py`)
"""
from noctusai_seed import create_product_app
from noctusai_seed.organs import mount_clients, mount_finance, mount_leads
from app.config import settings
from app.dependencies import _db, get_admin_client, get_current_user_org
from app.crm import CLIENTS_CONFIG, LEADS_CONFIG
from app.rate_limit import limiter
from app.routers.contexto_router import router as contexto_router
from app.routers.whatsapp_router import router as whatsapp_router

app = create_product_app(
    name="Monica",
    schema="monica",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    # Fail the boot in a deploy without the Fernet key: the WhatsApp connections store refuses to persist
    # a WAHA api key in the clear (503), so the QR page would be dead.
    required_prod_config=["ENCRYPTION_KEY"],
    routers=[whatsapp_router, contexto_router],
    # Finance organ (accounts, entries, DRE, reconciliation): one-call seed mount. Tables `fin_*` are
    # rendered by `noctus.dev.render_organ_migration` (migrations/012_finance.sql). Gateway sync stays
    # 503-not-configured until a product supplies `get_charge_operations`.
    organs=[
        mount_finance(
            schema="monica",
            auth_dependency=get_current_user_org,
            get_admin_client=get_admin_client,
            get_core_client=lambda: _db.get_core_client(),
        ),
        mount_leads(auth_dependency=get_current_user_org, get_admin_client=get_admin_client, config=LEADS_CONFIG),
        # Patients (`/api/clients`): tables rendered by `noctus.dev.render_organ_migration` (018_clients.sql);
        # charged sessions are booked into the finance organ above.
        mount_clients(
            schema="monica",
            auth_dependency=get_current_user_org,
            get_admin_client=get_admin_client,
            get_core_client=lambda: _db.get_core_client(),
            config=CLIENTS_CONFIG,
        ),
    ],
    # Uncomment when this product registers AI features in
    # `app/services/ai_consent_features.py` (each product owns its
    # consent catalog — see KB § PATTERNS/lgpd.md § 9):
    # consent_features="app.services.ai_consent_features",
)
