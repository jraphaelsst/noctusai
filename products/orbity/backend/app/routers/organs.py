"""The seed organs Orbity mounts for money: finance + contracts (``/api/finance``, ``/api/contracts``).

* Finance -- entries (receivable / payable), settlements, categories, recurrences, DRE, cash flow, aging, reconciliation,
  exports. Reads for any member of the org, writes for ORG ADMINS of the selected org (``make_organ_auth``).
* Billing reminders -- ``/api/finance/reminders`` + the daily ``finance_billing_reminders`` job (12:00 America/Sao_Paulo):
  WhatsApp dunning before / on / after a receivable's due date, OFF per org until an admin enables it. The host side
  (client contact, payment link + PIX from ``billing_charges``, the preserved / cancelled veto, the org's own WhatsApp
  line) is ``app/services/billing_reminders.py``.
* Contracts -- billing models, versions/amendments/readjustment, suspend/terminate, billing preview, document, e-signature
  (optional: no ``get_signature`` => those routes answer 409 ``assinatura_nao_configurada``). Receivables are booked through
  ``OrbityContractsBilling`` (the ``get_billing`` seam): the seed ``SupabaseContractsBilling`` + the gateway state of each
  receivable, for the router AND the daily ``contracts_generate_billing`` job alike.
"""
from noctusai_seed.organs import mount_contracts, mount_finance, mount_finance_reminders

from app.billing import CONTRACTS_CFG, FINANCE_CFG, SCHEMA, get_gateway
from app.dependencies import get_admin_client, get_core_client, get_current_user_org
from app.services.billing_charges import OrbityContractsBilling
from app.services.billing_reminders import build_reminder_ports

finance_organ = mount_finance(
    schema=SCHEMA,
    auth_dependency=get_current_user_org,
    get_admin_client=get_admin_client,
    get_core_client=get_core_client,
    cfg=FINANCE_CFG,
)

contracts_organ = mount_contracts(
    schema=SCHEMA,
    auth_dependency=get_current_user_org,
    get_admin_client=get_admin_client,
    get_core_client=get_core_client,
    get_billing=lambda db: OrbityContractsBilling(db, gateway=get_gateway()),
    cfg=CONTRACTS_CFG,
)

reminders_organ = mount_finance_reminders(
    schema=SCHEMA,
    auth_dependency=get_current_user_org,
    get_admin_client=get_admin_client,
    get_core_client=get_core_client,
    get_ports=build_reminder_ports,
    cfg=FINANCE_CFG,
    hour=12,
)
