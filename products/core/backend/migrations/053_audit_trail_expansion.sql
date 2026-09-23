-- ============================================================================
-- 053_audit_trail_expansion — audit_logs becomes the platform action-history
-- trail (owner directive, 2026-09-23: "the system should log it and record
-- history of actions for everything"). Slice S1 (core).
-- ============================================================================
--
-- `public.audit_logs` (001_noctusai_core.sql / 002_missing_tables.sql) was a
-- narrow security-audit table: who did what to which resource. This widens
-- it into a general request/action trail without breaking any existing
-- reader or writer (`app/services/audit_service.py::log()`, the two
-- `/api/audit-logs` routers — both `SELECT *`).
--
-- WHAT
--   1. New columns: request shape (method / route_template / path_params /
--      status_code / duration_ms), cross-call correlation (correlation_id),
--      actor classification (role / actor_kind — a user, an autonomous
--      agent, and a service-to-service call are NOT the same kind of actor),
--      client_hint (coarse UA/platform hint — see LGPD note below), and
--      before_snapshot (diffable history for updates).
--   2. Two new indexes matching the query shapes the product/resource lookup
--      and cross-call correlation need. `(org_id, created_at desc)` already
--      exists as `idx_audit_logs_org` (002) — not re-declared here.
--   3. Retention: `retention_until` (400 days from `created_at`, same
--      column-based-window shape as `009_webhook_retention.sql`'s
--      `webhook_deliveries.retention_until`).
--   4. Append-only: `audit_logs` becomes write-once. UPDATE is refused
--      unconditionally; DELETE is refused UNLESS the transaction-local flag
--      `core.audit_log_purge` is 'on' — the exact escape-hatch shape
--      `agents.guard_compiled_prompt_immutable` /
--      `agents.erase_compiled_prompts` established
--      (012_agent_studio_definitions.sql): the guard function checks the
--      flag, the SECURITY DEFINER purge function is the ONLY thing allowed
--      to set it. Unlike `webhook_deliveries` (no such guard — a plain
--      service-role DELETE purges it), `audit_logs` cannot be deleted by ANY
--      path except `public.purge_expired_audit_logs()`.
--
-- LGPD — ids only. This table stores identifiers (user_id, org_id,
-- resource_id, correlation_id) and structural request metadata (method,
-- route_template, status_code, duration_ms, role, actor_kind), never raw
-- personal data as a first-class column. `details` / `path_params` /
-- `before_snapshot` are free-form JSONB the CALLER populates — callers MUST
-- pass ids/enums/counts there, never PII payloads (name, CPF, email body,
-- full request body, ...); a migration cannot enforce JSONB *contents* at
-- the column level, so this is a caller-discipline note for every
-- `audit_service.log()` call site, not a DB guard. `client_hint` is a
-- coarse platform/browser-family hint (e.g. "web/chrome"), never the raw
-- User-Agent string (`user_agent`, already on the table since 001/002,
-- carries that). Retention (below) is the other LGPD lever: nothing here
-- lives forever.
--
-- `noctus.dev.verify_db_guards` probes `audit_logs.update_refused` /
-- `audit_logs.delete_refused_outside_purge` (mcp/noctusai/tools/noctus/dev/
-- verify_db_guards.py) prove the trigger actually refuses, not just that it
-- exists (KB § PATTERNS/common/methodology-execution-discipline.md § 8).
-- ============================================================================

-- ── Request / actor / history columns ───────────────────────────────────────

ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS product_slug TEXT;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS method TEXT;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS route_template TEXT;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS path_params JSONB NOT NULL DEFAULT '{}';
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS status_code INT;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS correlation_id TEXT;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS role TEXT;

-- `ADD COLUMN IF NOT EXISTS ... CHECK (...)` in one statement, on purpose:
-- an unnamed inline column-CHECK (never `ADD CONSTRAINT`), the three actors
-- this trail distinguishes — a user click, an autonomous agent turn, and a
-- service-to-service call are not the same kind of actor. Idempotent via
-- `IF NOT EXISTS` on the column itself (Postgres has no `ADD CONSTRAINT IF
-- NOT EXISTS`). `check_migration_guard_has_probe` deliberately does not
-- detect an unnamed column-level CHECK (documented limitation, its own
-- docstring) — no `noctus.dev.verify_db_guards` probe is required for this
-- specific shape, and the CHECK is exercised for free by every real INSERT
-- once `actor_kind` starts being populated.
ALTER TABLE public.audit_logs
    ADD COLUMN IF NOT EXISTS actor_kind TEXT NOT NULL DEFAULT 'user'
        CHECK (actor_kind IN ('user', 'agent', 'service'));

ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS client_hint TEXT;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS duration_ms INT;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS before_snapshot JSONB NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_audit_logs_product_resource
    ON public.audit_logs (product_slug, resource_type, resource_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_correlation
    ON public.audit_logs (correlation_id);

-- ── Retention (400 days — 009_webhook_retention.sql's column-window shape) ─

ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS retention_until TIMESTAMPTZ;

UPDATE public.audit_logs
SET retention_until = created_at + INTERVAL '400 days'
WHERE retention_until IS NULL;

ALTER TABLE public.audit_logs
    ALTER COLUMN retention_until SET DEFAULT (now() + INTERVAL '400 days');

ALTER TABLE public.audit_logs
    ALTER COLUMN retention_until SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_audit_logs_retention
    ON public.audit_logs (retention_until);

-- ── Append-only guard ────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.guard_audit_logs_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('core.audit_log_purge', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'audit_logs_append_only' USING ERRCODE = 'P0001';
END;
$$;

REVOKE ALL ON FUNCTION public.guard_audit_logs_append_only() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.guard_audit_logs_append_only() TO service_role;

DROP TRIGGER IF EXISTS guard_audit_logs_append_only ON public.audit_logs;
CREATE TRIGGER guard_audit_logs_append_only
    BEFORE UPDATE OR DELETE ON public.audit_logs
    FOR EACH ROW EXECUTE FUNCTION public.guard_audit_logs_append_only();

-- ── Purge — the ONLY allowed delete path ────────────────────────────────

-- `p_batch_limit` caps a single sweep so a large backlog doesn't hold the
-- row-level locks open for an unbounded DELETE — same batching rationale
-- `webhook_retention_service.purge_expired_deliveries(limit=1000)` uses,
-- just enforced server-side here since the client can no longer DELETE
-- directly at all.
CREATE OR REPLACE FUNCTION public.purge_expired_audit_logs(p_batch_limit INT DEFAULT 5000)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_count INT;
BEGIN
    PERFORM set_config('core.audit_log_purge', 'on', true);
    DELETE FROM public.audit_logs
    WHERE id IN (
        SELECT id FROM public.audit_logs
        WHERE retention_until < now()
        ORDER BY retention_until
        LIMIT p_batch_limit
    );
    GET DIAGNOSTICS v_count = ROW_COUNT;
    PERFORM set_config('core.audit_log_purge', 'off', true);
    RETURN v_count;
END;
$$;

REVOKE ALL ON FUNCTION public.purge_expired_audit_logs(INT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.purge_expired_audit_logs(INT) TO service_role;
