-- ============================================================================
-- 011_tool_call_audits.sql — per-product LLM tool-call audit trail (PF)
-- ============================================================================
-- Project: llm-tool-audit-rollout Phase 4 (Engineer LLM-PF, 2026-05-11).
-- Source: noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template
-- Shape mirrors the canonical seed template verbatim (column names + types +
-- index set); see media-scheduling/migrations/002_initial_schema.sql §13 for
-- the reference adopter pattern.
--
-- One row per `audit_writer(record)` call (see noctusai_lib.domain.ai.tool_audit
-- and `app.services.audit_hook` + the wrappers in `app.services.ai_service` /
-- `app.services.monthly_narrative_service`). Captures successful, failing,
-- and unknown-tool dispatches. Joinable to log lines via correlation_id;
-- grouped per-conversation via conversation_id (currently null in PF — no
-- chatbot framework yet, only HTTP endpoints).
--
-- LGPD: PF is finance-sensitive. `arguments` / `result` JSONB rows ARE
-- scrubbed at the dispatch site BEFORE this table is touched, via the
-- `redact_arguments` / `redact_result` callables registered alongside each
-- feature in `app.services.ai_consent_features`. The audit row therefore
-- keeps structural metadata (counts, category names, confidence, prompt
-- version, model_version) — never raw transaction descriptions, account
-- balances, or income figures. Over-redaction is the default for features
-- without a registered scrubber (`audit_hook.build_audit_record`).
--
-- Retention: no automatic TTL in v1. The `archived_at` column is COMMENTED OUT
-- — uncomment when the cross-product retention sweep ships (see PROJECT.md
-- §7 Q3). Until then rows persist indefinitely.
-- ============================================================================

SET search_path = "personal-finance", public;

CREATE TABLE IF NOT EXISTS "personal-finance".tool_call_audits (
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

-- Indexes (verbatim from seed template) -------------------------------------
-- correlation_id: log-line joins (primary observability path)
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_correlation_id
    ON "personal-finance".tool_call_audits (correlation_id);

-- (user_id, started_at): per-user time-window scans (BI / "what did user X do today")
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_user_started
    ON "personal-finance".tool_call_audits (user_id, started_at);

-- tool_name: per-tool failure-rate / call-volume scans
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_tool_name
    ON "personal-finance".tool_call_audits (tool_name);

-- status: error-rate scans, separates success vs failure vs unknown_tool
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_status
    ON "personal-finance".tool_call_audits (status);

-- conversation_id: per-conversation reconstruction (sorted tool sequence)
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_conversation
    ON "personal-finance".tool_call_audits (conversation_id, started_at);


-- Service-role bypass --------------------------------------------------------
-- The audit writer runs under the product's admin/service connection (the
-- SQLAlchemy engine in `app.services.audit_hook`). No RLS in v1 — PF's
-- user-facing routes never read this table; BI surfaces will land in a
-- separate project per PROJECT.md §4 out-of-scope.

GRANT INSERT, SELECT ON "personal-finance".tool_call_audits TO service_role;
GRANT USAGE, SELECT ON SEQUENCE "personal-finance".tool_call_audits_id_seq TO service_role;
