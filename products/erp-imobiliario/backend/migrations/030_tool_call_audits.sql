-- ============================================================================
-- 030_tool_call_audits.sql — LLM tool-call audit trail
-- ============================================================================
--
-- Adds `erp.tool_call_audits` per the canonical seed template at
-- `noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template`. One row
-- per `audit_writer(record)` call (see noctusai_lib.domain.ai.tool_audit).
-- Captures successful, failing, and unknown-tool dispatches across every
-- ERP LLM dispatch site (9 chat-completion sites in app/services/ai_service.py
-- + the certidoes / matricula sites refactored in Step A of the rollout).
--
-- Joinable to log lines via correlation_id; joinable to the calling user via
-- user_id (BIGINT — no FK to auth.users since ERP keys on auth_user_id UUIDs
-- in Supabase, see app/models/tool_call_audit.py docstring); grouped
-- per-conversation via conversation_id.
--
-- LGPD: `arguments` and `result` JSONB columns may carry PII (ERP touches
-- real-estate / client / financial data — addresses, CPF/CNPJ, lease terms).
-- Products handling sensitive data MUST redact those fields BEFORE
-- constructing the AuditRecord. See `KB § PATTERNS/llm-tool-audit.md § LGPD`.
-- Per-feature redaction lambdas land at `app/services/ai_consent_features.py`
-- once the seed `register_feature(...)` signature is extended to accept
-- `redact_arguments=` + `redact_result=` kwargs (rollout Phase 1 dependency).
--
-- Retention: no automatic TTL in v1. archived_at column reserved for the
-- future retention sweep but not added — uncomment when the cross-product
-- llm-audit-retention project ships (PROJECT.md §7 Q3).
-- ============================================================================

SET search_path = erp, public;

CREATE TABLE IF NOT EXISTS erp.tool_call_audits (
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
);

-- Indexes ---------------------------------------------------------------------
-- correlation_id: log-line joins (primary observability path)
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_correlation_id
    ON erp.tool_call_audits (correlation_id);

-- (user_id, started_at): per-user time-window scans (BI / debugging
-- "what did user X do today")
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_user_started
    ON erp.tool_call_audits (user_id, started_at);

-- tool_name: per-tool failure-rate / call-volume scans
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_tool_name
    ON erp.tool_call_audits (tool_name);

-- status: error-rate scans, separates success vs failure vs unknown_tool
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_status
    ON erp.tool_call_audits (status);

-- conversation_id: per-conversation reconstruction (sorted tool sequence)
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_conversation
    ON erp.tool_call_audits (conversation_id, started_at);


-- RLS -------------------------------------------------------------------------
-- ERP uses service_role_bypass per `KB § PATTERNS/database-rls.md`. The audit
-- table is written exclusively by the backend (via SQLAlchemy bound to
-- `postgres_url`) and read only via service-role admin queries / BI tooling.
-- No user-facing SELECT path lands in the API surface. Per the seed canonical
-- default (tool_call_audits.sql.template), RLS ships ON (service_role bypasses →
-- the backend writer is unaffected; anon/auth denied) — no read policy =
-- service_role-only. If a user-facing audit-history endpoint is added later,
-- add a SELECT policy scoped by `user_id` joined to `erp.profiles.user_id`.
ALTER TABLE erp.tool_call_audits ENABLE ROW LEVEL SECURITY;
