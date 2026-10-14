"""`finance_migration(cfg, schema)` -- the finance DDL for a product's schema.

Emits EVERY CONTRACT §3.2 table (including the slice-D tables: statement
imports / lines and gateway sync, whose services land in wave 2) plus the
private attachments bucket, as one re-runnable migration body composed from
`noctusai_lib.domain.sql_templates` (same conventions as `commerce_migration`):

- `org_id UUID NOT NULL` on every table; RLS enabled; an `authenticated` SELECT
  policy on `org_id = (SELECT <cfg.org_id_expr>)` plus the literal-named
  `service_role_bypass`. The backend writes through the service-role client, so
  no authenticated write policy exists.
- Forward-only and idempotent: `IF NOT EXISTS`, `DROP POLICY IF EXISTS` before
  each `CREATE POLICY`, guarded `ALTER`s (the chain replay applies a new file twice).
- Money is integer cents (`BIGINT`: a company's totals outgrow R$ 21 M); dates
  that are calendar days are `DATE`, instants are `timestamptz`.
- Every tenant uniqueness is scoped `(org_id, ...)`: an external reference must
  never collide, or leak existence, across organs' tenants.

Prerequisites (not created here): `public.current_org_id()` (storage policies)
and `public.current_org_id_for(text)` (core 070; the default `org_id_expr`).
"""
from __future__ import annotations

from noctusai_lib.domain._organ_common import definer_search_path, org_rls
from noctusai_lib.domain.sql_templates import (
    private_org_bucket_sql,
    set_search_path,
)

from .config import FinanceConfig
from .types import (
    AccountKind,
    CategoryBehavior,
    CategoryDirection,
    DreLine,
    EntryDirection,
    EntrySource,
    EntryStatus,
    Frequency,
    LedgerDirection,
    LedgerOrigin,
    MatchStatus,
    SettlementKind,
    StatementFormat,
    TaxRegime,
    values,
)

#: Every organ table (unprefixed), in dependency order. The generator test and
#: the org-isolation test iterate this -- a table added here without RLS fails the build.
FINANCE_TABLES: tuple[str, ...] = (
    "accounts",
    "categories",
    "cost_centers",
    "recurrences",
    "entries",
    "statement_imports",
    "statement_lines",
    "settlements",
    "ledger",
    "attachments",
    "gateway_sync",
    "dre_settings",
)

#: Rows that are only ever appended (history): settlements and ledger rows are
#: NEVER deleted -- a reversal flips `reversed_*` and books opposite ledger rows.
APPEND_ONLY_TABLES: tuple[str, ...] = ("settlements", "ledger")

_NIL_UUID = "00000000-0000-0000-0000-000000000000"


SETTLE_RPC = "settle_entry_locked"
REVERSE_RPC = "reverse_settlement_locked"


def rpc_name(cfg: FinanceConfig, base: str) -> str:
    """The prefixed name of a finance RPC (`fin_` + `settle_entry_locked`), so two hosts' prefixes coexist."""
    return f"{cfg.table_prefix}{base}"


def _in(enum_cls) -> str:
    return ", ".join(f"'{v}'" for v in values(enum_cls))


def _in_lines(*, with_unclassified: bool) -> str:
    """The DRE line CHECK list: settings choices may only name a REAL line (never `unclassified`)."""
    lines = [v for v in values(DreLine) if with_unclassified or v != DreLine.UNCLASSIFIED.value]
    return ", ".join(f"'{v}'" for v in lines)


def _section(title: str, schema: str, table: str, body: str, org: str, *, extra: str = "") -> str:
    return f"-- {title}\n{body.strip()}\n{extra}{org_rls(schema, table, org)}"


def _tables(cfg: FinanceConfig, s: str) -> list[str]:
    o = cfg.org_id_expr
    p = cfg.table_prefix
    t = {name: f"{p}{name}" for name in FINANCE_TABLES}
    out: list[str] = []

    def add(title: str, name: str, body: str, *, extra: str = "") -> None:
        out.append(_section(title, s, t[name], body, o, extra=extra))

    add(
        "Accounts (bank / cash / gateway wallets). One gateway account per (org, gateway).",
        "accounts",
        f"""
CREATE TABLE IF NOT EXISTS {s}.{t['accounts']} (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                UUID NOT NULL,
    name                  TEXT NOT NULL,
    kind                  TEXT NOT NULL CHECK (kind IN ({_in(AccountKind)})),
    bank_code             TEXT,
    agency                TEXT,
    number                TEXT,
    opening_balance_cents BIGINT NOT NULL DEFAULT 0,
    opening_date          DATE,
    gateway               TEXT,
    active                BOOLEAN NOT NULL DEFAULT true,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (kind <> 'gateway' OR gateway IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['accounts']}_gateway ON {s}.{t['accounts']} (org_id, gateway)
    WHERE kind = 'gateway';
CREATE INDEX IF NOT EXISTS idx_{t['accounts']}_org ON {s}.{t['accounts']} (org_id);
""",
    )
    add(
        "Categories (tree). Unique (org, parent, lower(name)); defaults are seeded per org on first use.",
        "categories",
        f"""
CREATE TABLE IF NOT EXISTS {s}.{t['categories']} (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    parent_id   UUID REFERENCES {s}.{t['categories']}(id) ON DELETE RESTRICT,
    name        TEXT NOT NULL,
    direction   TEXT NOT NULL CHECK (direction IN ({_in(CategoryDirection)})),
    is_default  BOOLEAN NOT NULL DEFAULT false,
    active      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['categories']}_name ON {s}.{t['categories']}
    (org_id, COALESCE(parent_id, '{_NIL_UUID}'::uuid), lower(name));
CREATE INDEX IF NOT EXISTS idx_{t['categories']}_parent ON {s}.{t['categories']} (parent_id);
""",
        extra=f"""-- DRE mapping (CONTRACT §10.3 / §10.5): additive and re-runnable (tables created by an older generator gain the columns).
-- dre_line NULL = unclassified (shown in its own block with a warning); behavior NULL = the line's default;
-- is_das marks the category that holds the DAS payable (routed by the store's tax regime).
ALTER TABLE {s}.{t['categories']} ADD COLUMN IF NOT EXISTS dre_line TEXT
    CHECK (dre_line IN ({_in_lines(with_unclassified=True)}));
ALTER TABLE {s}.{t['categories']} ADD COLUMN IF NOT EXISTS behavior TEXT
    CHECK (behavior IN ({_in(CategoryBehavior)}));
ALTER TABLE {s}.{t['categories']} ADD COLUMN IF NOT EXISTS is_das BOOLEAN NOT NULL DEFAULT false;
""",
    )
    add(
        "Cost centers (code unique per org).",
        "cost_centers",
        f"""
CREATE TABLE IF NOT EXISTS {s}.{t['cost_centers']} (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, code)
);
""",
    )
    add(
        "Recurrences: `template` is the entry shape; generation is idempotent on (recurrence_id, due_date).",
        "recurrences",
        f"""
CREATE TABLE IF NOT EXISTS {s}.{t['recurrences']} (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    template    JSONB NOT NULL,
    frequency   TEXT NOT NULL CHECK (frequency IN ({_in(Frequency)})),
    next_date   DATE NOT NULL,
    end_date    DATE,
    active      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (end_date IS NULL OR end_date >= next_date OR active = false)
);
CREATE INDEX IF NOT EXISTS idx_{t['recurrences']}_due ON {s}.{t['recurrences']} (next_date) WHERE active;
""",
    )
    add(
        "Entries: payables / receivables. `overdue` is NEVER stored (computed on read). "
        "`settled_cents` is derived from unreversed settlements.",
        "entries",
        f"""
CREATE TABLE IF NOT EXISTS {s}.{t['entries']} (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL,
    direction            TEXT NOT NULL CHECK (direction IN ({_in(EntryDirection)})),
    status               TEXT NOT NULL DEFAULT 'open' CHECK (status IN ({_in(EntryStatus)})),
    description          TEXT NOT NULL,
    counterparty_name    TEXT,
    counterparty_doc     TEXT,
    category_id          UUID REFERENCES {s}.{t['categories']}(id) ON DELETE RESTRICT,
    cost_center_id       UUID REFERENCES {s}.{t['cost_centers']}(id) ON DELETE RESTRICT,
    expected_account_id  UUID REFERENCES {s}.{t['accounts']}(id) ON DELETE RESTRICT,
    competence_month     DATE NOT NULL CHECK (EXTRACT(DAY FROM competence_month) = 1),
    due_date             DATE NOT NULL,
    amount_cents         BIGINT NOT NULL CHECK (amount_cents > 0),
    settled_cents        BIGINT NOT NULL DEFAULT 0 CHECK (settled_cents >= 0 AND settled_cents <= amount_cents),
    source               TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ({_in(EntrySource)})),
    source_ref           TEXT,
    recurrence_id        UUID REFERENCES {s}.{t['recurrences']}(id) ON DELETE SET NULL,
    installment_group_id UUID,
    installment_n        INTEGER,
    installment_total    INTEGER,
    notes                TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (installment_group_id IS NULL AND installment_n IS NULL AND installment_total IS NULL)
        OR (installment_group_id IS NOT NULL AND installment_n BETWEEN 1 AND installment_total
            AND installment_total >= 2)
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['entries']}_source_ref ON {s}.{t['entries']} (org_id, source, source_ref)
    WHERE source_ref IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['entries']}_recurrence_due ON {s}.{t['entries']} (recurrence_id, due_date)
    WHERE recurrence_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['entries']}_installment ON {s}.{t['entries']} (installment_group_id, installment_n)
    WHERE installment_group_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_{t['entries']}_org_due ON {s}.{t['entries']} (org_id, due_date);
CREATE INDEX IF NOT EXISTS idx_{t['entries']}_org_status ON {s}.{t['entries']} (org_id, status, due_date);
CREATE INDEX IF NOT EXISTS idx_{t['entries']}_org_competence ON {s}.{t['entries']} (org_id, competence_month);
CREATE INDEX IF NOT EXISTS idx_{t['entries']}_category ON {s}.{t['entries']} (category_id);
""",
    )
    add(
        "Statement imports (slice D service). sha256 unique per account: re-importing a file is a 409.",
        "statement_imports",
        f"""
CREATE TABLE IF NOT EXISTS {s}.{t['statement_imports']} (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    account_id    UUID NOT NULL REFERENCES {s}.{t['accounts']}(id) ON DELETE RESTRICT,
    format        TEXT NOT NULL CHECK (format IN ({_in(StatementFormat)})),
    filename      TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    period_start  DATE,
    period_end    DATE,
    imported_by   UUID,
    at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, sha256)
);
CREATE INDEX IF NOT EXISTS idx_{t['statement_imports']}_org ON {s}.{t['statement_imports']} (org_id, at DESC);
""",
    )
    add(
        "Statement lines (slice D service). `ledger_id` FK is added after the ledger exists (cycle).",
        "statement_lines",
        f"""
CREATE TABLE IF NOT EXISTS {s}.{t['statement_lines']} (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL,
    import_id            UUID NOT NULL REFERENCES {s}.{t['statement_imports']}(id) ON DELETE CASCADE,
    account_id           UUID NOT NULL REFERENCES {s}.{t['accounts']}(id) ON DELETE RESTRICT,
    posted_on            DATE NOT NULL,
    amount_cents         BIGINT NOT NULL CHECK (amount_cents <> 0),
    description          TEXT NOT NULL DEFAULT '',
    fitid                TEXT NOT NULL,
    match_status         TEXT NOT NULL DEFAULT 'unmatched' CHECK (match_status IN ({_in(MatchStatus)})),
    ledger_id            UUID,
    suggested_entry_id   UUID REFERENCES {s}.{t['entries']}(id) ON DELETE SET NULL,
    UNIQUE (account_id, fitid)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['statement_lines']}_ledger ON {s}.{t['statement_lines']} (ledger_id)
    WHERE ledger_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_{t['statement_lines']}_import ON {s}.{t['statement_lines']} (import_id);
CREATE INDEX IF NOT EXISTS idx_{t['statement_lines']}_org_status ON {s}.{t['statement_lines']} (org_id, match_status);
""",
    )
    add(
        "Settlements: payments / refunds against an entry. NEVER deleted -- a reversal sets reversed_* "
        "and books opposite ledger rows.",
        "settlements",
        f"""
CREATE TABLE IF NOT EXISTS {s}.{t['settlements']} (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL,
    entry_id          UUID NOT NULL REFERENCES {s}.{t['entries']}(id) ON DELETE RESTRICT,
    account_id        UUID NOT NULL REFERENCES {s}.{t['accounts']}(id) ON DELETE RESTRICT,
    kind              TEXT NOT NULL CHECK (kind IN ({_in(SettlementKind)})),
    settled_on        DATE NOT NULL,
    amount_cents      BIGINT NOT NULL CHECK (amount_cents > 0),
    fee_cents         BIGINT NOT NULL DEFAULT 0 CHECK (fee_cents >= 0),
    method            TEXT,
    external_ref      TEXT,
    statement_line_id UUID REFERENCES {s}.{t['statement_lines']}(id) ON DELETE SET NULL,
    created_by        UUID,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    reversed_at       TIMESTAMPTZ,
    reversed_by       UUID,
    reversal_reason   TEXT,
    CHECK ((reversed_at IS NULL) = (reversal_reason IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['settlements']}_external ON {s}.{t['settlements']} (org_id, kind, external_ref)
    WHERE external_ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_{t['settlements']}_entry ON {s}.{t['settlements']} (entry_id);
CREATE INDEX IF NOT EXISTS idx_{t['settlements']}_org_date ON {s}.{t['settlements']} (org_id, settled_on);
""",
    )
    add(
        "Ledger (append-only): the money that actually moved on an account. Transfers = two rows "
        "sharing transfer_group. A reversal row points at the row it reverses.",
        "ledger",
        f"""
CREATE TABLE IF NOT EXISTS {s}.{t['ledger']} (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    account_id     UUID NOT NULL REFERENCES {s}.{t['accounts']}(id) ON DELETE RESTRICT,
    occurred_on    DATE NOT NULL,
    direction      TEXT NOT NULL CHECK (direction IN ({_in(LedgerDirection)})),
    amount_cents   BIGINT NOT NULL CHECK (amount_cents > 0),
    origin         TEXT NOT NULL CHECK (origin IN ({_in(LedgerOrigin)})),
    settlement_id  UUID REFERENCES {s}.{t['settlements']}(id) ON DELETE RESTRICT,
    transfer_group UUID,
    reverses_id    UUID REFERENCES {s}.{t['ledger']}(id) ON DELETE RESTRICT,
    description    TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (origin <> 'transfer' OR transfer_group IS NOT NULL),
    CHECK (origin NOT IN ('settlement', 'fee') OR settlement_id IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['ledger']}_settlement_origin ON {s}.{t['ledger']} (settlement_id, origin)
    WHERE settlement_id IS NOT NULL AND reverses_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_{t['ledger']}_reverses ON {s}.{t['ledger']} (reverses_id)
    WHERE reverses_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_{t['ledger']}_account_date ON {s}.{t['ledger']} (org_id, account_id, occurred_on);
CREATE INDEX IF NOT EXISTS idx_{t['ledger']}_transfer ON {s}.{t['ledger']} (transfer_group)
    WHERE transfer_group IS NOT NULL;
""",
        extra=f"""DO $fin_fk$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = '{t['statement_lines']}_ledger_id_fkey' AND conrelid = '{s}.{t['statement_lines']}'::regclass
    ) THEN
        ALTER TABLE {s}.{t['statement_lines']}
            ADD CONSTRAINT {t['statement_lines']}_ledger_id_fkey
            FOREIGN KEY (ledger_id) REFERENCES {s}.{t['ledger']}(id) ON DELETE SET NULL;
    END IF;
END
$fin_fk$;
""",
    )
    add(
        "Attachments: private bucket objects, keys `<org_id>/entries/<entry_id>/<id>.<ext>` (server-generated).",
        "attachments",
        f"""
CREATE TABLE IF NOT EXISTS {s}.{t['attachments']} (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    entry_id      UUID NOT NULL REFERENCES {s}.{t['entries']}(id) ON DELETE CASCADE,
    storage_path  TEXT NOT NULL,
    filename      TEXT NOT NULL,
    content_type  TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL CHECK (size_bytes >= 0),
    uploaded_by   UUID,
    at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_{t['attachments']}_entry ON {s}.{t['attachments']} (entry_id);
""",
    )
    add(
        "Gateway sync cursor (slice D service): one row per gateway account.",
        "gateway_sync",
        f"""
CREATE TABLE IF NOT EXISTS {s}.{t['gateway_sync']} (
    account_id      UUID PRIMARY KEY REFERENCES {s}.{t['accounts']}(id) ON DELETE CASCADE,
    org_id          UUID NOT NULL,
    cursor          TEXT,
    last_synced_at  TIMESTAMPTZ,
    last_error      TEXT
);
CREATE INDEX IF NOT EXISTS idx_{t['gateway_sync']}_org ON {s}.{t['gateway_sync']} (org_id);
""",
    )
    add(
        "DRE settings (CONTRACT §10.5): ONE row per org. The per-store mapping of every provisional accounting "
        "choice is DATA so an accountant changes it without touching money records. `choice_meta` is "
        "`{<choice>: {provisional, confirmed_by, confirmed_at, note}}` -- absent = provisional (the default).",
        "dre_settings",
        f"""
CREATE TABLE IF NOT EXISTS {s}.{t['dre_settings']} (
    id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                     UUID NOT NULL UNIQUE,
    tax_regime                 TEXT NOT NULL DEFAULT 'unknown' CHECK (tax_regime IN ({_in(TaxRegime)})),
    das_split_irpj_csll        BOOLEAN NOT NULL DEFAULT false,
    das_irpj_csll_share_bps    INTEGER NOT NULL DEFAULT 0 CHECK (das_irpj_csll_share_bps BETWEEN 0 AND 10000),
    gateway_fee_line           TEXT NOT NULL DEFAULT 'selling_expenses' CHECK (gateway_fee_line IN ({_in_lines(with_unclassified=False)})),
    anticipation_fee_line      TEXT NOT NULL DEFAULT 'financial_expenses' CHECK (anticipation_fee_line IN ({_in_lines(with_unclassified=False)})),
    chargeback_line            TEXT NOT NULL DEFAULT 'deductions' CHECK (chargeback_line IN ({_in_lines(with_unclassified=False)})),
    chargeback_fee_line        TEXT NOT NULL DEFAULT 'selling_expenses' CHECK (chargeback_fee_line IN ({_in_lines(with_unclassified=False)})),
    installment_interest_line  TEXT NOT NULL DEFAULT 'gross_revenue' CHECK (installment_interest_line IN ({_in_lines(with_unclassified=False)})),
    choice_meta                JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    updated_by                 UUID,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);
""",
    )
    return out


def _rpcs(cfg: FinanceConfig, s: str) -> str:
    """Row-locked settle / reverse (closes `NOC-REMEDIATE[finance-settle-overpay-race]`).

    PostgREST has no multi-statement transaction, so "read the balance, check it, insert" from Python lets two
    concurrent settlements both pass the check. These functions take `SELECT ... FOR UPDATE` on the ENTRY row and
    re-derive the balance from the settlement ROWS (never the cached `settled_cents`) inside that lock, so the
    second caller waits and then sees the first one's row. They return jsonb (`status` + payload) instead of
    raising for a business refusal; the Python side keeps writing the ledger rows and re-deriving the entry total
    (both idempotent), exactly as before."""
    t = {name: f"{cfg.table_prefix}{name}" for name in FINANCE_TABLES}
    settle, reverse = rpc_name(cfg, SETTLE_RPC), rpc_name(cfg, REVERSE_RPC)
    return f"""-- Settle under a row lock: the balance is checked and the settlement inserted in ONE transaction.
CREATE OR REPLACE FUNCTION {s}.{settle}(p_org_id UUID, p_entry_id UUID, p_row JSONB) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
{definer_search_path(s)}
AS $fn$
DECLARE
    v_entry   {s}.{t['entries']}%ROWTYPE;
    v_row     {s}.{t['settlements']}%ROWTYPE;
    v_settled BIGINT;
    v_amount  BIGINT := (p_row->>'amount_cents')::BIGINT;
    v_kind    TEXT := p_row->>'kind';
BEGIN
    IF v_amount IS NULL OR v_amount <= 0 THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'valor_invalido');
    END IF;
    IF v_kind IS NULL OR v_kind NOT IN ('payment', 'refund') THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'tipo_invalido');
    END IF;
    SELECT * INTO v_entry FROM {s}.{t['entries']} WHERE id = p_entry_id AND org_id = p_org_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'not_found');
    END IF;
    IF v_entry.status = 'cancelled' THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'lancamento_cancelado');
    END IF;
    SELECT COALESCE(SUM(CASE WHEN kind = 'payment' THEN amount_cents ELSE -amount_cents END), 0) INTO v_settled
        FROM {s}.{t['settlements']} WHERE entry_id = p_entry_id AND reversed_at IS NULL;
    IF v_kind = 'payment' AND v_amount > v_entry.amount_cents - v_settled THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'baixa_excede_saldo');
    END IF;
    IF v_kind = 'refund' AND v_amount > v_settled THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'estorno_excede_pago');
    END IF;
    INSERT INTO {s}.{t['settlements']}
        SELECT * FROM jsonb_populate_record(
            NULL::{s}.{t['settlements']},
            jsonb_set(jsonb_set(p_row, '{{org_id}}', to_jsonb(p_org_id::text)), '{{entry_id}}', to_jsonb(p_entry_id::text))
        )
        RETURNING * INTO v_row;
    RETURN jsonb_build_object('status', 'ok', 'settlement', to_jsonb(v_row));
END;
$fn$;
REVOKE ALL ON FUNCTION {s}.{settle}(UUID, UUID, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION {s}.{settle}(UUID, UUID, JSONB) TO service_role;

-- Reverse under the same lock: stamp the settlement and book the opposite ledger rows atomically.
CREATE OR REPLACE FUNCTION {s}.{reverse}(p_org_id UUID, p_settlement_id UUID, p_reason TEXT, p_user UUID, p_on DATE) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
{definer_search_path(s)}
AS $fn$
DECLARE
    v_st      {s}.{t['settlements']}%ROWTYPE;
    v_entry   {s}.{t['entries']}%ROWTYPE;
    v_settled BIGINT;
    v_after   BIGINT;
BEGIN
    SELECT * INTO v_st FROM {s}.{t['settlements']} WHERE id = p_settlement_id AND org_id = p_org_id;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'not_found');
    END IF;
    SELECT * INTO v_entry FROM {s}.{t['entries']} WHERE id = v_st.entry_id AND org_id = p_org_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'settlement % has no entry in org %', p_settlement_id, p_org_id USING ERRCODE = 'P0002';
    END IF;
    SELECT * INTO v_st FROM {s}.{t['settlements']} WHERE id = p_settlement_id;
    IF v_st.reversed_at IS NOT NULL THEN
        RETURN jsonb_build_object('status', 'already_reversed');
    END IF;
    SELECT COALESCE(SUM(CASE WHEN kind = 'payment' THEN amount_cents ELSE -amount_cents END), 0) INTO v_settled
        FROM {s}.{t['settlements']} WHERE entry_id = v_entry.id AND reversed_at IS NULL;
    v_after := CASE WHEN v_st.kind = 'payment' THEN v_settled - v_st.amount_cents ELSE v_settled + v_st.amount_cents END;
    IF v_after < 0 OR v_after > v_entry.amount_cents THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'baixa_com_estorno');
    END IF;
    UPDATE {s}.{t['settlements']}
        SET reversed_at = now(), reversed_by = p_user, reversal_reason = p_reason
        WHERE id = p_settlement_id RETURNING * INTO v_st;
    INSERT INTO {s}.{t['ledger']} (org_id, account_id, occurred_on, direction, amount_cents, origin, description, settlement_id, reverses_id)
        SELECT l.org_id, l.account_id, p_on, CASE l.direction WHEN 'in' THEN 'out' ELSE 'in' END, l.amount_cents, l.origin,
               'Estorno: ' || COALESCE(l.description, ''), l.settlement_id, l.id
        FROM {s}.{t['ledger']} l
        WHERE l.settlement_id = p_settlement_id AND l.reverses_id IS NULL
          AND NOT EXISTS (SELECT 1 FROM {s}.{t['ledger']} r WHERE r.reverses_id = l.id);
    RETURN jsonb_build_object('status', 'ok', 'settlement', to_jsonb(v_st));
END;
$fn$;
REVOKE ALL ON FUNCTION {s}.{reverse}(UUID, UUID, TEXT, UUID, DATE) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION {s}.{reverse}(UUID, UUID, TEXT, UUID, DATE) TO service_role;"""


def finance_migration(cfg: FinanceConfig, schema: str) -> str:
    """The whole finance DDL for `schema`, as one re-runnable migration body.

    Includes the 12 `FINANCE_TABLES` and the private attachments bucket with
    per-org object RLS. Prerequisites: see the module docstring.
    """
    if not schema or not schema.strip():
        raise ValueError("finance_migration requires a non-empty schema")
    sections = [
        "-- Finance organ -- generated by noctusai_lib.domain.finance.sql (do not hand-edit)",
        f"{set_search_path(schema)};",
        *_tables(cfg, schema),
        _rpcs(cfg, schema),
        private_org_bucket_sql(
            cfg.bucket,
            comment="Private finance attachments bucket; object RLS keys on the org_id first path segment.",
        ),
    ]
    return "\n\n".join(sections) + "\n"


__all__ = ["APPEND_ONLY_TABLES", "FINANCE_TABLES", "REVERSE_RPC", "SETTLE_RPC", "finance_migration", "rpc_name"]
