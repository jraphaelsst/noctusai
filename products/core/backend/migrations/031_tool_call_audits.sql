-- ============================================================================
-- 031_tool_call_audits — Core LLM tool-call audit trail
-- ============================================================================
--
-- Source template: noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template
-- (canonical seed shape). Per `KB § PATTERNS/llm-tool-audit.md`, each product
-- owns its own `tool_call_audits` table — the cross-product LGPD block
-- forbids a shared platform PII table until encryption lands.
--
-- Schema: core sits at `public` (no dedicated schema; see app/main.py
-- `schema="public"`). All other shape decisions mirror the seed template
-- verbatim. The `user_id` column stays BIGINT NULL per the seed
-- `AuditRecord.user_id: int | None` contract — core users are UUID-keyed in
-- `public.noctus_users(id UUID)`, so no FK; we capture identifying data
-- (correlation_id, conversation_id) for join paths instead.
--
-- LGPD: `arguments` + `result` may carry org / user / billing fields. Core's
-- audit-hook applies a feature-specific redaction lambda (see
-- `app/services/ai_consent_features.py: REDACT_AUDIT_DIGEST_ARGUMENTS` +
-- `REDACT_AUDIT_DIGEST_RESULT`) BEFORE the AuditRecord is constructed,
-- so the JSONB columns only ever receive scrubbed values.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.tool_call_audits (
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

-- Indexes — canonical seed template shape (verbatim).
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_correlation_id
    ON public.tool_call_audits (correlation_id);

CREATE INDEX IF NOT EXISTS ix_tool_call_audits_user_started
    ON public.tool_call_audits (user_id, started_at);

CREATE INDEX IF NOT EXISTS ix_tool_call_audits_tool_name
    ON public.tool_call_audits (tool_name);

CREATE INDEX IF NOT EXISTS ix_tool_call_audits_status
    ON public.tool_call_audits (status);

CREATE INDEX IF NOT EXISTS ix_tool_call_audits_conversation
    ON public.tool_call_audits (conversation_id, started_at);

-- RLS — admin-only read surface. Core's only dispatch site is the weekly
-- audit digest, run by an admin cron (no per-user surface today). When a
-- router exposes this table, add a policy keyed on `noctus_users.role='admin'`.
-- Per the seed canonical default (tool_call_audits.sql.template), RLS ships ON
-- (service_role bypasses → the digest cron is unaffected; anon/auth denied). No
-- read policy = service_role-only, which is exactly the admin-only surface here.
ALTER TABLE public.tool_call_audits ENABLE ROW LEVEL SECURITY;
