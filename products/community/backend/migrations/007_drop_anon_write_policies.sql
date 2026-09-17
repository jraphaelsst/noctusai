-- ============================================================================
-- 007_drop_anon_write_policies.sql — close the anon REST surface on the
-- application tables.
--
-- WHY
-- ---
-- Migration 006 shipped two `anon` policies so the PUBLIC application form
-- could work before sign-in:
--     aplicacao_perguntas_select_anon_ativas  (SELECT, ativa = true)
--     aplicacoes_insert_anon                  (INSERT, WITH CHECK (true))
--
-- Neither is needed, and the INSERT one is a real hole. The two public routes
-- (`GET /api/aplicacoes/formulario`, `POST /api/aplicacoes`) use the
-- SERVICE-ROLE client (`get_admin_client()` in app/dependencies.py, see
-- routers/aplicacoes_router.py), and service_role BYPASSES RLS. So the anon
-- policies are dead weight for our own code path — but the `community` schema
-- is exposed through PostgREST (pgrst.db_schemas) and 001 granted table
-- privileges to `anon`, so with `WITH CHECK (true)` anyone could POST straight
-- to `/rest/v1/aplicacoes` and:
--   * insert rows for ANY org_id (the policy asserts nothing),
--   * skip the obrigatoria-question validation the endpoint enforces,
--   * skip the endpoint's rate limit (spam surface),
--   * set `status`, `revisado_por`, `revisado_em`, `membro_id` freely —
--     i.e. pre-approve their own application row.
--
-- The endpoint remains the only write path, which is where validation, the
-- rate limit and org resolution live. This is the "no silent hole" leg of the
-- same rule that made the ledger tables RLS-locked in core 048.
--
-- Applied live 2026-09-16, the same session 006 landed, with no rows in either
-- table (zero data risk).
--
-- IDEMPOTENT: DROP POLICY IF EXISTS; REVOKE is a no-op when not granted.
-- ============================================================================

SET search_path = community, public;

-- ----- aplicacoes: anon could insert arbitrary, pre-approved rows -----
DROP POLICY IF EXISTS "aplicacoes_insert_anon" ON community.aplicacoes;
REVOKE ALL ON community.aplicacoes FROM anon;

-- ----- aplicacao_perguntas: anon read is served by the service-role route ---
DROP POLICY IF EXISTS "aplicacao_perguntas_select_anon_ativas" ON community.aplicacao_perguntas;
REVOKE ALL ON community.aplicacao_perguntas FROM anon;

-- `authenticated` keeps its org-scoped policies from 006 (managers work
-- through a session); `service_role` is unaffected (it bypasses RLS) and is
-- what both public routes use.
