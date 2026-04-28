-- 017_llm_preferences.sql
-- Per-org LLM provider/model preferences for the ERP product.
--
-- Populated by the shared /api/llm/preferences endpoint (defined in
-- noctusai_seed.llm_router). One row per org. NULL values mean "use the
-- product's default" — read by services via noctusai_lib.llm's dispatch.
--
-- RLS: org members read; org admins+managers+owners write.

CREATE TABLE IF NOT EXISTS erp.llm_preferences (
    org_id UUID PRIMARY KEY,
    provider TEXT NOT NULL,
    chat_model TEXT,
    embedding_model TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by UUID REFERENCES auth.users(id)
);

ALTER TABLE erp.llm_preferences ENABLE ROW LEVEL SECURITY;

-- SELECT: any org member can read their org's preferences
CREATE POLICY "llm_preferences_select" ON erp.llm_preferences
    FOR SELECT
    USING (
        org_id IN (
            SELECT org_id FROM public.org_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

-- INSERT/UPDATE/DELETE: owner/admin/manager only
CREATE POLICY "llm_preferences_write" ON erp.llm_preferences
    FOR ALL
    USING (
        org_id IN (
            SELECT org_id FROM public.org_members
            WHERE user_id = (SELECT auth.uid())
            AND role IN ('owner', 'admin', 'manager')
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT org_id FROM public.org_members
            WHERE user_id = (SELECT auth.uid())
            AND role IN ('owner', 'admin', 'manager')
        )
    );

CREATE INDEX IF NOT EXISTS llm_preferences_updated_idx
    ON erp.llm_preferences (updated_at DESC);

COMMENT ON TABLE erp.llm_preferences IS
    'Per-org LLM provider + model selection for ERP. Shared surface via noctusai_seed.llm_router.';
