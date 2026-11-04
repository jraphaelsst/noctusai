-- Migration: 098_rename_monica_to_nosnolimiar
-- Schema: public (core)
--
-- WHY: owner decision 2026-11-02 -- the live product `monica` (clinic CRM/ERP) is renamed to
-- `nosnolimiar` ("Nós no Limiar"), the company that owns the practice. The slug, display name, host and
-- Postgres schema all change; the product ID does not, so every license, org-picker selection and
-- member-access rule keyed by product_id survives untouched.
-- Roadmap: project-history/roadmaps/nosnolimiar-rename-2026-11.md.
--
-- WHAT: rename the catalog row IN PLACE (guarded on slug='monica' -> idempotent, a no-op on a fresh DB or a
-- re-run) and rename the slug-keyed LIVE rows of the platform tables. Historical rows
-- (sso_token_redemptions, audit_logs.product_slug, act_as_sessions, ai_usage, scheduler_runs) are history
-- and are deliberately left as written.
-- ORDER (prod): this runs BEFORE the product's 020 (which renames the Postgres schema); the product container
-- is stopped for the window. KB § PATTERNS/architect/product-working-scope.md.

UPDATE public.products
   SET slug      = 'nosnolimiar',
       nome      = 'Nós no Limiar',
       descricao = 'CRM/ERP do consultório de psicanálise da Nós no Limiar: leads vindos do conteúdo no Instagram, funil, conversas de WhatsApp, pacientes, financeiro e o contexto da Mônica.',
       url_base  = 'https://nosnolimiar.noctusai.com',
       db_schema = 'nosnolimiar'
 WHERE slug = 'monica';

-- Slug-keyed LIVE rows of the platform tables (guarded: a table/column absent in an older DB is skipped).
DO $$
DECLARE
    t record;
BEGIN
    FOR t IN
        SELECT * FROM (VALUES
            ('scheduler_jobs',     'product'),
            ('platform_templates', 'product')
        ) AS x(tbl, col)
    LOOP
        IF EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = t.tbl AND column_name = t.col) THEN
            EXECUTE format('UPDATE public.%I SET %I = %L WHERE %I = %L',
                           t.tbl, t.col, 'nosnolimiar', t.col, 'monica');
        END IF;
    END LOOP;
END
$$;
