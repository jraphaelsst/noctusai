-- ============================================================
-- 029 — billing_events table (Stripe webhook audit log)
-- ============================================================
-- Closes the REAL_BUG surfaced by Engineer RR's Phase 0 triage
-- (`projects/keeper-trio-platform-triage/phase-0-triage.md`):
-- `products/core/backend/app/routers/billing.py:284` writes to
-- `billing_events` but no `CREATE TABLE` exists anywhere in the
-- platform. MockSupabase WARN+skip masks this in tests; production
-- raises "relation does not exist".
--
-- Stripe webhook design: every event Stripe POSTs gets logged here
-- BEFORE dispatch, indexed by `stripe_event_id` for idempotency
-- (replay protection) + `stripe_customer_id` / `org_id` for audit
-- queries.
--
-- The `service_role_bypass` policy uses the canonical name + shape
-- emitted by `noctusai_lib.sql.service_role_bypass("billing_events",
-- schema="public")` (Wave 0 helper, commit `b76c43f`). The keeper
-- detector (`check_admin_endpoint_service_role_bypass`) requires the
-- literal name `service_role_bypass` — renaming re-opens the finding.
--
-- Apply via Supabase MCP `apply_migration` to land on the live DB
-- ("MCP migrations mirror the file" rule).
-- ============================================================

CREATE TABLE IF NOT EXISTS public.billing_events (
    stripe_event_id    TEXT PRIMARY KEY,
    event_type         TEXT NOT NULL,
    stripe_customer_id TEXT,
    org_id             UUID,
    payload            JSONB NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for Stripe webhook query patterns: replay-detection by event
-- id is the PK (free); event-type funnels + per-customer/per-org audit
-- queries hit the remaining columns.
CREATE INDEX IF NOT EXISTS idx_billing_events_type        ON public.billing_events(event_type);
CREATE INDEX IF NOT EXISTS idx_billing_events_customer    ON public.billing_events(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_billing_events_org         ON public.billing_events(org_id);
CREATE INDEX IF NOT EXISTS idx_billing_events_created_at  ON public.billing_events(created_at);

ALTER TABLE public.billing_events ENABLE ROW LEVEL SECURITY;

-- Canonical service_role_bypass policy. Emitted byte-equal by
-- `noctusai_lib.sql.service_role_bypass("billing_events", schema="public")`.
-- The keeper detector matches the literal policy NAME — do not rename.
DROP POLICY IF EXISTS "service_role_bypass" ON public.billing_events;
CREATE POLICY "service_role_bypass" ON public.billing_events FOR ALL TO service_role USING (true) WITH CHECK (true);
