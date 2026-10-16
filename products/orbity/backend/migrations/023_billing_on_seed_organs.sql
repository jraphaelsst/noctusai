-- ============================================================================
-- Migration 023 -- Orbity billing on the SEED organs (finance 019 + contracts 021)
--
-- WHY:
--   Orbity's product-local finance (006: contracts / expenses / revenues) never generated a charge, had no
--   gateway and no closure. The seed ships the organs for exactly this: contracts (billing run, terminate,
--   suspend) over finance (entries, settlements, DRE, cash flow), which own their OWN tables (ctr_* / fin_*)
--   -- there is no "organ over product tables" seam. So the rows MOVE onto them and 006's tables are retired
--   to *_legacy (kept, never dropped: this is financial history).
--
-- WHAT (all idempotent -- runs twice on a real Postgres):
--   1. clients: legal_name (Razao Social, NOT NULL, backfilled from name), document (CPF/CNPJ -- the gateway
--      refuses a customer without one), inactivated_at (the offboarding timestamp the cash-flow rule reads).
--   2. billing_charges -- the gateway state of ONE receivable (fin_entries row): queued / generating /
--      retrying / generated / failed / skipped + last error, the gateway charge id, the idempotency reference
--      sent to the gateway, the "kept after inactivation" flag and the pending gateway cancel.
--   3. payment_gateway_events -- the webhook idempotency inbox (seed `event_inbox_table_sql`, verbatim).
--   4. DATA MOVE, 1:1 and id-preserving (the owner's SMOKE-TEST rows included):
--        contracts -> ctr_contracts (+ initial version)    monthly_value -> recurring/monthly, cents
--        revenues  -> fin_entries (receivable) + billing_charges (+ ctr_contract_billings when it came from a
--                     contract, so the seed billing run never bills the same month twice) + settlement/ledger
--                     for the paid ones
--        expenses  -> fin_entries (payable) (+ settlement/ledger when paid)
--      The billing cursor (next_period_on) NEVER backfills the past: it is the first due day >= today, or the
--      month after the last migrated revenue, whichever is later.
--   5. views orbity.revenues / orbity.expenses over fin_entries, SECURITY INVOKER -- a read-only compatibility
--      surface so reports_service (aggregates paid revenues / expenses) keeps answering from the NEW ledger.
--      NOC-REMEDIATE[orbity-reports-on-fin-entries]: move reports_service onto fin_entries and drop the views.
--   6. RPC offboard_client -- the ATOMIC part of inactivating a client (cancel / keep each open charge + the
--      client row); RPC billing_reserve_charges -- claim queued charges (SKIP LOCKED) and RECOVER the ones stuck
--      in 'generating' after a worker crash.
-- ============================================================================

SET search_path = orbity, public;


-- ============================================================================
-- 1. clients
-- ============================================================================

ALTER TABLE orbity.clients ADD COLUMN IF NOT EXISTS legal_name TEXT;
ALTER TABLE orbity.clients ADD COLUMN IF NOT EXISTS document TEXT;
ALTER TABLE orbity.clients ADD COLUMN IF NOT EXISTS inactivated_at TIMESTAMPTZ;

UPDATE orbity.clients SET legal_name = name WHERE legal_name IS NULL OR btrim(legal_name) = '';
UPDATE orbity.clients SET inactivated_at = updated_at WHERE active = false AND inactivated_at IS NULL;
ALTER TABLE orbity.clients ALTER COLUMN legal_name SET NOT NULL;


-- ============================================================================
-- 2. billing_charges -- gateway state of one receivable
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.billing_charges (
    id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                       UUID NOT NULL,
    entry_id                     UUID NOT NULL UNIQUE REFERENCES orbity.fin_entries(id) ON DELETE CASCADE,
    client_id                    UUID REFERENCES orbity.clients(id) ON DELETE SET NULL,
    contract_id                  UUID,
    gateway                      TEXT,
    billing_method               TEXT,
    -- the idempotency / conciliation reference SENT to the gateway on every attempt ('orbity:<entry_id>')
    external_ref                 TEXT NOT NULL,
    external_id                  TEXT,
    invoice_url                  TEXT,
    pix_payload                  TEXT,
    generation_status            TEXT NOT NULL DEFAULT 'queued'
                                 CHECK (generation_status IN ('queued', 'generating', 'retrying', 'generated', 'failed', 'skipped')),
    generation_attempts          INTEGER NOT NULL DEFAULT 0,
    last_error                   TEXT,
    last_attempt_at              TIMESTAMPTZ,
    next_attempt_at              TIMESTAMPTZ,
    locked_at                    TIMESTAMPTZ,
    locked_by                    TEXT,
    generated_at                 TIMESTAMPTZ,
    preserved_after_deactivation BOOLEAN NOT NULL DEFAULT false,
    preserved_at                 TIMESTAMPTZ,
    gateway_cancel_status        TEXT CHECK (gateway_cancel_status IS NULL OR gateway_cancel_status IN ('pending', 'done', 'failed')),
    gateway_cancel_error         TEXT,
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, external_ref)
);

CREATE INDEX IF NOT EXISTS billing_charges_org_client_idx ON orbity.billing_charges (org_id, client_id);
CREATE INDEX IF NOT EXISTS billing_charges_queue_idx
    ON orbity.billing_charges (generation_status, next_attempt_at)
    WHERE generation_status IN ('queued', 'retrying');
CREATE INDEX IF NOT EXISTS billing_charges_gateway_cancel_idx
    ON orbity.billing_charges (gateway_cancel_status) WHERE gateway_cancel_status = 'pending';

DROP TRIGGER IF EXISTS trg_billing_charges_updated_at ON orbity.billing_charges;
CREATE TRIGGER trg_billing_charges_updated_at
    BEFORE UPDATE ON orbity.billing_charges
    FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

ALTER TABLE orbity.billing_charges ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "billing_charges_select_own_org" ON orbity.billing_charges;
CREATE POLICY "billing_charges_select_own_org" ON orbity.billing_charges
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('orbity')));

DROP POLICY IF EXISTS "service_role_bypass" ON orbity.billing_charges;
CREATE POLICY "service_role_bypass" ON orbity.billing_charges
    FOR ALL TO service_role USING (true) WITH CHECK (true);

GRANT SELECT ON orbity.billing_charges TO authenticated;
GRANT ALL ON orbity.billing_charges TO service_role;


-- ============================================================================
-- 3. payment_gateway_events -- webhook idempotency inbox (seed event_inbox_table_sql, verbatim)
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.payment_gateway_events (
    gateway     TEXT NOT NULL,
    event_id    TEXT NOT NULL,
    claimed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (gateway, event_id)
);
ALTER TABLE orbity.payment_gateway_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON orbity.payment_gateway_events;
CREATE POLICY "service_role_bypass" ON orbity.payment_gateway_events FOR ALL TO service_role USING (true) WITH CHECK (true);
GRANT ALL ON orbity.payment_gateway_events TO service_role;


-- ============================================================================
-- 4. DATA MOVE -- 006's tables -> the seed organs' tables (id-preserving, idempotent)
-- ============================================================================

-- 4a. retire the product-local tables (renamed, never dropped); a second run finds views/renamed tables and skips.
DO $retire$
BEGIN
    IF (SELECT c.relkind FROM pg_class c WHERE c.oid = to_regclass('orbity.contracts')) = 'r' THEN
        ALTER TABLE orbity.contracts RENAME TO contracts_legacy;
    END IF;
    IF (SELECT c.relkind FROM pg_class c WHERE c.oid = to_regclass('orbity.revenues')) = 'r' THEN
        ALTER TABLE orbity.revenues RENAME TO revenues_legacy;
    END IF;
    IF (SELECT c.relkind FROM pg_class c WHERE c.oid = to_regclass('orbity.expenses')) = 'r' THEN
        ALTER TABLE orbity.expenses RENAME TO expenses_legacy;
    END IF;
END
$retire$;

-- 4b. one cash account per org that has money history to carry ("Caixa (migrado do Orbity)").
DO $move_accounts$
BEGIN
    IF to_regclass('orbity.revenues_legacy') IS NOT NULL AND to_regclass('orbity.expenses_legacy') IS NOT NULL THEN
        INSERT INTO orbity.fin_accounts (id, org_id, name, kind)
        SELECT md5('orbity-legacy-cash:' || o.org_id::text)::uuid, o.org_id, 'Caixa (migrado do Orbity)', 'cash'
          FROM (
              SELECT org_id FROM orbity.revenues_legacy WHERE status = 'paid'
              UNION
              SELECT org_id FROM orbity.expenses_legacy WHERE paid
          ) o
        ON CONFLICT (id) DO NOTHING;
    END IF;
END
$move_accounts$;

-- 4c. contracts -> ctr_contracts (+ the initial version). monthly_value -> recurring/monthly in cents.
DO $move_contracts$
BEGIN
    IF to_regclass('orbity.contracts_legacy') IS NOT NULL THEN
        INSERT INTO orbity.ctr_contracts (
            id, org_id, title, party_id, party_name, party_doc, status, billing_model, amount_cents, frequency,
            due_day, first_due_date, next_period_on, start_date, end_date, activated_at, suspended_at,
            suspension_reason, terminated_on, termination_reason, notes, created_at, updated_at
        )
        SELECT
            l.id, l.org_id, COALESCE(NULLIF(btrim(l.title), ''), 'Contrato'), l.client_id,
            COALESCE(cl.legal_name, cl.name), NULLIF(regexp_replace(COALESCE(cl.document, ''), '\D', '', 'g'), ''),
            CASE WHEN l.status = 'ended' THEN 'terminated'
                 WHEN l.status = 'paused' THEN 'suspended'
                 WHEN round(l.monthly_value * 100) < 1 THEN 'draft'   -- a zero-value contract cannot bill: draft, never silently active
                 ELSE 'active' END,
            'recurring', GREATEST(round(l.monthly_value * 100)::bigint, 0), 'monthly',
            l.billing_day,
            (date_trunc('month', l.start_date)
                + (LEAST(l.billing_day, EXTRACT(DAY FROM (date_trunc('month', l.start_date) + interval '1 month' - interval '1 day'))::int) - 1) * interval '1 day')::date,
            CASE WHEN l.status = 'ended' OR round(l.monthly_value * 100) < 1 THEN NULL ELSE nx.next_on END,
            l.start_date,
            CASE WHEN l.end_date IS NULL OR l.end_date >= l.start_date THEN l.end_date END,
            CASE WHEN l.status IN ('active', 'paused', 'ended') AND round(l.monthly_value * 100) >= 1 THEN l.created_at END,
            CASE WHEN l.status = 'paused' THEN l.updated_at END,
            CASE WHEN l.status = 'paused' THEN 'Migrado do Orbity (contrato pausado)' END,
            CASE WHEN l.status = 'ended' THEN COALESCE(l.end_date, l.updated_at::date) END,
            CASE WHEN l.status = 'ended' THEN 'Migrado do Orbity (contrato encerrado)' END,
            l.notes, l.created_at, l.updated_at
          FROM orbity.contracts_legacy l
          LEFT JOIN orbity.clients cl ON cl.id = l.client_id
          LEFT JOIN LATERAL (
              -- the contract's due day inside a given month (clamped to short months)
              SELECT
                  (date_trunc('month', CURRENT_DATE)
                      + (LEAST(l.billing_day, EXTRACT(DAY FROM (date_trunc('month', CURRENT_DATE) + interval '1 month' - interval '1 day'))::int) - 1) * interval '1 day')::date AS this_month_on,
                  (date_trunc('month', CURRENT_DATE + interval '1 month')
                      + (LEAST(l.billing_day, EXTRACT(DAY FROM (date_trunc('month', CURRENT_DATE + interval '1 month') + interval '1 month' - interval '1 day'))::int) - 1) * interval '1 day')::date AS next_month_on,
                  (SELECT (date_trunc('month', max(r.reference_month) + interval '1 month')
                      + (LEAST(l.billing_day, EXTRACT(DAY FROM (date_trunc('month', max(r.reference_month) + interval '1 month') + interval '1 month' - interval '1 day'))::int) - 1) * interval '1 day')::date
                     FROM orbity.revenues_legacy r WHERE r.contract_id = l.id) AS after_last
          ) calc ON true
          -- the first due day >= today AND after the last migrated revenue: the past is never backfilled
          LEFT JOIN LATERAL (
              SELECT GREATEST(CASE WHEN calc.this_month_on >= CURRENT_DATE THEN calc.this_month_on ELSE calc.next_month_on END,
                              calc.after_last) AS next_on
          ) nx ON true
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO orbity.ctr_contract_versions (id, org_id, contract_id, version_n, kind, summary, changes, snapshot, effective_on, created_at)
        SELECT md5('orbity-legacy-contract-v1:' || c.id::text)::uuid, c.org_id, c.id, 1, 'initial',
               'Migrado do Orbity (termos iniciais)', '{}'::jsonb,
               jsonb_build_object('title', c.title, 'amount_cents', c.amount_cents, 'billing_model', c.billing_model,
                                  'due_day', c.due_day, 'party_id', c.party_id, 'status', c.status),
               c.start_date, c.created_at
          FROM orbity.ctr_contracts c
          JOIN orbity.contracts_legacy l ON l.id = c.id
        ON CONFLICT (contract_id, version_n) DO NOTHING;
    END IF;
END
$move_contracts$;

-- 4d. revenues -> fin_entries (receivable) + billing_charges (+ ctr_contract_billings) + settlement/ledger when paid.
DO $move_revenues$
BEGIN
    IF to_regclass('orbity.revenues_legacy') IS NOT NULL THEN
        INSERT INTO orbity.fin_entries (
            id, org_id, direction, status, description, counterparty_name, competence_month, due_date,
            amount_cents, settled_cents, source, source_ref, notes, created_at, updated_at
        )
        SELECT
            r.id, r.org_id, 'receivable',
            CASE r.status WHEN 'paid' THEN 'paid' WHEN 'canceled' THEN 'cancelled' ELSE 'open' END,
            CASE WHEN ct.id IS NOT NULL
                 THEN COALESCE(NULLIF(btrim(ct.title), ''), 'Contrato') || ' — ' || to_char(r.reference_month, 'MM/YYYY')
                 ELSE 'Mensalidade ' || to_char(r.reference_month, 'MM/YYYY') || COALESCE(' — ' || COALESCE(cl.legal_name, cl.name), '')
            END,
            COALESCE(cl.legal_name, cl.name),
            date_trunc('month', r.reference_month)::date, r.due_date,
            round(r.amount * 100)::bigint,
            CASE WHEN r.status = 'paid' THEN round(r.amount * 100)::bigint ELSE 0 END,
            CASE WHEN ct.id IS NOT NULL THEN 'contracts' ELSE 'manual' END,
            CASE WHEN ct.id IS NULL THEN NULL
                 WHEN r.dup_rank = 1 THEN r.contract_id::text || ':' || r.due_date::text
                 ELSE r.contract_id::text || ':' || r.due_date::text || '-' || r.dup_rank::text END,
            'Migrado do Orbity (receitas)', r.created_at, r.updated_at
          FROM (
              SELECT rl.*, row_number() OVER (PARTITION BY rl.org_id, rl.contract_id, rl.due_date ORDER BY rl.created_at, rl.id) AS dup_rank
                FROM orbity.revenues_legacy rl
          ) r
          LEFT JOIN orbity.clients cl ON cl.id = r.client_id
          LEFT JOIN orbity.ctr_contracts ct ON ct.id = r.contract_id AND ct.org_id = r.org_id
        ON CONFLICT (id) DO NOTHING;

        -- the contract-side record of every contract-born month, so the seed billing run never bills it again
        INSERT INTO orbity.ctr_contract_billings (id, org_id, contract_id, period_key, kind, entry_id, source_ref, amount_cents, due_date, created_at)
        SELECT md5('orbity-legacy-billing:' || e.id::text)::uuid, e.org_id, ct.id,
               substr(e.source_ref, length(ct.id::text) + 2), 'fixed', e.id, e.source_ref, e.amount_cents, e.due_date, e.created_at
          FROM orbity.revenues_legacy r
          JOIN orbity.fin_entries e ON e.id = r.id AND e.source = 'contracts'
          JOIN orbity.ctr_contracts ct ON ct.id = r.contract_id AND ct.org_id = r.org_id
        ON CONFLICT DO NOTHING;

        INSERT INTO orbity.billing_charges (id, org_id, entry_id, client_id, contract_id, external_ref, generation_status, last_error)
        SELECT md5('orbity-legacy-charge:' || r.id::text)::uuid, r.org_id, r.id, r.client_id, r.contract_id,
               'orbity:' || r.id::text, 'skipped', 'Receita migrada do Orbity: cobrança simples, sem gateway.'
          FROM orbity.revenues_legacy r
        ON CONFLICT DO NOTHING;

        INSERT INTO orbity.fin_settlements (id, org_id, entry_id, account_id, kind, settled_on, amount_cents, fee_cents, method, external_ref, created_at)
        SELECT md5('orbity-legacy-settlement:' || r.id::text)::uuid, r.org_id, r.id,
               md5('orbity-legacy-cash:' || r.org_id::text)::uuid, 'payment',
               COALESCE(r.paid_at::date, r.due_date), round(r.amount * 100)::bigint, 0, 'migrado',
               'orbity-legacy-revenue:' || r.id::text, COALESCE(r.paid_at, r.updated_at)
          FROM orbity.revenues_legacy r
         WHERE r.status = 'paid'
        ON CONFLICT DO NOTHING;

        INSERT INTO orbity.fin_ledger (id, org_id, account_id, occurred_on, direction, amount_cents, origin, settlement_id, description, created_at)
        SELECT md5('orbity-legacy-ledger:' || r.id::text)::uuid, r.org_id,
               md5('orbity-legacy-cash:' || r.org_id::text)::uuid, COALESCE(r.paid_at::date, r.due_date), 'in',
               round(r.amount * 100)::bigint, 'settlement', md5('orbity-legacy-settlement:' || r.id::text)::uuid,
               'Migrado do Orbity (receita paga)', COALESCE(r.paid_at, r.updated_at)
          FROM orbity.revenues_legacy r
         WHERE r.status = 'paid'
        ON CONFLICT DO NOTHING;
    END IF;
END
$move_revenues$;

-- 4e. expenses -> fin_entries (payable) + settlement/ledger when paid. No recurrence/installment GROUP is invented
--     (the legacy rows carry no group id): the numbers ride in the description, the category in the notes.
DO $move_expenses$
BEGIN
    IF to_regclass('orbity.expenses_legacy') IS NOT NULL THEN
        INSERT INTO orbity.fin_entries (
            id, org_id, direction, status, description, competence_month, due_date, amount_cents, settled_cents,
            source, notes, created_at, updated_at
        )
        SELECT
            x.id, x.org_id, 'payable', CASE WHEN x.paid THEN 'paid' ELSE 'open' END,
            x.description
                || CASE WHEN x.recurrence = 'installment' AND x.installment_n IS NOT NULL AND x.installments_total IS NOT NULL
                        THEN ' (parcela ' || x.installment_n || '/' || x.installments_total || ')' ELSE '' END,
            date_trunc('month', x.due_date)::date, x.due_date, round(x.amount * 100)::bigint,
            CASE WHEN x.paid THEN round(x.amount * 100)::bigint ELSE 0 END,
            'manual',
            'Migrado do Orbity (despesas). Categoria: ' || x.category || '; recorrência: ' || x.recurrence,
            x.created_at, x.updated_at
          FROM orbity.expenses_legacy x
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO orbity.fin_settlements (id, org_id, entry_id, account_id, kind, settled_on, amount_cents, fee_cents, method, external_ref, created_at)
        SELECT md5('orbity-legacy-settlement:' || x.id::text)::uuid, x.org_id, x.id,
               md5('orbity-legacy-cash:' || x.org_id::text)::uuid, 'payment',
               COALESCE(x.paid_at::date, x.due_date), round(x.amount * 100)::bigint, 0, 'migrado',
               'orbity-legacy-expense:' || x.id::text, COALESCE(x.paid_at, x.updated_at)
          FROM orbity.expenses_legacy x
         WHERE x.paid
        ON CONFLICT DO NOTHING;

        INSERT INTO orbity.fin_ledger (id, org_id, account_id, occurred_on, direction, amount_cents, origin, settlement_id, description, created_at)
        SELECT md5('orbity-legacy-ledger:' || x.id::text)::uuid, x.org_id,
               md5('orbity-legacy-cash:' || x.org_id::text)::uuid, COALESCE(x.paid_at::date, x.due_date), 'out',
               round(x.amount * 100)::bigint, 'settlement', md5('orbity-legacy-settlement:' || x.id::text)::uuid,
               'Migrado do Orbity (despesa paga)', COALESCE(x.paid_at, x.updated_at)
          FROM orbity.expenses_legacy x
         WHERE x.paid
        ON CONFLICT DO NOTHING;
    END IF;
END
$move_expenses$;


-- ============================================================================
-- 5. compatibility views (read-only) -- reports_service still aggregates `revenues` / `expenses`
-- ============================================================================

CREATE OR REPLACE VIEW orbity.revenues WITH (security_invoker = true) AS
SELECT
    e.id,
    e.org_id,
    bc.client_id,
    bc.contract_id,
    e.competence_month AS reference_month,
    (e.amount_cents / 100.0)::numeric(12, 2) AS amount,
    CASE
        WHEN e.status = 'paid' THEN 'paid'
        WHEN e.status = 'cancelled' THEN 'canceled'
        WHEN e.due_date < CURRENT_DATE THEN 'overdue'
        ELSE 'pending'
    END AS status,
    e.due_date,
    (SELECT max(s.created_at) FROM orbity.fin_settlements s
      WHERE s.entry_id = e.id AND s.kind = 'payment' AND s.reversed_at IS NULL) AS paid_at,
    e.created_at,
    e.updated_at
FROM orbity.fin_entries e
LEFT JOIN orbity.billing_charges bc ON bc.entry_id = e.id
WHERE e.direction = 'receivable';

CREATE OR REPLACE VIEW orbity.expenses WITH (security_invoker = true) AS
SELECT
    e.id,
    e.org_id,
    'other'::text AS category,
    e.description,
    (e.amount_cents / 100.0)::numeric(12, 2) AS amount,
    e.due_date,
    (e.status = 'paid') AS paid,
    (SELECT max(s.created_at) FROM orbity.fin_settlements s
      WHERE s.entry_id = e.id AND s.kind = 'payment' AND s.reversed_at IS NULL) AS paid_at,
    'none'::text AS recurrence,
    NULL::integer AS installments_total,
    NULL::integer AS installment_n,
    e.created_at,
    e.updated_at
FROM orbity.fin_entries e
WHERE e.direction = 'payable' AND e.status <> 'cancelled';

GRANT SELECT ON orbity.revenues TO authenticated, service_role;
GRANT SELECT ON orbity.expenses TO authenticated, service_role;


-- ============================================================================
-- 6. RPCs (service_role only)
-- ============================================================================

-- Claim up to p_limit queued/retrying charges (SKIP LOCKED: two workers never take the same row) after RECOVERING the
-- rows a crashed worker left in 'generating' (back to 'retrying' -- the gateway lookup by external_ref makes the retry
-- safe -- or 'failed' once the attempts are spent).
CREATE OR REPLACE FUNCTION orbity.billing_reserve_charges(p_limit INTEGER, p_worker TEXT, p_stale_minutes INTEGER DEFAULT 10, p_max_attempts INTEGER DEFAULT 5)
RETURNS SETOF orbity.billing_charges
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, orbity, pg_temp
AS $fn$
DECLARE
    v_limit INTEGER := GREATEST(1, LEAST(COALESCE(p_limit, 5), 25));
BEGIN
    UPDATE orbity.billing_charges
       SET generation_status = CASE WHEN generation_attempts >= p_max_attempts THEN 'failed' ELSE 'retrying' END,
           last_error = 'Processamento interrompido (worker parou no meio); ' ||
                        CASE WHEN generation_attempts >= p_max_attempts THEN 'tentativas esgotadas.' ELSE 'nova tentativa agendada.' END,
           next_attempt_at = CASE WHEN generation_attempts >= p_max_attempts THEN NULL ELSE now() END,
           locked_at = NULL,
           locked_by = NULL
     WHERE generation_status = 'generating'
       AND locked_at < now() - make_interval(mins => p_stale_minutes);

    RETURN QUERY
    WITH candidates AS (
        SELECT bc.id
          FROM orbity.billing_charges bc
          JOIN orbity.fin_entries e ON e.id = bc.entry_id
         WHERE bc.generation_status IN ('queued', 'retrying')
           AND COALESCE(bc.next_attempt_at, now()) <= now()
           AND e.status IN ('open', 'partial')
         ORDER BY COALESCE(bc.next_attempt_at, bc.created_at), bc.created_at, bc.id
         LIMIT v_limit
         FOR UPDATE OF bc SKIP LOCKED
    )
    UPDATE orbity.billing_charges b
       SET generation_status = 'generating',
           generation_attempts = b.generation_attempts + 1,
           last_attempt_at = now(),
           locked_at = now(),
           locked_by = COALESCE(p_worker, 'billing-worker')
      FROM candidates
     WHERE b.id = candidates.id
    RETURNING b.*;
END;
$fn$;
REVOKE ALL ON FUNCTION orbity.billing_reserve_charges(INTEGER, TEXT, INTEGER, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION orbity.billing_reserve_charges(INTEGER, TEXT, INTEGER, INTEGER) TO service_role;

-- Inactivate a client ATOMICALLY: every open receivable of the client is either cancelled or kept (flagged
-- preserved), and the client row goes inactive -- all or nothing. Every open charge not yet kept MUST be decided (the
-- dialog defaults to cancel); a partially paid charge cannot be cancelled (keep it). Re-runnable: a retry after a
-- later step failed finds nothing left to decide. The caller (the admin-only endpoint)
-- then terminates the contracts through the seed contracts organ and cancels the gateway charges listed back.
CREATE OR REPLACE FUNCTION orbity.offboard_client(p_org_id UUID, p_client_id UUID, p_cancel_entry_ids UUID[], p_preserve_entry_ids UUID[])
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, orbity, pg_temp
AS $fn$
DECLARE
    v_cancel    UUID[] := COALESCE(p_cancel_entry_ids, '{}'::uuid[]);
    v_preserve  UUID[] := COALESCE(p_preserve_entry_ids, '{}'::uuid[]);
    v_open      UUID[];
    v_cancelled INTEGER := 0;
    v_gateway   UUID[];
BEGIN
    PERFORM 1 FROM orbity.clients WHERE id = p_client_id AND org_id = p_org_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'client_not_found' USING ERRCODE = 'P0002';
    END IF;
    IF v_cancel && v_preserve THEN
        RAISE EXCEPTION 'charge_in_both_lists' USING ERRCODE = '22023';
    END IF;

    -- lock the open charges first (a webhook settling one of them waits for this transaction)
    PERFORM 1
      FROM orbity.billing_charges bc
      JOIN orbity.fin_entries e ON e.id = bc.entry_id
     WHERE bc.org_id = p_org_id AND bc.client_id = p_client_id AND e.org_id = p_org_id
       AND e.direction = 'receivable' AND e.status IN ('open', 'partial')
       FOR UPDATE OF e;

    SELECT COALESCE(array_agg(e.id), '{}'::uuid[]) INTO v_open
      FROM orbity.billing_charges bc
      JOIN orbity.fin_entries e ON e.id = bc.entry_id
     WHERE bc.org_id = p_org_id AND bc.client_id = p_client_id AND e.org_id = p_org_id
       AND e.direction = 'receivable' AND e.status IN ('open', 'partial')
       AND NOT bc.preserved_after_deactivation;   -- already decided (kept) by an earlier inactivation: nothing to ask again

    IF EXISTS (SELECT 1 FROM unnest(v_cancel || v_preserve) AS x(id) WHERE x.id <> ALL (v_open)) THEN
        RAISE EXCEPTION 'charge_not_open_for_client' USING ERRCODE = '22023';
    END IF;
    IF EXISTS (SELECT 1 FROM unnest(v_open) AS o(id) WHERE o.id <> ALL (v_cancel || v_preserve)) THEN
        RAISE EXCEPTION 'unresolved_charges' USING ERRCODE = '22023';
    END IF;

    UPDATE orbity.fin_entries e
       SET status = 'cancelled', updated_at = now()
     WHERE e.org_id = p_org_id AND e.id = ANY (v_cancel)
       AND NOT EXISTS (SELECT 1 FROM orbity.fin_settlements s WHERE s.entry_id = e.id AND s.reversed_at IS NULL);
    GET DIAGNOSTICS v_cancelled = ROW_COUNT;
    IF v_cancelled <> cardinality(v_cancel) THEN
        RAISE EXCEPTION 'charge_has_settlements' USING ERRCODE = '22023';
    END IF;

    UPDATE orbity.billing_charges
       SET preserved_after_deactivation = true, preserved_at = now()
     WHERE org_id = p_org_id AND entry_id = ANY (v_preserve);

    -- a cancelled charge that already exists at the gateway must be cancelled THERE too (done after commit, retried by the worker)
    UPDATE orbity.billing_charges
       SET gateway_cancel_status = 'pending', gateway_cancel_error = NULL
     WHERE org_id = p_org_id AND entry_id = ANY (v_cancel) AND external_id IS NOT NULL;

    -- a cancelled charge that never reached the gateway must not be generated later
    UPDATE orbity.billing_charges
       SET generation_status = 'skipped', last_error = 'Cancelada na inativação do cliente.', next_attempt_at = NULL
     WHERE org_id = p_org_id AND entry_id = ANY (v_cancel) AND external_id IS NULL
       AND generation_status IN ('queued', 'retrying', 'failed');

    SELECT COALESCE(array_agg(bc.entry_id), '{}'::uuid[]) INTO v_gateway
      FROM orbity.billing_charges bc
     WHERE bc.org_id = p_org_id AND bc.entry_id = ANY (v_cancel) AND bc.gateway_cancel_status = 'pending';

    UPDATE orbity.clients
       SET active = false, inactivated_at = COALESCE(inactivated_at, now())
     WHERE id = p_client_id AND org_id = p_org_id;

    RETURN jsonb_build_object(
        'client_id', p_client_id,
        'cancelled', v_cancelled,
        'preserved', cardinality(v_preserve),
        'cancelled_entry_ids', to_jsonb(v_cancel),
        'preserved_entry_ids', to_jsonb(v_preserve),
        'gateway_cancel_entry_ids', to_jsonb(v_gateway)
    );
END;
$fn$;
REVOKE ALL ON FUNCTION orbity.offboard_client(UUID, UUID, UUID[], UUID[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION orbity.offboard_client(UUID, UUID, UUID[], UUID[]) TO service_role;
