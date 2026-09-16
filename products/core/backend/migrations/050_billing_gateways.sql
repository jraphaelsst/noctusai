-- ============================================================================
-- 050_billing_gateways — Core subscription billing on Stripe + Asaas (edicao-fotos R2)
-- ============================================================================
--
-- Numbered 050, not the plan's "046"/"047": 046 is `046_permissions_fx_cost_
-- ledger.sql` (applied), 047 is `047_seed_community_product.sql` on
-- `feat/community-scaffold` (applied live), and 048/049 are the ledger-lock /
-- schema-exposure migrations on origin/dev. Checked against disk, origin/dev
-- and every local branch on 2026-09-16.
--
-- What it adds (all in `public`, Core's schema):
--
--   1. `plans`            += product_id / audience / trial_days / grace_days
--   2. `plan_prices`      — one row per (plan, cycle, currency); the price the
--                           admin sets in the UI, in integer cents, plus the
--                           Stripe Price id per mode (Stripe bills a Price
--                           object; Asaas bills the amount directly).
--   3. `subscriptions`    += gateway / mode / ids / cycle / method / currency /
--                           amount / period / trial_ends_at / grace_ends_at /
--                           past_due_since / automation_managed; the status
--                           CHECK is widened with past_due / grace / incomplete.
--                           `automation_managed` defaults FALSE: every row that
--                           exists today is invisible to the billing automations.
--   4. `billing_customers` — the org's customer id per (gateway, mode).
--   5. `payment_events`   — webhook inbox. UNIQUE (gateway, event_id) IS the
--                           idempotency guarantee (`noctusai_lib.domain.payments.
--                           RealSupabaseEventInbox` inserts and reads a 23505 as
--                           "already processed").
--   6. `billing_payments` — one row per charge: gross / fee / net (integer
--                           cents, gross = fee + net enforced) + PTAX conversion.
--   7. `licenses.source`  — 'legacy' | 'manual' | 'subscription'. EVERY row that
--                           exists when this runs becomes 'legacy'. The billing
--                           automations only ever read/write `source =
--                           'subscription'`; that is how "existing licensed orgs
--                           keep their licenses exactly as they are" is enforced.
--   8. `app_integration_config` — Fernet-encrypted key→value store backing
--                           `noctusai_lib.security.app_config.RealAppConfigStore`
--                           (gateway API keys + webhook secrets, entered in the UI).
--   9. `storage_usage_snapshots` + `storage_usage_by_prefix()` — daily storage
--                           size per bucket/org for the storage-cost job.
--  10. `platform_settings` defaults — automations OFF, gateways OFF, mode test.
--
-- ── VERIFICATION (run by hand around the apply) ──────────────────────────────
--
--   BEFORE:  SELECT count(*) AS pre_total,
--                   count(*) FILTER (WHERE status = 'active') AS pre_active
--            FROM public.licenses;
--
--   AFTER:   SELECT count(*) FILTER (WHERE source = 'legacy')                     AS legacy_total,
--                   count(*) FILTER (WHERE source = 'legacy' AND status = 'active') AS legacy_active,
--                   count(*) FILTER (WHERE source <> 'legacy')                    AS non_legacy
--            FROM public.licenses;
--
--   Expected: legacy_total = pre_total, legacy_active = pre_active, non_legacy = 0.
--   The DO block in §7 also asserts backfilled-rows == pre-count inside the
--   transaction and aborts the whole migration if they differ.
--
-- FORWARD-ONLY. MIGRATION FILE ONLY — not applied by this change. Applying it
-- needs owner consent (`projects/edicao-fotos/PROJECT.md` §5).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. plans — which product a plan licenses, who it is for, trial + grace
-- ----------------------------------------------------------------------------

ALTER TABLE public.plans ADD COLUMN IF NOT EXISTS product_id UUID REFERENCES public.products (id);
ALTER TABLE public.plans ADD COLUMN IF NOT EXISTS audience TEXT NOT NULL DEFAULT 'any';
ALTER TABLE public.plans ADD COLUMN IF NOT EXISTS trial_days INT NOT NULL DEFAULT 0;
ALTER TABLE public.plans ADD COLUMN IF NOT EXISTS grace_days INT NOT NULL DEFAULT 0;

ALTER TABLE public.plans DROP CONSTRAINT IF EXISTS plans_audience_check;
ALTER TABLE public.plans ADD CONSTRAINT plans_audience_check
    CHECK (audience IN ('individual', 'company', 'any'));
ALTER TABLE public.plans DROP CONSTRAINT IF EXISTS plans_trial_days_check;
ALTER TABLE public.plans ADD CONSTRAINT plans_trial_days_check CHECK (trial_days >= 0);
ALTER TABLE public.plans DROP CONSTRAINT IF EXISTS plans_grace_days_check;
ALTER TABLE public.plans ADD CONSTRAINT plans_grace_days_check CHECK (grace_days >= 0);

CREATE INDEX IF NOT EXISTS ix_plans_product ON public.plans (product_id);

-- ----------------------------------------------------------------------------
-- 2. plan_prices
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.plan_prices (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id               UUID NOT NULL REFERENCES public.plans (id) ON DELETE CASCADE,
    billing_cycle         TEXT NOT NULL CHECK (billing_cycle IN ('monthly', 'yearly')),
    currency              TEXT NOT NULL DEFAULT 'BRL' CHECK (currency ~ '^[A-Z]{3}$'),
    amount_cents          BIGINT NOT NULL CHECK (amount_cents >= 0),
    stripe_price_id_test  TEXT,
    stripe_price_id_live  TEXT,
    ativo                 BOOLEAN NOT NULL DEFAULT true,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One sellable price per plan/cycle/currency at a time; retired prices stay
-- as history (a subscription keeps pointing at the price it was sold at).
CREATE UNIQUE INDEX IF NOT EXISTS ux_plan_prices_active
    ON public.plan_prices (plan_id, billing_cycle, currency)
    WHERE ativo;
CREATE INDEX IF NOT EXISTS ix_plan_prices_plan ON public.plan_prices (plan_id);

ALTER TABLE public.plan_prices ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "plan_prices_read_active" ON public.plan_prices;
CREATE POLICY "plan_prices_read_active" ON public.plan_prices
    FOR SELECT TO authenticated
    USING (ativo OR public.is_platform_admin());

DROP POLICY IF EXISTS "service_role_bypass" ON public.plan_prices;
CREATE POLICY "service_role_bypass" ON public.plan_prices FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. subscriptions — gateway fields + widened status
-- ----------------------------------------------------------------------------

ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS gateway TEXT;
ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS gateway_mode TEXT;
ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS gateway_subscription_id TEXT;
ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS gateway_customer_id TEXT;
ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS plan_price_id UUID REFERENCES public.plan_prices (id);
ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS billing_cycle TEXT;
ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS billing_method TEXT;
ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS currency TEXT;
ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS amount_cents BIGINT;
ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS current_period_start TIMESTAMPTZ;
ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMPTZ;
ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMPTZ;
ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS grace_ends_at TIMESTAMPTZ;
ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS past_due_since TIMESTAMPTZ;
ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS cancel_at_period_end BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS automation_managed BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS payment_url TEXT;

ALTER TABLE public.subscriptions DROP CONSTRAINT IF EXISTS subscriptions_status_check;
ALTER TABLE public.subscriptions ADD CONSTRAINT subscriptions_status_check
    CHECK (status IN ('active', 'canceled', 'expired', 'trial', 'past_due', 'grace', 'incomplete'));
ALTER TABLE public.subscriptions DROP CONSTRAINT IF EXISTS subscriptions_gateway_check;
ALTER TABLE public.subscriptions ADD CONSTRAINT subscriptions_gateway_check
    CHECK (gateway IS NULL OR gateway IN ('stripe', 'asaas', 'manual'));
ALTER TABLE public.subscriptions DROP CONSTRAINT IF EXISTS subscriptions_gateway_mode_check;
ALTER TABLE public.subscriptions ADD CONSTRAINT subscriptions_gateway_mode_check
    CHECK (gateway_mode IS NULL OR gateway_mode IN ('test', 'live'));
ALTER TABLE public.subscriptions DROP CONSTRAINT IF EXISTS subscriptions_billing_cycle_check;
ALTER TABLE public.subscriptions ADD CONSTRAINT subscriptions_billing_cycle_check
    CHECK (billing_cycle IS NULL OR billing_cycle IN ('monthly', 'yearly'));
ALTER TABLE public.subscriptions DROP CONSTRAINT IF EXISTS subscriptions_billing_method_check;
ALTER TABLE public.subscriptions ADD CONSTRAINT subscriptions_billing_method_check
    CHECK (billing_method IS NULL OR billing_method IN ('card', 'pix', 'boleto', 'unspecified'));
ALTER TABLE public.subscriptions DROP CONSTRAINT IF EXISTS subscriptions_amount_cents_check;
ALTER TABLE public.subscriptions ADD CONSTRAINT subscriptions_amount_cents_check
    CHECK (amount_cents IS NULL OR amount_cents >= 0);

CREATE UNIQUE INDEX IF NOT EXISTS ux_subscriptions_gateway_id
    ON public.subscriptions (gateway, gateway_subscription_id)
    WHERE gateway_subscription_id IS NOT NULL;
-- The automations' read path: managed rows by status + the deadline column.
CREATE INDEX IF NOT EXISTS ix_subscriptions_automation
    ON public.subscriptions (status, automation_managed)
    WHERE automation_managed;

-- Mirror the legacy Stripe ids into the generic columns so the admin list
-- shows them. `automation_managed` stays FALSE for these rows.
UPDATE public.subscriptions
   SET gateway = 'stripe',
       gateway_subscription_id = stripe_subscription_id,
       gateway_customer_id = stripe_customer_id
 WHERE stripe_subscription_id IS NOT NULL
   AND gateway IS NULL;

-- ----------------------------------------------------------------------------
-- 4. billing_customers
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.billing_customers (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    gateway              TEXT NOT NULL CHECK (gateway IN ('stripe', 'asaas')),
    gateway_mode         TEXT NOT NULL CHECK (gateway_mode IN ('test', 'live')),
    gateway_customer_id  TEXT NOT NULL,
    email                TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, gateway, gateway_mode),
    UNIQUE (gateway, gateway_mode, gateway_customer_id)
);

ALTER TABLE public.billing_customers ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "billing_customers_select_own_org" ON public.billing_customers;
CREATE POLICY "billing_customers_select_own_org" ON public.billing_customers
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id() OR public.is_platform_admin());

DROP POLICY IF EXISTS "service_role_bypass" ON public.billing_customers;
CREATE POLICY "service_role_bypass" ON public.billing_customers FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 5. payment_events — webhook inbox
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.payment_events (
    id               BIGSERIAL PRIMARY KEY,
    gateway          TEXT NOT NULL,
    event_id         TEXT NOT NULL,
    gateway_mode     TEXT CHECK (gateway_mode IS NULL OR gateway_mode IN ('test', 'live')),
    event_type       TEXT,
    org_id           UUID,
    subscription_id  UUID REFERENCES public.subscriptions (id) ON DELETE SET NULL,
    payload          JSONB NOT NULL DEFAULT '{}'::jsonb,
    status           TEXT NOT NULL DEFAULT 'received'
                     CHECK (status IN ('received', 'processed', 'ignored')),
    claimed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at     TIMESTAMPTZ,
    CONSTRAINT payment_events_gateway_event_id_key UNIQUE (gateway, event_id)
);

CREATE INDEX IF NOT EXISTS ix_payment_events_org ON public.payment_events (org_id, claimed_at DESC);
CREATE INDEX IF NOT EXISTS ix_payment_events_type ON public.payment_events (event_type);

ALTER TABLE public.payment_events ENABLE ROW LEVEL SECURITY;

-- Raw gateway payloads carry payer PII — platform admin only.
DROP POLICY IF EXISTS "payment_events_select_platform_admin" ON public.payment_events;
CREATE POLICY "payment_events_select_platform_admin" ON public.payment_events
    FOR SELECT TO authenticated
    USING (public.is_platform_admin());

DROP POLICY IF EXISTS "service_role_bypass" ON public.payment_events;
CREATE POLICY "service_role_bypass" ON public.payment_events FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 6. billing_payments — one row per charge, fee + net, PTAX conversion
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.billing_payments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    subscription_id     UUID REFERENCES public.subscriptions (id) ON DELETE SET NULL,
    gateway             TEXT NOT NULL CHECK (gateway IN ('stripe', 'asaas')),
    gateway_mode        TEXT NOT NULL CHECK (gateway_mode IN ('test', 'live')),
    gateway_payment_id  TEXT NOT NULL,      -- Stripe invoice id / Asaas payment id
    gateway_charge_id   TEXT,               -- Stripe charge id (fee lookup); NULL for Asaas
    status              TEXT NOT NULL CHECK (status IN ('pending', 'paid', 'failed', 'refunded')),
    billing_method      TEXT,
    currency            TEXT NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    gross_cents         BIGINT NOT NULL CHECK (gross_cents >= 0),
    fee_cents           BIGINT NOT NULL DEFAULT 0 CHECK (fee_cents >= 0),
    net_cents           BIGINT NOT NULL,
    -- The gateway reports the fee after settlement; until then the row is
    -- fee_pending and the reconcile job fills it in.
    fee_pending         BOOLEAN NOT NULL DEFAULT false,
    fx_rate             NUMERIC(12, 5),
    fx_quote_date       DATE,
    gross_brl           NUMERIC(14, 2),
    fee_brl             NUMERIC(14, 2),
    fx_pending          BOOLEAN NOT NULL DEFAULT false,
    paid_at             TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT billing_payments_gateway_payment_key UNIQUE (gateway, gateway_payment_id),
    CONSTRAINT billing_payments_gross_equals_fee_plus_net CHECK (gross_cents = fee_cents + net_cents),
    -- Same all-or-nothing conversion rule as `cost_ledger` (migration 046).
    CONSTRAINT billing_payments_fx_state CHECK (
        (currency = 'BRL' AND fx_pending = false AND fx_rate IS NULL AND fx_quote_date IS NULL)
        OR (currency <> 'BRL' AND fx_pending = true
            AND fx_rate IS NULL AND fx_quote_date IS NULL AND gross_brl IS NULL AND fee_brl IS NULL)
        OR (currency <> 'BRL' AND fx_pending = false
            AND fx_rate IS NOT NULL AND fx_quote_date IS NOT NULL AND gross_brl IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_billing_payments_org ON public.billing_payments (org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_billing_payments_subscription ON public.billing_payments (subscription_id);
CREATE INDEX IF NOT EXISTS ix_billing_payments_fee_pending
    ON public.billing_payments (fee_pending) WHERE fee_pending;

ALTER TABLE public.billing_payments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "billing_payments_select_own_org" ON public.billing_payments;
CREATE POLICY "billing_payments_select_own_org" ON public.billing_payments
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id() OR public.is_platform_admin());

DROP POLICY IF EXISTS "service_role_bypass" ON public.billing_payments;
CREATE POLICY "service_role_bypass" ON public.billing_payments FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 7. licenses.source — every existing row becomes 'legacy'
-- ----------------------------------------------------------------------------

-- Added WITHOUT a default so every pre-existing row is NULL right here —
-- which makes "rows still NULL" exactly the pre-count the DO block needs.
ALTER TABLE public.licenses ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE public.licenses ADD COLUMN IF NOT EXISTS subscription_id UUID REFERENCES public.subscriptions (id) ON DELETE SET NULL;

DO $$
DECLARE
    v_pre     BIGINT;
    v_updated BIGINT;
BEGIN
    SELECT count(*) INTO v_pre FROM public.licenses WHERE source IS NULL;

    UPDATE public.licenses SET source = 'legacy' WHERE source IS NULL;
    GET DIAGNOSTICS v_updated = ROW_COUNT;

    IF v_updated <> v_pre THEN
        RAISE EXCEPTION
            '050: licenses legacy backfill mismatch — pre-count %, backfilled % (aborting)',
            v_pre, v_updated;
    END IF;

    RAISE NOTICE '050: licenses legacy backfill — pre-count %, backfilled %', v_pre, v_updated;
END $$;

-- Re-running is a no-op: after the first run no NULL remains, and NOT NULL
-- keeps it that way. New grants from the admin UI are 'manual' by default;
-- only the billing flow writes 'subscription'.
ALTER TABLE public.licenses ALTER COLUMN source SET DEFAULT 'manual';
ALTER TABLE public.licenses ALTER COLUMN source SET NOT NULL;
ALTER TABLE public.licenses DROP CONSTRAINT IF EXISTS licenses_source_check;
ALTER TABLE public.licenses ADD CONSTRAINT licenses_source_check
    CHECK (source IN ('legacy', 'manual', 'subscription'));

CREATE INDEX IF NOT EXISTS ix_licenses_subscription
    ON public.licenses (subscription_id) WHERE subscription_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_licenses_source ON public.licenses (source);

-- ----------------------------------------------------------------------------
-- 8. app_integration_config — encrypted gateway keys
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.app_integration_config (
    key             TEXT PRIMARY KEY,
    encrypted_value TEXT NOT NULL,              -- Fernet(value), never plaintext
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.app_integration_config ENABLE ROW LEVEL SECURITY;

-- Service role only. No authenticated policy: secrets are read and written
-- exclusively by the admin-gated billing settings endpoints.
DROP POLICY IF EXISTS "service_role_bypass" ON public.app_integration_config;
CREATE POLICY "service_role_bypass" ON public.app_integration_config FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 9. storage usage — snapshot table + size RPC
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.storage_usage_snapshots (
    id             BIGSERIAL PRIMARY KEY,
    snapshot_date  DATE NOT NULL,
    bucket_id      TEXT NOT NULL,
    org_id         UUID,               -- NULL = objects whose path has no org prefix
    total_bytes    BIGINT NOT NULL CHECK (total_bytes >= 0),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_storage_usage_snapshots_date
    ON public.storage_usage_snapshots (snapshot_date DESC);

ALTER TABLE public.storage_usage_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "storage_usage_snapshots_select_platform_admin" ON public.storage_usage_snapshots;
CREATE POLICY "storage_usage_snapshots_select_platform_admin" ON public.storage_usage_snapshots
    FOR SELECT TO authenticated
    USING (public.is_platform_admin());

DROP POLICY IF EXISTS "service_role_bypass" ON public.storage_usage_snapshots;
CREATE POLICY "service_role_bypass" ON public.storage_usage_snapshots FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Bytes per (bucket, org). An object is attributed to an org when the first
-- path segment is a UUID (`{org_id}/...` — the edicao-fotos layout).
CREATE OR REPLACE FUNCTION public.storage_usage_by_prefix()
RETURNS TABLE (bucket_id TEXT, org_id UUID, total_bytes BIGINT)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, storage
AS $$
    SELECT o.bucket_id::text,
           CASE
               WHEN split_part(o.name, '/', 1) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
               THEN split_part(o.name, '/', 1)::uuid
           END AS org_id,
           COALESCE(sum((o.metadata ->> 'size')::bigint), 0)::bigint AS total_bytes
      FROM storage.objects o
     GROUP BY 1, 2;
$$;

REVOKE ALL ON FUNCTION public.storage_usage_by_prefix() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.storage_usage_by_prefix() FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.storage_usage_by_prefix() TO service_role;

-- ----------------------------------------------------------------------------
-- 10. platform_settings defaults — everything starts OFF
-- ----------------------------------------------------------------------------

INSERT INTO public.platform_settings (key, value, description, is_secret) VALUES
    ('billing_automations_enabled', 'false', 'Billing automations (trial end, grace, period end, reconcile). Owner flips it in Admin > Faturamento.', false),
    ('billing_gateway_mode', 'test', 'Gateway mode used for new charges: test | live.', false),
    ('billing_stripe_enabled', 'false', 'Offer Stripe (card) at checkout.', false),
    ('billing_asaas_enabled', 'false', 'Offer Asaas (Pix, boleto, card) at checkout.', false),
    ('storage_price_usd_per_gb_month', '0.021', 'Supabase storage price used by the daily storage-cost snapshot (USD per GB-month).', false)
ON CONFLICT (key) DO NOTHING;
