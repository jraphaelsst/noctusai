-- ============================================================================
-- Migration 006 — Orbity Financial Core: contracts, expenses, revenues
--
-- WHY:
--   Implements the agency back-office financial organ: commercial contracts
--   with clients, recurring/installment expenses (AP), and monthly billing
--   records per client (AR / faturas-core).
--
--   agency_id (Orbity native) → org_id (noc tenancy).
--   RLS on every table via public.current_org_id() (SECURITY DEFINER,
--   trusted-table-derived — defined in 001_orbity.sql, codified in
--   004_rls_current_org_id.sql). NEVER USING(true), NEVER JWT/user_metadata.
--
--   NOTE [fiscal seam]: NOC-REMEDIATE[orbity-finance-fiscal]
--   Conexa/Asaas BR-fiscal gateway integration and PPR profit-sharing are
--   OUT OF SCOPE for this core migration. The seam attaches at:
--     • revenues.status — add 'gateway_pending' + external_id col when wiring
--     • expenses.category — join to expense_categories table when full AP lands
--   See KNOWLEDGE-BASE/CONTEXT/ABSORPTIONS/orbity/09-DEEPDIVE-FINANCIAL-MANAGEMENT.md
--   §5 for gateway validation rules and dunning config shape.
--
-- IDEMPOTENT: CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS.
--
-- SEARCH PATH: session-pinned to orbity, public (consistent with 001).
-- ============================================================================

SET search_path = orbity, public;


-- ============================================================================
-- 1. contracts — agency↔client commercial relationship
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.contracts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    client_id       UUID REFERENCES orbity.clients(id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    monthly_value   NUMERIC(12, 2) NOT NULL CHECK (monthly_value >= 0),
    billing_day     INT NOT NULL DEFAULT 1 CHECK (billing_day BETWEEN 1 AND 31),
    start_date      DATE NOT NULL,
    end_date        DATE,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'paused', 'ended')),
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS contracts_org_id_idx
  ON orbity.contracts (org_id);
CREATE INDEX IF NOT EXISTS contracts_org_client_idx
  ON orbity.contracts (org_id, client_id);
CREATE INDEX IF NOT EXISTS contracts_org_status_idx
  ON orbity.contracts (org_id, status);

DROP TRIGGER IF EXISTS trg_contracts_updated_at ON orbity.contracts;
CREATE TRIGGER trg_contracts_updated_at
  BEFORE UPDATE ON orbity.contracts
  FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

ALTER TABLE orbity.contracts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "contracts_select_own_org" ON orbity.contracts;
CREATE POLICY "contracts_select_own_org" ON orbity.contracts
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "contracts_insert_own_org" ON orbity.contracts;
CREATE POLICY "contracts_insert_own_org" ON orbity.contracts
  FOR INSERT TO authenticated
  WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "contracts_update_own_org" ON orbity.contracts;
CREATE POLICY "contracts_update_own_org" ON orbity.contracts
  FOR UPDATE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "contracts_delete_own_org" ON orbity.contracts;
CREATE POLICY "contracts_delete_own_org" ON orbity.contracts
  FOR DELETE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "contracts_service_role_all" ON orbity.contracts;
CREATE POLICY "contracts_service_role_all" ON orbity.contracts
  FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 2. expenses — recurring + installment costs (AP)
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.expenses (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    category            TEXT NOT NULL DEFAULT 'other',
    description         TEXT NOT NULL,
    amount              NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    due_date            DATE NOT NULL,
    paid                BOOLEAN NOT NULL DEFAULT false,
    paid_at             TIMESTAMPTZ,
    -- recurrence: none = one-off, monthly = recurring master,
    --             installment = multi-part purchase
    recurrence          TEXT NOT NULL DEFAULT 'none'
                        CHECK (recurrence IN ('none', 'monthly', 'installment')),
    -- installment fields (only set when recurrence = 'installment')
    installments_total  INT CHECK (installments_total IS NULL OR installments_total > 0),
    installment_n       INT CHECK (installment_n IS NULL OR installment_n > 0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS expenses_org_id_idx
  ON orbity.expenses (org_id);
CREATE INDEX IF NOT EXISTS expenses_org_due_date_idx
  ON orbity.expenses (org_id, due_date);
CREATE INDEX IF NOT EXISTS expenses_org_paid_idx
  ON orbity.expenses (org_id, paid);

DROP TRIGGER IF EXISTS trg_expenses_updated_at ON orbity.expenses;
CREATE TRIGGER trg_expenses_updated_at
  BEFORE UPDATE ON orbity.expenses
  FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

ALTER TABLE orbity.expenses ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "expenses_select_own_org" ON orbity.expenses;
CREATE POLICY "expenses_select_own_org" ON orbity.expenses
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "expenses_insert_own_org" ON orbity.expenses;
CREATE POLICY "expenses_insert_own_org" ON orbity.expenses
  FOR INSERT TO authenticated
  WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "expenses_update_own_org" ON orbity.expenses;
CREATE POLICY "expenses_update_own_org" ON orbity.expenses
  FOR UPDATE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "expenses_delete_own_org" ON orbity.expenses;
CREATE POLICY "expenses_delete_own_org" ON orbity.expenses
  FOR DELETE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "expenses_service_role_all" ON orbity.expenses;
CREATE POLICY "expenses_service_role_all" ON orbity.expenses
  FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 3. revenues — monthly billing records per client (AR / faturas-core)
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.revenues (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    client_id       UUID REFERENCES orbity.clients(id) ON DELETE SET NULL,
    contract_id     UUID REFERENCES orbity.contracts(id) ON DELETE SET NULL,
    reference_month DATE NOT NULL,   -- first day of the month (YYYY-MM-01)
    amount          NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'paid', 'overdue', 'canceled')),
    due_date        DATE NOT NULL,
    paid_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS revenues_org_id_idx
  ON orbity.revenues (org_id);
CREATE INDEX IF NOT EXISTS revenues_org_client_idx
  ON orbity.revenues (org_id, client_id);
CREATE INDEX IF NOT EXISTS revenues_org_month_idx
  ON orbity.revenues (org_id, reference_month);
CREATE INDEX IF NOT EXISTS revenues_org_status_idx
  ON orbity.revenues (org_id, status);

-- One revenue row per (org, client, reference_month) per contract — prevents
-- double-generation from the monthly closure procedure.
CREATE UNIQUE INDEX IF NOT EXISTS revenues_org_client_contract_month_ux
  ON orbity.revenues (org_id, client_id, COALESCE(contract_id, '00000000-0000-0000-0000-000000000000'), reference_month);

DROP TRIGGER IF EXISTS trg_revenues_updated_at ON orbity.revenues;
CREATE TRIGGER trg_revenues_updated_at
  BEFORE UPDATE ON orbity.revenues
  FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

ALTER TABLE orbity.revenues ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "revenues_select_own_org" ON orbity.revenues;
CREATE POLICY "revenues_select_own_org" ON orbity.revenues
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "revenues_insert_own_org" ON orbity.revenues;
CREATE POLICY "revenues_insert_own_org" ON orbity.revenues
  FOR INSERT TO authenticated
  WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "revenues_update_own_org" ON orbity.revenues;
CREATE POLICY "revenues_update_own_org" ON orbity.revenues
  FOR UPDATE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "revenues_delete_own_org" ON orbity.revenues;
CREATE POLICY "revenues_delete_own_org" ON orbity.revenues
  FOR DELETE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "revenues_service_role_all" ON orbity.revenues;
CREATE POLICY "revenues_service_role_all" ON orbity.revenues
  FOR ALL TO service_role USING (true) WITH CHECK (true);
