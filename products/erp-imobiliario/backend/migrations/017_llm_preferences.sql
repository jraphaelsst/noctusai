-- 017_llm_preferences.sql
-- Per-org LLM provider/model preferences for the ERP product.
--
-- Populated by the shared /api/llm/preferences endpoint (defined in
-- noctusai_seed.llm_router). One row per org. NULL values mean "use the
-- product's default" — read by services via noctusai_lib.llm's dispatch.
--
-- RLS: org members read; org owners/admins/managers write.
--
-- ── 2026-09-17 REPAIR — this migration had NEVER been applied ───────────────
-- It was authored against `public.org_members`, a table that has never
-- existed anywhere in this database. Every other erp migration scopes by
-- `public.current_org_id()` (79 occurrences) or reads `public.noctus_users`
-- (13); this file was the ONLY one referencing `org_members` (3), so it could
-- not be applied and silently never was. `erp.llm_preferences` therefore
-- existed in NO schema while `/configuracoes/llm` (App.tsx:283) shipped a
-- routed page querying it — a live dead page, invisible because the
-- `schema_migrations` ledger for erp was empty and nothing compared the
-- declared migration set against the real schema.
--
-- Repaired to erp's canonical shape: `org_id = public.current_org_id()`
-- (which itself reads `public.noctus_users`, per 038's "one identity source,
-- not five"), with writes gated on `noctus_users.org_role`. Role vocabulary
-- verified live: owner | admin | corretor.
-- ───────────────────────────────────────────────────────────────────────────

SET search_path = erp, public;

CREATE TABLE IF NOT EXISTS erp.llm_preferences (
    org_id UUID PRIMARY KEY,
    provider TEXT NOT NULL,
    chat_model TEXT,
    embedding_model TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by UUID REFERENCES auth.users(id)
);

ALTER TABLE erp.llm_preferences ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "llm_preferences_select" ON erp.llm_preferences;
CREATE POLICY "llm_preferences_select" ON erp.llm_preferences
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "llm_preferences_write" ON erp.llm_preferences;
CREATE POLICY "llm_preferences_write" ON erp.llm_preferences
    FOR ALL TO authenticated
    USING (
        org_id = public.current_org_id()
        AND EXISTS (
            SELECT 1 FROM public.noctus_users u
            WHERE u.id = (SELECT auth.uid())
              AND u.org_role IN ('owner', 'admin', 'manager')
        )
    )
    WITH CHECK (
        org_id = public.current_org_id()
        AND EXISTS (
            SELECT 1 FROM public.noctus_users u
            WHERE u.id = (SELECT auth.uid())
              AND u.org_role IN ('owner', 'admin', 'manager')
        )
    );

NOTIFY pgrst, 'reload schema';
