-- ============================================================
-- 030 — service_role_bypass policy backfill for core admin tables
-- ============================================================
-- Closes the 149 DEFENSE_IN_DEPTH findings classified by Engineer RR
-- (`projects/keeper-trio-platform-triage/phase-0-triage.md`) for core's
-- 12 admin-touched tables (billing_events covered by 029).
--
-- WHY: every table listed below already has a `<table>_service` /
-- `<table>_admin_full` policy in `001_noctusai_core.sql:357+` (49+
-- such policies) with the same FOR-ALL-TO-service_role shape. They
-- work at runtime — Supabase service_role JWT bypasses RLS at the
-- connection level. But the keeper detector
-- (`check_admin_endpoint_service_role_bypass`) matches the LITERAL
-- name `service_role_bypass` — the convention adopted by therapy's
-- `001_therapy_platform.sql:846+` and now formalized in
-- `noctusai_lib.sql.service_role_bypass(table, schema)` (Wave 0
-- commit `b76c43f`).
--
-- We ADD the canonically-named policies alongside the existing
-- `<table>_service` policies — we do NOT rename. Renaming would
-- temporarily re-open keeper findings + churn the migration audit
-- trail. Having two policies of the same shape on the same table is
-- harmless (PostgreSQL OR-merges policies for the same role).
--
-- Every CREATE POLICY line below is byte-equal to the output of
-- `noctusai_lib.sql.service_role_bypass(table, schema="public")` —
-- helper drift would surface in test_sql_templates.py simultaneously.
--
-- Table list (counts = detector hit counts in baseline --review):
--   noctus_users (43), subscriptions (32), roles (16), licenses (14),
--   plans (11), webhook_endpoints (6), webhook_deliveries (5),
--   org_settings (5), audit_logs (5), api_keys (5),
--   platform_settings (4), notifications (2).
--
-- Apply via Supabase MCP `apply_migration` ("MCP migrations mirror
-- the file" rule).
-- ============================================================

DROP POLICY IF EXISTS "service_role_bypass" ON public.noctus_users;
CREATE POLICY "service_role_bypass" ON public.noctus_users FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON public.subscriptions;
CREATE POLICY "service_role_bypass" ON public.subscriptions FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON public.roles;
CREATE POLICY "service_role_bypass" ON public.roles FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON public.licenses;
CREATE POLICY "service_role_bypass" ON public.licenses FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON public.plans;
CREATE POLICY "service_role_bypass" ON public.plans FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON public.webhook_endpoints;
CREATE POLICY "service_role_bypass" ON public.webhook_endpoints FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON public.webhook_deliveries;
CREATE POLICY "service_role_bypass" ON public.webhook_deliveries FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON public.org_settings;
CREATE POLICY "service_role_bypass" ON public.org_settings FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON public.audit_logs;
CREATE POLICY "service_role_bypass" ON public.audit_logs FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON public.api_keys;
CREATE POLICY "service_role_bypass" ON public.api_keys FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON public.platform_settings;
CREATE POLICY "service_role_bypass" ON public.platform_settings FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_bypass" ON public.notifications;
CREATE POLICY "service_role_bypass" ON public.notifications FOR ALL TO service_role USING (true) WITH CHECK (true);
