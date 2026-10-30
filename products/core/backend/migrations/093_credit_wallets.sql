-- Migration: 093_credit_wallets
-- Schema: public (core)
-- Roadmap: project-history/roadmaps/product-agents-platform-2026-10.md — the prepaid credit wallet
-- over the central AI usage ledger (091, D25). Owner billing decisions 2026-10-29.
--
-- WHAT: per-ORG AI billing, discriminated by product (then feature).
--   1. public.credit_pricing   — versioned, insert-only rate card. A usage row is priced
--        price_BRL = cost_usd × (fx + fx_buffer_brl) × (1 + iof_rate + import_tax_rate)
--                    ÷ (1 − simples_rate − gateway_fee_rate) × (1 + margin)
--        credits   = price_BRL ÷ credit_unit_brl
--      (the formula lives in ONE place: app/services/credits/pricing.py; this table is its data).
--      Seeded version 1: margin 1.0 (100% markup ≈ 45-50% usage gross margin), IOF 3.5%,
--      FX buffer R$0.10/USD, Simples 6% (CONTADOR MUST CONFIRM), gateway 3.99%, 1 credit = R$0.01.
--   2. public.credit_wallets   — one row per org: mode prepaid | postpaid_trusted | byok,
--      balance, overdraft limit, 50/80/100% alert state, charge_from (usage before the wallet
--      existed is never charged retroactively).
--   3. public.credit_entries   — append-only money ledger: purchase | grant | adjustment |
--      usage_debit | refund. A debit is UNIQUE per ai_usage row; a purchase/refund UNIQUE per
--      payment ref. Admin grants travel the SAME path as purchases (kind='grant', source says who).
--   4. public.credit_purchases — a prepaid PIX/boleto/card charge opened through the existing
--      billing gateways (Asaas/Stripe); the paid webhook turns it into a purchase entry.
--   5. public.credit_apply_entry(...) — the ONLY writer of entries + balances: SECURITY DEFINER,
--      serialised per org by an advisory xact lock (no lost update), idempotent on ai_usage_id /
--      payment ref, stamps ai_usage.charged_credits (091's one allowed write) in the same txn.
--      Direct INSERT into credit_entries and direct balance writes are refused by trigger
--      (GUC carve-out `noctus.credit_wallet_write`, set only inside the function).
--   6. RLS: org owner/admin/manager read their org's wallet/entries/purchases; platform admins
--      read everything (credit_pricing — the margin — is platform-admin only). No authenticated
--      write grant anywhere; writes are the backend service role.
--
-- LGPD: amounts, identifiers and references only — no personal data.
-- Re-runnable: IF NOT EXISTS / OR REPLACE / ON CONFLICT / DROP-then-CREATE.
SET search_path = public, public;

-- ── 1. pricing (versioned, insert-only) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.credit_pricing (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version           INTEGER NOT NULL UNIQUE CHECK (version >= 1),
    effective_from    TIMESTAMPTZ NOT NULL DEFAULT now(),
    credit_unit_brl   NUMERIC(12, 6) NOT NULL CHECK (credit_unit_brl > 0),
    margin            NUMERIC(8, 4) NOT NULL CHECK (margin >= 0),
    fx_buffer_brl     NUMERIC(8, 4) NOT NULL DEFAULT 0 CHECK (fx_buffer_brl >= 0),
    iof_rate          NUMERIC(6, 4) NOT NULL CHECK (iof_rate >= 0 AND iof_rate < 1),
    import_tax_rate   NUMERIC(6, 4) NOT NULL DEFAULT 0 CHECK (import_tax_rate >= 0 AND import_tax_rate < 1),
    simples_rate      NUMERIC(6, 4) NOT NULL CHECK (simples_rate >= 0 AND simples_rate < 1),
    gateway_fee_rate  NUMERIC(6, 4) NOT NULL CHECK (gateway_fee_rate >= 0 AND gateway_fee_rate < 1),
    notes             TEXT CHECK (notes IS NULL OR length(notes) <= 2000),
    created_by        UUID,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT credit_pricing_divisor_positive CHECK (simples_rate + gateway_fee_rate < 0.9)
);
COMMENT ON TABLE public.credit_pricing IS
    'Versioned AI credit rate card (insert-only). Effective version = latest effective_from <= now(). '
    'Formula: app/services/credits/pricing.py. Platform-admin read only (it carries the margin).';

INSERT INTO public.credit_pricing
    (version, effective_from, credit_unit_brl, margin, fx_buffer_brl, iof_rate, import_tax_rate,
     simples_rate, gateway_fee_rate, notes)
VALUES
    (1, '2026-10-29T00:00:00Z', 0.01, 1.0, 0.10, 0.035, 0, 0.06, 0.0399,
     'Seed defaults (owner 2026-10-29). simples_rate 6% and import_tax_rate 0 — CONTADOR MUST CONFIRM. '
     'margin 1.0 = 100% markup (~45-50% usage gross margin after IOF/Simples/gateway).')
ON CONFLICT (version) DO NOTHING;

-- ── 2. wallets ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.credit_wallets (
    org_id                   UUID PRIMARY KEY REFERENCES public.organizations(id) ON DELETE CASCADE,
    mode                     TEXT NOT NULL DEFAULT 'prepaid'
                                 CHECK (mode IN ('prepaid', 'postpaid_trusted', 'byok')),
    balance_credits          NUMERIC(20, 6) NOT NULL DEFAULT 0,
    overdraft_limit_credits  NUMERIC(20, 6) NOT NULL DEFAULT 0 CHECK (overdraft_limit_credits >= 0),
    alert_thresholds         NUMERIC[] NOT NULL DEFAULT '{0.5,0.8,1.0}'::numeric[]
                                 CHECK (cardinality(alert_thresholds) BETWEEN 0 AND 10
                                        AND 0 < ALL (alert_thresholds) AND 1 >= ALL (alert_thresholds)),
    -- Alert state: the balance right after the last purchase/grant, and the highest threshold
    -- already notified since then. Written only by credit_apply_entry.
    alert_base_credits       NUMERIC(20, 6) NOT NULL DEFAULT 0 CHECK (alert_base_credits >= 0),
    last_alert_threshold     NUMERIC(6, 4) NOT NULL DEFAULT 0,
    charge_from              TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by               UUID
);
COMMENT ON TABLE public.credit_wallets IS
    'Per-org AI credit wallet. balance/alert columns written only by credit_apply_entry (trigger + GUC). '
    'mode/overdraft/thresholds are admin settings (service role).';

-- ── 3. entries (append-only) ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.credit_entries (
    id                 BIGSERIAL PRIMARY KEY,
    org_id             UUID NOT NULL REFERENCES public.organizations(id),
    product            TEXT CHECK (product IS NULL OR length(product) BETWEEN 1 AND 200),
    feature            TEXT CHECK (feature IS NULL OR length(feature) <= 200),
    kind               TEXT NOT NULL
                           CHECK (kind IN ('purchase', 'grant', 'adjustment', 'usage_debit', 'refund')),
    source             TEXT NOT NULL CHECK (length(source) BETWEEN 1 AND 80),
    credits            NUMERIC(20, 6) NOT NULL,
    balance_after      NUMERIC(20, 6) NOT NULL,
    brl_amount         NUMERIC(18, 6),
    usd_amount         NUMERIC(18, 8),
    provider_cost_brl  NUMERIC(18, 8),
    fx_rate            NUMERIC(12, 5),
    pricing_version    INTEGER,
    ai_usage_id        BIGINT REFERENCES public.ai_usage(id),
    payment_ref        TEXT CHECK (payment_ref IS NULL OR length(payment_ref) BETWEEN 1 AND 200),
    reason             TEXT CHECK (reason IS NULL OR length(reason) <= 1000),
    detail             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by         UUID,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT credit_entries_sign CHECK (
        (kind IN ('purchase', 'grant') AND credits > 0)
        OR (kind = 'usage_debit' AND credits <= 0)
        OR (kind = 'refund' AND credits < 0)
        OR (kind = 'adjustment' AND credits <> 0)
    ),
    CONSTRAINT credit_entries_debit_has_usage CHECK ((kind = 'usage_debit') = (ai_usage_id IS NOT NULL)),
    CONSTRAINT credit_entries_purchase_has_ref CHECK (kind <> 'purchase' OR payment_ref IS NOT NULL)
);
COMMENT ON TABLE public.credit_entries IS
    'Append-only AI credit ledger. Written only via credit_apply_entry (trigger refuses direct INSERT, '
    'every UPDATE/DELETE/TRUNCATE). One debit per ai_usage row; one purchase/refund per payment ref.';

CREATE UNIQUE INDEX IF NOT EXISTS ux_credit_entries_ai_usage
    ON public.credit_entries (ai_usage_id) WHERE ai_usage_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_credit_entries_payment
    ON public.credit_entries (kind, payment_ref) WHERE payment_ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_credit_entries_org_created
    ON public.credit_entries (org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_credit_entries_org_product_created
    ON public.credit_entries (org_id, product, created_at DESC);

-- ── 4. purchases (pending gateway charges) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.credit_purchases (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             UUID NOT NULL REFERENCES public.organizations(id),
    credits            NUMERIC(20, 6) NOT NULL CHECK (credits > 0),
    amount_cents       INTEGER NOT NULL CHECK (amount_cents > 0),
    currency           TEXT NOT NULL DEFAULT 'BRL' CHECK (currency = 'BRL'),
    pricing_version    INTEGER NOT NULL,
    gateway            TEXT NOT NULL CHECK (gateway IN ('stripe', 'asaas')),
    gateway_mode       TEXT NOT NULL CHECK (gateway_mode IN ('test', 'live')),
    billing_method     TEXT NOT NULL CHECK (billing_method IN ('pix', 'boleto', 'card', 'unspecified')),
    gateway_charge_id  TEXT,
    checkout_url       TEXT,
    status             TEXT NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending', 'paid', 'failed', 'canceled', 'refunded')),
    credit_entry_id    BIGINT REFERENCES public.credit_entries(id),
    created_by         UUID,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    paid_at            TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_credit_purchases_org_created
    ON public.credit_purchases (org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_credit_purchases_charge
    ON public.credit_purchases (gateway, gateway_charge_id) WHERE gateway_charge_id IS NOT NULL;

-- ── 5. guards ───────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.guard_credit_pricing_insert_only()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'credit_pricing_insert_only' USING ERRCODE = 'P0001';
END;
$$;
REVOKE ALL ON FUNCTION public.guard_credit_pricing_insert_only() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS guard_credit_pricing_insert_only ON public.credit_pricing;
CREATE TRIGGER guard_credit_pricing_insert_only
    BEFORE UPDATE OR DELETE ON public.credit_pricing
    FOR EACH ROW EXECUTE FUNCTION public.guard_credit_pricing_insert_only();

CREATE OR REPLACE FUNCTION public.guard_credit_entries_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF coalesce(current_setting('noctus.credit_wallet_write', true), '') = 'on' THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'credit_entries_write_via_credit_apply_entry' USING ERRCODE = 'P0001';
    END IF;
    RAISE EXCEPTION 'credit_entries_append_only' USING ERRCODE = 'P0001';
END;
$$;
REVOKE ALL ON FUNCTION public.guard_credit_entries_append_only() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS guard_credit_entries_append_only ON public.credit_entries;
CREATE TRIGGER guard_credit_entries_append_only
    BEFORE INSERT OR UPDATE OR DELETE ON public.credit_entries
    FOR EACH ROW EXECUTE FUNCTION public.guard_credit_entries_append_only();
DROP TRIGGER IF EXISTS guard_credit_entries_no_truncate ON public.credit_entries;
CREATE TRIGGER guard_credit_entries_no_truncate
    BEFORE TRUNCATE ON public.credit_entries
    FOR EACH STATEMENT EXECUTE FUNCTION public.guard_credit_entries_append_only();

CREATE OR REPLACE FUNCTION public.guard_credit_wallet_balance()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    IF coalesce(current_setting('noctus.credit_wallet_write', true), '') = 'on' THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.balance_credits = 0 AND NEW.alert_base_credits = 0 AND NEW.last_alert_threshold = 0 THEN
            RETURN NEW;
        END IF;
    ELSIF NEW.balance_credits IS NOT DISTINCT FROM OLD.balance_credits
          AND NEW.alert_base_credits IS NOT DISTINCT FROM OLD.alert_base_credits
          AND NEW.last_alert_threshold IS NOT DISTINCT FROM OLD.last_alert_threshold THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'credit_wallet_balance_via_credit_apply_entry' USING ERRCODE = 'P0001';
END;
$$;
REVOKE ALL ON FUNCTION public.guard_credit_wallet_balance() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS guard_credit_wallet_balance ON public.credit_wallets;
CREATE TRIGGER guard_credit_wallet_balance
    BEFORE INSERT OR UPDATE ON public.credit_wallets
    FOR EACH ROW EXECUTE FUNCTION public.guard_credit_wallet_balance();

-- ── 6. the one writer ───────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.credit_apply_entry(
    p_org_id            UUID,
    p_kind              TEXT,
    p_credits           NUMERIC,
    p_source            TEXT,
    p_product           TEXT DEFAULT NULL,
    p_feature           TEXT DEFAULT NULL,
    p_brl_amount        NUMERIC DEFAULT NULL,
    p_usd_amount        NUMERIC DEFAULT NULL,
    p_provider_cost_brl NUMERIC DEFAULT NULL,
    p_fx_rate           NUMERIC DEFAULT NULL,
    p_pricing_version   INTEGER DEFAULT NULL,
    p_ai_usage_id       BIGINT DEFAULT NULL,
    p_payment_ref       TEXT DEFAULT NULL,
    p_reason            TEXT DEFAULT NULL,
    p_detail            JSONB DEFAULT '{}'::jsonb,
    p_created_by        UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_wallet     public.credit_wallets%ROWTYPE;
    v_dup        public.credit_entries%ROWTYPE;
    v_usage_org  UUID;
    v_charged    NUMERIC;
    v_entry_id   BIGINT;
    v_balance    NUMERIC;
    v_base       NUMERIC;
    v_last       NUMERIC;
    v_consumed   NUMERIC;
    v_threshold  NUMERIC := NULL;
    t            NUMERIC;
BEGIN
    IF p_org_id IS NULL THEN
        RAISE EXCEPTION 'credit_apply_entry: org_id is required' USING ERRCODE = '22023';
    END IF;

    -- Serialise every write of this org's wallet (no lost update between the debit job,
    -- a webhook and an admin grant running at the same instant).
    PERFORM pg_advisory_xact_lock(hashtextextended('credit_wallet:' || p_org_id::text, 0));

    -- Idempotency: a retried debit / webhook is a proven no-op.
    IF p_ai_usage_id IS NOT NULL THEN
        SELECT org_id, charged_credits INTO v_usage_org, v_charged
          FROM public.ai_usage WHERE id = p_ai_usage_id FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'credit_apply_entry: ai_usage % not found', p_ai_usage_id USING ERRCODE = '22023';
        END IF;
        IF v_usage_org IS DISTINCT FROM p_org_id THEN
            RAISE EXCEPTION 'credit_apply_entry: ai_usage % belongs to another org', p_ai_usage_id
                USING ERRCODE = '22023';
        END IF;
        SELECT * INTO v_dup FROM public.credit_entries WHERE ai_usage_id = p_ai_usage_id;
        IF FOUND THEN
            RETURN jsonb_build_object('status', 'duplicate', 'entry_id', v_dup.id,
                                      'balance_credits', v_dup.balance_after);
        END IF;
        IF v_charged IS NOT NULL THEN
            RETURN jsonb_build_object('status', 'already_charged', 'entry_id', NULL,
                                      'charged_credits', v_charged);
        END IF;
    END IF;
    IF p_payment_ref IS NOT NULL THEN
        SELECT * INTO v_dup FROM public.credit_entries WHERE kind = p_kind AND payment_ref = p_payment_ref;
        IF FOUND THEN
            RETURN jsonb_build_object('status', 'duplicate', 'entry_id', v_dup.id,
                                      'balance_credits', v_dup.balance_after);
        END IF;
    END IF;

    PERFORM set_config('noctus.credit_wallet_write', 'on', true);

    INSERT INTO public.credit_wallets (org_id) VALUES (p_org_id) ON CONFLICT (org_id) DO NOTHING;
    SELECT * INTO v_wallet FROM public.credit_wallets WHERE org_id = p_org_id FOR UPDATE;

    v_balance := v_wallet.balance_credits + p_credits;
    v_base := v_wallet.alert_base_credits;
    v_last := v_wallet.last_alert_threshold;
    IF p_kind IN ('purchase', 'grant') THEN
        -- A top-up starts a new alert cycle measured against the new balance.
        v_base := GREATEST(v_balance, 0);
        v_last := 0;
    ELSIF p_credits < 0 AND v_base > 0 THEN
        v_consumed := (v_base - v_balance) / v_base;
        FOREACH t IN ARRAY v_wallet.alert_thresholds LOOP
            IF v_consumed >= t AND t > v_last THEN
                v_threshold := GREATEST(coalesce(v_threshold, 0), t);
            END IF;
        END LOOP;
        IF v_threshold IS NOT NULL THEN
            v_last := v_threshold;
        END IF;
    END IF;

    INSERT INTO public.credit_entries (
        org_id, product, feature, kind, source, credits, balance_after, brl_amount, usd_amount,
        provider_cost_brl, fx_rate, pricing_version, ai_usage_id, payment_ref, reason, detail, created_by
    ) VALUES (
        p_org_id, p_product, p_feature, p_kind, p_source, p_credits, v_balance, p_brl_amount, p_usd_amount,
        p_provider_cost_brl, p_fx_rate, p_pricing_version, p_ai_usage_id, p_payment_ref, p_reason,
        coalesce(p_detail, '{}'::jsonb), p_created_by
    ) RETURNING id INTO v_entry_id;

    UPDATE public.credit_wallets
       SET balance_credits = v_balance,
           alert_base_credits = v_base,
           last_alert_threshold = v_last,
           updated_at = now()
     WHERE org_id = p_org_id;

    IF p_ai_usage_id IS NOT NULL THEN
        UPDATE public.ai_usage SET charged_credits = -p_credits
         WHERE id = p_ai_usage_id AND charged_credits IS NULL;
    END IF;

    PERFORM set_config('noctus.credit_wallet_write', '', true);

    RETURN jsonb_build_object(
        'status', 'applied',
        'entry_id', v_entry_id,
        'balance_credits', v_balance,
        'alert_base_credits', v_base,
        'alert_threshold', v_threshold,
        'mode', v_wallet.mode
    );
END;
$$;

REVOKE ALL ON FUNCTION public.credit_apply_entry(
    UUID, TEXT, NUMERIC, TEXT, TEXT, TEXT, NUMERIC, NUMERIC, NUMERIC, NUMERIC, INTEGER, BIGINT, TEXT, TEXT, JSONB, UUID
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.credit_apply_entry(
    UUID, TEXT, NUMERIC, TEXT, TEXT, TEXT, NUMERIC, NUMERIC, NUMERIC, NUMERIC, INTEGER, BIGINT, TEXT, TEXT, JSONB, UUID
) TO service_role;

-- ── 7. access ───────────────────────────────────────────────────────────────────
ALTER TABLE public.credit_pricing   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.credit_wallets   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.credit_entries   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.credit_purchases ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.credit_pricing, public.credit_wallets, public.credit_entries, public.credit_purchases
    FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.credit_pricing, public.credit_wallets, public.credit_entries, public.credit_purchases
    TO authenticated;

REVOKE ALL ON public.credit_pricing, public.credit_wallets, public.credit_entries, public.credit_purchases
    FROM service_role;
GRANT SELECT, INSERT ON public.credit_pricing TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.credit_wallets TO service_role;
GRANT SELECT ON public.credit_entries TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.credit_purchases TO service_role;

DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['credit_pricing', 'credit_wallets', 'credit_entries', 'credit_purchases'] LOOP
        EXECUTE format('DROP POLICY IF EXISTS "service_role_bypass" ON public.%I', tbl);
        EXECUTE format(
            'CREATE POLICY "service_role_bypass" ON public.%I FOR ALL TO service_role USING (true) WITH CHECK (true)',
            tbl);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', tbl || '_platform_admin_read', tbl);
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING ((SELECT public.is_platform_admin()))',
            tbl || '_platform_admin_read', tbl);
    END LOOP;
    -- Org owner/admin/manager read their own org (never the pricing table: it carries the margin).
    FOREACH tbl IN ARRAY ARRAY['credit_wallets', 'credit_entries', 'credit_purchases'] LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', tbl || '_org_admin_read', tbl);
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING ('
            'org_id IN (SELECT m.org_id FROM public.org_memberships m '
            'WHERE m.user_id = (SELECT auth.uid()) AND m.status = ''active'' '
            'AND m.org_role IN (''owner'', ''admin'', ''manager'')))',
            tbl || '_org_admin_read', tbl);
    END LOOP;
END;
$$;
