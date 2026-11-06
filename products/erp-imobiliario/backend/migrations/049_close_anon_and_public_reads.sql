-- Migration 049: close_anon_and_public_reads
-- Schema: erp
--
-- WHY (access-tier ledger, verified in prod 2026-11-05; every table held 0 live
-- rows, so the exposure was latent): the data API (PostgREST) serves `erp` and
-- 003 granted anon/authenticated full DML on every table + default privileges.
--   AT-af2a4272 erp.portal_tokens   `portal_tokens_anon_read`  (anon, is_active AND expires_at>now())
--   AT-5d90688d erp.portal_acessos  `portal_acessos_anon_read` (anon, ativo)   -- both carry a `token` column
--   AT-a8c3505d erp.site_config     `site_config_anon_read`     (anon)          -- telefone/whatsapp/email_contato
--   AT-418d68d1 meta_periodos / AT-999c2102 metas_configuracao /
--   AT-d3d36c2c metas_empresa / AT-b87d15b7 regras_pontuacao: `corretor_select_*`
--     policies with role PUBLIC and USING (true) -> anon (and any org) read every row.
--
-- NO browser-facing replacement is needed: the public portal / public site
-- resolve the token and the slug SERVER-SIDE with the service-role client
-- (app/routers/portal_externo.py::_validate_token, site_imoveis.py::site_publico),
-- and the frontend never reads these tables. A SECURITY DEFINER RPC would only
-- re-open the surface the backend already closes. So: anon loses the policies AND
-- the grants (Supabase: "RLS is defence in depth; revoke what a role must not
-- touch" -- https://supabase.com/docs/guides/database/postgres/row-level-security,
-- https://supabase.com/docs/guides/api/securing-your-api ; OWASP API1:2023 BOLA /
-- API3:2023 broken object property level authorization).
--
-- Authenticated keeps its org-scoped CRUD (`*_select_policy` etc. from 032): the
-- staff list/issue routes use the caller's JWT client and project the token out
-- of list responses (portal_externo._project_*). Column-level REVOKE of `token`
-- would break insert-returning-representation, so it is deliberately not done.
--
-- NOT DONE HERE (AT-847e83bb, erp still in pgrst.db_schemas while ativo=false):
-- NOC-REMEDIATE[access-tier]: `authenticator.pgrst.db_schemas` is a shared, fleet-wide role setting. Its only repo
-- owner (noctus.dev.ensure_schema_exposure) is append-only by design; nothing derives the list from the catalog's
-- active products or removes asleep schemas (core 077 removed `mailing` by hand-written one-off). Proposal for the
-- coordinator: add a `prune` action to ensure_schema_exposure (dry-run default) = served list MINUS schemas of
-- catalog ativo=false products, re-added by the existing wake path (`apply`). Until then, with the grants/policies
-- above, erp being served exposes no anon-readable row; the schema simply answers 401/42501 to browser roles.
--
-- Forward-safe vs N-1: the previous image never used anon on these tables.
-- Idempotent (DROP POLICY IF EXISTS / REVOKE / re-create).
-- Runner lock_timeout default (5s) applies.

SET search_path = erp, public;

-- 1. Drop the anonymous policies (the token tables and site_config).
DROP POLICY IF EXISTS portal_tokens_anon_read  ON erp.portal_tokens;
DROP POLICY IF EXISTS portal_acessos_anon_read ON erp.portal_acessos;
DROP POLICY IF EXISTS site_config_anon_read    ON erp.site_config;

-- 2. anon holds no privilege on them at all.
REVOKE ALL ON erp.portal_tokens, erp.portal_acessos, erp.site_config,
              erp.meta_periodos, erp.metas_configuracao, erp.metas_empresa,
              erp.regras_pontuacao
    FROM anon;

-- 3. No future erp table inherits anon DML (003 set these default privileges).
ALTER DEFAULT PRIVILEGES IN SCHEMA erp REVOKE ALL ON TABLES FROM anon;

-- 4. The PUBLIC `USING (true)` metas policies -> authenticated + org scope.
DROP POLICY IF EXISTS corretor_select_meta_periodos ON erp.meta_periodos;
CREATE POLICY corretor_select_meta_periodos ON erp.meta_periodos
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

DROP POLICY IF EXISTS corretor_select_metas_empresa ON erp.metas_empresa;
-- metas_empresa has NO org_id (016): it belongs to an org through its period (periodo_id -> meta_periodos.org_id).
CREATE POLICY corretor_select_metas_empresa ON erp.metas_empresa
    FOR SELECT TO authenticated
    USING (EXISTS (SELECT 1 FROM erp.meta_periodos p
                   WHERE p.id = metas_empresa.periodo_id AND p.org_id = current_org_id()));

DROP POLICY IF EXISTS corretor_select_metas_configuracao ON erp.metas_configuracao;
CREATE POLICY corretor_select_metas_configuracao ON erp.metas_configuracao
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

-- regras_pontuacao: org_id NULL = platform default rules (016), readable by every
-- authenticated member so the UI can show formulas; tenant rows stay org-scoped.
DROP POLICY IF EXISTS corretor_select_regras_pontuacao ON erp.regras_pontuacao;
CREATE POLICY corretor_select_regras_pontuacao ON erp.regras_pontuacao
    FOR SELECT TO authenticated
    USING (org_id IS NULL OR org_id = current_org_id());
