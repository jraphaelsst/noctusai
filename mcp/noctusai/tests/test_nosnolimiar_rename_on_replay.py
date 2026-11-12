"""The monica -> nosnolimiar rename (2026-11): cutover scripts + the migrations that carry it, on a real Postgres.

* ``cutover-dry-run.sql`` is ``cutover.sql`` with ONLY the first line and the final COMMIT/ROLLBACK changed -- the
  dry-run is what the owner reads before the irreversible run, so it must never drift from it.
* The cutover's cascade inventory (section 6a) is catalog-derived: an org-referencing table that is not allowlisted
  aborts the script before the delete, whatever its ON DELETE action, and so does a row reached through
  ``org_memberships`` (one hop). Proven on the replayed core chain plus tiny fixtures.
* Core 120 renames the slug in every catalog-derived platform column (incl. ``agents.agent_product_grants``) and
  fails if a non-historical column still holds the old slug.
* Product 022 adopts a ``nosnolimiar`` schema holding only the ledger (the fresh-DB ``migrate_product`` bootstrap).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_ROOT = Path(REPO_ROOT)
_RENAME = _ROOT / "products/nosnolimiar/projects/rename-2026-11"
_M120 = "products/core/backend/migrations/120_rename_monica_to_nosnolimiar.sql"
_M022 = "products/nosnolimiar/backend/migrations/022_rename_schema.sql"

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
@pytest.mark.parametrize("name", ["cutover", "cleanup-old-org"])
def test_dry_run_body_is_byte_identical_to_the_real_script(name):
    real = (_RENAME / f"{name}.sql").read_text(encoding="utf-8").split("\n")
    dry = (_RENAME / f"{name}-dry-run.sql").read_text(encoding="utf-8").split("\n")
    assert len(real) == len(dry)
    assert real[1:-2] == dry[1:-2], f"{name}-dry-run.sql drifted from {name}.sql -- regenerate it"
    assert dry[0] == "-- *** DRY RUN (ends in ROLLBACK) *** " + real[0][3:]
    assert real[-2] == "COMMIT;" and dry[-2].startswith("ROLLBACK;")


def test_the_window_script_deletes_nothing_the_old_org_goes_in_the_deferred_cleanup():
    """Owner delegation 2026-11-12: the old org is deleted >= 7 days after the window, never inside it."""
    win = (_RENAME / "cutover.sql").read_text(encoding="utf-8")
    for forbidden in ("DELETE FROM", "DROP ", "TRUNCATE", "core.audit_log_purge"):
        assert forbidden not in win, f"cutover.sql (the window) must not contain {forbidden!r}: irreversible steps live in cleanup-old-org.sql"
    late = (_RENAME / "cleanup-old-org.sql").read_text(encoding="utf-8")
    assert "DELETE FROM public.organizations" in late and "still have MT as home org" in late


# ---------------------------------------------------------------- cutover section 3: one branding per org --------
# Owner 2026-11-05: MT's marca + its Studio chat are DELETED (never moved to NnL); NnL keeps exactly ONE marca.
_MK = "07798cf9-01aa-465e-aa11-49f3a0a18386"
_NNL_MK = "06c35543-1a90-44eb-ab6f-e111e879e3f4"
_SW_FIXTURE = f"""
CREATE SCHEMA IF NOT EXISTS social_wiring;
CREATE TABLE social_wiring.marcas (id uuid PRIMARY KEY, org_id uuid NOT NULL, name text, is_primary boolean NOT NULL DEFAULT false);
CREATE TABLE social_wiring.cs_chat_conversas (id serial PRIMARY KEY, org_id uuid NOT NULL,
    marca_id uuid NOT NULL REFERENCES social_wiring.marcas(id) ON DELETE CASCADE);
CREATE TABLE social_wiring.cs_chat_mensagens (id serial PRIMARY KEY, org_id uuid NOT NULL,
    conversa_id int NOT NULL REFERENCES social_wiring.cs_chat_conversas(id) ON DELETE CASCADE);
CREATE TABLE social_wiring.campanhas (id serial PRIMARY KEY, org_id uuid NOT NULL,
    marca_id uuid REFERENCES social_wiring.marcas(id) ON DELETE SET NULL);
INSERT INTO social_wiring.marcas VALUES ('{_MK}', '{_MT}', 'Mônica Tangerino', true), ('{_NNL_MK}', '{_NNL}', 'Nós no Limiar', true);
INSERT INTO social_wiring.cs_chat_conversas (org_id, marca_id) VALUES ('{_MT}', '{_MK}');
INSERT INTO social_wiring.cs_chat_mensagens (org_id, conversa_id) VALUES ('{_MT}', 1);
"""
_SW_AFTER = f"""
DO $$ BEGIN
  IF (SELECT count(*) FROM social_wiring.marcas WHERE org_id = '{_MT}') <> 0 THEN RAISE EXCEPTION 'MT marca left'; END IF;
  IF (SELECT count(*) FROM social_wiring.cs_chat_conversas) + (SELECT count(*) FROM social_wiring.cs_chat_mensagens) <> 0
    THEN RAISE EXCEPTION 'MT chat left'; END IF;
  IF (SELECT count(*) FROM social_wiring.marcas WHERE org_id = '{_NNL}') <> 1 THEN RAISE EXCEPTION 'NnL must keep exactly 1 marca'; END IF;
END $$;
"""


def test_section3_deletes_mt_brand_never_moves_it(pglite):
    sql = (_RENAME / "cleanup-old-org.sql").read_text(encoding="utf-8")
    sec3 = _section(sql, "-- ── 3 · social_wiring", "-- ── 4 ·")
    assert "SET org_id" not in sec3, "section 3 must never MOVE social_wiring rows to NnL (one branding per org)"
    steps = [
        _step("sw_fixture", _SW_FIXTURE),
        # a campanha pointing at MT's marca would be silently SET NULL -> abort (the DO is atomic: nothing deleted)
        _step("fx_ref", f"INSERT INTO social_wiring.campanhas (org_id, marca_id) VALUES ('{_NNL}', '{_MK}');"),
        _step("s3_ref", sec3),
        # over the max-count cap -> abort
        _step("fx_cap", "DELETE FROM social_wiring.campanhas;"
                        f"INSERT INTO social_wiring.cs_chat_mensagens (org_id, conversa_id) VALUES ('{_MT}', 1);"),
        _step("s3_cap", sec3),
        # an MT row in another org_id table (not the marca chain) -> abort
        _step("fx_stray", f"DELETE FROM social_wiring.cs_chat_mensagens WHERE id = 2;"
                          f"INSERT INTO social_wiring.campanhas (org_id) VALUES ('{_MT}');"),
        _step("s3_stray", sec3),
        _step("fx_clean", "DELETE FROM social_wiring.campanhas;"),
        _step("s3_ok", sec3),
        _step("after", _SW_AFTER),
    ]
    res = mr._run_harness(steps, 600, None)
    assert _failures(res, "sw_fixture") == ""
    assert "would cascade/null" in _failures(res, "s3_ref")
    assert "max 1" in _failures(res, "s3_cap")
    assert "campanhas" in _failures(res, "s3_stray") and "still holds" in _failures(res, "s3_stray")
    assert _failures(res, "s3_ok") == ""
    assert _failures(res, "after") == ""


# ---------------------------------------------------------------- cutover section 6a inventory --------------------
_INV_FIXTURE = f"""
CREATE SCHEMA IF NOT EXISTS erp;
CREATE TABLE IF NOT EXISTS erp.pipeline_stages (id serial PRIMARY KEY, org_id uuid NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE);
SET session_replication_role = replica;
INSERT INTO public.organizations (id, nome, slug) VALUES ('{_MT}', 'Mônica Tangerino', 'inv-mt'), ('{_NNL}', 'Nós no Limiar', 'inv-nnl');
INSERT INTO erp.pipeline_stages (org_id) SELECT '{_MT}' FROM generate_series(1, 13);
INSERT INTO erp.pipeline_stages (org_id) SELECT '{_NNL}' FROM generate_series(1, 13);
INSERT INTO auth.users (id, email) VALUES ('11111111-1111-1111-1111-111111111111', 'inv@test');
INSERT INTO public.org_memberships (id, user_id, org_id, org_role, status)
VALUES ('22222222-2222-2222-2222-222222222222', '11111111-1111-1111-1111-111111111111', '{_MT}', 'owner', 'active');
SET session_replication_role = origin;
"""


def test_inventory_allows_the_allowlist_and_blocks_everything_else(pglite):
    sql = (_RENAME / "cleanup-old-org.sql").read_text(encoding="utf-8")
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
                             f"INSERT INTO erp.pipeline_stages (org_id) VALUES ('{_MT}');"),
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


# ---------------------------------------------------------------- core 120: derived slug columns -------------------
def test_120_renames_every_derived_column_and_guards_the_rest(pglite):
    sql = (_ROOT / _M120).read_text(encoding="utf-8")
    steps = mr._steps_for(_ROOT, "core", set(), "worktree", {})
    steps += [
        _step("fixture", "CREATE SCHEMA IF NOT EXISTS agents;"
                         "CREATE TABLE agents.agent_product_grants (product text);"
                         "INSERT INTO agents.agent_product_grants VALUES ('monica'), ('social-wiring');"
                         "UPDATE public.audit_logs SET product_slug = product_slug WHERE false;"),
        _step("run_120", sql),
        _step("assert", "DO $$ BEGIN IF (SELECT count(*) FROM agents.agent_product_grants WHERE product = 'nosnolimiar') <> 1"
                        " OR EXISTS (SELECT 1 FROM agents.agent_product_grants WHERE product = 'monica') THEN"
                        " RAISE EXCEPTION 'agent_product_grants not renamed'; END IF; END $$;"),
        # a column the rename cannot fix (a trigger puts the old slug back) must fail the migration, not pass silently
        _step("fixture_sticky", "CREATE TABLE agents.zz_sticky (product text);"
                                "CREATE FUNCTION agents.zz_stick() RETURNS trigger LANGUAGE plpgsql AS $f$ BEGIN NEW.product := 'monica'; RETURN NEW; END $f$;"
                                "CREATE TRIGGER zz BEFORE INSERT OR UPDATE ON agents.zz_sticky FOR EACH ROW EXECUTE FUNCTION agents.zz_stick();"
                                "INSERT INTO agents.zz_sticky VALUES ('x');"),
        _step("run_120_sticky", sql),
    ]
    res = mr._run_harness(steps, 900, None)
    assert _failures(res, "fixture") == ""
    assert _failures(res, "run_120") == ""
    assert _failures(res, "assert") == ""
    assert "agents.zz_sticky.product" in _failures(res, "run_120_sticky")


# ---------------------------------------------------------------- product 022: fresh-DB bootstrap ------------------
_LEDGER_FIRST = """
CREATE SCHEMA nosnolimiar;
CREATE TABLE nosnolimiar.schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now(), checksum TEXT);
INSERT INTO nosnolimiar.schema_migrations (filename, checksum) VALUES ('boot.sql', 'x');
"""


def test_022_adopts_a_ledger_only_nosnolimiar_schema(pglite):
    """`migrate_product` without schema=monica creates `nosnolimiar` + ledger BEFORE 001 creates `monica`."""
    steps = mr._steps_for(_ROOT, "nosnolimiar", {_M022}, "worktree", {})
    first = next(i for i, s in enumerate(steps) if s["product"] == "nosnolimiar")
    steps.insert(first, _step("ledger_first", _LEDGER_FIRST, product="nosnolimiar"))
    steps.append(_step(
        "assert", "DO $$ BEGIN IF to_regnamespace('monica') IS NOT NULL OR to_regnamespace('nosnolimiar') IS NULL THEN"
                  " RAISE EXCEPTION 'schema not renamed'; END IF;"
                  " IF NOT EXISTS (SELECT 1 FROM nosnolimiar.schema_migrations WHERE filename = 'boot.sql') THEN"
                  " RAISE EXCEPTION 'bootstrap ledger row lost'; END IF; END $$;", product="nosnolimiar"))
    res = mr._run_harness(steps, 900, None)
    assert _failures(res, "ledger_first") == ""
    assert _failures(res, "022_rename_schema.sql") == "", "022 must apply whole AND re-apply (twice) on the bootstrap shape"
    assert _failures(res, "assert") == ""


def test_022_still_refuses_two_real_schemas(pglite):
    steps = mr._steps_for(_ROOT, "nosnolimiar", {_M022}, "worktree", {})
    first = next(i for i, s in enumerate(steps) if s["product"] == "nosnolimiar")
    steps.insert(first, _step("second_schema", "CREATE SCHEMA nosnolimiar; CREATE TABLE nosnolimiar.real_data (id int);",
                              product="nosnolimiar"))
    res = mr._run_harness(steps, 900, None)
    assert "BOTH schemas" in _failures(res, "022_rename_schema.sql")
