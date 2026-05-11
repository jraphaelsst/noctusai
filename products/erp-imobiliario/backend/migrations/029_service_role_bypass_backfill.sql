-- Migration 029: service_role_bypass policy backfill (ERP)
--
-- Project:   projects/keeper-trio-erp/PROJECT.md
-- Wave:      Wave 1 child B of keeper-trio-platform-triage
-- Surfaced:  2026-05-11 phase-0-triage.md (ERP §DEFENSE_IN_DEPTH)
--
-- Background:
--   `check_admin_endpoint_service_role_bypass` flagged 33 sites in ERP
--   touching 14 tables via the admin client without a named
--   `service_role_bypass` policy on the target table. RLS bypass works
--   today via the connection-level service_role JWT plus per-table
--   `auth.role() = 'service_role'` USING clauses (e.g. erp.001:2362
--   `certidao_consultas_service`) and dynamic DO-block policies
--   (e.g. erp.001:2264, 004:1074). The detector looks for the literal
--   policy NAME `"service_role_bypass"` — the canonical platform shape
--   adopted by therapy-platform's 001:846+.
--
--   This backfill adds the canonical-named policy to the 14 admin-touched
--   tables ERP exposes to its routers / services / scheduler. The
--   existing implicit-bypass policies stay in place — that's defense in
--   depth, not a conflict (Postgres accepts multiple FOR ALL policies on
--   the same table, evaluating them as OR-of-USING).
--
-- The canonical policy SQL is produced by
-- `noctusai_lib.sql.service_role_bypass(table, schema="erp")`. Each
-- line below is byte-identical to the helper output (snapshot
-- 2026-05-11) — do not hand-edit. Re-author from the helper when
-- a 15th table joins the admin-touched set.
--
-- Idempotency: every `CREATE POLICY` is wrapped in a DROP-then-CREATE
-- pair so re-applying this migration is a no-op (Postgres has no
-- `CREATE POLICY ... IF NOT EXISTS` at version 17.6).
--
-- Per `feedback_mcp_migrations_mirror_file`: this file is committed
-- BEFORE being applied via mcp__claude_ai_Supabase__apply_migration.

DROP POLICY IF EXISTS "service_role_bypass" ON erp.ativos;
CREATE POLICY "service_role_bypass" ON erp.ativos FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON erp.assinaturas;
CREATE POLICY "service_role_bypass" ON erp.assinaturas FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON erp.site_config;
CREATE POLICY "service_role_bypass" ON erp.site_config FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON erp.meta_config;
CREATE POLICY "service_role_bypass" ON erp.meta_config FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON erp.whatsapp_messages;
CREATE POLICY "service_role_bypass" ON erp.whatsapp_messages FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON erp.profiles;
CREATE POLICY "service_role_bypass" ON erp.profiles FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON erp.clientes;
CREATE POLICY "service_role_bypass" ON erp.clientes FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON erp.campanhas;
CREATE POLICY "service_role_bypass" ON erp.campanhas FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON erp.whatsapp_config;
CREATE POLICY "service_role_bypass" ON erp.whatsapp_config FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON erp.parcelas_contrato;
CREATE POLICY "service_role_bypass" ON erp.parcelas_contrato FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON erp.meta_leads;
CREATE POLICY "service_role_bypass" ON erp.meta_leads FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON erp.matches;
CREATE POLICY "service_role_bypass" ON erp.matches FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON erp.envios_email;
CREATE POLICY "service_role_bypass" ON erp.envios_email FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON erp.contratos;
CREATE POLICY "service_role_bypass" ON erp.contratos FOR ALL TO service_role USING (true) WITH CHECK (true);
