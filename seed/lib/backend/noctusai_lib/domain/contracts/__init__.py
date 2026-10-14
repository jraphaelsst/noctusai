"""Contracts -- agreements with a party that turn into receivables, as an L1 seed organ (roadmap E2/W4).

One contract = a party + lines (services / items) + a BILLING MODEL (the seam):

- `one_time`      a single receivable;
- `installments`  N receivables splitting the total (the last absorbs the remainder);
- `recurring`     monthly / quarterly / yearly at a due day, open-ended or until `end_date`;
- `retainer`      a monthly fee with a franchise of hours; usage beyond it is billed as EXCESS in arrears.

Status flow `draft -> active <-> suspended -> terminated | expired`; a vigente contract changes only by
AMENDMENT (every version kept with a `changes` diff), readjusts by a stored index choice + a typed
percentage (v1 fetches no index -- NOC-REMEDIATE[contracts-index-fetch] in `contracts.py`), terminates with
notice and a penalty, renders its own document and can go to e-signature through the seed's
`SignatureAdapter`. Money is integer cents; percentages are basis points.

Billing goes through `ContractsBilling` (Protocol + Fake + Real + factory) into the finance organ with
`source='contracts'`, `source_ref=<contract_id>:<period>`: idempotent by construction. The daily
`contracts_generate_billing` job is registered like `finance_generate_recurrences`.

Mount it from a product:

    cfg = ContractsConfig(schema="erp", with_parties=True, with_items=True)
    sql = contracts_migration(cfg, "erp")                      # -> migrations/0NN_contracts.sql
    app.include_router(make_contracts_router(cfg, auth_dependency, admin_dependency, resolve_context=...,
                                             get_db=..., get_billing=lambda db: make_contracts_billing("supabase", db=db, finance_cfg=FIN),
                                             get_signature=..., get_storage=...))
    register_contracts_billing(cfg, get_db=get_admin_client, get_billing=lambda db: make_contracts_billing(...))
    max_body_path_overrides[ATTACHMENT_UPLOAD_PATH_PATTERN] = ATTACHMENT_UPLOAD_MAX_BYTES

The quotes organ's accept seam creates a draft with `create_contract_from_quote(scope, ContractFromQuote(...))`.
"""
from . import attachments, billing_run, contracts, documents, schedule, signature
from .attachments import ATTACHMENT_UPLOAD_MAX_BYTES, ATTACHMENT_UPLOAD_PATH_PATTERN
from .billing import (
    ContractsBilling, FakeContractsBilling, NoopContractsBilling, SupabaseContractsBilling, make_contracts_billing,
)
from .billing_run import JOB_ID, contracts_generate_billing, register_contracts_billing
from .config import ContractsConfig, ContractsContext
from .documents import DocumentRenderer, brl, render_contract_text
from .errors import ContractsError
from .quotes import ContractFromQuote, QuoteLine, create_contract_from_quote
from .router import make_contracts_router
from .signature import handle_signature_webhook
from .sql import CONTRACTS_TABLES, contracts_migration
from .types import (
    BillingFrequency, BillingKind, BillingModel, ContractStatus, ReadjustmentIndex, SignatureStatus, VersionKind,
)

__all__ = [
    "ATTACHMENT_UPLOAD_MAX_BYTES", "ATTACHMENT_UPLOAD_PATH_PATTERN", "BillingFrequency", "BillingKind", "BillingModel",
    "CONTRACTS_TABLES", "ContractFromQuote", "ContractStatus", "ContractsBilling", "ContractsConfig", "ContractsContext",
    "ContractsError", "DocumentRenderer", "FakeContractsBilling", "JOB_ID", "NoopContractsBilling", "QuoteLine",
    "ReadjustmentIndex", "SignatureStatus", "SupabaseContractsBilling", "VersionKind", "attachments", "billing_run", "brl",
    "contracts", "contracts_generate_billing", "contracts_migration", "create_contract_from_quote", "documents",
    "handle_signature_webhook", "make_contracts_billing", "make_contracts_router", "register_contracts_billing",
    "render_contract_text", "schedule", "signature",
]
