-- 005_llm_preferences.sql
-- Per-clinic LLM provider/model preferences for the Therapy product.
--
-- Therapy's tenant key is clinic_id (not org_id). The shared llm_router
-- uses deps.get_org_id(user), which for Therapy returns the caller's
-- clinic_id. Storing under that key keeps the shared endpoint uniform.
--
-- RLS: clinic members read; clinic_admin / therapist writes.

CREATE TABLE IF NOT EXISTS therapy.llm_preferences (
    org_id UUID PRIMARY KEY,   -- maps to clinic_id in Therapy's model
    provider TEXT NOT NULL,
    chat_model TEXT,
    embedding_model TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by UUID REFERENCES auth.users(id)
);

ALTER TABLE therapy.llm_preferences ENABLE ROW LEVEL SECURITY;

-- SELECT: any clinic member can read their clinic's preferences
CREATE POLICY "llm_preferences_select" ON therapy.llm_preferences
    FOR SELECT
    USING (
        org_id IN (
            SELECT clinic_id FROM therapy.clinic_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

-- INSERT/UPDATE/DELETE: clinic_admin only
CREATE POLICY "llm_preferences_write" ON therapy.llm_preferences
    FOR ALL
    USING (
        org_id IN (
            SELECT clinic_id FROM therapy.clinic_members
            WHERE user_id = (SELECT auth.uid())
            AND role IN ('clinic_admin', 'clinic_owner')
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT clinic_id FROM therapy.clinic_members
            WHERE user_id = (SELECT auth.uid())
            AND role IN ('clinic_admin', 'clinic_owner')
        )
    );

CREATE INDEX IF NOT EXISTS llm_preferences_updated_idx
    ON therapy.llm_preferences (updated_at DESC);

COMMENT ON TABLE therapy.llm_preferences IS
    'Per-clinic LLM provider + model selection for Therapy. Shared surface via noctusai_seed.llm_router.';
