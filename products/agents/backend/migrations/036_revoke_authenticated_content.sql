-- ============================================================================
-- 036_revoke_authenticated_content.sql -- SECURITY FINDING C2 (critical, 2026-10-19).
--
-- The `agents` schema is exposed to PostgREST and the browser holds a persisted
-- Supabase session plus the publishable key, so any logged-in member of ANY org
-- could `GET /rest/v1/agent_prompt_sections` with `Accept-Profile: agents` and
-- read Julia's prompt (the studio content tables carried an org-only
-- `FOR SELECT TO authenticated` policy, and `current_org_id_for('agents')` falls
-- back to the home org with no license check). Same for transcripts
-- (`messages_select_own_org` etc.), leads, finance and credentials metadata.
--
-- The agents backend reads and writes EVERY table through the service-role
-- (admin) client; the agents frontend only talks to supabase-js for auth and for
-- ONE table read, `status_pagina` (page-visibility flags, no PII). So:
--   * every table below is service-role only: REVOKE ALL from PUBLIC/anon/
--     authenticated, and every policy that names those roles is dropped;
--   * `status_pagina` is the sole allowlisted table; it keeps SELECT (the
--     `todos_veem_producao` / `dev_veem_desenvolvimento` policies stay) but the
--     leftover write privileges of 001's `GRANT ALL` are removed;
--   * the 001 default privileges that would hand every FUTURE table to
--     authenticated are revoked, so a new table is private by default.
-- service_role has BYPASSRLS, so dropping the authenticated policies cannot
-- break a backend path.
--
-- Forward-only + idempotent (REVOKE / DROP POLICY IF EXISTS are replay-safe; a
-- table not present yet is skipped). The final DO block RAISEs when ANY agents
-- table outside the allowlist still grants anything to anon/authenticated or
-- still carries a policy naming them -- applying this file half-way is a loud
-- failure, never a silent partial lockdown.
-- ============================================================================

DO $revoke$
DECLARE
  t text;
  pol record;
  v_tables text[] := ARRAY[
    -- 001-010: tenancy, conversations, tokens, credentials, transcripts
    'agents', 'examples', 'conversations', 'messages', 'approvals', 'invitations',
    'api_tokens', 'api_token_audit', 'credentials', 'app_integration_config',
    'runtime_settings', 'session_transcript_entries',
    -- 006 / 012: personas and the studio definitions (Julia's prompt lives here)
    'agent_personas', 'agent_versions', 'agent_prompt_sections', 'agent_skills',
    'agent_skill_files', 'agent_clients', 'agent_client_entries', 'compiled_prompts',
    'agent_audit_log',
    -- 013: knowledge + evals
    'knowledge_collections', 'knowledge_documents', 'knowledge_revisions',
    'eval_cases', 'eval_runs', 'eval_results',
    -- 017: package trees, project sources, learnings
    'agent_package_trees', 'agent_project_sources', 'agent_learnings',
    -- editorial
    'editorial_items', 'editorial_versions', 'editorial_events',
    -- 025: channels
    'channel_inbound',
    -- 027: finance
    'fin_accounts', 'fin_categories', 'fin_cost_centers', 'fin_recurrences',
    'fin_entries', 'fin_statement_imports', 'fin_statement_lines', 'fin_settlements',
    'fin_ledger', 'fin_attachments', 'fin_gateway_sync', 'fin_dre_settings',
    'fin_budgets',
    -- 031: Julia v2 content
    'agent_version_textos', 'agent_version_ferramentas', 'agent_version_decisoes',
    'agent_version_specs', 'textos_plataforma', 'agent_org_specs',
    -- 032: qualification + lead data
    'qualificacao_versoes', 'qualificacao_estagios', 'qualificacao_criterios',
    'qualificacao_parametros', 'qualificacao_padroes', 'lead_identificacao',
    'lead_identificacao_acessos', 'lead_imovel_eventos', 'lead_qualificacao_confirmacoes',
    'lead_qualificacao_estado', 'lead_qualificacao_registros',
    -- 033-035: shared thread
    'lead_refs', 'thread_participantes', 'thread_participante_eventos',
    'thread_skill_aberturas', 'agent_message_feedback', 'thread_handoffs'
  ];
BEGIN
  FOREACH t IN ARRAY v_tables LOOP
    IF to_regclass(format('agents.%I', t)) IS NULL THEN
      CONTINUE;  -- not created on this database (yet): nothing to revoke
    END IF;
    EXECUTE format('REVOKE ALL ON agents.%I FROM PUBLIC, anon, authenticated', t);
    FOR pol IN
      SELECT policyname FROM pg_policies
       WHERE schemaname = 'agents' AND tablename = t
         AND roles && ARRAY['public', 'anon', 'authenticated']::name[]
    LOOP
      EXECUTE format('DROP POLICY IF EXISTS %I ON agents.%I', pol.policyname, t);
    END LOOP;
  END LOOP;
END $revoke$;

-- The one allowlisted table: the frontend reads page-visibility flags through
-- supabase-js (`usePageStatus`). Read-only -- 001's `GRANT ALL` left write
-- privileges that only the absence of a write policy was holding back.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON agents.status_pagina FROM PUBLIC, anon, authenticated;
GRANT SELECT ON agents.status_pagina TO anon, authenticated;

-- 001 granted every FUTURE table to authenticated by default; a new table is now
-- private until a migration deliberately grants it (keeper
-- check_no_authenticated_grant_on_content_tables guards the grant itself).
ALTER DEFAULT PRIVILEGES IN SCHEMA agents REVOKE ALL ON TABLES FROM authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA agents REVOKE ALL ON TABLES FROM anon;

-- Assertion: fail the migration if anything outside the allowlist is still reachable.
DO $assert$
DECLARE
  v_allow constant text[] := ARRAY['status_pagina'];
  v_bad text;
BEGIN
  SELECT string_agg(c.relname, ', ' ORDER BY c.relname) INTO v_bad
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'agents' AND c.relkind IN ('r', 'p') AND NOT (c.relname = ANY (v_allow))
     AND (has_table_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
          OR has_any_column_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES')
          OR has_table_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
          OR has_any_column_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES'));
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION '036: agents table(s) still reachable by anon/authenticated: %', v_bad;
  END IF;

  SELECT string_agg(p.tablename || '.' || p.policyname, ', ') INTO v_bad
    FROM pg_policies p
   WHERE p.schemaname = 'agents' AND NOT (p.tablename = ANY (v_allow))
     AND p.roles && ARRAY['public', 'anon', 'authenticated']::name[];
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION '036: agents polic(ies) still name anon/authenticated/public: %', v_bad;
  END IF;

  IF has_table_privilege('authenticated', 'agents.status_pagina', 'INSERT, UPDATE, DELETE, TRUNCATE') THEN
    RAISE EXCEPTION '036: agents.status_pagina must stay read-only for authenticated';
  END IF;
END $assert$;
