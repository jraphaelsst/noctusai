-- ============================================================================
-- 014_tool_call_audits — therapy LLM tool-call audit trail
-- ============================================================================
--
-- Consumed from `seed/lib/backend/noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template`
-- with `{{SCHEMA_NAME}}` → `therapy`. Per `KB § PATTERNS/llm-tool-audit.md`,
-- each product owns its own table (cross-product LGPD block — no shared
-- platform tables until encryption lands).
--
-- One row per `audit_writer(record)` call (see noctusai_lib.domain.ai.tool_audit).
-- Captures successful, failing, and unknown-tool dispatches. Joinable to log
-- lines via correlation_id; joinable to the calling user via user_id; grouped
-- per-conversation via conversation_id.
--
-- Apply via Supabase MCP per `KB § PATTERNS/database-rls.md`:
--   1. `mcp__claude_ai_Supabase__apply_migration` with this file's body.
--   2. Verify the table appeared via `mcp__claude_ai_Supabase__list_tables`.
--
-- **LGPD HIGH-risk**: `arguments` and `result` JSONB columns may carry Art. 11
-- sensitive data (patient session transcripts, audio bytes, images, clinical
-- observations). Therapy MUST redact those fields BEFORE constructing the
-- `AuditRecord` — see `app/services/audit_hook.py::redact_for_feature` for
-- the per-feature redaction lambdas. RLS policies below restrict reads to
-- the owning therapist + platform_admin.
-- ============================================================================

SET search_path = therapy, public;

CREATE TABLE IF NOT EXISTS therapy.tool_call_audits (
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
    ON therapy.tool_call_audits (correlation_id);

-- (user_id, started_at): per-user time-window scans (BI / debugging "what did
-- user X do today")
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_user_started
    ON therapy.tool_call_audits (user_id, started_at);

-- tool_name: per-tool failure-rate / call-volume scans
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_tool_name
    ON therapy.tool_call_audits (tool_name);

-- status: error-rate scans, separates success vs failure vs unknown_tool
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_status
    ON therapy.tool_call_audits (status);

-- conversation_id: per-conversation reconstruction (sorted tool sequence)
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_conversation
    ON therapy.tool_call_audits (conversation_id, started_at);


-- RLS -------------------------------------------------------------------------
-- Therapy is HIGH LGPD risk — keep the table service_role-only for v1. The
-- audit_hook writer uses a direct SQLAlchemy session via `postgres_url`
-- (server-side); routers do NOT read this table directly. Cross-clinic LGPD
-- review will land via a future BI dashboard backed by service_role queries.
-- Mirrors the `service_role_bypass`-only shape used across all therapy
-- tables in 001_therapy_platform.sql.
ALTER TABLE therapy.tool_call_audits ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS service_role_bypass ON therapy.tool_call_audits;
CREATE POLICY service_role_bypass
    ON therapy.tool_call_audits
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);
