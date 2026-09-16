-- 121_jobs.sql -- social_wiring: generic background-job queue
--
-- Numbering: SW next-free was re-verified twice during this slice. The
-- approved plan said 119; PROJECT.md's Wave 1 note moved next-free to 119
-- (114-118 applied); the dispatching tech-lead then reported 119 AND 120
-- claimed by a parallel slice (feat/sw-contract-docx-identity-docs: rg/cpf
-- activation + contrato_versao_docx_artifact) not yet visible on disk/
-- origin/dev at write time -- so this migration starts at 121, the
-- tech-lead's corrected number, not the 120 this file was originally
-- authored as.
--
-- Instantiated from noctusai_lib/domain/jobs/migrations/jobs.sql.template
-- (Wave 1 slice S1, edicao-fotos), {{SCHEMA_NAME}} -> social_wiring, no
-- other changes. Backs fotos.* job types (fotos.ingest, fotos.submit_lote,
-- fotos.edit, fotos.poll_openai_batch, fotos.avaliar, fotos.lote_pronto,
-- fotos.regen_guia, fotos.propor_regras, fotos.fx_backfill -- W3+, this
-- migration only ships the table + RPCs).
--
-- 🔴 NOT A NEW QUEUE: social_wiring already runs scheduler-driven workers
-- for other modules (services/imoveis_sync_scheduler.py, scheduling/retry.py)
-- against their OWN tables. This is the seed-generic jobs queue -- the
-- edicao-fotos pipeline is its first social_wiring consumer.
--
-- FORWARD-ONLY. MIGRATION FILE ONLY -- not applied to any database by this
-- change. Applying needs owner consent.

-- ============================================================================
-- jobs — generic background-job queue (Job / JobRepository / Worker)
-- ============================================================================
--
-- Source: noctusai_lib/domain/jobs/migrations/jobs.sql.template
--
-- Backs `noctusai_lib.domain.jobs.repo.RealSupabaseJobRepository`. Copy this
-- template into `products/<your-product>/backend/migrations/NNN_jobs.sql`,
-- substitute `social_wiring` with the product schema, renumber if needed —
-- same recipe as `domain/ai/migrations/tool_call_audits.sql.template`.
--
-- Apply via Supabase MCP per `KB § PATTERNS/database-rls.md`:
--   1. Land this file in the product's migrations/.
--   2. Apply via `mcp__claude_ai_Supabase__apply_migration`.
--   3. Verify the table + the four functions appeared with
--      `mcp__claude_ai_Supabase__list_tables` / a `\df` check.
--
-- Hardening (S1, edicao-fotos, 2026-09):
--   - `dedupe_key` — idempotent re-enqueue. NULL-distinct under the UNIQUE
--     index, so job types that don't dedupe are unaffected.
--   - `worker_id` + `lease_expires_at` — a claimed job survives a worker
--     dying mid-processing: `claim_next_job` reclaims a RUNNING row once
--     its lease has expired, exactly like a fresh PENDING row.
--   - `fail_job` decides retry-vs-dead-letter AND schedules the backoff in
--     ONE `UPDATE ... RETURNING *` — no consumer-side read-then-write race
--     window between two workers failing the same job concurrently.
--
-- LGPD: `payload` / `last_error` JSONB/TEXT columns may carry PII depending
-- on the job type (e.g. an uploaded photo's storage path, a customer's
-- error message). Products handling Art. 11 sensitive data MUST redact
-- before enqueueing. See `KB § PATTERNS/llm-tool-audit.md § LGPD` for the
-- analogous redaction discipline on the audit-trail table.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.jobs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type              TEXT NOT NULL,
    payload           JSONB NOT NULL DEFAULT '{}'::jsonb,
    status            TEXT NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'running', 'completed', 'failed', 'dead_letter')),
    retry_count       INT NOT NULL DEFAULT 0,
    max_retries       INT NOT NULL DEFAULT 3,
    last_error        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    scheduled_for     TIMESTAMPTZ,
    dedupe_key        TEXT,
    worker_id         TEXT,
    lease_expires_at  TIMESTAMPTZ
);

-- Indexes ---------------------------------------------------------------------

-- Idempotency: one row per logical unit of work. Postgres treats multiple
-- NULLs as distinct under a UNIQUE index, so job types that never set
-- `dedupe_key` are completely unaffected.
CREATE UNIQUE INDEX IF NOT EXISTS ux_jobs_dedupe_key
    ON social_wiring.jobs (dedupe_key);

-- `claim_next_job`'s PENDING-and-due branch (status filter + ORDER BY).
CREATE INDEX IF NOT EXISTS ix_jobs_status_scheduled
    ON social_wiring.jobs (status, scheduled_for, created_at);

-- `claim_next_job`'s RUNNING-with-expired-lease reclaim branch.
CREATE INDEX IF NOT EXISTS ix_jobs_status_lease
    ON social_wiring.jobs (status, lease_expires_at);

-- Per-type filtering (`job_types` in claim_next_job; `list_dead_letters`).
CREATE INDEX IF NOT EXISTS ix_jobs_type
    ON social_wiring.jobs (type);


-- RPCs --------------------------------------------------------------------
-- All four are SECURITY INVOKER (the default) — called by the backend's
-- service_role Supabase client, which bypasses RLS on every statement
-- inside the function body same as it would on a direct query.


-- claim_next_job — FOR UPDATE SKIP LOCKED so two workers racing on the
-- same pending job never both receive it. Single UPDATE; the subquery's
-- FOR UPDATE SKIP LOCKED lock is held for the statement's duration only.
CREATE OR REPLACE FUNCTION social_wiring.claim_next_job(
    p_worker_id     TEXT,
    p_job_types     TEXT[] DEFAULT NULL,
    p_lease_seconds NUMERIC DEFAULT 600
) RETURNS SETOF social_wiring.jobs
LANGUAGE plpgsql
AS $$
DECLARE
    v_now TIMESTAMPTZ := now();
BEGIN
    RETURN QUERY
    UPDATE social_wiring.jobs
    SET status = 'running',
        worker_id = p_worker_id,
        lease_expires_at = v_now + make_interval(secs => p_lease_seconds),
        updated_at = v_now
    WHERE id = (
        SELECT id
        FROM social_wiring.jobs
        WHERE (
                (status = 'pending' AND (scheduled_for IS NULL OR scheduled_for <= v_now))
                -- Reclaim: the previous worker died mid-job without
                -- completing, failing, or heartbeating via extend_lease.
                OR (status = 'running' AND lease_expires_at IS NOT NULL AND lease_expires_at <= v_now)
              )
          AND (p_job_types IS NULL OR type = ANY (p_job_types))
        ORDER BY created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING *;
END;
$$;


-- fail_job — the retry-vs-dead-letter decision AND the backoff-scheduled
-- requeue, computed against the row's OWN current retry_count inside this
-- one UPDATE. No consumer-side SELECT precedes it — the read-then-write
-- race the previous shape had (SELECT the row, decide in Python, UPDATE)
-- is closed: two concurrent failures of the same job can no longer both
-- decide "retries remain" off a stale retry_count.
CREATE OR REPLACE FUNCTION social_wiring.fail_job(
    p_job_id              UUID,
    p_error               TEXT,
    p_max_retries         INT,
    p_backoff_seconds     NUMERIC,
    p_backoff_multiplier  NUMERIC,
    p_max_backoff_seconds NUMERIC,
    p_dead_letter         BOOLEAN DEFAULT FALSE
) RETURNS SETOF social_wiring.jobs
LANGUAGE plpgsql
AS $$
DECLARE
    v_now TIMESTAMPTZ := now();
BEGIN
    RETURN QUERY
    UPDATE social_wiring.jobs
    SET status = CASE
            WHEN p_dead_letter OR retry_count >= p_max_retries THEN 'dead_letter'
            ELSE 'pending'
        END,
        retry_count = CASE
            WHEN p_dead_letter OR retry_count >= p_max_retries THEN retry_count
            ELSE retry_count + 1
        END,
        scheduled_for = CASE
            WHEN p_dead_letter OR retry_count >= p_max_retries THEN scheduled_for
            ELSE v_now + make_interval(
                secs => LEAST(
                    p_backoff_seconds * (p_backoff_multiplier ^ retry_count),
                    p_max_backoff_seconds
                )
            )
        END,
        last_error = p_error,
        worker_id = NULL,
        lease_expires_at = NULL,
        updated_at = v_now
    WHERE id = p_job_id
    RETURNING *;
END;
$$;


-- complete_job — terminal status + lease release in one statement.
-- Idempotent: a job already COMPLETED is left untouched and the current
-- row is still returned (mirrors FakeJobRepository.mark_completed's
-- no-op-on-already-terminal contract).
CREATE OR REPLACE FUNCTION social_wiring.complete_job(
    p_job_id UUID
) RETURNS SETOF social_wiring.jobs
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    UPDATE social_wiring.jobs
    SET status = 'completed',
        worker_id = NULL,
        lease_expires_at = NULL,
        updated_at = now()
    WHERE id = p_job_id AND status <> 'completed'
    RETURNING *;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT * FROM social_wiring.jobs WHERE id = p_job_id AND status = 'completed';
    END IF;
END;
$$;


-- extend_lease — heartbeat. Only succeeds while `p_worker_id` still holds
-- the job (status RUNNING AND worker_id match); otherwise returns zero
-- rows, which `RealSupabaseJobRepository.extend_lease` turns into
-- `LeaseLostError` — the caller must abandon its in-flight work because
-- another worker has already reclaimed the job via `claim_next_job`.
CREATE OR REPLACE FUNCTION social_wiring.extend_lease(
    p_job_id        UUID,
    p_worker_id     TEXT,
    p_lease_seconds NUMERIC DEFAULT 600
) RETURNS SETOF social_wiring.jobs
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    UPDATE social_wiring.jobs
    SET lease_expires_at = now() + make_interval(secs => p_lease_seconds),
        updated_at = now()
    WHERE id = p_job_id AND status = 'running' AND worker_id = p_worker_id
    RETURNING *;
END;
$$;


-- RLS -------------------------------------------------------------------------
-- CANONICAL DEFAULT: RLS ON, no policies. A job queue is an internal
-- worker surface written/read by `service_role` (which BYPASSES RLS —
-- backend + the four RPC functions above are unaffected). With RLS
-- enabled and no policy, anon/authenticated are denied — the correct,
-- safe default for a table in an API-exposed schema. RLS-OFF here is an
-- `rls_disabled_in_public` advisor flag (the predeploy supabase_advisors
-- gate catches it), so the enable is NOT opt-in.
ALTER TABLE social_wiring.jobs ENABLE ROW LEVEL SECURITY;

-- Add a scoped SELECT policy ONLY if the product exposes job status to
-- end users directly (e.g. a "batch progress" UI polling job rows).
-- Default ships nothing:
--
-- CREATE POLICY jobs_owner_select
--     ON social_wiring.jobs
--     FOR SELECT
--     USING (payload->>'org_id' = (auth.jwt() ->> 'org_id'));
--
-- See `KB § PATTERNS/database-rls.md` for the auth.uid()/auth.jwt() rule.
