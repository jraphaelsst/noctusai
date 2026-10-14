"""`contracts_migration(cfg, schema)` -- the contracts DDL for a product's schema.

One re-runnable migration body composed from `noctusai_lib.domain.sql_templates` (same conventions
as `finance_migration` / `parties_migration`):

- `org_id UUID NOT NULL` on every table; RLS enabled; an `authenticated` SELECT policy on
  `org_id = (SELECT <cfg.org_id_expr>)` plus the literal-named `service_role_bypass`. The backend
  writes through the service-role client, so no authenticated write policy exists.
- Forward-only and idempotent (`IF NOT EXISTS`, `DROP POLICY IF EXISTS` first): the chain replay
  applies a new file twice.
- Every child row names its parent through a composite FK `(parent_id, org_id)`, so a row can never
  point into another org even through the service role. `party_id` / `item_id` get the same
  composite FK when `cfg.with_parties` / `cfg.with_items`.
- ALL money is integer cents (`*_cents BIGINT`); percentages are basis points (`*_bp`, 450 = 4.5%).
- When `cfg.finance_entries_table` exists, its `source` CHECK is widened to admit `'contracts'`
  (guarded by `to_regclass`, so the migration also runs before finance is mounted).

Prerequisite (not created here): `public.current_org_id_for(text)` (core 070).
"""
from __future__ import annotations

from noctusai_lib.domain.finance.types import EntrySource
from noctusai_lib.domain._organ_common import org_rls
from noctusai_lib.domain.sql_templates import set_search_path

from .config import ContractsConfig
from .types import (
    AttachmentKind, BillingFrequency, BillingKind, BillingModel, ContractStatus, ReadjustmentIndex,
    SignatureStatus, VersionKind, values,
)

CONTRACTS_TABLES: tuple[str, ...] = (
    "contracts", "contract_lines", "contract_versions", "contract_billings", "contract_usage", "contract_attachments",
)


def _in(enum_cls) -> str:
    return ", ".join(f"'{v}'" for v in values(enum_cls))


def _tables(cfg: ContractsConfig, s: str) -> list[str]:
    o = cfg.org_id_expr
    t = {n: cfg.table(n) for n in CONTRACTS_TABLES}
    party_fk = (f",\n    FOREIGN KEY (party_id, org_id) REFERENCES {s}.{cfg.parties_table}(id, org_id)"
                if cfg.with_parties else "")
    item_fk = (f",\n    FOREIGN KEY (org_id, item_id) REFERENCES {s}.{cfg.items_table}(org_id, id)"
               if cfg.with_items else "")
    contracts = f"""-- Contracts: one commercial agreement with a party; the billing model decides how it turns into receivables.
CREATE TABLE IF NOT EXISTS {s}.{t['contracts']} (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL,
    number                  TEXT,
    title                   TEXT NOT NULL CHECK (length(btrim(title)) > 0),
    party_id                UUID,
    party_name              TEXT,
    party_doc               TEXT,
    status                  TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ({_in(ContractStatus)})),
    billing_model           TEXT NOT NULL CHECK (billing_model IN ({_in(BillingModel)})),
    amount_cents            BIGINT NOT NULL DEFAULT 0 CHECK (amount_cents >= 0),
    frequency               TEXT CHECK (frequency IS NULL OR frequency IN ({_in(BillingFrequency)})),
    installments_count      INTEGER CHECK (installments_count IS NULL OR installments_count BETWEEN 1 AND 120),
    due_day                 INTEGER CHECK (due_day IS NULL OR due_day BETWEEN 1 AND 31),
    first_due_date          DATE,
    next_period_on          DATE,
    start_date              DATE,
    end_date                DATE,
    auto_renew              BOOLEAN NOT NULL DEFAULT false,
    renewal_months          INTEGER NOT NULL DEFAULT 12 CHECK (renewal_months BETWEEN 1 AND 120),
    retainer_minutes        INTEGER CHECK (retainer_minutes IS NULL OR retainer_minutes >= 0),
    excess_rate_cents       BIGINT CHECK (excess_rate_cents IS NULL OR excess_rate_cents >= 0),
    readjustment_index      TEXT NOT NULL DEFAULT 'none' CHECK (readjustment_index IN ({_in(ReadjustmentIndex)})),
    readjustment_percent_bp INTEGER CHECK (readjustment_percent_bp IS NULL OR readjustment_percent_bp BETWEEN 0 AND 100000),
    readjustment_every_months INTEGER NOT NULL DEFAULT 12 CHECK (readjustment_every_months BETWEEN 1 AND 120),
    last_readjusted_on      DATE,
    notice_days             INTEGER NOT NULL DEFAULT 0 CHECK (notice_days BETWEEN 0 AND 365),
    penalty_cents           BIGINT NOT NULL DEFAULT 0 CHECK (penalty_cents >= 0),
    penalty_bp              INTEGER NOT NULL DEFAULT 0 CHECK (penalty_bp BETWEEN 0 AND 10000),
    penalty_applied_cents   BIGINT CHECK (penalty_applied_cents IS NULL OR penalty_applied_cents >= 0),
    document_body           TEXT,
    version_n               INTEGER NOT NULL DEFAULT 1 CHECK (version_n >= 1),
    activated_at            TIMESTAMPTZ,
    suspended_at            TIMESTAMPTZ,
    suspension_reason       TEXT,
    terminated_on           DATE,
    termination_reason      TEXT,
    signature_provider      TEXT,
    signature_external_id   TEXT,
    signature_status        TEXT NOT NULL DEFAULT 'none' CHECK (signature_status IN ({_in(SignatureStatus)})),
    signed_at               TIMESTAMPTZ,
    source_quote_id         TEXT,
    notes                   TEXT,
    created_by              UUID,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, org_id),
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date){party_fk}
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['contracts']}_number ON {s}.{t['contracts']} (org_id, lower(number)) WHERE number IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['contracts']}_signature ON {s}.{t['contracts']} (signature_provider, signature_external_id) WHERE signature_external_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['contracts']}_quote ON {s}.{t['contracts']} (org_id, source_quote_id) WHERE source_quote_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_{t['contracts']}_org_status ON {s}.{t['contracts']} (org_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_{t['contracts']}_org_party ON {s}.{t['contracts']} (org_id, party_id) WHERE party_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_{t['contracts']}_due ON {s}.{t['contracts']} (next_period_on) WHERE status = 'active';
"""
    lines = f"""-- Services / items billed by the contract. `amount_cents` of the contract is the sum of its lines when it has any.
CREATE TABLE IF NOT EXISTS {s}.{t['contract_lines']} (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL,
    contract_id      UUID NOT NULL,
    position         INTEGER NOT NULL DEFAULT 0,
    item_id          UUID,
    description      TEXT NOT NULL CHECK (length(btrim(description)) > 0),
    quantity         INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 1),
    unit_price_cents BIGINT NOT NULL CHECK (unit_price_cents >= 0),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (contract_id, org_id) REFERENCES {s}.{t['contracts']}(id, org_id) ON DELETE CASCADE{item_fk}
);
CREATE INDEX IF NOT EXISTS idx_{t['contract_lines']}_contract ON {s}.{t['contract_lines']} (org_id, contract_id, position);
"""
    versions = f"""-- Versions / amendments: every change to the terms is a new row (v1 = the initial terms), append-only.
CREATE TABLE IF NOT EXISTS {s}.{t['contract_versions']} (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    contract_id UUID NOT NULL,
    version_n   INTEGER NOT NULL CHECK (version_n >= 1),
    kind        TEXT NOT NULL CHECK (kind IN ({_in(VersionKind)})),
    summary     TEXT,
    changes     JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    snapshot    JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    effective_on DATE,
    created_by  UUID,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (contract_id, version_n),
    CHECK (jsonb_typeof(changes) = 'object' AND jsonb_typeof(snapshot) = 'object'),
    FOREIGN KEY (contract_id, org_id) REFERENCES {s}.{t['contracts']}(id, org_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_{t['contract_versions']}_contract ON {s}.{t['contract_versions']} (org_id, contract_id, version_n);
"""
    billings = f"""-- What each contract already billed (one row per finance receivable). UNIQUE (contract, period, kind) is the idempotency floor.
CREATE TABLE IF NOT EXISTS {s}.{t['contract_billings']} (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    contract_id  UUID NOT NULL,
    period_key   TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'fixed' CHECK (kind IN ({_in(BillingKind)})),
    entry_id     UUID,
    source_ref   TEXT NOT NULL,
    amount_cents BIGINT NOT NULL CHECK (amount_cents >= 0),
    due_date     DATE NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (contract_id, period_key, kind),
    FOREIGN KEY (contract_id, org_id) REFERENCES {s}.{t['contracts']}(id, org_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_{t['contract_billings']}_contract ON {s}.{t['contract_billings']} (org_id, contract_id, due_date);
"""
    usage = f"""-- Retainer usage log (minutes worked per month); the excess over the franchise is billed in arrears.
CREATE TABLE IF NOT EXISTS {s}.{t['contract_usage']} (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    contract_id  UUID NOT NULL,
    period_month DATE NOT NULL CHECK (period_month = date_trunc('month', period_month)::date),
    minutes      INTEGER NOT NULL CHECK (minutes > 0),
    description  TEXT,
    created_by   UUID,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (contract_id, org_id) REFERENCES {s}.{t['contracts']}(id, org_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_{t['contract_usage']}_contract ON {s}.{t['contract_usage']} (org_id, contract_id, period_month);
"""
    attachments = f"""-- Attachments (the signed scan, annexes). Objects live in the PRIVATE bucket; `storage_path` is server-generated.
CREATE TABLE IF NOT EXISTS {s}.{t['contract_attachments']} (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    contract_id  UUID NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'other' CHECK (kind IN ({_in(AttachmentKind)})),
    storage_path TEXT NOT NULL,
    filename     TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes   BIGINT NOT NULL CHECK (size_bytes >= 0),
    uploaded_by  UUID,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (contract_id, org_id) REFERENCES {s}.{t['contracts']}(id, org_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_{t['contract_attachments']}_contract ON {s}.{t['contract_attachments']} (org_id, contract_id, created_at);
"""
    return [f"{ddl}\n{org_rls(s, t[name], o, grants=True, authenticated_select=name != 'contracts')}" for name, ddl in (
        ("contracts", contracts), ("contract_lines", lines), ("contract_versions", versions),
        ("contract_billings", billings), ("contract_usage", usage), ("contract_attachments", attachments),
    )]


def _finance_source_widening(cfg: ContractsConfig, s: str) -> str:
    """Admit `source = 'contracts'` on the finance entries table (the CHECK is generated from `EntrySource`)."""
    table = cfg.finance_entries_table
    allowed = ", ".join(f"'{v}'" for v in values(EntrySource))
    return f"""-- Finance entries admit source='contracts' (guarded: no-op while the finance organ is not mounted in this schema).
DO $contracts_src$
BEGIN
    IF to_regclass('{s}.{table}') IS NOT NULL THEN
        ALTER TABLE {s}.{table} DROP CONSTRAINT IF EXISTS {table}_source_check;
        ALTER TABLE {s}.{table} ADD CONSTRAINT {table}_source_check CHECK (source IN ({allowed}));
    END IF;
END
$contracts_src$;"""


def contracts_migration(cfg: ContractsConfig, schema: str) -> str:
    """The whole contracts DDL for `schema`, as one re-runnable migration body."""
    if not schema or not schema.strip():
        raise ValueError("contracts_migration requires a non-empty schema")
    sections = [
        "-- Contracts organ -- generated by noctusai_lib.domain.contracts.sql (do not hand-edit)",
        f"{set_search_path(schema)};",
        *_tables(cfg, schema),
    ]
    if cfg.finance_entries_table:
        sections.append(_finance_source_widening(cfg, schema))
    return "\n\n".join(sections) + "\n"


__all__ = ["CONTRACTS_TABLES", "contracts_migration"]
