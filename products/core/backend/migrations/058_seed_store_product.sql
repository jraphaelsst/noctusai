-- ============================================================
-- 058 — Seed Store product row
-- ============================================================
-- Auto-emitted by scaffold_product so the new product appears on
-- the noc dashboard (Dashboard.tsx reads /api/auth/me which joins
-- public.products). Apply via Supabase MCP apply_migration to land
-- on the live DB ("MCP migrations mirror the file" rule).
-- ============================================================

INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES (
    'Store',
    'store',
    'Loja de produtos digitais: página de vendas pública + checkout Asaas + entrega por e-mail',
    'ShoppingBag',
    'http://localhost:8018',
    '#b08d57',
    true
)
ON CONFLICT (slug) DO NOTHING;

-- Expose `store` to PostgREST by APPENDING to authenticator's
-- pgrst.db_schemas — a schema absent from this list makes every REST call
-- against it fail with PGRST106. Idempotent + append-only: reads the
-- CURRENT list (never a literal copy, which goes stale — see
-- products/p-studio/backend/migrations/002_plataforma_e_seeds.sql for the
-- near-miss this pattern exists to prevent), appends `store` only if
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

    IF v_current !~ '(^|,)\s*store\s*(,|$)' THEN
        EXECUTE format(
            'ALTER ROLE authenticator SET pgrst.db_schemas = %L',
            v_current || ', store'
        );
        NOTIFY pgrst, 'reload config';
        NOTIFY pgrst, 'reload schema';
    END IF;
END
$$;
