"""The monica -> nosnolimiar rename (2026-11): cutover scripts + the migrations that carry it, on a real Postgres.

* ``cutover-dry-run.sql`` is ``cutover.sql`` with ONLY the first line and the final COMMIT/ROLLBACK changed -- the
  dry-run is what the owner reads before the irreversible run, so it must never drift from it.
* The cutover's cascade inventory (section 6a) is catalog-derived: an org-referencing table that is not allowlisted
  aborts the script before the delete, whatever its ON DELETE action, and so does a row reached through
  ``org_memberships`` (one hop). Proven on the replayed core chain plus tiny fixtures.
* Core 098 renames the slug in every catalog-derived platform column (incl. ``agents.agent_product_grants``) and
  fails if a non-historical column still holds the old slug.
* Product 020 adopts a ``nosnolimiar`` schema holding only the ledger (the fresh-DB ``migrate_product`` bootstrap).
"""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_ROOT = Path(REPO_ROOT)
_RENAME = _ROOT / "products/nosnolimiar/projects/rename-2026-11"
_M098 = "products/core/backend/migrations/098_rename_monica_to_nosnolimiar.sql"
_M020 = "products/nosnolimiar/backend/migrations/020_rename_schema.sql"

_MT = "ad6ec2e2-b470-4044-884e-6345e4fe66d4"
_NNL = "fa80a1e0-1bcd-4c65-8a37-2162e8ffa688"


def _step(file: str, sql: str, product: str = "core") -> dict:
    return {"product": product, "file": file, "sql": sql, "mode": "file", "twice": False}


def _failures(res: dict, file: str) -> str:
    assert res.get("ok"), res
    for st in res["steps"]:
        if st["file"] == file:
            return " | ".join(f["error"] for f in st["failures"])
    raise AssertionError(f"step {file} not in result")


def _section(sql: str, start: str, end: str) -> str:
    a = sql.index(start)
    b = sql.index(end, a)
    return sql[a:b].strip()


# ---------------------------------------------------------------- dry-run == real (pure text) ---------------------
def test_dry_run_body_is_byte_identical_to_cutover():
    real = (_RENAME / "cutover.sql").read_text(encoding="utf-8").split("\n")
    dry = (_RENAME / "cutover-dry-run.sql").read_text(encoding="utf-8").split("\n")
    assert len(real) == len(dry)
    assert real[1:-2] == dry[1:-2], "cutover-dry-run.sql drifted from cutover.sql -- regenerate it"
    assert dry[0] == "-- *** DRY RUN (ends in ROLLBACK) *** " + real[0][3:]
    assert real[-2] == "COMMIT;" and dry[-2].startswith("ROLLBACK;")


# ---------------------------------------------------------------- cutover section 6a inventory --------------------
_INV_FIXTURE = f"""
CREATE TABLE IF NOT EXISTS public.pipeline_stages (id serial PRIMARY KEY, org_id uuid NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE);
SET session_replication_role = replica;
INSERT INTO public.organizations (id, nome, slug) VALUES ('{_MT}', 'Mônica Tangerino', 'inv-mt'), ('{_NNL}', 'Nós no Limiar', 'inv-nnl');
INSERT INTO public.pipeline_stages (org_id) SELECT '{_MT}' FROM generate_series(1, 13);
INSERT INTO public.pipeline_stages (org_id) SELECT '{_NNL}' FROM generate_series(1, 13);
INSERT INTO auth.users (id, email) VALUES ('11111111-1111-1111-1111-111111111111', 'inv@test');
INSERT INTO public.org_memberships (id, user_id, org_id, org_role, status)
VALUES ('22222222-2222-2222-2222-222222222222', '11111111-1111-1111-1111-111111111111', '{_MT}', 'owner', 'active');
SET session_replication_role = origin;
"""


def test_inventory_allows_the_allowlist_and_blocks_everything_else(pglite):
    sql = (_RENAME / "cutover.sql").read_text(encoding="utf-8")
    inv = _section(sql, "-- ── 6a", "-- ── 6 ·")
    steps = mr._steps_for(_ROOT, "core", set(), "worktree", {})
    steps += [
        _step("fixture", _INV_FIXTURE),
        _step("inv_ok", inv),
        # one hop through org_memberships: a row hanging off MT's membership, ON DELETE CASCADE
        _step("fixture_hop", "CREATE TABLE public.zz_hop (membership_id uuid REFERENCES public.org_memberships(id) ON DELETE CASCADE);"
                             "INSERT INTO public.zz_hop VALUES ('22222222-2222-2222-2222-222222222222');"),
        _step("inv_hop", inv),
        # SET NULL is a silent loss too
        _step("fixture_nullify", "DROP TABLE public.zz_hop;"
                                 "CREATE TABLE public.zz_nullify (org_id uuid REFERENCES public.organizations(id) ON DELETE SET NULL);"
                                 f"INSERT INTO public.zz_nullify VALUES ('{_MT}');"),
        _step("inv_nullify", inv),
        # composite key onto organizations(id, slug) is caught too
        _step("fixture_multi", "DROP TABLE public.zz_nullify;"
                               "ALTER TABLE public.organizations ADD CONSTRAINT zz_org_id_slug UNIQUE (id, slug);"
                               "CREATE TABLE public.zz_multi (o uuid, s text, FOREIGN KEY (o, s) REFERENCES public.organizations(id, slug));"
                               f"INSERT INTO public.zz_multi VALUES ('{_MT}', 'inv-mt');"),
        _step("inv_multi", inv),
        # an allowlisted table over its cap is blocked as well
        _step("fixture_cap", "DROP TABLE public.zz_multi;"
                             f"INSERT INTO public.pipeline_stages (org_id) VALUES ('{_MT}');"),
        _step("inv_cap", inv),
    ]
    res = mr._run_harness(steps, 900, None)
    assert _failures(res, "fixture") == ""
    assert _failures(res, "inv_ok") == "", "allowlisted cascades (13 pipeline_stages, 1 membership) must pass"
    hop = _failures(res, "inv_hop")
    assert "zz_hop" in hop and "via org_memberships" in hop, hop
    nul = _failures(res, "inv_nullify")
    assert "zz_nullify" in nul and "ON DELETE n" in nul, nul
    assert "zz_multi" in _failures(res, "inv_multi")
    assert "pipeline_stages" in _failures(res, "inv_cap")


# ---------------------------------------------------------------- core 098: derived slug columns -------------------
def test_098_renames_every_derived_column_and_guards_the_rest(pglite):
    sql = (_ROOT / _M098).read_text(encoding="utf-8")
    steps = mr._steps_for(_ROOT, "core", set(), "worktree", {})
    steps += [
        _step("fixture", "CREATE SCHEMA IF NOT EXISTS agents;"
                         "CREATE TABLE agents.agent_product_grants (product text);"
                         "INSERT INTO agents.agent_product_grants VALUES ('monica'), ('social-wiring');"
                         "UPDATE public.audit_logs SET product_slug = product_slug WHERE false;"),
        _step("run_098", sql),
        _step("assert", "DO $$ BEGIN IF (SELECT count(*) FROM agents.agent_product_grants WHERE product = 'nosnolimiar') <> 1"
                        " OR EXISTS (SELECT 1 FROM agents.agent_product_grants WHERE product = 'monica') THEN"
                        " RAISE EXCEPTION 'agent_product_grants not renamed'; END IF; END $$;"),
        # a column the rename cannot fix (a trigger puts the old slug back) must fail the migration, not pass silently
        _step("fixture_sticky", "CREATE TABLE agents.zz_sticky (product text);"
                                "CREATE FUNCTION agents.zz_stick() RETURNS trigger LANGUAGE plpgsql AS $f$ BEGIN NEW.product := 'monica'; RETURN NEW; END $f$;"
                                "CREATE TRIGGER zz BEFORE INSERT OR UPDATE ON agents.zz_sticky FOR EACH ROW EXECUTE FUNCTION agents.zz_stick();"
                                "INSERT INTO agents.zz_sticky VALUES ('x');"),
        _step("run_098_sticky", sql),
    ]
    res = mr._run_harness(steps, 900, None)
    assert _failures(res, "fixture") == ""
    assert _failures(res, "run_098") == ""
    assert _failures(res, "assert") == ""
    assert "agents.zz_sticky.product" in _failures(res, "run_098_sticky")


# ---------------------------------------------------------------- product 020: fresh-DB bootstrap ------------------
_LEDGER_FIRST = """
CREATE SCHEMA nosnolimiar;
CREATE TABLE nosnolimiar.schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now(), checksum TEXT);
INSERT INTO nosnolimiar.schema_migrations (filename, checksum) VALUES ('boot.sql', 'x');
"""


def test_020_adopts_a_ledger_only_nosnolimiar_schema(pglite):
    """`migrate_product` without schema=monica creates `nosnolimiar` + ledger BEFORE 001 creates `monica`."""
    steps = mr._steps_for(_ROOT, "nosnolimiar", {_M020}, "worktree", {})
    first = next(i for i, s in enumerate(steps) if s["product"] == "nosnolimiar")
    steps.insert(first, _step("ledger_first", _LEDGER_FIRST, product="nosnolimiar"))
    steps.append(_step(
        "assert", "DO $$ BEGIN IF to_regnamespace('monica') IS NOT NULL OR to_regnamespace('nosnolimiar') IS NULL THEN"
                  " RAISE EXCEPTION 'schema not renamed'; END IF;"
                  " IF NOT EXISTS (SELECT 1 FROM nosnolimiar.schema_migrations WHERE filename = 'boot.sql') THEN"
                  " RAISE EXCEPTION 'bootstrap ledger row lost'; END IF; END $$;", product="nosnolimiar"))
    res = mr._run_harness(steps, 900, None)
    assert _failures(res, "ledger_first") == ""
    assert _failures(res, "020_rename_schema.sql") == "", "020 must apply whole AND re-apply (twice) on the bootstrap shape"
    assert _failures(res, "assert") == ""


def test_020_still_refuses_two_real_schemas(pglite):
    steps = mr._steps_for(_ROOT, "nosnolimiar", {_M020}, "worktree", {})
    first = next(i for i, s in enumerate(steps) if s["product"] == "nosnolimiar")
    steps.insert(first, _step("second_schema", "CREATE SCHEMA nosnolimiar; CREATE TABLE nosnolimiar.real_data (id int);",
                              product="nosnolimiar"))
    res = mr._run_harness(steps, 900, None)
    assert "BOTH schemas" in _failures(res, "020_rename_schema.sql")
