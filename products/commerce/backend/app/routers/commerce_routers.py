"""The commerce organ's routers, bound to this product's deps.

staff (`/api/commerce/*`, license-gated via `get_current_user_org`) · storefront
(`/api/storefront/*`, public, Host-resolved org) · payment webhook
(`/api/webhooks/payments/{gateway}/{org_id}`, verify-before-side-effect) · fiscal
(`/api/commerce/fiscal*`, invoices) + invoice webhook (`/api/webhooks/invoices/...`) ·
finance (`/api/finance/*`) · items (`/api/items/*`) · parties (`/api/parties/*`) · inventory
(`/api/inventory/*`) · purchasing (`/api/purchasing/*`) · quotes (`/api/quotes/*` staff, `/api/public/quotes/*` the
customer's signed link) · contracts (`/api/contracts/*`).
"""
from __future__ import annotations

from app import commerce_deps as deps
from app.commerce import CFG, CONTRACTS_CFG, PURCHASING_CFG, QUOTES_CFG, SCHEMA
from app.database import _db
from app.dependencies import get_admin_client, get_current_user_org
from app.rate_limit import limiter
from noctusai_lib.domain.commerce import commerce_staff_router, commerce_webhook_router, storefront_router
from noctusai_lib.domain.commerce.fiscal_router import commerce_fiscal_router, commerce_invoice_webhook_router
from noctusai_lib.domain.finance import FinanceConfig
from noctusai_lib.domain.parties import PartiesConfig
from noctusai_seed.organs import (
    ORGAN_REGISTRY,
    MountedOrgan,
    mount_finance,
    mount_contracts,
    mount_inventory,
    mount_items,
    mount_parties,
    mount_purchasing,
    mount_quotes,
)

staff_router = commerce_staff_router(
    CFG,
    auth_dependency=get_current_user_org,
    resolve_context=deps.resolve_context,
    get_db=deps.get_db,
    get_storage=deps.get_storage,
    get_cnpj_lookup=deps.get_cnpj_lookup,
    is_platform_admin=deps.is_platform_admin,
    admin_dependency=deps.require_org_admin,
    get_gateway=deps.get_gateway,
    get_finance=deps.get_finance,
    get_fulfillment=deps.get_fulfillment,
    get_email=deps.get_email_sender,
    on_paid_hooks=deps.ON_PAID_HOOKS,
    on_revoked_hooks=deps.ON_REVOKED_HOOKS,
)

public_router = storefront_router(
    CFG,
    get_db=deps.get_db,
    get_storage=deps.get_storage,
    get_gateway=deps.get_gateway,
    get_email=deps.get_email_sender,
    get_license_checker=deps.get_license_checker,
    get_link_secret=deps.get_link_secret,
    get_fulfillment=deps.get_fulfillment,  # stock holds at checkout (E6)
    rate_limit=limiter.limit,
)

payment_webhook_router = commerce_webhook_router(
    CFG,
    get_db=deps.get_db,
    get_gateway=deps.get_gateway,
    get_event_inbox=deps.get_event_inbox,
    get_fulfillment=deps.get_fulfillment,
    get_finance=deps.get_finance,
    get_email=deps.get_email_sender,
    on_paid_hooks=deps.ON_PAID_HOOKS,
    on_revoked_hooks=deps.ON_REVOKED_HOOKS,
    rate_limit=limiter.limit,
)

# Fiscal (invoices): settings + certificate + issue / cancel / documents, and the provider callback.
fiscal_router = commerce_fiscal_router(
    CFG,
    auth_dependency=get_current_user_org,
    admin_dependency=deps.require_org_admin,
    resolve_context=deps.resolve_context,
    get_db=deps.get_db,
    get_storage=deps.get_storage,
    get_jobs=deps.get_jobs,
    make_provider=deps.make_provider,
    platform_admin_dependency=deps.require_platform_admin,
)

invoice_webhook_router = commerce_invoice_webhook_router(
    CFG,
    get_db=deps.get_db,
    get_storage=deps.get_storage,
    get_event_inbox=deps.get_event_inbox,
    make_provider=deps.make_provider,
    get_webhook_token=deps.get_webhook_token,
    get_jobs=deps.get_jobs,
    get_mailer=deps.get_email_sender,
    rate_limit=limiter.limit,
)

fiscal_organ = MountedOrgan(
    name="commerce_fiscal",
    routers=(fiscal_router, invoice_webhook_router),
    max_body_path_overrides=dict(ORGAN_REGISTRY["commerce_fiscal"].max_body_path_overrides()),
)

# Finance (+ statement reconciliation) and items: one-call seed mounts (routers + upload body overrides).
finance_organ = mount_finance(
    schema=SCHEMA,
    auth_dependency=get_current_user_org,
    get_admin_client=get_admin_client,
    get_core_client=lambda: _db.get_core_client(),
    get_storage=deps.get_storage,
    get_charge_operations=deps.get_charge_operations,
    default_tax_regime=deps.default_tax_regime,
    cfg=FinanceConfig(schema=SCHEMA, with_parties=True),  # fin_entries.party_id (migration 023)
)

items_organ = mount_items(
    schema=SCHEMA,
    auth_dependency=get_current_user_org,
    get_admin_client=get_admin_client,
    get_core_client=lambda: _db.get_core_client(),
)

# ERP W1-W4: parties (suppliers / customers), inventory (warehouses, kardex), purchasing (PO -> receipt -> stock + payables),
# quotes (orçamentos; the accepted quote converts through `deps.get_quote_accept_handler`) and contracts (recurring billing
# over finance). Migrations are rendered by `noctus.dev.render_organ_migration`; the order is pinned by the wiring test.
parties_organ = mount_parties(
    schema=SCHEMA,
    auth_dependency=get_current_user_org,
    get_admin_client=get_admin_client,
    get_core_client=lambda: _db.get_core_client(),
    # A party referenced by a finance entry is archived, never hard-deleted (409 parceiro_em_uso).
    cfg=PartiesConfig(
        schema=SCHEMA,
        reference_tables=(
            ("fin_entries", "party_id"),
            ("pur_orders", "party_id"),
            ("quo_quotes", "party_id"),
            ("ctr_contracts", "party_id"),
        ),
    ),
)

inventory_organ = mount_inventory(
    schema=SCHEMA,
    auth_dependency=get_current_user_org,
    get_admin_client=get_admin_client,
    get_core_client=lambda: _db.get_core_client(),
)

# Purchasing: approval is org-scoped (`pur_approvers`, managed by org admins); receiving posts stock + the payable.
purchasing_organ = mount_purchasing(
    schema=SCHEMA,
    auth_dependency=get_current_user_org,
    get_admin_client=get_admin_client,
    get_core_client=lambda: _db.get_core_client(),
    cfg=PURCHASING_CFG,
)

# Quotes: staff routes + the customer's PUBLIC signed link (rate-limited, no login). The link secret is the commerce
# one (`COMMERCE_LINK_SECRET`; unset => send answers 503 `link_indisponivel`, never an unsigned link).
quotes_organ = mount_quotes(
    schema=SCHEMA,
    auth_dependency=get_current_user_org,
    get_admin_client=get_admin_client,
    get_core_client=lambda: _db.get_core_client(),
    cfg=QUOTES_CFG,
    get_link_secret=deps.get_link_secret,
    accept_url=deps.quote_accept_url,
    get_email=deps.get_email_sender,
    issuer=deps.quote_issuer,
    get_accept_handler=deps.get_quote_accept_handler,
    rate_limit=limiter.limit,
    client_ip=deps.quote_client_ip,
    is_org_active=deps.quote_org_is_active,
)

# Contracts: billing books receivables into finance; the `contracts_generate_billing` job rides on the seed scheduler
# (`app/scheduler.py`). E-signature is optional: no `get_signature` => its routes answer 409 `assinatura_nao_configurada`.
contracts_organ = mount_contracts(
    schema=SCHEMA,
    auth_dependency=get_current_user_org,
    get_admin_client=get_admin_client,
    get_core_client=lambda: _db.get_core_client(),
    get_storage=deps.get_storage,
    cfg=CONTRACTS_CFG,
)
