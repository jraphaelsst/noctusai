-- Migration: 089_org_brand_identities
-- Schema: public (core)
-- Contract: projects/org-brand-identity/CONTRACT.md §1 (data) · §2 (tokens) · §3 (API)
--
-- WHAT: one visual identity per org, owned by core, worn by core + every product of the selected org.
--   1. public.org_brand_identities  (versioned; org_id NULL = the platform / NOC standard row)
--   2. partial uniques: one ACTIVE row per org, one ACTIVE platform row; unique (org, version)
--   3. RLS: members SELECT their org's rows, every authenticated user SELECTs the platform row —
--      through a COLUMN grant that never includes voice / source / brand_book / validation
--      (voice is server-only, CONTRACT §1). All writes: backend service role after settings:manage.
--   4. public.brand_identity_activate(identity, org) — atomic archive-previous + activate
--   5. private storage bucket brand-identities (10 MB/object cap; signed URLs only)
--   6. the platform row, tokens = tokens.css :root + .dark verbatim
--      (app/services/brand/platform_tokens.json; tests/services/test_brand_migration_089.py
--      fails if this literal and the derived artifact disagree).
-- Re-runnable: IF NOT EXISTS / OR REPLACE / ON CONFLICT / DROP-then-CREATE POLICY / WHERE NOT EXISTS.
SET search_path = public, public;

-- ── 1. table ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.org_brand_identities (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID REFERENCES public.organizations(id) ON DELETE CASCADE,
    version       INT NOT NULL CHECK (version >= 1),
    status        TEXT NOT NULL CHECK (status IN ('draft', 'active', 'archived', 'failed')),
    tokens        JSONB NOT NULL,
    brand_book    TEXT NOT NULL DEFAULT '',
    voice         JSONB NOT NULL DEFAULT '{}'::jsonb,
    assets        JSONB NOT NULL DEFAULT '{}'::jsonb,
    source        JSONB NOT NULL DEFAULT '{}'::jsonb,
    validation    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by    UUID,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    activated_at  TIMESTAMPTZ,
    CONSTRAINT org_brand_identities_tokens_schema
        CHECK (tokens->>'schema' = 'noctus.brand-tokens/v1')
);
COMMENT ON TABLE public.org_brand_identities IS
    'Org visual identity versions (CONTRACT org-brand-identity). org_id NULL = platform (NOC standard). '
    'voice/source/brand_book are server-only: never column-granted to authenticated.';

-- ── 2. uniques ──────────────────────────────────────────────────────────────────
CREATE UNIQUE INDEX IF NOT EXISTS ux_org_brand_identities_active_org
    ON public.org_brand_identities (org_id) WHERE status = 'active' AND org_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_org_brand_identities_active_platform
    ON public.org_brand_identities ((org_id IS NULL)) WHERE status = 'active' AND org_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_org_brand_identities_org_version
    ON public.org_brand_identities (COALESCE(org_id, '00000000-0000-0000-0000-000000000000'::uuid), version);
CREATE INDEX IF NOT EXISTS ix_org_brand_identities_job
    ON public.org_brand_identities ((source->'extraction'->>'job_id'))
    WHERE source->'extraction'->>'job_id' IS NOT NULL;

-- ── 3. access ───────────────────────────────────────────────────────────────────
ALTER TABLE public.org_brand_identities ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.org_brand_identities FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.org_brand_identities TO service_role;
GRANT SELECT (id, org_id, version, status, tokens, assets, created_at, activated_at)
    ON public.org_brand_identities TO authenticated;

DROP POLICY IF EXISTS "service_role_bypass" ON public.org_brand_identities;
CREATE POLICY "service_role_bypass" ON public.org_brand_identities
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS org_brand_identities_member_read ON public.org_brand_identities;
CREATE POLICY org_brand_identities_member_read ON public.org_brand_identities
    FOR SELECT TO authenticated
    USING (
        org_id IS NULL
        OR org_id IN (
            SELECT m.org_id FROM public.org_memberships m
            WHERE m.user_id = (SELECT auth.uid()) AND m.status = 'active'
        )
    );

-- ── 4. activation (atomic; service role only) ───────────────────────────────────
CREATE OR REPLACE FUNCTION public.brand_identity_activate(p_identity_id UUID, p_org_id UUID)
RETURNS SETOF public.org_brand_identities
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    v_status TEXT;
BEGIN
    IF p_org_id IS NULL THEN
        RAISE EXCEPTION 'brand_identity_activate:not_found';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('org_brand_identities:' || p_org_id::text, 0));
    SELECT status INTO v_status FROM public.org_brand_identities
     WHERE id = p_identity_id AND org_id = p_org_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'brand_identity_activate:not_found';
    END IF;
    IF v_status <> 'active' THEN
        IF v_status NOT IN ('draft', 'archived') THEN
            RAISE EXCEPTION 'brand_identity_activate:invalid_status';
        END IF;
        UPDATE public.org_brand_identities SET status = 'archived'
         WHERE org_id = p_org_id AND status = 'active';
        UPDATE public.org_brand_identities SET status = 'active', activated_at = now()
         WHERE id = p_identity_id;
    END IF;
    RETURN QUERY SELECT * FROM public.org_brand_identities WHERE id = p_identity_id;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.brand_identity_activate(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.brand_identity_activate(UUID, UUID) TO service_role;

-- ── 5. private bucket ───────────────────────────────────────────────────────────
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('brand-identities', 'brand-identities', false, 10485760,
        ARRAY['text/markdown', 'application/pdf', 'image/png', 'image/jpeg', 'image/webp', 'font/woff2']::text[])
ON CONFLICT (id) DO UPDATE
    SET public = false,
        file_size_limit = EXCLUDED.file_size_limit,
        allowed_mime_types = EXCLUDED.allowed_mime_types;

-- ── 6. platform row (NOC standard = tokens.css :root + .dark) ───────────────────
INSERT INTO public.org_brand_identities (org_id, version, status, tokens, validation, activated_at)
SELECT NULL, 1, 'active',
       '{"schema": "noctus.brand-tokens/v1", "light": {"background": "0 0% 97%", "foreground": "0 0% 10%", "card": "0 0% 100%", "card-foreground": "0 0% 10%", "popover": "0 0% 100%", "popover-foreground": "0 0% 10%", "primary": "220 10% 40%", "primary-foreground": "0 0% 100%", "primary-light": "220 10% 60%", "primary-dark": "220 10% 25%", "secondary": "0 0% 75%", "secondary-foreground": "0 0% 20%", "secondary-light": "0 0% 88%", "muted": "0 0% 94%", "muted-foreground": "0 0% 50%", "accent": "210 20% 93%", "accent-foreground": "0 0% 20%", "success": "142 40% 60%", "success-foreground": "0 0% 100%", "success-light": "142 40% 92%", "warning": "43 70% 70%", "warning-foreground": "0 0% 20%", "warning-light": "43 70% 92%", "danger": "0 60% 70%", "danger-foreground": "0 0% 100%", "danger-light": "0 60% 92%", "info": "217 60% 70%", "info-foreground": "0 0% 100%", "info-light": "217 60% 92%", "destructive": "0 60% 70%", "destructive-foreground": "0 0% 100%", "border": "0 0% 88%", "input": "0 0% 88%", "ring": "220 10% 40%", "sidebar-background": "0 0% 10%", "sidebar-foreground": "0 0% 92%", "sidebar-primary": "220 10% 40%", "sidebar-primary-foreground": "0 0% 100%", "sidebar-accent": "0 0% 16%", "sidebar-accent-foreground": "0 0% 92%", "sidebar-border": "0 0% 18%", "sidebar-ring": "220 10% 40%", "chart-1": "220 70% 55%", "chart-2": "160 60% 40%", "chart-3": "35 85% 50%", "chart-4": "280 60% 55%", "chart-5": "10 75% 50%", "chart-6": "195 70% 45%", "chart-7": "320 55% 50%", "chart-8": "95 45% 40%"}, "dark": {"background": "0 0% 8%", "foreground": "0 0% 92%", "card": "0 0% 11%", "card-foreground": "0 0% 92%", "popover": "0 0% 11%", "popover-foreground": "0 0% 92%", "primary": "220 10% 50%", "primary-foreground": "0 0% 100%", "primary-light": "220 10% 70%", "primary-dark": "220 10% 30%", "secondary": "0 0% 60%", "secondary-foreground": "0 0% 100%", "secondary-light": "0 0% 20%", "muted": "0 0% 16%", "muted-foreground": "0 0% 62%", "accent": "0 0% 16%", "accent-foreground": "0 0% 92%", "success": "142 71% 48%", "success-foreground": "0 0% 100%", "success-light": "142 71% 14%", "warning": "43 96% 65%", "warning-foreground": "0 0% 8%", "warning-light": "43 96% 14%", "danger": "0 84% 68%", "danger-foreground": "0 0% 100%", "danger-light": "0 84% 14%", "info": "217 91% 70%", "info-foreground": "0 0% 100%", "info-light": "217 91% 14%", "destructive": "0 60% 75%", "destructive-foreground": "0 0% 100%", "border": "0 0% 18%", "input": "0 0% 18%", "ring": "220 10% 50%", "sidebar-background": "0 0% 6%", "sidebar-foreground": "0 0% 92%", "sidebar-primary": "220 10% 50%", "sidebar-primary-foreground": "0 0% 100%", "sidebar-accent": "0 0% 13%", "sidebar-accent-foreground": "0 0% 92%", "sidebar-border": "0 0% 16%", "sidebar-ring": "220 10% 50%", "chart-1": "220 75% 65%", "chart-2": "160 55% 55%", "chart-3": "35 85% 62%", "chart-4": "280 65% 68%", "chart-5": "10 80% 65%", "chart-6": "195 75% 60%", "chart-7": "320 60% 65%", "chart-8": "95 45% 55%"}, "radius": "0.5rem", "fonts": {}}'::jsonb,
       '{"seeded_from": "seed/lib/frontend/src/design-system/tokens.css"}'::jsonb,
       now()
WHERE NOT EXISTS (SELECT 1 FROM public.org_brand_identities WHERE org_id IS NULL);
