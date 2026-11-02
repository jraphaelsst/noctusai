-- nosnolimiar rename 2026-11 -- ONE-OFF prod data move + old-org delete (owner-approved 2026-11-02)
--
-- Owner decisions (2026-11-02): the app (ex-`monica`, now `nosnolimiar`) and its data live in the org
-- "Nós no Limiar" (company); the org "Mônica Tangerino" (individual, created by her signup) is DELETED.
-- Mônica's user account is KEPT: its home org becomes Nós no Limiar (owner).
--
--   Nós no Limiar    fa80a1e0-1bcd-4c65-8a37-2162e8ffa688   KEEP  (target)
--   Mônica Tangerino ad6ec2e2-b470-4044-884e-6345e4fe66d4   DELETE
--
-- Preconditions (RUNBOOK.md): core 095 + product 020 applied (schema `nosnolimiar` exists). The old
-- container is stopped. Run as service role / owner, ONE session, via the Supabase SQL editor or the MCP.
-- Run cutover-dry-run.sql FIRST (identical, ends in ROLLBACK).
-- Triggers stay ON for the user/org statements (the noctus_users -> org_memberships mirror + auth metadata
-- sync must fire). The social_wiring moves run under session_replication_role = replica (composite
-- (org_id, id) FKs are not deferrable and have no ON UPDATE CASCADE); integrity is re-checked in section 7.

BEGIN;

-- ── 0 · guards (wrong database / wrong order / already applied -> refuse) ─────────────────────────────────
DO $$
DECLARE
  v_mt  constant uuid := 'ad6ec2e2-b470-4044-884e-6345e4fe66d4';
  v_nnl constant uuid := 'fa80a1e0-1bcd-4c65-8a37-2162e8ffa688';
  v_n int;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.organizations WHERE id = v_nnl AND nome = 'Nós no Limiar' AND org_type = 'company') THEN
    RAISE EXCEPTION 'cutover: target org % is not "Nós no Limiar"/company -- wrong database', v_nnl;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.organizations WHERE id = v_mt AND nome = 'Mônica Tangerino' AND is_personal) THEN
    RAISE EXCEPTION 'cutover: org % is not the personal "Mônica Tangerino" org (already deleted, or wrong database)', v_mt;
  END IF;
  IF to_regnamespace('nosnolimiar') IS NULL THEN
    RAISE EXCEPTION 'cutover: schema nosnolimiar missing -- apply product migration 020 first';
  END IF;
  -- Exactly one user has MT as home org, it is the MT owner, and it is already an owner member of Nós no Limiar.
  SELECT count(*) INTO v_n FROM public.noctus_users WHERE org_id = v_mt;
  IF v_n <> 1 THEN RAISE EXCEPTION 'cutover: expected exactly 1 user with home org MT, found %', v_n; END IF;
  IF NOT EXISTS (SELECT 1 FROM public.noctus_users u JOIN public.organizations o ON o.owner_id = u.id
                  WHERE u.org_id = v_mt AND o.id = v_mt AND u.id = '1da6a758-b222-4bdc-ab6b-599b6d599612') THEN
    RAISE EXCEPTION 'cutover: the user whose home org is MT is not MT''s owner (expected Mônica''s user 1da6a758-…)';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.org_memberships m JOIN public.noctus_users u ON u.id = m.user_id
                  WHERE m.org_id = v_nnl AND u.org_id = v_mt AND m.org_role = 'owner') THEN
    RAISE EXCEPTION 'cutover: the MT user is not an owner member of Nós no Limiar -- decide before moving';
  END IF;
  -- fin_categories: the unique key is (org_id, parent, lower(name)); NnL must hold none yet.
  EXECUTE 'SELECT count(*) FROM nosnolimiar.fin_categories WHERE org_id = $1' INTO v_n USING v_nnl;
  IF v_n <> 0 THEN RAISE EXCEPTION 'cutover: Nós no Limiar already has % fin_categories -- would duplicate', v_n; END IF;
  EXECUTE 'SELECT count(*) FROM nosnolimiar.fin_categories WHERE org_id = $1' INTO v_n USING v_mt;
  IF v_n <> 30 THEN RAISE NOTICE 'cutover: fin_categories of MT = % (recon saw 30)', v_n; END IF;
END $$;

-- ── 1 · the user: home org -> Nós no Limiar (owner). Triggers ON (membership mirror + auth sync) ─────────────
UPDATE public.noctus_users
   SET org_id = 'fa80a1e0-1bcd-4c65-8a37-2162e8ffa688', org_role = 'owner'
 WHERE org_id = 'ad6ec2e2-b470-4044-884e-6345e4fe66d4';

-- ── 2 · nosnolimiar.* : every row of MT -> Nós no Limiar (fin_categories is the only non-empty table) ─────────
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT c.table_name FROM information_schema.columns c
             JOIN information_schema.tables x ON x.table_schema = c.table_schema AND x.table_name = c.table_name AND x.table_type = 'BASE TABLE'
            WHERE c.table_schema = 'nosnolimiar' AND c.column_name = 'org_id'
  LOOP
    EXECUTE format('UPDATE nosnolimiar.%I SET org_id = %L WHERE org_id = %L', t.table_name,
                   'fa80a1e0-1bcd-4c65-8a37-2162e8ffa688', 'ad6ec2e2-b470-4044-884e-6345e4fe66d4');
  END LOOP;
END $$;

-- ── 3 · social_wiring.*: the MT brand + the one Studio chat -> Nós no Limiar (no longer primary) ───────────────
SET LOCAL session_replication_role = replica;
UPDATE social_wiring.marcas SET is_primary = false
 WHERE org_id = 'ad6ec2e2-b470-4044-884e-6345e4fe66d4';   -- NnL already has its own primary brand (uq_marcas_one_primary_per_org)
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT c.table_name FROM information_schema.columns c
             JOIN information_schema.tables x ON x.table_schema = c.table_schema AND x.table_name = c.table_name AND x.table_type = 'BASE TABLE'
            WHERE c.table_schema = 'social_wiring' AND c.column_name = 'org_id'
  LOOP
    EXECUTE format('UPDATE social_wiring.%I SET org_id = %L WHERE org_id = %L', t.table_name,
                   'fa80a1e0-1bcd-4c65-8a37-2162e8ffa688', 'ad6ec2e2-b470-4044-884e-6345e4fe66d4');
  END LOOP;
END $$;
SET LOCAL session_replication_role = origin;

-- ── 4 · erp.profiles of MT (no FK -> would be orphaned by the org delete; NnL has its own agency profile) ──────
DELETE FROM erp.profiles WHERE org_id = 'ad6ec2e2-b470-4044-884e-6345e4fe66d4';

-- ── 5 · audit_logs of MT: FK is NO ACTION + the append-only guard. The sanctioned carve-out is the GUC the ───
--      purge function sets (core 053). Owner-approved 2026-11-02 (the 5 rows are signup, 2 grants, 2 SW POSTs).
SELECT set_config('core.audit_log_purge', 'on', true);
DELETE FROM public.audit_logs WHERE org_id = 'ad6ec2e2-b470-4044-884e-6345e4fe66d4';
SELECT set_config('core.audit_log_purge', 'off', true);

-- ── 6 · delete the org (cascades: licenses, memberships, platform_org_selections, notifications, pipeline_stages) ─
DELETE FROM public.organizations WHERE id = 'ad6ec2e2-b470-4044-884e-6345e4fe66d4';

-- ── 7 · post-checks: ZERO references anywhere; the user and her ownership survive ─────────────────────────────
DO $$
DECLARE
  v_mt  constant uuid := 'ad6ec2e2-b470-4044-884e-6345e4fe66d4';
  v_nnl constant uuid := 'fa80a1e0-1bcd-4c65-8a37-2162e8ffa688';
  t record; v_n bigint; v_left text := '';
BEGIN
  FOR t IN SELECT c.table_schema, c.table_name, c.column_name
             FROM information_schema.columns c
             JOIN information_schema.tables x ON x.table_schema = c.table_schema AND x.table_name = c.table_name AND x.table_type = 'BASE TABLE'
            WHERE c.column_name IN ('org_id', 'organization_id', 'target_org_id', 'home_org_id', 'acting_org_id', 'owner_org_id')
              AND c.table_schema NOT IN ('pg_catalog', 'information_schema')
  LOOP
    EXECUTE format('SELECT count(*) FROM %I.%I WHERE %I = $1', t.table_schema, t.table_name, t.column_name) INTO v_n USING v_mt;
    IF v_n > 0 THEN v_left := v_left || format('%s.%s.%s=%s; ', t.table_schema, t.table_name, t.column_name, v_n); END IF;
  END LOOP;
  IF v_left <> '' THEN RAISE EXCEPTION 'post-check: rows still reference the deleted org: %', v_left; END IF;
  IF EXISTS (SELECT 1 FROM public.organizations WHERE id = v_mt) THEN RAISE EXCEPTION 'post-check: org MT still exists'; END IF;
  IF NOT EXISTS (SELECT 1 FROM public.noctus_users u JOIN public.org_memberships m ON m.user_id = u.id AND m.org_id = v_nnl
                  WHERE u.org_id = v_nnl AND u.org_role = 'owner' AND m.org_role = 'owner'
                    AND u.id = (SELECT owner_id FROM public.organizations WHERE id = v_nnl)) THEN
    RAISE EXCEPTION 'post-check: the user does not have home org = Nós no Limiar with owner membership';
  END IF;
  EXECUTE 'SELECT count(*) FROM nosnolimiar.fin_categories WHERE org_id = $1' INTO v_n USING v_nnl;
  IF v_n < 30 THEN RAISE EXCEPTION 'post-check: Nós no Limiar has only % fin_categories (expected >= 30)', v_n; END IF;
  IF (SELECT count(*) FROM social_wiring.marcas WHERE org_id = v_nnl AND is_primary) <> 1 THEN
    RAISE EXCEPTION 'post-check: Nós no Limiar must have exactly one primary marca';
  END IF;
  RAISE NOTICE 'post-checks OK: no references to the deleted org; fin_categories(NnL)=%', v_n;
END $$;

COMMIT;
