-- =====================================================================
-- 012 — Per-feature AI consent (LGPD X6 from ai-expansion Phase 19)
--
-- Platform-wide table — one source of truth across products. Each
-- product registers feature keys at startup; users grant/revoke per key.
-- noctusai_lib.ai.consent.require(db, user_id, key) is called at every
-- AI entry point that this catalog flags as consent-gated.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.ai_consent (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    org_id          UUID,                                -- nullable for personal-context features
    feature_key     TEXT NOT NULL,                       -- e.g. 'erp.lead_score', 'pf.categorize'
    granted         BOOLEAN NOT NULL,
    granted_at      TIMESTAMPTZ,                         -- timestamp of last grant
    revoked_at      TIMESTAMPTZ,                         -- timestamp of last revoke
    rationale_pt    TEXT,                                -- snapshot of the PT-BR rationale shown
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ai_consent_user_feature_unique UNIQUE (user_id, feature_key)
);

CREATE INDEX IF NOT EXISTS ai_consent_user_idx
    ON public.ai_consent (user_id);
CREATE INDEX IF NOT EXISTS ai_consent_feature_idx
    ON public.ai_consent (feature_key);

ALTER TABLE public.ai_consent ENABLE ROW LEVEL SECURITY;

CREATE POLICY "ai_consent_select_own" ON public.ai_consent
    FOR SELECT
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "ai_consent_upsert_own" ON public.ai_consent
    FOR INSERT
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "ai_consent_update_own" ON public.ai_consent
    FOR UPDATE
    USING (user_id = (SELECT auth.uid()))
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "ai_consent_admin_full" ON public.ai_consent
    FOR ALL
    USING ((SELECT auth.uid()) IN (SELECT id FROM public.noctus_users WHERE role = 'admin'))
    WITH CHECK ((SELECT auth.uid()) IN (SELECT id FROM public.noctus_users WHERE role = 'admin'));

COMMENT ON TABLE public.ai_consent IS
    'Per-user / per-feature AI consent records (LGPD). Read+written by /api/me/consents and noctusai_lib.ai.consent.require.';
