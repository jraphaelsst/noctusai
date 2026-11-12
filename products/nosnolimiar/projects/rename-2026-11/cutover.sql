-- nosnolimiar rename 2026-11 -- ONE-OFF prod data MOVE (the cutover window; owner-approved 2026-11-02)
--
-- Owner decisions (2026-11-02): the app (ex-`monica`, now `nosnolimiar`) and its data live in the org
-- "Nós no Limiar" (company); the org "Mônica Tangerino" (individual, created by her signup) is DELETED -- but
-- ONLY by cleanup-old-org.sql, after 7 days of verification (owner delegation 2026-11-12): this script deletes nothing.
-- Mônica's user account is KEPT: its home org becomes Nós no Limiar (owner).
--
--   Nós no Limiar    fa80a1e0-1bcd-4c65-8a37-2162e8ffa688   KEEP  (target)
--   Mônica Tangerino ad6ec2e2-b470-4044-884e-6345e4fe66d4   kept for 7 days, then cleanup-old-org.sql
--
-- Preconditions (RUNBOOK.md): core 120 + product 022 applied (schema `nosnolimiar` exists). The old
-- container is stopped. Run as service role / owner, ONE session, via the Supabase SQL editor or the MCP.
-- Run cutover-dry-run.sql FIRST (identical, ends in ROLLBACK). Triggers stay ON for the user statement (the
-- noctus_users -> org_memberships mirror + auth metadata sync must fire).

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
    RAISE EXCEPTION 'cutover: schema nosnolimiar missing -- apply product migration 022 first';
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
  -- M1: the surviving org MUST hold an active license on the RENAMED product. The app's license gate
  -- (org_sem_licenca) is evaluated against Nós no Limiar from now on; without this row the user is locked out
  -- the moment the org delete commits. Needs core 120 (the catalog row is already `nosnolimiar`).
  IF NOT EXISTS (SELECT 1 FROM public.licenses l JOIN public.products p ON p.id = l.product_id
                  WHERE l.org_id = v_nnl AND p.slug = 'nosnolimiar'
                    AND l.status = 'active' AND (l.fim IS NULL OR l.fim > now())) THEN
    RAISE EXCEPTION 'cutover: Nós no Limiar holds no ACTIVE license on product nosnolimiar (core 120 applied? license granted?) -- refusing to delete the old org';
  END IF;
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

-- ── 2b · public.notifications of MT (3 rows): MOVED, not cascaded -- they are the owner's own in-app notices and ─
--      she now logs into Nós no Limiar. The FK column is read from the catalog (no hand-typed column name).
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT a.attname AS col
             FROM pg_constraint c
             CROSS JOIN LATERAL unnest(c.conkey, c.confkey) AS k(child, parent)
             JOIN pg_attribute a  ON a.attrelid  = c.conrelid  AND a.attnum  = k.child
             JOIN pg_attribute pa ON pa.attrelid = c.confrelid AND pa.attnum = k.parent AND pa.attname = 'id'
            WHERE c.contype = 'f' AND c.confrelid = 'public.organizations'::regclass
              AND c.conrelid = 'public.notifications'::regclass AND cardinality(c.conkey) = 1
  LOOP
    EXECUTE format('UPDATE public.notifications SET %I = %L WHERE %I = %L', t.col,
                   'fa80a1e0-1bcd-4c65-8a37-2162e8ffa688', t.col, 'ad6ec2e2-b470-4044-884e-6345e4fe66d4');
  END LOOP;
END $$;

-- ── 3 · post-checks (the move is complete; the old org is untouched and still deletable by cleanup-old-org.sql) ──
DO $$
DECLARE
  v_mt  constant uuid := 'ad6ec2e2-b470-4044-884e-6345e4fe66d4';
  v_nnl constant uuid := 'fa80a1e0-1bcd-4c65-8a37-2162e8ffa688';
  v_n bigint;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.noctus_users u JOIN public.org_memberships m ON m.user_id = u.id AND m.org_id = v_nnl
                  WHERE u.org_id = v_nnl AND u.org_role = 'owner' AND m.org_role = 'owner'
                    AND u.id = (SELECT owner_id FROM public.organizations WHERE id = v_nnl)) THEN
    RAISE EXCEPTION 'post-check: the user does not have home org = Nós no Limiar with owner membership';
  END IF;
  EXECUTE 'SELECT count(*) FROM nosnolimiar.fin_categories WHERE org_id = $1' INTO v_n USING v_nnl;
  IF v_n < 30 THEN RAISE EXCEPTION 'post-check: Nós no Limiar has only % fin_categories (expected >= 30)', v_n; END IF;
  EXECUTE 'SELECT count(*) FROM nosnolimiar.fin_categories WHERE org_id = $1' INTO v_n USING v_mt;
  IF v_n <> 0 THEN RAISE EXCEPTION 'post-check: % fin_categories still point at the old org', v_n; END IF;
  RAISE NOTICE 'post-checks OK: user + nosnolimiar.* now in Nós no Limiar; old org kept for cleanup-old-org.sql';
END $$;

COMMIT;
