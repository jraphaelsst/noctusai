-- ============================================================================
-- 005 — mailing.tool_call_audits (LLM tool-call audit trail)
-- ============================================================================
--
-- Per-product audit table consumed by the seed
-- `noctusai_lib.domain.ai.tool_audit.make_audit_writer(db, ToolCallAudit)`.
-- Shape mirrors `seed/lib/backend/noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template`
-- verbatim — JSONB args / result, started_at default, no archived_at TTL
-- column yet (retention sweep deferred to the audit-observability project).
--
-- Filed by `projects/llm-tool-audit-rollout/` Phase 3 (mailing rollout,
-- 2026-05-11). Reference adopter: media-scheduling.
--
-- LGPD: `arguments` and `result` JSONB columns may carry PII (campaign
-- copy, contact emails, list-member names). Mailing's per-feature
-- redactors in `app/services/ai_consent_features.py` scrub PII BEFORE
-- the AuditRecord lands here (`apply_feature_redaction(...)`).
-- ============================================================================

SET search_path = mailing, public;

CREATE TABLE IF NOT EXISTS mailing.tool_call_audits (
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

-- Indexes (verbatim from seed template) -----------------------------------
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_correlation_id
    ON mailing.tool_call_audits (correlation_id);

CREATE INDEX IF NOT EXISTS ix_tool_call_audits_user_started
    ON mailing.tool_call_audits (user_id, started_at);

CREATE INDEX IF NOT EXISTS ix_tool_call_audits_tool_name
    ON mailing.tool_call_audits (tool_name);

CREATE INDEX IF NOT EXISTS ix_tool_call_audits_status
    ON mailing.tool_call_audits (status);

CREATE INDEX IF NOT EXISTS ix_tool_call_audits_conversation
    ON mailing.tool_call_audits (conversation_id, started_at);


-- RLS ---------------------------------------------------------------------
-- Mailing is a marketer-tool; audits are admin-only. We keep RLS disabled
-- and route reads through the service_role admin client. If a marketer-
-- facing audit-history surface lands later, enable RLS + add a
-- `user_id = (SELECT id FROM auth.users WHERE auth.uid() = ...)`-style
-- policy per `KB § PATTERNS/database-rls.md`.
