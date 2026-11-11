-- Migration: 120_rename_monica_to_nosnolimiar
-- Schema: public (core)
-- noc:lock-timeout 30s
-- (lock timeout: renames rows in hot platform tables during the owner-scheduled window; the 5s default is too tight.)
--
-- WHY: owner decision 2026-11-02 -- the live product `monica` (clinic CRM/ERP) is renamed to
-- `nosnolimiar` ("Nós no Limiar"), the company that owns the practice. The slug, display name, host and
-- Postgres schema all change; the product ID does not, so every license, org-picker selection and
-- member-access rule keyed by product_id survives untouched.
-- Roadmap: project-history/roadmaps/nosnolimiar-rename-2026-11.md.
--
-- WHAT: rename the catalog row IN PLACE (guarded on slug='monica' -> idempotent, a no-op on a fresh DB or a
-- re-run) and rename the slug-keyed LIVE rows of the platform tables (derived from the catalog, see below).
-- Historical rows (sso_token_redemptions, audit_logs.product_slug, act_as_sessions, ai_usage, scheduler_runs,
-- credit_entries, help_chat_conversas, ai_trace_spans, notification_sends) are history and are deliberately left as written.
-- ORDER (prod): this runs BEFORE the product's 022 (which renames the Postgres schema); the product container
-- is stopped for the window. KB § PATTERNS/architect/product-working-scope.md.

UPDATE public.products
   SET slug      = 'nosnolimiar',
       nome      = 'Nós no Limiar',
       descricao = 'CRM/ERP do consultório de psicanálise da Nós no Limiar: leads vindos do conteúdo no Instagram, funil, conversas de WhatsApp, pacientes, financeiro e o contexto da Mônica.',
       url_base  = 'https://nosnolimiar.noctusai.com',
       db_schema = 'nosnolimiar'
 WHERE slug = 'monica';

-- Slug-keyed LIVE rows: DERIVED from the catalog, never hand-listed (the hand-list missed
-- agents.agent_product_grants.product). Candidate = every text column in the platform schemas (public, agents)
-- whose NAME says "product slug". The declared HISTORICAL set below is excluded on purpose: those rows record what
-- the product was called when the event happened (append-only ledgers / audit / session history) and stay as written.
-- A final guard fails the migration if a non-historical candidate still holds 'monica', so a column added later
-- (or one this pattern did not anticipate) cannot be silently skipped.
DO $$
DECLARE
    -- schema.table.column of the declared historical set (RUNBOOK Notes; sso/audit are the owner-named ones)
    v_historical constant text[] := ARRAY[
        'public.sso_token_redemptions.product',
        'public.audit_logs.product_slug',
        'public.act_as_sessions.entry_product_slug',
        'public.ai_usage.product',
        'public.scheduler_runs.product',
        'public.credit_entries.product',
        'public.help_chat_conversas.produto',
        'public.ai_trace_spans.product',       -- core 116: per-call span ledger (like ai_usage)
        'public.notification_sends.product'    -- core 117: one row per dispatch decision (a log)
    ];
    v_cols constant text[] := ARRAY['product', 'product_slug', 'produto', 'owner_product'];
    c record;
    v_left text := '';
    v_n bigint;
BEGIN
    FOR c IN
        SELECT col.table_schema AS sch, col.table_name AS tbl, col.column_name AS col
          FROM information_schema.columns col
          JOIN information_schema.tables t
            ON t.table_schema = col.table_schema AND t.table_name = col.table_name AND t.table_type = 'BASE TABLE'
         WHERE col.table_schema IN ('public', 'agents')
           AND col.column_name = ANY (v_cols)
           AND col.data_type IN ('text', 'character varying')
           AND format('%s.%s.%s', col.table_schema, col.table_name, col.column_name) <> ALL (v_historical)
         ORDER BY 1, 2, 3
    LOOP
        EXECUTE format('UPDATE %I.%I SET %I = %L WHERE %I = %L',
                       c.sch, c.tbl, c.col, 'nosnolimiar', c.col, 'monica');
        -- guard: nothing non-historical may still hold the old slug
        EXECUTE format('SELECT count(*) FROM %I.%I WHERE %I = %L', c.sch, c.tbl, c.col, 'monica') INTO v_n;
        IF v_n > 0 THEN
            v_left := v_left || format('%s.%s.%s=%s; ', c.sch, c.tbl, c.col, v_n);
        END IF;
    END LOOP;
    IF v_left <> '' THEN
        RAISE EXCEPTION '120: non-historical column(s) still hold the slug monica: %', v_left;
    END IF;
END
$$;
