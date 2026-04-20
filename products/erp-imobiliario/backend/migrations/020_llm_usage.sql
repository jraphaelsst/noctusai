-- 020_llm_usage.sql
-- Per-org LLM token usage for the ERP product.
--
-- Written by noctusai_lib.llm.usage.SupabaseUsageSink (service role) after
-- every successful provider call. Read via the shared /api/llm/usage
-- endpoint (org-scoped RLS via public.current_org_id()) and the Core
-- /api/admin/llm-usage endpoint (platform-admin, service role).
--
-- LGPD: this table intentionally stores counts + model/provider + org_id
-- only. Never prompt or response text. See KB CONTEXT/PATTERNS/llm-usage.md.

CREATE TABLE IF NOT EXISTS erp.llm_usage (
    id          BIGSERIAL PRIMARY KEY,
    org_id      UUID,
    provider    TEXT NOT NULL,
    model       TEXT NOT NULL,
    operation   TEXT NOT NULL,          -- 'chat' | 'embedding' | 'audio' | 'vision'
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    total_tokens        INTEGER,
    cost_estimate_usd   NUMERIC(12,6) NOT NULL DEFAULT 0,
    at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE erp.llm_usage ENABLE ROW LEVEL SECURITY;

-- SELECT: users see rows matching their JWT org (current_org_id()); admins
-- see every row in their org regardless. Platform admin reads via service
-- role at the Core /api/admin/llm-usage endpoint.
CREATE POLICY "llm_usage_select_own_org" ON erp.llm_usage
    FOR SELECT
    USING (
        org_id IS NOT NULL AND org_id = public.current_org_id()
    );

CREATE POLICY "llm_usage_admin_full" ON erp.llm_usage
    FOR ALL
    USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role))
    WITH CHECK (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));

-- INSERT: service role only (bypasses RLS). No user-facing INSERT policy —
-- writes come from SupabaseUsageSink running under the admin client.

CREATE INDEX IF NOT EXISTS llm_usage_org_at_idx
    ON erp.llm_usage (org_id, at DESC);
CREATE INDEX IF NOT EXISTS llm_usage_provider_model_idx
    ON erp.llm_usage (provider, model);
CREATE INDEX IF NOT EXISTS llm_usage_at_idx
    ON erp.llm_usage (at DESC);

COMMENT ON TABLE erp.llm_usage IS
    'LLM token usage + cost estimate per ERP org. Written by SupabaseUsageSink (service role). LGPD: no prompt/response text stored.';
