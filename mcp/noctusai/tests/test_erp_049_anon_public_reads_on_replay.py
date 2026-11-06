"""erp 049 (close_anon_and_public_reads), access-tier rows AT-af2a4272/5d90688d/a8c3505d/418d68d1/999c2102/d3d36c2c/b87d15b7.

The erp chain does not replay on PGlite (no migration-replay.json residue baseline; 001/003/016 depend on objects
the stubs lack), so the PRE-049 state of the seven tables is rebuilt from the exact grants/policies the chain left
(003 grants + default privileges, 004/001 anon policies, 016 PUBLIC `USING (true)`, 032 org policies) and the REAL 049
file is replayed on top, twice (idempotency). Per-table role matrix, asserted on rows and on writes:
anon / authenticated other org / authenticated owner org (+ service_role untouched).
Non-vacuous: with 049 replaced by a no-op the same matrix FAILS.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

MIG = Path(REPO_ROOT) / "products/erp-imobiliario/backend/migrations/049_close_anon_and_public_reads.sql"

ORG_A = "aaaaaaaa-0000-0000-0000-00000000000a"
ORG_B = "bbbbbbbb-0000-0000-0000-00000000000b"

# table -> (extra column DDL, extra insert cols/vals)
TABLES = {
    "portal_tokens": ("token text, is_active boolean default true, expires_at timestamptz default now() + interval '1 day'", "token", "'tok-A'"),
    "portal_acessos": ("token text, ativo boolean default true", "token", "'tok-A'"),
    "site_config": ("is_active boolean default true, telefone text", "telefone", "'+5511999999999'"),
    "meta_periodos": ("nome text", "nome", "'p'"),
    "metas_empresa": ("nome text", "nome", "'m'"),
    "metas_configuracao": ("nome text", "nome", "'c'"),
    "regras_pontuacao": ("nome text", "nome", "'r'"),
}
ANON_POLICY = {
    "portal_tokens": "portal_tokens_anon_read", "portal_acessos": "portal_acessos_anon_read",
    "site_config": "site_config_anon_read",
}
PUBLIC_POLICY = {t: f"corretor_select_{t}" for t in ("meta_periodos", "metas_empresa", "metas_configuracao", "regras_pontuacao")}


def _fixture_sql() -> str:
    out = ["""
CREATE SCHEMA erp;
GRANT USAGE ON SCHEMA erp TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT USAGE ON SEQUENCES TO anon, authenticated, service_role;
CREATE FUNCTION erp.current_org_id() RETURNS uuid LANGUAGE sql STABLE AS
  $f$ SELECT nullif(current_setting('request.jwt.claims', true)::jsonb ->> 'org_id', '')::uuid $f$;
GRANT EXECUTE ON FUNCTION erp.current_org_id() TO anon, authenticated;
"""]
    for t, (cols, _c, _v) in TABLES.items():
        pk = "org_id uuid PRIMARY KEY" if t == "metas_configuracao" else "id serial PRIMARY KEY, org_id uuid"
        out.append(f"CREATE TABLE erp.{t} ({pk}, {cols});")
        out.append(f"GRANT SELECT, INSERT, UPDATE, DELETE ON erp.{t} TO anon, authenticated;")
        out.append(f"ALTER TABLE erp.{t} ENABLE ROW LEVEL SECURITY;")
        out.append(f"GRANT ALL ON erp.{t} TO service_role;")
        for op in ("select", "insert", "update", "delete"):
            clause = {"select": "FOR SELECT USING", "insert": "FOR INSERT WITH CHECK",
                      "update": "FOR UPDATE USING", "delete": "FOR DELETE USING"}[op]
            out.append(f"CREATE POLICY {t}_{op}_policy ON erp.{t} {clause} (org_id = erp.current_org_id());".replace(
                f"ON erp.{t} FOR", f"ON erp.{t} AS PERMISSIVE FOR").replace("AS PERMISSIVE FOR", "FOR"))
    # make the org policies authenticated-only like 032
    out = [s.replace("FOR SELECT USING (org_id", "FOR SELECT TO authenticated USING (org_id")
           .replace("FOR INSERT WITH CHECK (org_id", "FOR INSERT TO authenticated WITH CHECK (org_id")
           .replace("FOR UPDATE USING (org_id", "FOR UPDATE TO authenticated USING (org_id")
           .replace("FOR DELETE USING (org_id", "FOR DELETE TO authenticated USING (org_id") for s in out]
    out.append("CREATE POLICY site_config_anon_read ON erp.site_config FOR SELECT TO anon USING (is_active = true);")
    out.append("CREATE POLICY portal_tokens_anon_read ON erp.portal_tokens FOR SELECT TO anon USING (is_active = true AND expires_at > now());")
    out.append("CREATE POLICY portal_acessos_anon_read ON erp.portal_acessos FOR SELECT TO anon USING (ativo = true);")
    for t, p in PUBLIC_POLICY.items():
        out.append(f"CREATE POLICY {p} ON erp.{t} FOR SELECT USING (true);")
    return "\n".join(out)


def _seed_sql() -> str:
    rows = []
    for t, (_cols, c, v) in TABLES.items():
        rows.append(f"INSERT INTO erp.{t} (org_id, {c}) VALUES ('{ORG_A}', {v});")
    rows.append(f"INSERT INTO erp.regras_pontuacao (org_id, nome) VALUES (NULL, 'plataforma');")
    return "\n".join(rows)


def _matrix_sql() -> str:
    """Raises 'ASSERT ...' on any deviation from the post-049 contract."""
    b = ["DO $t$ DECLARE n int; BEGIN"]
    for t, (_cols, c, v) in TABLES.items():
        # anon: no grant at all -> insufficient_privilege on read AND write
        b.append(f"""
  SET LOCAL ROLE anon;
  BEGIN PERFORM 1 FROM erp.{t}; RESET ROLE; RAISE EXCEPTION 'ASSERT anon read {t}';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  SET LOCAL ROLE anon;
  BEGIN INSERT INTO erp.{t} (org_id, {c}) VALUES ('{ORG_A}', {v}); RESET ROLE; RAISE EXCEPTION 'ASSERT anon write {t}';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  RESET ROLE;
  -- authenticated, OTHER org: sees nothing of org A, cannot write into org A
  PERFORM set_config('request.jwt.claims', '{{"org_id":"{ORG_B}"}}', true);
  SET LOCAL ROLE authenticated;
  SELECT count(*) INTO n FROM erp.{t} WHERE org_id = '{ORG_A}';
  IF n <> 0 THEN RESET ROLE; RAISE EXCEPTION 'ASSERT other org reads % rows of {t}', n; END IF;
  BEGIN INSERT INTO erp.{t} (org_id, {c}) VALUES ('{ORG_A}', {v}); RESET ROLE; RAISE EXCEPTION 'ASSERT other org writes {t}';
  EXCEPTION WHEN insufficient_privilege OR check_violation THEN NULL; END;
  RESET ROLE;
  -- authenticated, OWNER org: reads own row, can write own row
  PERFORM set_config('request.jwt.claims', '{{"org_id":"{ORG_A}"}}', true);
  SET LOCAL ROLE authenticated;
  SELECT count(*) INTO n FROM erp.{t} WHERE org_id = '{ORG_A}';
  IF n < 1 THEN RESET ROLE; RAISE EXCEPTION 'ASSERT owner cannot read {t}'; END IF;
  RESET ROLE;
""")
    # platform-default rules (org_id NULL) stay readable to members, never to anon / writes
    b.append(f"""
  PERFORM set_config('request.jwt.claims', '{{"org_id":"{ORG_B}"}}', true);
  SET LOCAL ROLE authenticated;
  SELECT count(*) INTO n FROM erp.regras_pontuacao WHERE org_id IS NULL;
  IF n <> 1 THEN RESET ROLE; RAISE EXCEPTION 'ASSERT platform default rules hidden'; END IF;
  RESET ROLE;
  -- owner writes (non-PUBLIC tables keep their org insert policy)
  PERFORM set_config('request.jwt.claims', '{{"org_id":"{ORG_A}"}}', true);
  SET LOCAL ROLE authenticated;
  INSERT INTO erp.portal_tokens (org_id, token) VALUES ('{ORG_A}', 'tok-2');
  RESET ROLE;
  -- no future erp table inherits anon DML
  CREATE TABLE erp.zz_future (id int);
  IF has_table_privilege('anon', 'erp.zz_future', 'SELECT') THEN RAISE EXCEPTION 'ASSERT anon default privileges'; END IF;
  -- policies: none left for anon/PUBLIC
  SELECT count(*) INTO n FROM pg_policies WHERE schemaname='erp' AND (policyname LIKE '%anon_read'
     OR (policyname LIKE 'corretor_select_%' AND roles = '{{public}}'));
  IF n <> 0 THEN RAISE EXCEPTION 'ASSERT % anon/PUBLIC policies remain', n; END IF;
END $t$;""")
    return "\n".join(b)


def _run(mig_sql: str):
    steps = [
        {"product": "erp-imobiliario", "file": "step:fixture", "sql": _fixture_sql(), "mode": "file", "twice": False},
        {"product": "erp-imobiliario", "file": "step:seed", "sql": _seed_sql(), "mode": "file", "twice": False},
        {"product": "erp-imobiliario", "file": MIG.name, "sql": mig_sql, "mode": "file", "twice": True},
        {"product": "erp-imobiliario", "file": "step:matrix", "sql": _matrix_sql(), "mode": "file", "twice": False},
    ]
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    return {s["file"]: s["failures"] for s in res["steps"]}


def test_matrix_holds_with_049_applied_twice(pglite):
    out = _run(MIG.read_text(encoding="utf-8"))
    assert out == {"step:fixture": [], "step:seed": [], MIG.name: [], "step:matrix": []}, out


def test_matrix_fails_without_049(pglite):
    out = _run("SELECT 1;\n")
    assert out["step:fixture"] == [] and out["step:seed"] == []
    assert out["step:matrix"], "matrix passed with no migration: the test is vacuous"
