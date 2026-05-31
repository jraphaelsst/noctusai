-- ============================================================================
-- tool_call_audits — per-product LLM tool-call audit trail
-- ============================================================================
--
-- Source: noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template
-- Rollout phase: `projects/llm-tool-audit-rollout/` Phase 4 — daily-life adoption.
--
-- One row per `audit_writer(record)` call (see noctusai_lib.domain.ai.tool_audit).
-- Captures successful, failing, and unknown-tool dispatches. Joinable to log
-- lines via correlation_id; joinable to the calling user via user_id; grouped
-- per-conversation via conversation_id.
--
-- Per the cross-product LGPD block: each product owns its own table. This
-- file is a verbatim copy of the seed template with `{{SCHEMA_NAME}}` →
-- `daily_life`. Apply via Supabase MCP per `KB § PATTERNS/database-rls.md`.
--
-- Retention: no automatic TTL in v1. The `archived_at` column is COMMENTED OUT
-- — uncomment when daily-life adopts a retention sweep.
--
-- LGPD: `arguments` and `result` JSONB columns carry personal narrative /
-- journal / task data. Daily Life's three consent features (daily_brief,
-- weekly_review, note_extract) register `redact_arguments` + `redact_result`
-- lambdas in `app/services/ai_consent_features.py` to scrub sensitive
-- content BEFORE the AuditRecord is constructed. See
-- `KB § PATTERNS/llm-tool-audit.md § LGPD redaction`.
-- ============================================================================

SET search_path = daily_life, public;

CREATE TABLE IF NOT EXISTS daily_life.tool_call_audits (
    id                BIGSERIAL PRIMARY KEY,
    correlation_id    VARCHAR(64),
    gpt_call_id       VARCHAR(64),
    tool_call_id      VARCHAR(64),
    conversation_id   VARCHAR(64),
    user_id           BIGINT,
    tool_name         VARCHAR(80) NOT NULL,
    status            VARCHAR(16) NOT NULL,
    arguments         JSONB,
    result            JSONB,
    error             TEXT,
    duration_ms       INTEGER,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    -- archived_at    TIMESTAMPTZ  -- uncomment when retention sweep ships
);

-- Indexes ---------------------------------------------------------------------
-- correlation_id: log-line joins (one of the two primary observability paths)
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_correlation_id
    ON daily_life.tool_call_audits (correlation_id);

-- (user_id, started_at): per-user time-window scans (BI / debugging "what did
-- user X do today")
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_user_started
    ON daily_life.tool_call_audits (user_id, started_at);

-- tool_name: per-tool failure-rate / call-volume scans
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_tool_name
    ON daily_life.tool_call_audits (tool_name);

-- status: error-rate scans, separates success vs failure vs unknown_tool
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_status
    ON daily_life.tool_call_audits (status);

-- conversation_id: per-conversation reconstruction (sorted tool sequence)
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_conversation
    ON daily_life.tool_call_audits (conversation_id, started_at);


-- RLS -------------------------------------------------------------------------
-- Daily-life's audit table is service-role-only in v1 (writes happen via the
-- audit_hook factory with the admin client). Per the seed canonical default
-- (tool_call_audits.sql.template), RLS ships ON (service_role bypasses → the
-- writer is unaffected; anon/auth denied) — no read policy = service_role-only.
ALTER TABLE daily_life.tool_call_audits ENABLE ROW LEVEL SECURITY;

-- Add a user-facing SELECT policy when the BI / "your AI activity" surface
-- ships. Reference shape (commented):
--
-- CREATE POLICY tool_call_audits_owner_select
--     ON daily_life.tool_call_audits
--     FOR SELECT
--     USING (user_id = (SELECT id FROM daily_life.noctus_users
--                       WHERE auth_user_id = auth.uid()));
--
-- See `KB § PATTERNS/database-rls.md` for the auth.uid() subquery rule.
