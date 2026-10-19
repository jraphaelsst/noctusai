"""Migration 287 (Lais -> Julia rename) on the REAL social-wiring chain on PGlite: after the whole chain every
`lais_*` base table is a `julia_*` table, the pre-rename name survives ONLY as a security_invoker compat view that the
previous image can still read AND write, nothing is left named `lais` but those views, and the trigger-function
bodies were re-created against the new names (a body is text: a table rename does not rewrite it).
NOC-REMEDIATE[drop-lais-compat-views]: when the views are dropped, delete the view assertions below."""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_CHECK = r"""
DO $t$
DECLARE n int; v text;
BEGIN
  -- 1. no lais BASE table / index / constraint / trigger / policy / function is left
  SELECT count(*) INTO n FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace
   WHERE s.nspname = 'social_wiring' AND c.relname ILIKE '%lais%' AND c.relkind <> 'v';
  IF n <> 0 THEN RAISE EXCEPTION 'a lais relation survived the rename: %', n; END IF;
  SELECT count(*) INTO n FROM pg_constraint k JOIN pg_namespace s ON s.oid = k.connamespace
   WHERE s.nspname = 'social_wiring' AND k.conname ILIKE '%lais%';
  IF n <> 0 THEN RAISE EXCEPTION 'a lais constraint survived the rename: %', n; END IF;
  SELECT count(*) INTO n FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid JOIN pg_namespace s ON s.oid = c.relnamespace
   WHERE s.nspname = 'social_wiring' AND NOT t.tgisinternal AND t.tgname ILIKE '%lais%';
  IF n <> 0 THEN RAISE EXCEPTION 'a lais trigger survived the rename: %', n; END IF;
  SELECT count(*) INTO n FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid JOIN pg_namespace s ON s.oid = c.relnamespace
   WHERE s.nspname = 'social_wiring' AND p.polname ILIKE '%lais%';
  IF n <> 0 THEN RAISE EXCEPTION 'a lais policy survived the rename: %', n; END IF;
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace s ON s.oid = p.pronamespace
   WHERE s.nspname = 'social_wiring' AND (p.proname ILIKE '%lais%' OR p.prosrc ILIKE '%lais%');
  IF n <> 0 THEN RAISE EXCEPTION 'a lais function (name or body) survived the rename: %', n; END IF;

  -- 2. every renamed table keeps a compat view under the old name, security_invoker
  SELECT count(*) INTO n FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace
   WHERE s.nspname = 'social_wiring' AND c.relkind = 'v' AND c.relname LIKE 'lais\_%'
     AND 'security_invoker=true' = ANY (c.reloptions)
     AND to_regclass('social_wiring.julia_' || substr(c.relname, 6)) IS NOT NULL;
  IF n < 38 THEN RAISE EXCEPTION 'expected 38 compat views, found %', n; END IF;

  -- 3. the previous image writes THROUGH the old name and the new name sees the row (defaults, CHECKs, triggers hold)
  INSERT INTO social_wiring.lais_etiquetas (org_id, nome, cor)
       VALUES ('00000000-0000-4000-8000-000000000287', 'noc-compat', '#112233');
  SELECT count(*) INTO n FROM social_wiring.julia_etiquetas WHERE nome = 'noc-compat';
  IF n <> 1 THEN RAISE EXCEPTION 'a write through the compat view did not reach julia_etiquetas'; END IF;
  UPDATE social_wiring.lais_etiquetas SET cor = '#445566' WHERE nome = 'noc-compat';
  SELECT cor INTO v FROM social_wiring.julia_etiquetas WHERE nome = 'noc-compat';
  IF v <> '#445566' THEN RAISE EXCEPTION 'an update through the compat view did not reach julia_etiquetas'; END IF;
  DELETE FROM social_wiring.lais_etiquetas WHERE nome = 'noc-compat';
  SELECT count(*) INTO n FROM social_wiring.julia_etiquetas WHERE nome = 'noc-compat';
  IF n <> 0 THEN RAISE EXCEPTION 'a delete through the compat view did not reach julia_etiquetas'; END IF;

  -- 4. the base table's CHECK still refuses through the view (the guard moved with the table)
  BEGIN
    INSERT INTO social_wiring.lais_etiquetas (org_id, nome, cor)
         VALUES ('00000000-0000-4000-8000-000000000287', 'noc-compat', 'not-a-colour');
    RAISE EXCEPTION 'the colour CHECK did not refuse a write through the compat view';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
END
$t$;
"""


def test_the_rename_leaves_only_compat_views_and_the_old_name_still_reads_and_writes(pglite):
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "social-wiring", set(), "worktree", {})
    steps.append({"product": "social-wiring", "file": "287_compat_check", "sql": _CHECK, "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    mine = [s for s in res["steps"] if s["file"] == "287_compat_check"]
    assert len(mine) == 1 and not mine[0]["failures"], mine
