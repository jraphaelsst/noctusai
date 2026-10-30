-- Migration: 090_scheduler_runs
-- Schema: public (core)
--
-- WHAT: the fleet-wide scheduler run ledger behind core's Operação page and the owner daily brief.
--   1. public.scheduler_runs  — one row per finished run of a job registered on the seed scheduler
--                               (noctusai_lib.api.scheduler), written by every product through
--                               noctusai_lib.domain.scheduler_runs.SupabaseRunLedger (service role).
--                               `alerted` = this failed run notified the platform admins (dedupe: one
--                               alert per product+job per 6h, read off this column).
--   2. public.scheduler_jobs  — each product's registered schedules (cron or interval), upserted when
--                               its scheduler starts; `last_seen_at` = that product last booted with it.
--   3. public.owner_briefs    — the owner daily brief (code-only composition, no LLM): one row per
--                               generated brief with its structured payload + rendered text and how
--                               it was delivered. The brief job ALSO lands in scheduler_runs (it is a
--                               seed-scheduler job), which is what the Operação dead-man reads.
--   4. access: service role only (the backend reads for platform admins; no browser grant).
-- Retention: core job `core_scheduler_runs_retention` (ok/skipped 14 days, error 90 days).
-- Re-runnable: IF NOT EXISTS / DROP-then-CREATE POLICY.
SET search_path = public, public;

-- ── 1. runs ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.scheduler_runs (
    id           BIGSERIAL PRIMARY KEY,
    product      TEXT NOT NULL CHECK (length(product) BETWEEN 1 AND 100),
    job          TEXT NOT NULL CHECK (length(job) BETWEEN 1 AND 200),
    started_at   TIMESTAMPTZ NOT NULL,
    finished_at  TIMESTAMPTZ NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('ok', 'error', 'skipped')),
    error        TEXT CHECK (error IS NULL OR length(error) <= 1000),
    duration_ms  INTEGER NOT NULL DEFAULT 0 CHECK (duration_ms >= 0),
    alerted      BOOLEAN NOT NULL DEFAULT false,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (finished_at >= started_at)
);
COMMENT ON TABLE public.scheduler_runs IS
    'One row per finished seed-scheduler job run, every product (noctusai_lib.domain.scheduler_runs). '
    'error text is redacted + capped by the writer. Service role only.';

CREATE INDEX IF NOT EXISTS ix_scheduler_runs_product_job_started
    ON public.scheduler_runs (product, job, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_scheduler_runs_started
    ON public.scheduler_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS ix_scheduler_runs_errors
    ON public.scheduler_runs (started_at DESC) WHERE status = 'error';

-- ── 2. registered schedules ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.scheduler_jobs (
    product             TEXT NOT NULL CHECK (length(product) BETWEEN 1 AND 100),
    job                 TEXT NOT NULL CHECK (length(job) BETWEEN 1 AND 200),
    cron                TEXT,
    interval_seconds    INTEGER CHECK (interval_seconds IS NULL OR interval_seconds > 0),
    timezone            TEXT,
    misfire_grace_time  INTEGER NOT NULL DEFAULT 30,
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (product, job),
    CHECK ((cron IS NULL) <> (interval_seconds IS NULL))
);
COMMENT ON TABLE public.scheduler_jobs IS
    'Each product''s seed-scheduler schedules, upserted at scheduler start. Service role only.';

-- ── 3. owner daily brief ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.owner_briefs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    period_start      TIMESTAMPTZ NOT NULL,
    period_end        TIMESTAMPTZ NOT NULL,
    trigger           TEXT NOT NULL DEFAULT 'schedule' CHECK (trigger IN ('schedule', 'manual')),
    payload           JSONB NOT NULL DEFAULT '{}'::jsonb,
    text_body         TEXT NOT NULL DEFAULT '',
    exceptions_count  INTEGER NOT NULL DEFAULT 0 CHECK (exceptions_count >= 0),
    in_app_sent       INTEGER NOT NULL DEFAULT 0 CHECK (in_app_sent >= 0),
    email_status      TEXT NOT NULL DEFAULT 'not_sent'
        CHECK (email_status IN ('sent', 'failed', 'not_configured', 'not_sent')),
    CHECK (period_end >= period_start)
);
COMMENT ON TABLE public.owner_briefs IS
    'Owner daily brief (core job core_owner_daily_brief, 07:00 platform tz). Code-only, zero LLM spend. Service role only.';
CREATE INDEX IF NOT EXISTS ix_owner_briefs_generated ON public.owner_briefs (generated_at DESC);

-- ── 4. access ───────────────────────────────────────────────────────────────────
ALTER TABLE public.scheduler_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scheduler_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.owner_briefs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.scheduler_runs FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.scheduler_jobs FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.owner_briefs FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.scheduler_runs TO service_role;
GRANT ALL ON public.scheduler_jobs TO service_role;
GRANT ALL ON public.owner_briefs TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.scheduler_runs_id_seq TO service_role;

DROP POLICY IF EXISTS "service_role_bypass" ON public.scheduler_runs;
CREATE POLICY "service_role_bypass" ON public.scheduler_runs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON public.scheduler_jobs;
CREATE POLICY "service_role_bypass" ON public.scheduler_jobs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON public.owner_briefs;
CREATE POLICY "service_role_bypass" ON public.owner_briefs
    FOR ALL TO service_role USING (true) WITH CHECK (true);
