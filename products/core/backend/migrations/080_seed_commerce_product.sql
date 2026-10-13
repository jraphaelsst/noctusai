-- ============================================================
-- 080 — Seed Commerce product row
-- ============================================================
-- Auto-emitted by scaffold_product so the new product appears on
-- the noc dashboard (Dashboard.tsx reads /api/auth/me which joins
-- public.products). Apply via Supabase MCP apply_migration to land
-- on the live DB ("MCP migrations mirror the file" rule).
-- ============================================================

INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo, deploy_scope, aceita_clientes)
VALUES (
    'Commerce',
    'commerce',
    'E-commerce + ERP de referência (vertical seed commerce): loja pública por domínio + back office',
    'Store',
    'https://commerce.noctusai.com',
    '#0f766e',
    true,
    'dev',   -- dev-only until owner validation (gate T2); live needs deploy/consent/commerce.prod.yml
    false
)
ON CONFLICT (slug) DO NOTHING;

-- The container HOUSE port is its own column (core 076): url_base is the
-- canonical https prod URL and carries no port.
UPDATE public.products SET house_port = 8019
 WHERE slug = 'commerce' AND house_port IS NULL;

UPDATE public.products SET db_schema = 'commerce'
 WHERE slug = 'commerce' AND db_schema IS NULL;

-- Expose `commerce` to PostgREST by APPENDING to authenticator's
-- pgrst.db_schemas — a schema absent from this list makes every REST call
-- against it fail with PGRST106. Idempotent + append-only: reads the
-- CURRENT list (never a literal copy, which goes stale — see
-- products/p-studio/backend/migrations/002_plataforma_e_seeds.sql for the
-- near-miss this pattern exists to prevent), appends `commerce` only if
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

    IF v_current !~ '(^|,)\s*commerce\s*(,|$)' THEN
        EXECUTE format(
            'ALTER ROLE authenticator SET pgrst.db_schemas = %L',
            v_current || ', commerce'
        );
        NOTIFY pgrst, 'reload config';
        NOTIFY pgrst, 'reload schema';
    END IF;
END
$$;
