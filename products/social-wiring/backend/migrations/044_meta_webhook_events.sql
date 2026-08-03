-- 044_meta_webhook_events.sql — durable inbox for inbound Meta Lead-Ads
-- webhook deliveries (roadmap `meta-ads-console-2026-07`, Phase 3.2).
--
-- WHY AN INBOX AT ALL. Meta's delivery contract is unforgiving in both
-- directions: it RETRIES any non-2xx with backoff and will eventually
-- DISABLE the subscription, and it NEVER re-sends after a 200. So a
-- receiver has exactly one safe shape — verify the signature, persist the
-- raw payload, return 200, then process. Without this table, a transient
-- Graph error while enriching `leadgen_id` → lead PII loses that lead
-- permanently; returning 500 instead trades permanent loss for a retry
-- storm that can cost us the whole subscription. This table converts an
-- unrecoverable delivery into a replayable row.
--
-- It also answers the question today's setup cannot: "did Meta actually
-- call us?" The 2026-08-03 investigation could only observe a silently
-- stale `meta_ads_leads.synced_at` and had no way to distinguish "no leads
-- arrived" from "deliveries arrived and we dropped them."
--
-- SHAPE — modelled on `products/core/backend/migrations/029_billing_events.sql`
-- (the platform's only other true inbound-webhook inbox): a NATURAL-KEY
-- primary key for replay dedup + the verified payload as `jsonb`. Diverges
-- from 029 by adding `status`/`attempts`/`error`/`processed_at`, because
-- 029 is a pure audit log while this is a WORK QUEUE — the `*/15` retry job
-- drains it.
--
-- `id` is Meta's own `leadgen_id` (globally unique), so the PK IS the
-- idempotency guarantee: a duplicate delivery conflicts and short-circuits
-- before it can re-hit Graph or re-notify the operator. This is the second
-- of three dedup layers (Redis SETNX pre-filter → this PK → the
-- `meta_ads_leads.id` upsert), and the only one that survives a restart.
--
-- `org_id` is NULLABLE ON PURPOSE. A delivery whose page cannot be mapped
-- to an org lands `status='unresolved'` with a null org rather than being
-- guessed into one — writing one tenant's lead PII into another tenant's
-- RLS scope is the exact failure the 2026-07-23 scheduler fix exists to
-- prevent. The row stays replayable once the mapping is configured.
--
-- LGPD: `payload` contains lead PII (name/phone/email). The DURABLE copy
-- lives in `meta_ads_leads`; this row exists only for delivery-debugging
-- and replay, so it has no reason to outlive that window. The retry job
-- purges `status='processed'` rows older than 90 days — deliberately the
-- same horizon as Meta's own lead retention, so we never hold lead PII in
-- the inbox longer than Meta itself does.
--
-- RLS shape mirrors 033_meta_ads_leads.sql exactly: authenticated reads
-- via `public.current_org_id()` (SECURITY DEFINER, resolves the caller's
-- org from `public.noctus_users` — NEVER `auth.jwt()` / `user_metadata`,
-- per `memory/feedback_rls_never_key_on_user_metadata.md`); service_role
-- ALL for the receiver's admin-client writes. Policy naming follows this
-- product's dominant `<table>_service_role` convention (59 uses vs 11 of
-- the `service_role_bypass` literal), matching sibling migration 033.
--
-- PREREQUISITE: public.current_org_id() (011_rls_current_org_id.sql).
-- Forward-only + idempotent (IF NOT EXISTS / DROP POLICY IF EXISTS).
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply
-- via noctus.dev.migrate_product with explicit tech-lead consent.

SET search_path = social_wiring, public;

-- ─── meta_webhook_events ────────────────────────────────────────────────
-- One row per inbound `leadgen` delivery, keyed on Meta's lead id.
CREATE TABLE IF NOT EXISTS social_wiring.meta_webhook_events (
    id            TEXT PRIMARY KEY,          -- Meta leadgen_id (natural dedup key)
    org_id        UUID,                      -- NULL ⇒ status='unresolved' (never guessed)
    page_id       TEXT,
    form_id       TEXT,
    ad_id         TEXT,
    object_type   TEXT NOT NULL DEFAULT 'page',
    field         TEXT NOT NULL DEFAULT 'leadgen',
    created_time  TIMESTAMPTZ,               -- Meta's value.created_time (submission)
    payload       JSONB NOT NULL,            -- the verified changes[].value, lossless
    status        TEXT NOT NULL DEFAULT 'received',
    error         TEXT,
    attempts      INTEGER NOT NULL DEFAULT 0,
    received_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at  TIMESTAMPTZ,
    CONSTRAINT meta_webhook_events_status_chk CHECK (
        status IN ('received', 'processed', 'error', 'unresolved', 'ignored')
    )
);

ALTER TABLE social_wiring.meta_webhook_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "meta_webhook_events_select_own_org" ON social_wiring.meta_webhook_events;
CREATE POLICY "meta_webhook_events_select_own_org" ON social_wiring.meta_webhook_events
    FOR SELECT
    TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "meta_webhook_events_service_role" ON social_wiring.meta_webhook_events;
CREATE POLICY "meta_webhook_events_service_role" ON social_wiring.meta_webhook_events
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- The retry job's exact predicate: pending work, oldest first. Partial so
-- the index stays small — the steady state is that almost every row is
-- 'processed' and therefore not in it.
CREATE INDEX IF NOT EXISTS idx_sw_meta_webhook_events_pending
    ON social_wiring.meta_webhook_events (status, received_at)
    WHERE status IN ('received', 'error', 'unresolved');

-- Operator-facing health panel: "what arrived recently, for my org".
CREATE INDEX IF NOT EXISTS idx_sw_meta_webhook_events_org_time
    ON social_wiring.meta_webhook_events (org_id, received_at DESC);

-- Page-scoped lookups when diagnosing "is this Page's subscription live?"
CREATE INDEX IF NOT EXISTS idx_sw_meta_webhook_events_page
    ON social_wiring.meta_webhook_events (page_id);

-- The 90-day LGPD purge scans by age within the processed set.
CREATE INDEX IF NOT EXISTS idx_sw_meta_webhook_events_processed_at
    ON social_wiring.meta_webhook_events (processed_at)
    WHERE status = 'processed';

COMMENT ON TABLE social_wiring.meta_webhook_events IS
    'Durable inbox for inbound Meta Lead-Ads webhook deliveries. PK = Meta leadgen_id '
    '(replay dedup). Persist-then-200: Meta retries non-2xx and can disable the '
    'subscription, so processing failures are recorded here and re-driven by the '
    'meta_leadgen_retry job, never surfaced as a non-2xx. payload is lead PII — '
    'purged 90d after processing (durable copy lives in meta_ads_leads).';

NOTIFY pgrst, 'reload schema';
