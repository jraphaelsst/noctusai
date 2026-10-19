-- ============================================================================
-- Migration 287 -- social_wiring: rename the Lais module to Julia (owner order 2026-10-19)
-- ============================================================================
-- WHY
-- ---
-- "Lais" is Lastro's product (the reverse-engineered casa.lais.ai); Julia is the agent we actually build (Noc's One
-- Consultoria SDR, hosted in `agents`). Everything built here under the Lais name becomes Julia so the code matches
-- the agent. This file is the DATABASE half; the code half ships in the same change.
--
-- WHAT (one transaction -- the whole file is one multi-statement request, atomic by construction)
--   1. every `social_wiring.lais_*` table is RENAMED to `julia_*` (same OID: data, RLS, grants, FKs, defaults follow);
--   2. every constraint / index / sequence / trigger / policy / function whose NAME carries `lais` is renamed, and
--      the plpgsql / sql function BODIES that reference a renamed table are re-created with the new names (a body is
--      stored as text, so a rename does not rewrite it);
--   3. a COMPATIBILITY VIEW `social_wiring.lais_<x>` = `select * from social_wiring.julia_<x>` (security_invoker, the
--      table's privileges copied) is left behind for every renamed table, so the previous image -- still running while
--      the new one rolls out -- keeps reading AND writing (a simple view is auto-updatable; defaults, CHECKs, triggers
--      and RLS of the base table all still apply);
--   4. data that spelled the old name is rewritten: status_pagina keys, the studio agent key `lead-imob` -> `julia`
--      (whatsapp_connections + the atendimento-blocks tables), queued job types / dedupe keys, in-app notification
--      kinds (metadata.tipo), and the `{{nome_lais}}` template placeholder.
--
-- NOC-REMEDIATE[drop-lais-compat-views]: a later release (once no `lais_*` reader/writer is left -- the previous image is
-- gone) drops the compat views with `DROP VIEW social_wiring.lais_<x>`; nothing else in this file has to be undone.
--
-- DELIBERATELY UNCHANGED
--   * event-type strings stored in julia_eventos ('novo_lead', 'handoff', 'envio_bloqueado', 'relatorio', ...) and
--     payload.origem: none of them contains "lais";
--   * migrations 252-286 and their ledger rows: applied history, never edited (they keep creating `lais_*` on a fresh
--     chain; this migration then renames them, so a fresh database and the live one converge).
-- FORWARD-ONLY, IDEMPOTENT: a second run finds no `lais_*` base table and does nothing. NO SECURITY DEFINER function.
-- ============================================================================

SET search_path = social_wiring, public;

DO $rename$
DECLARE
  r      record;
  v_new  text;
  v_cols text;
  v_ident text;
  v_def  text;
  v_n    int;
BEGIN
  -- 0. Fail loud on a column we would leave behind: the compat views expose the OLD column names only if no column
  --    carries `lais` (none does today). A future one must be handled here, not silently skipped.
  SELECT count(*) INTO v_n
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'social_wiring' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped
     AND a.attname ILIKE '%lais%';
  IF v_n > 0 THEN
    RAISE EXCEPTION 'migration 287: % column(s) in social_wiring carry "lais" in their name -- rename them explicitly first', v_n;
  END IF;

  -- 1. tables -> julia_*, remembering which ones we renamed (for the compat views below)
  CREATE TEMP TABLE _lais_renamed (old_name text PRIMARY KEY, new_name text NOT NULL) ON COMMIT DROP;
  FOR r IN
    SELECT c.relname
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'social_wiring' AND c.relkind IN ('r', 'p') AND c.relname LIKE 'lais\_%'
     ORDER BY c.relname
  LOOP
    v_new := 'julia_' || substr(r.relname, 6);
    IF to_regclass(format('social_wiring.%I', v_new)) IS NOT NULL THEN
      RAISE EXCEPTION 'migration 287: social_wiring.% already exists -- cannot rename social_wiring.%', v_new, r.relname;
    END IF;
    EXECUTE format('ALTER TABLE social_wiring.%I RENAME TO %I', r.relname, v_new);
    INSERT INTO _lais_renamed VALUES (r.relname, v_new);
  END LOOP;

  -- 2a. constraints (PK / UNIQUE / CHECK / FK; renaming a PK or UNIQUE renames its backing index too)
  FOR r IN
    SELECT con.conname, cl.relname AS tbl
      FROM pg_constraint con
      JOIN pg_class cl ON cl.oid = con.conrelid
      JOIN pg_namespace n ON n.oid = cl.relnamespace
     WHERE n.nspname = 'social_wiring' AND con.conname ILIKE '%lais%' AND con.contype <> 't'
     ORDER BY cl.relname, con.conname
  LOOP
    EXECUTE format('ALTER TABLE social_wiring.%I RENAME CONSTRAINT %I TO %I',
                   r.tbl, r.conname, replace(r.conname, 'lais', 'julia'));
  END LOOP;

  -- 2b. the remaining indexes (the standalone idx_lais_* ones)
  FOR r IN
    SELECT c.relname
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'social_wiring' AND c.relkind IN ('i', 'I') AND c.relname ILIKE '%lais%'
     ORDER BY c.relname
  LOOP
    EXECUTE format('ALTER INDEX social_wiring.%I RENAME TO %I', r.relname, replace(r.relname, 'lais', 'julia'));
  END LOOP;

  -- 2c. sequences (identity/serial sequences of the renamed tables)
  FOR r IN
    SELECT c.relname
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'social_wiring' AND c.relkind = 'S' AND c.relname ILIKE '%lais%'
     ORDER BY c.relname
  LOOP
    EXECUTE format('ALTER SEQUENCE social_wiring.%I RENAME TO %I', r.relname, replace(r.relname, 'lais', 'julia'));
  END LOOP;

  -- 2d. triggers
  FOR r IN
    SELECT t.tgname, cl.relname AS tbl
      FROM pg_trigger t
      JOIN pg_class cl ON cl.oid = t.tgrelid
      JOIN pg_namespace n ON n.oid = cl.relnamespace
     WHERE n.nspname = 'social_wiring' AND NOT t.tgisinternal AND t.tgname ILIKE '%lais%'
     ORDER BY cl.relname, t.tgname
  LOOP
    EXECUTE format('ALTER TRIGGER %I ON social_wiring.%I RENAME TO %I', r.tgname, r.tbl, replace(r.tgname, 'lais', 'julia'));
  END LOOP;

  -- 2e. RLS policies
  FOR r IN
    SELECT p.polname, cl.relname AS tbl
      FROM pg_policy p
      JOIN pg_class cl ON cl.oid = p.polrelid
      JOIN pg_namespace n ON n.oid = cl.relnamespace
     WHERE n.nspname = 'social_wiring' AND p.polname ILIKE '%lais%'
     ORDER BY cl.relname, p.polname
  LOOP
    EXECUTE format('ALTER POLICY %I ON social_wiring.%I RENAME TO %I', r.polname, r.tbl, replace(r.polname, 'lais', 'julia'));
  END LOOP;

  -- 2f. functions: rename by name, then re-create every function whose body still names a lais object
  FOR r IN
    SELECT p.oid, p.proname
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'social_wiring' AND p.proname ILIKE '%lais%' AND p.prokind = 'f'
     ORDER BY p.proname
  LOOP
    EXECUTE format('ALTER FUNCTION social_wiring.%I(%s) RENAME TO %I',
                   r.proname, pg_get_function_identity_arguments(r.oid), replace(r.proname, 'lais', 'julia'));
  END LOOP;
  FOR r IN
    SELECT p.oid
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'social_wiring' AND p.prokind = 'f' AND p.prosrc ILIKE '%lais%'
     ORDER BY p.proname
  LOOP
    v_def := replace(replace(pg_get_functiondef(r.oid), 'lais', 'julia'), 'Lais', 'Julia');
    EXECUTE v_def;
  END LOOP;

  -- 3. compat views `lais_<x>` over `julia_<x>` + privileges copied from the table
  FOR r IN SELECT old_name, new_name FROM _lais_renamed ORDER BY old_name LOOP
    EXECUTE format('CREATE VIEW social_wiring.%I WITH (security_invoker = true) AS SELECT * FROM social_wiring.%I',
                   r.old_name, r.new_name);
    EXECUTE format($c$COMMENT ON VIEW social_wiring.%I IS %L$c$, r.old_name,
                   'NOC-REMEDIATE[drop-lais-compat-views] compatibility alias of ' || r.new_name
                   || ' for the pre-rename image (migration 287); drop it once that image is gone.');
    FOR v_ident IN
      SELECT format('GRANT %s ON social_wiring.%I TO %s',
                    string_agg(a.privilege_type, ', ' ORDER BY a.privilege_type), r.old_name,
                    CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(a.grantee)) END)
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN LATERAL aclexplode(c.relacl) a
       WHERE n.nspname = 'social_wiring' AND c.relname = r.new_name
         AND a.privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')
         AND a.grantee <> c.relowner
       GROUP BY a.grantee
    LOOP
      EXECUTE v_ident;
    END LOOP;
  END LOOP;
END
$rename$;

-- ── 4. data that spelled the old name ───────────────────────────────────────────────────────────────────────────────

-- 4a. nav visibility rows (status_pagina.nome_pagina = the route key the layout derives from the path); the previous
-- image looks the OLD keys up, so its Lais nav items stay hidden for the short rollout window -- by design, no orphan rows.
UPDATE social_wiring.status_pagina
   SET nome_pagina = 'julia_' || substr(nome_pagina, 6),
       descricao   = replace(replace(descricao, 'Lais', 'Julia'), 'lais', 'julia')
 WHERE nome_pagina LIKE 'lais\_%'
   AND NOT EXISTS (SELECT 1 FROM social_wiring.status_pagina o WHERE o.nome_pagina = 'julia_' || substr(status_pagina.nome_pagina, 6));
DELETE FROM social_wiring.status_pagina
 WHERE nome_pagina LIKE 'lais\_%'
   AND EXISTS (SELECT 1 FROM social_wiring.status_pagina o WHERE o.nome_pagina = 'julia_' || substr(status_pagina.nome_pagina, 6));

-- 4b. the studio agent key: `lead-imob` becomes `julia` (agents accepts both for one release)
UPDATE social_wiring.whatsapp_connections SET agente_leads_key = 'julia' WHERE agente_leads_key = 'lead-imob';
UPDATE social_wiring.atendimento_blocos    SET agent_key = 'julia'      WHERE agent_key = 'lead-imob';
UPDATE social_wiring.atendimento_handoffs  SET de_agent_key = 'julia'   WHERE de_agent_key = 'lead-imob';
UPDATE social_wiring.atendimento_handoffs  SET para_agent_key = 'julia' WHERE para_agent_key = 'lead-imob';
UPDATE social_wiring.agente_scorecards     SET agent_key = 'julia'      WHERE agent_key = 'lead-imob';

-- 4c. queued background jobs: the job TYPE is the handler registry key and the dedupe key carries the module prefix
UPDATE social_wiring.jobs SET type = 'julia_' || substr(type, 6) WHERE type LIKE 'lais\_%';
UPDATE social_wiring.jobs SET dedupe_key = 'julia:' || substr(dedupe_key, 6) WHERE dedupe_key LIKE 'lais:%';

-- 4d. the message-template placeholder `{{nome_lais}}` -> `{{nome_julia}}` (stored bodies + their parameter list);
-- the renderer still accepts the old spelling for one release (NOC-REMEDIATE[drop-nome-lais-alias]).
UPDATE social_wiring.julia_modelos
   SET corpo = regexp_replace(corpo, '\{\{\s*nome_lais\s*\}\}', '{{nome_julia}}', 'g'),
       parametros = replace(parametros::text, '"nome_lais"', '"nome_julia"')::jsonb
 WHERE corpo ~ 'nome_lais' OR parametros::text LIKE '%nome_lais%';

-- 4e. the lead source Julia creates per org on its first send: label (and the raw origin stamped on its leads) was
-- 'Lais (Julia)'; the slug was already 'julia'.
UPDATE social_wiring.lead_sources SET label = 'Julia' WHERE slug = 'julia' AND label = 'Lais (Julia)';
UPDATE social_wiring.leads        SET origem_raw = 'Julia' WHERE origem_raw = 'Lais (Julia)';

-- 4f. in-app notifications live in core's public.notifications: `type` is always 'system', the product kind rides in
-- metadata.tipo as 'lais_<tipo>' (noctusai_lib.domain.notifications).
DO $notif$
BEGIN
  IF to_regclass('public.notifications') IS NOT NULL
     AND EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_schema = 'public' AND table_name = 'notifications'
                    AND column_name = 'metadata' AND data_type = 'jsonb') THEN
    UPDATE public.notifications
       SET metadata = jsonb_set(metadata, '{tipo}', to_jsonb('julia_' || substr(metadata->>'tipo', 6)))
     WHERE metadata ? 'tipo' AND (metadata->>'tipo') LIKE 'lais\_%';
  END IF;
END
$notif$;

-- PostgREST must re-read the schema: the table names it exposes just changed.
NOTIFY pgrst, 'reload schema';
