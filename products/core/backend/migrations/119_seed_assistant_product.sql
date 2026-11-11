-- ============================================================
-- 119 — Seed Assistant product row
-- ============================================================
-- Auto-emitted by scaffold_product so the new product appears on
-- the noc dashboard (Dashboard.tsx reads /api/auth/me which joins
-- public.products). Apply via Supabase MCP apply_migration to land
-- on the live DB ("MCP migrations mirror the file" rule).
-- ============================================================

-- deploy_scope 'dev': the Assistant never reaches prod without the owner's explicit consent
-- (KB § PATTERNS/architect/product-working-scope.md).
INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo, deploy_scope)
VALUES (
    'Assistant',
    'assistant',
    'Personal-line shadow assistant: reads a linked WhatsApp line (never writes) and classifies scheduling intent.',
    'MessageCircle',
    'https://assistant.noctusai.com',
    '#6366f1',
    true,
    'dev'
)
ON CONFLICT (slug) DO NOTHING;

-- The container HOUSE port is its own column (core 076): url_base is the
-- canonical https prod URL and carries no port.
UPDATE public.products SET house_port = 8021
 WHERE slug = 'assistant' AND house_port IS NULL;

UPDATE public.products SET db_schema = 'assistant'
 WHERE slug = 'assistant' AND db_schema IS NULL;

-- Expose `assistant` to PostgREST by APPENDING to authenticator's
-- pgrst.db_schemas — a schema absent from this list makes every REST call
-- against it fail with PGRST106. Idempotent + append-only: reads the
-- CURRENT list (never a literal copy, which goes stale — see
-- products/p-studio/backend/migrations/002_plataforma_e_seeds.sql for the
-- near-miss this pattern exists to prevent), appends `assistant` only if
-- absent, and never drops or reorders existing entries.
DO $$
DECLARE
    v_current text;
BEGIN
    SELECT substring(cfg FROM 'pgrst[.]db_schemas=(.*)') INTO v_current
    FROM (
        SELECT unnest(setconfig) AS cfg
        FROM pg_db_role_setting s
        JOIN pg_roles r ON r.oid = s.setrole
        WHERE r.rolname = 'authenticator'
    ) t
    WHERE cfg LIKE 'pgrst.db_schemas=%';

    v_current := COALESCE(v_current, 'public, graphql_public');

    IF v_current !~ '(^|,)\s*assistant\s*(,|$)' THEN
        EXECUTE format(
            'ALTER ROLE authenticator SET pgrst.db_schemas = %L',
            v_current || ', assistant'
        );
        NOTIFY pgrst, 'reload config';
        NOTIFY pgrst, 'reload schema';
    END IF;
END
$$;
