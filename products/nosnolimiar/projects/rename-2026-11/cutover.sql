-- nosnolimiar rename 2026-11 -- ONE-OFF prod data move + old-org delete (owner-approved 2026-11-02)
--
-- Owner decisions (2026-11-02): the app (ex-`monica`, now `nosnolimiar`) and its data live in the org
-- "Nós no Limiar" (company); the org "Mônica Tangerino" (individual, created by her signup) is DELETED.
-- Mônica's user account is KEPT: its home org becomes Nós no Limiar (owner).
-- Owner decision (2026-11-05): ONE branding per org -- MT's marca + its Studio chat are DELETED, never moved to NnL.
--
--   Nós no Limiar    fa80a1e0-1bcd-4c65-8a37-2162e8ffa688   KEEP  (target)
--   Mônica Tangerino ad6ec2e2-b470-4044-884e-6345e4fe66d4   DELETE
--
-- Preconditions (RUNBOOK.md): core 120 + product 022 applied (schema `nosnolimiar` exists). The old
-- container is stopped. Run as service role / owner, ONE session, via the Supabase SQL editor or the MCP.
-- Run cutover-dry-run.sql FIRST (identical, ends in ROLLBACK).
-- Triggers stay ON for the user/org statements (the noctus_users -> org_memberships mirror + auth metadata
-- sync must fire). social_wiring rows of MT are DELETED, not moved (owner 2026-11-05, one branding per org —
-- section 3); integrity is re-checked in section 7.

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
  -- M2: this script does NOT move Storage objects. Any object filed under MT's org id (first folder segment,
  -- or anywhere in the name) would be orphaned/unreachable once the org is gone: refuse, move them first.
  IF to_regclass('storage.objects') IS NULL THEN
    RAISE EXCEPTION 'cutover: storage.objects not found -- cannot prove MT owns no Storage objects';
  END IF;
  EXECUTE 'SELECT count(*) FROM storage.objects WHERE split_part(name, ''/'', 1) = $1 OR position($1 in name) > 0'
     INTO v_n USING v_mt::text;
  IF v_n <> 0 THEN
    RAISE EXCEPTION 'cutover: % storage.objects row(s) are filed under MT''s org id -- this script does not move Storage; move or re-key them first', v_n;
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

-- ── 3 · social_wiring.*: DELETE MT's brand + its one Studio chat — NOT moved (owner 2026-11-05: "one branding
--    per org"; "delete monica, let's keep only nos no limiar"). NnL keeps exactly ONE marca (its own primary).
--    Max-count guarded (live inventory 2026-11-05: cs_chat_mensagens 1, cs_chat_conversas 1, marcas 1); more -> abort.
--    marcas has no archive column, so "archive" = this audited delete. Children first; nothing may cascade/SET NULL
--    silently off the marca (any other marca_id reference aborts).
DO $$
DECLARE
  v_mt uuid := 'ad6ec2e2-b470-4044-884e-6345e4fe66d4';
  v_mk uuid := '07798cf9-01aa-465e-aa11-49f3a0a18386';
  v_n int; v_left text := ''; t record;
BEGIN
  IF (SELECT count(*) FROM social_wiring.marcas WHERE org_id = v_mt) <> 1
     OR NOT EXISTS (SELECT 1 FROM social_wiring.marcas WHERE id = v_mk AND org_id = v_mt) THEN
    RAISE EXCEPTION 'social_wiring: MT must hold exactly its one marca %', v_mk;
  END IF;
  DELETE FROM social_wiring.cs_chat_mensagens WHERE org_id = v_mt; GET DIAGNOSTICS v_n = ROW_COUNT;
  IF v_n > 1 THEN RAISE EXCEPTION 'social_wiring: % cs_chat_mensagens for MT (max 1 allowlisted) -- re-inventory', v_n; END IF;
  RAISE NOTICE 'social_wiring: deleted % cs_chat_mensagens of MT', v_n;
  DELETE FROM social_wiring.cs_chat_conversas WHERE org_id = v_mt; GET DIAGNOSTICS v_n = ROW_COUNT;
  IF v_n > 1 THEN RAISE EXCEPTION 'social_wiring: % cs_chat_conversas for MT (max 1 allowlisted) -- re-inventory', v_n; END IF;
  RAISE NOTICE 'social_wiring: deleted % cs_chat_conversas of MT', v_n;
  FOR t IN SELECT c.table_name FROM information_schema.columns c
             JOIN information_schema.tables x ON x.table_schema = c.table_schema AND x.table_name = c.table_name AND x.table_type = 'BASE TABLE'
            WHERE c.table_schema = 'social_wiring' AND c.column_name = 'marca_id'
  LOOP
    EXECUTE format('SELECT count(*) FROM social_wiring.%I WHERE marca_id = $1', t.table_name) INTO v_n USING v_mk;
    IF v_n > 0 THEN v_left := v_left || format('%s=%s; ', t.table_name, v_n); END IF;
  END LOOP;
  IF v_left <> '' THEN RAISE EXCEPTION 'social_wiring: rows still reference the MT marca (would cascade/null): %', v_left; END IF;
  DELETE FROM social_wiring.marcas WHERE id = v_mk AND org_id = v_mt; GET DIAGNOSTICS v_n = ROW_COUNT;
  IF v_n <> 1 THEN RAISE EXCEPTION 'social_wiring: expected to delete 1 MT marca, deleted %', v_n; END IF;
  RAISE NOTICE 'social_wiring: deleted MT marca % (Mônica Tangerino)', v_mk;
  FOR t IN SELECT c.table_name FROM information_schema.columns c
             JOIN information_schema.tables x ON x.table_schema = c.table_schema AND x.table_name = c.table_name AND x.table_type = 'BASE TABLE'
            WHERE c.table_schema = 'social_wiring' AND c.column_name = 'org_id'
  LOOP
    EXECUTE format('SELECT count(*) FROM social_wiring.%I WHERE org_id = $1', t.table_name) INTO v_n USING v_mt;
    IF v_n > 0 THEN RAISE EXCEPTION 'social_wiring: %.org_id still holds % MT row(s) -- re-inventory', t.table_name, v_n; END IF;
  END LOOP;
END $$;

-- ── 4 · erp.profiles of MT (no FK -> would be orphaned by the org delete; NnL has its own agency profile) ──────
DELETE FROM erp.profiles WHERE org_id = 'ad6ec2e2-b470-4044-884e-6345e4fe66d4';

-- ── 5 · audit_logs of MT: FK is NO ACTION + the append-only guard. The sanctioned carve-out is the GUC the ───
--      purge function sets (core 053). Owner-approved 2026-11-02 (the 5 rows are signup, 2 grants, 2 SW POSTs).
SELECT set_config('core.audit_log_purge', 'on', true);
DELETE FROM public.audit_logs WHERE org_id = 'ad6ec2e2-b470-4044-884e-6345e4fe66d4';
SELECT set_config('core.audit_log_purge', 'off', true);

-- ── 5b · public.notifications of MT (3 rows): MOVED, not cascaded -- they are the owner's own in-app notices and ─
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

-- ── 6a · CASCADE INVENTORY (catalog-derived) -- runs BEFORE the delete, so losses are visible and abortable ──────
-- The old post-check (section 7) runs AFTER the delete: ON DELETE CASCADE rows are already gone and invisible to
-- it. Here we walk pg_constraint: EVERY foreign key onto public.organizations (any ON DELETE action, multi-column
-- keys included) PLUS one hop through public.org_memberships (e.g. org_member_product_access, keyed by the
-- membership rows of MT). A table still holding MT rows that is NOT in the allowlist below aborts the script.
-- The allowlist is the ONLY set of tables this script knowingly lets the delete remove. Value = the maximum rows
-- tolerated (recon 2026-11-02: exact; a larger count means data appeared since and must be looked at):
--   erp.pipeline_stages.org_id               13  MT's signup-seeded default funnel template; Nós no Limiar has its own
--                                                   (guarded below: it must hold >= 1). Moving would duplicate stages.
--   public.licenses.org_id                       2  MT's own licenses; NnL's license on nosnolimiar is guarded in section 0.
--   public.org_memberships.org_id                1  MT's membership row of the user (home org just moved; the NnL
--                                                   owner membership already exists and is asserted in sections 0 and 7).
--   public.platform_org_selections.target_org_id 13 \ platform-staff org-picker session history (service-role only,
--   public.platform_org_selections.home_org_id    4 /  ephemeral) that names MT; carries no business data.
-- NOT allowlisted because moved/purged earlier: noctus_users (1, step 1), nosnolimiar.* (moved, step 2),
-- social_wiring.* (DELETED, step 3: cs_chat_mensagens 1 / cs_chat_conversas 1 / marcas 1), audit_logs (5, step 5),
-- notifications (3, 5b).
DO $$
DECLARE
  v_mt  constant uuid := 'ad6ec2e2-b470-4044-884e-6345e4fe66d4';
  v_nnl constant uuid := 'fa80a1e0-1bcd-4c65-8a37-2162e8ffa688';
  v_allow constant jsonb := '{
    "erp.pipeline_stages.org_id": 13,
    "public.licenses.org_id": 2,
    "public.org_memberships.org_id": 1,
    "public.platform_org_selections.target_org_id": 13,
    "public.platform_org_selections.home_org_id": 4
  }'::jsonb;
  f record; v_n bigint; v_cap bigint; v_key text; v_bad text := ''; v_tot bigint := 0;
BEGIN
  -- NnL must own a funnel of its own, or the pipeline_stages cascade would leave the moved leads without stages.
  EXECUTE 'SELECT count(*) FROM erp.pipeline_stages WHERE org_id = $1' INTO v_n USING v_nnl;
  IF v_n < 1 THEN RAISE EXCEPTION 'inventory: Nós no Limiar has no pipeline_stages -- move MT''s instead of cascading them'; END IF;

  FOR f IN
    SELECT format('%I.%I', rn.nspname, rc.relname) AS rel,       -- always schema-qualified (regclass::text drops 'public.')
           (c.confrelid = 'public.organizations'::regclass) AS on_org, c.confdeltype AS del,
           string_agg(a.attname, '+' ORDER BY k.ord) AS cols,
           string_agg(format('o.%I = t.%I', pa.attname, a.attname), ' AND ' ORDER BY k.ord) AS join_pred
      FROM pg_constraint c
      JOIN pg_class rc ON rc.oid = c.conrelid
      JOIN pg_namespace rn ON rn.oid = rc.relnamespace
      CROSS JOIN LATERAL unnest(c.conkey, c.confkey) WITH ORDINALITY AS k(child, parent, ord)
      JOIN pg_attribute a  ON a.attrelid  = c.conrelid  AND a.attnum  = k.child
      JOIN pg_attribute pa ON pa.attrelid = c.confrelid AND pa.attnum = k.parent
     WHERE c.contype = 'f'
       AND c.confrelid IN ('public.organizations'::regclass, 'public.org_memberships'::regclass)
     GROUP BY c.oid, rn.nspname, rc.relname, c.confrelid, c.confdeltype
     ORDER BY 1, 4
  LOOP
    IF f.on_org THEN
      EXECUTE format('SELECT count(*) FROM %s t WHERE EXISTS (SELECT 1 FROM public.organizations o WHERE o.id = $1 AND %s)',
                     f.rel, f.join_pred) INTO v_n USING v_mt;
      v_key := f.rel || '.' || f.cols;
    ELSE   -- one hop: rows pointing at a membership row OF MT
      EXECUTE format('SELECT count(*) FROM %s t WHERE EXISTS (SELECT 1 FROM public.org_memberships o WHERE o.org_id = $1 AND %s)',
                     f.rel, f.join_pred) INTO v_n USING v_mt;
      v_key := f.rel || '.' || f.cols || ' (via org_memberships)';
    END IF;
    IF v_n = 0 THEN CONTINUE; END IF;
    v_cap := (v_allow ->> v_key)::bigint;
    IF v_cap IS NULL OR v_n > v_cap THEN
      v_bad := v_bad || format('%s=%s (ON DELETE %s, allowed %s); ', v_key, v_n, f.del, coalesce(v_cap::text, 'none'));
    ELSE
      v_tot := v_tot + v_n;
      RAISE NOTICE 'inventory: allowed cascade % = % row(s) (cap %)', v_key, v_n, v_cap;
    END IF;
  END LOOP;
  IF v_bad <> '' THEN
    RAISE EXCEPTION 'inventory: the org delete would silently drop/null rows not in the allowlist: %', v_bad;
  END IF;
  RAISE NOTICE 'inventory OK: % row(s) will cascade, all allowlisted', v_tot;
END $$;

-- ── 6 · delete the org. Cascades ONLY what section 6a allowlisted (pipeline_stages, licenses, org_memberships, ─
--      platform_org_selections); everything else was moved/purged above and 6a proved nothing else references it.
DELETE FROM public.organizations WHERE id = 'ad6ec2e2-b470-4044-884e-6345e4fe66d4';

-- ── 7 · post-checks (AFTER the delete: cascaded rows are gone, so 6a is the loss check; this proves no dangling ──
--      org_id-like column survives and the user's ownership is intact) ─────────────────────────────────────────
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
  IF (SELECT count(*) FROM social_wiring.marcas WHERE org_id = v_nnl) <> 1
     OR (SELECT count(*) FROM social_wiring.marcas WHERE org_id = v_nnl AND is_primary) <> 1 THEN
    RAISE EXCEPTION 'post-check: Nós no Limiar must have exactly ONE marca, and it primary (one branding per org)';
  END IF;
  RAISE NOTICE 'post-checks OK: no references to the deleted org; fin_categories(NnL)=%', v_n;
END $$;

COMMIT;
