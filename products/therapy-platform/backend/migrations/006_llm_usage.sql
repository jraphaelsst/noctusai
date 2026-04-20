-- 006_llm_usage.sql
-- Per-clinic LLM token usage for the Therapy product.
--
-- Written by noctusai_lib.llm.usage.SupabaseUsageSink (service role) after
-- every successful provider call. Read via the shared /api/llm/usage
-- endpoint (clinic-scoped RLS via therapy.current_clinic_id()) and the
-- Core /api/admin/llm-usage endpoint (platform-admin, service role).
--
-- Therapy's tenant key is clinic_id; stored under `org_id` column to keep
-- the shared sink contract uniform across products (mirrors the
-- therapy.llm_preferences convention from migration 005).
--
-- LGPD: counts + provider/model + clinic_id only. Never prompt or response
-- text. Clinical content paths pass cache=False AND never reach the sink
-- with prompt bodies.

CREATE TABLE IF NOT EXISTS therapy.llm_usage (
    id          BIGSERIAL PRIMARY KEY,
    org_id      UUID,                   -- maps to clinic_id in Therapy's model
    provider    TEXT NOT NULL,
    model       TEXT NOT NULL,
    operation   TEXT NOT NULL,
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    total_tokens        INTEGER,
    cost_estimate_usd   NUMERIC(12,6) NOT NULL DEFAULT 0,
    at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE therapy.llm_usage ENABLE ROW LEVEL SECURITY;

-- SELECT: clinic users see only their clinic's rows via JWT clinic_id.
CREATE POLICY "llm_usage_select_own_clinic" ON therapy.llm_usage
    FOR SELECT
    USING (
        org_id IS NOT NULL AND org_id = therapy.current_clinic_id()
    );

CREATE INDEX IF NOT EXISTS llm_usage_org_at_idx
    ON therapy.llm_usage (org_id, at DESC);
CREATE INDEX IF NOT EXISTS llm_usage_provider_model_idx
    ON therapy.llm_usage (provider, model);
CREATE INDEX IF NOT EXISTS llm_usage_at_idx
    ON therapy.llm_usage (at DESC);

COMMENT ON TABLE therapy.llm_usage IS
    'LLM token usage + cost estimate per Therapy clinic. Written by SupabaseUsageSink (service role). LGPD: no prompt/response text stored.';
