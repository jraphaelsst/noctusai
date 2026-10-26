-- ============================================================
-- 087 — Seed Monica product row
-- ============================================================
-- Auto-emitted by scaffold_product so the new product appears on
-- the noc dashboard (Dashboard.tsx reads /api/auth/me which joins
-- public.products). Apply via Supabase MCP apply_migration to land
-- on the live DB ("MCP migrations mirror the file" rule).
--
-- The row is ativo=true and deploy_scope stays at its default 'dev': the flip to 'live' is NEVER a migration
-- (core 075's trigger refuses it without a passing SSO callback probe) -- it is the LAST step of the first
-- go-live, in core admin (KB § GUIDES/production-deploy.md § 5a). Monica serves end customers? No:
-- aceita_clientes stays false (default) -- it is a back-office CRM for one practice.
-- ============================================================

INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES (
    'Monica',
    'monica',
    'CRM do consultório de psicanálise de Mônica Tangerino: leads vindos do conteúdo no Instagram, funil, conversas de WhatsApp e o contexto da Mônica (futuro ERP).',
    'UsersRound',
    'https://monica.noctusai.com',
    '#7c5c8a',
    true
)
ON CONFLICT (slug) DO NOTHING;

-- The container HOUSE port is its own column (core 076): url_base is the
-- canonical https prod URL and carries no port.
UPDATE public.products SET house_port = 8020
 WHERE slug = 'monica' AND house_port IS NULL;

UPDATE public.products SET db_schema = 'monica'
 WHERE slug = 'monica' AND db_schema IS NULL;

-- Expose `monica` to PostgREST by APPENDING to authenticator's
-- pgrst.db_schemas — a schema absent from this list makes every REST call
-- against it fail with PGRST106. Idempotent + append-only: reads the
-- CURRENT list (never a literal copy, which goes stale — see
-- products/p-studio/backend/migrations/002_plataforma_e_seeds.sql for the
-- near-miss this pattern exists to prevent), appends `monica` only if
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

    IF v_current !~ '(^|,)\s*monica\s*(,|$)' THEN
        EXECUTE format(
            'ALTER ROLE authenticator SET pgrst.db_schemas = %L',
            v_current || ', monica'
        );
        NOTIFY pgrst, 'reload config';
        NOTIFY pgrst, 'reload schema';
    END IF;
END
$$;

-- License the product to the org it was built for (Mônica Tangerino -- org-per-brand-restructure data-move.sql).
-- The platform org already holds every license by construction (core 068 triggers); this is the customer org's
-- own. Guarded: an environment without that org (a fresh dev DB) simply skips the grant. Idempotent: the unique
-- index `idx_licenses_one_active_per_org_product` allows one active license per (org, product).
INSERT INTO public.licenses (org_id, product_id, status, inicio, fim, source)
SELECT o.id, p.id, 'active', now(), NULL, 'manual'
  FROM public.organizations o
 CROSS JOIN public.products p
 WHERE o.id = 'fa80a1e0-1bcd-4c65-8a37-2162e8ffa688'
   AND p.slug = 'monica'
   AND NOT EXISTS (
     SELECT 1 FROM public.licenses l
      WHERE l.org_id = o.id AND l.product_id = p.id AND l.status = 'active'
   );
