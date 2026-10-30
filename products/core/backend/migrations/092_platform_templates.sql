-- Migration: 092_platform_templates
-- Schema: public (core)
--
-- WHAT: the platform's editable, versioned template library (admin > Templates).
--   1. public.platform_templates: one row per VERSION of a template. product NULL = platform-wide.
--      kind in design_system | agent | message | document | repo_workflow.
--   2. Uniques: (product, kind, key, version); at most ONE active version per (product, kind, key).
--   3. Append-only history: rows are never deleted; once a row leaves 'draft' its content
--      (kind/product/key/title/description/format/body/version) is frozen -- an edit is a NEW version.
--   4. public.platform_template_activate(id) -- atomic archive-previous + activate.
--   5. RLS: no policy for anon/authenticated. Platform admins reach it only through core's
--      /api/admin/templates router (service role, after the platform-admin check).
--   6. Seed: the design-system template the platform/Bia uses to build an org design system
--      = the NOC standard tokens (noctus.brand-tokens/v1, same values as 089's platform row;
--      tests/services/test_platform_templates_migration_092.py compares them).
-- Re-runnable: IF NOT EXISTS / OR REPLACE / DROP-then-CREATE / WHERE NOT EXISTS.
SET search_path = public, public;

CREATE TABLE IF NOT EXISTS public.platform_templates (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product      TEXT CHECK (product IS NULL OR product ~ '^[a-z0-9][a-z0-9-]{0,62}$'),
    kind         TEXT NOT NULL CHECK (kind IN ('design_system', 'agent', 'message', 'document', 'repo_workflow')),
    key          TEXT NOT NULL CHECK (key ~ '^[a-z0-9][a-z0-9_.-]{0,79}$'),
    title        TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    description  TEXT NOT NULL DEFAULT '' CHECK (length(description) <= 2000),
    format       TEXT NOT NULL CHECK (format IN ('json', 'markdown', 'text')),
    body         TEXT NOT NULL CHECK (length(body) <= 200000),
    version      INT NOT NULL CHECK (version >= 1),
    status       TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'archived')),
    created_by   UUID,
    updated_by   UUID,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    activated_at TIMESTAMPTZ
);
COMMENT ON TABLE public.platform_templates IS
    'Versioned platform template library (admin > Templates). product NULL = platform-wide. '
    'Append-only history: non-draft rows are content-frozen, never deleted.';

CREATE UNIQUE INDEX IF NOT EXISTS ux_platform_templates_version
    ON public.platform_templates (COALESCE(product, ''), kind, key, version);
CREATE UNIQUE INDEX IF NOT EXISTS ux_platform_templates_active
    ON public.platform_templates (COALESCE(product, ''), kind, key) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS ix_platform_templates_scope
    ON public.platform_templates (kind, product, key);

ALTER TABLE public.platform_templates ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.platform_templates FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.platform_templates TO service_role;
DROP POLICY IF EXISTS "service_role_bypass" ON public.platform_templates;
CREATE POLICY "service_role_bypass" ON public.platform_templates
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── append-only guard ────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.platform_templates_guard()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'platform_templates is append-only: archive the version instead of deleting it';
    END IF;
    IF OLD.status <> 'draft' AND (
        NEW.product IS DISTINCT FROM OLD.product OR NEW.kind <> OLD.kind OR NEW.key <> OLD.key
        OR NEW.title <> OLD.title OR NEW.description <> OLD.description OR NEW.format <> OLD.format
        OR NEW.body <> OLD.body OR NEW.version <> OLD.version
    ) THEN
        RAISE EXCEPTION 'platform_templates: a non-draft version is frozen; create a new version';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_platform_templates_guard ON public.platform_templates;
CREATE TRIGGER trg_platform_templates_guard
    BEFORE UPDATE OR DELETE ON public.platform_templates
    FOR EACH ROW EXECUTE FUNCTION public.platform_templates_guard();

-- ── activation (atomic; service role only) ──────────────────────────────────────
CREATE OR REPLACE FUNCTION public.platform_template_activate(p_id UUID)
RETURNS SETOF public.platform_templates
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    v_row public.platform_templates%ROWTYPE;
BEGIN
    SELECT * INTO v_row FROM public.platform_templates WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'platform_template_activate:not_found';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(
        'platform_templates:' || COALESCE(v_row.product, '') || ':' || v_row.kind || ':' || v_row.key, 0));
    IF v_row.status <> 'active' THEN
        UPDATE public.platform_templates SET status = 'archived', updated_at = now()
         WHERE COALESCE(product, '') = COALESCE(v_row.product, '') AND kind = v_row.kind
           AND key = v_row.key AND status = 'active';
        UPDATE public.platform_templates SET status = 'active', activated_at = now(), updated_at = now()
         WHERE id = p_id;
    END IF;
    RETURN QUERY SELECT * FROM public.platform_templates WHERE id = p_id;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.platform_template_activate(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.platform_template_activate(UUID) TO service_role;

-- ── seed: the design-system template (NOC standard tokens) ──────────────────────
INSERT INTO public.platform_templates
    (product, kind, key, title, description, format, body, version, status, activated_at)
SELECT NULL, 'design_system', 'org-design-system',
       'Design system da organizacao (padrao NOC)',
       'Template que a plataforma e a Bia usam para montar o design system de uma nova organizacao. Esquema noctus.brand-tokens/v1; valores iniciais = tokens padrao da plataforma.',
       'json',
       '{"schema": "noctus.brand-tokens/v1", "light": {"background": "0 0% 97%", "foreground": "0 0% 10%", "card": "0 0% 100%", "card-foreground": "0 0% 10%", "popover": "0 0% 100%", "popover-foreground": "0 0% 10%", "primary": "220 10% 40%", "primary-foreground": "0 0% 100%", "primary-light": "220 10% 60%", "primary-dark": "220 10% 25%", "secondary": "0 0% 75%", "secondary-foreground": "0 0% 20%", "secondary-light": "0 0% 88%", "muted": "0 0% 94%", "muted-foreground": "0 0% 50%", "accent": "210 20% 93%", "accent-foreground": "0 0% 20%", "success": "142 40% 60%", "success-foreground": "0 0% 100%", "success-light": "142 40% 92%", "warning": "43 70% 70%", "warning-foreground": "0 0% 20%", "warning-light": "43 70% 92%", "danger": "0 60% 70%", "danger-foreground": "0 0% 100%", "danger-light": "0 60% 92%", "info": "217 60% 70%", "info-foreground": "0 0% 100%", "info-light": "217 60% 92%", "destructive": "0 60% 70%", "destructive-foreground": "0 0% 100%", "border": "0 0% 88%", "input": "0 0% 88%", "ring": "220 10% 40%", "sidebar-background": "0 0% 10%", "sidebar-foreground": "0 0% 92%", "sidebar-primary": "220 10% 40%", "sidebar-primary-foreground": "0 0% 100%", "sidebar-accent": "0 0% 16%", "sidebar-accent-foreground": "0 0% 92%", "sidebar-border": "0 0% 18%", "sidebar-ring": "220 10% 40%", "chart-1": "220 70% 55%", "chart-2": "160 60% 40%", "chart-3": "35 85% 50%", "chart-4": "280 60% 55%", "chart-5": "10 75% 50%", "chart-6": "195 70% 45%", "chart-7": "320 55% 50%", "chart-8": "95 45% 40%"}, "dark": {"background": "0 0% 8%", "foreground": "0 0% 92%", "card": "0 0% 11%", "card-foreground": "0 0% 92%", "popover": "0 0% 11%", "popover-foreground": "0 0% 92%", "primary": "220 10% 50%", "primary-foreground": "0 0% 100%", "primary-light": "220 10% 70%", "primary-dark": "220 10% 30%", "secondary": "0 0% 60%", "secondary-foreground": "0 0% 100%", "secondary-light": "0 0% 20%", "muted": "0 0% 16%", "muted-foreground": "0 0% 62%", "accent": "0 0% 16%", "accent-foreground": "0 0% 92%", "success": "142 71% 48%", "success-foreground": "0 0% 100%", "success-light": "142 71% 14%", "warning": "43 96% 65%", "warning-foreground": "0 0% 8%", "warning-light": "43 96% 14%", "danger": "0 84% 68%", "danger-foreground": "0 0% 100%", "danger-light": "0 84% 14%", "info": "217 91% 70%", "info-foreground": "0 0% 100%", "info-light": "217 91% 14%", "destructive": "0 60% 75%", "destructive-foreground": "0 0% 100%", "border": "0 0% 18%", "input": "0 0% 18%", "ring": "220 10% 50%", "sidebar-background": "0 0% 6%", "sidebar-foreground": "0 0% 92%", "sidebar-primary": "220 10% 50%", "sidebar-primary-foreground": "0 0% 100%", "sidebar-accent": "0 0% 13%", "sidebar-accent-foreground": "0 0% 92%", "sidebar-border": "0 0% 16%", "sidebar-ring": "220 10% 50%", "chart-1": "220 75% 65%", "chart-2": "160 55% 55%", "chart-3": "35 85% 62%", "chart-4": "280 65% 68%", "chart-5": "10 80% 65%", "chart-6": "195 75% 60%", "chart-7": "320 60% 65%", "chart-8": "95 45% 55%"}, "radius": "0.5rem", "fonts": {}}',
       1, 'active', now()
WHERE NOT EXISTS (
    SELECT 1 FROM public.platform_templates
     WHERE product IS NULL AND kind = 'design_system' AND key = 'org-design-system');
