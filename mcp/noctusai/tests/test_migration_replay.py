"""noctus.dev.migration_replay — PGlite chain replay (KB § PATTERNS/backend/migration-chain-replay.md).

The harness tests need `node` + the toolkit's pinned PGlite (`npm ci` in
mcp/noctusai/node). Locally they skip with the reason; in CI (where the mcp job
runs that `npm ci`) a missing PGlite FAILS — a self-skipping gate test is zero
coverage that reads as green.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_NODE_DIR = Path(REPO_ROOT) / mr.NODE_DIR
_FIXTURES = Path(__file__).parent / "fixtures" / "migration_replay"
_SW_231 = "products/social-wiring/backend/migrations/231_intermediario_documento_canonico.sql"


def _pglite_ready() -> bool:
    return shutil.which("node") is not None and (_NODE_DIR / "node_modules" / "@electric-sql" / "pglite").is_dir()


@pytest.fixture
def pglite():
    if not _pglite_ready():
        if os.environ.get("CI"):
            pytest.fail("PGlite not installed in CI — the mcp job's `npm ci` in mcp/noctusai/node must provide it")
        pytest.skip("node + PGlite not installed (run `npm ci` in mcp/noctusai/node)")


def _node_eval(js: str) -> str:
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", js], cwd=_NODE_DIR / "migration_replay",
        capture_output=True, text=True, check=True,
    )
    return proc.stdout


# ── splitter / transaction-control detection (node only, no PGlite) ──────────

def test_comment_before_begin_is_still_transaction_control():
    """The 2026-10-10 trap: "-- note\\nBEGIN" slipped past ^BEGIN, opened a
    transaction, and the next error's ROLLBACK wiped 2749 statements' objects."""
    out = _node_eval(
        "import {isTransactionControl as t} from './split_sql.mjs';"
        "console.log(JSON.stringify(["
        "t('-- note\\nBEGIN'), t('/* x */ COMMIT'), t('begin transaction'), t('BEGIN ISOLATION LEVEL SERIALIZABLE'),"
        "t('ROLLBACK'), t('CREATE TABLE begin_log (id int)'), t('-- BEGIN\\nSELECT 1')]))"
    )
    assert json.loads(out) == [True, True, True, True, True, False, False]


def test_split_respects_dollar_quotes_strings_and_comments():
    out = _node_eval(
        "import {splitSql} from './split_sql.mjs';"
        "const sql = `CREATE FUNCTION f() RETURNS void AS $fn$ BEGIN PERFORM 1; END $fn$ LANGUAGE plpgsql;\n"
        "INSERT INTO t VALUES ('a;b', 'it''s');\n-- trailing; comment\nSELECT 2; /* c; */`;"
        "console.log(JSON.stringify(splitSql(sql).length))"
    )
    assert json.loads(out) == 3


# ── synthetic chains (tmp repo) ──────────────────────────────────────────────

def _repo(tmp_path: Path, chains: dict[str, dict[str, str]], configs: dict[str, dict] | None = None) -> Path:
    for slug, files in chains.items():
        d = tmp_path / "products" / slug / "backend" / "migrations"
        d.mkdir(parents=True)
        for name, sql in files.items():
            (d / name).write_text(sql, encoding="utf-8")
    for slug, cfg in (configs or {}).items():
        (tmp_path / "products" / slug / "backend" / mr.CONFIG_NAME).write_text(json.dumps(cfg), encoding="utf-8")
    return tmp_path


_CORE = {"001_core.sql": "CREATE TABLE public.noctus_users (id uuid PRIMARY KEY);"}


def _replay(root: Path, slug: str, paths=(), **kw):
    return mr.migration_replay([slug], list(paths), root=root, active_only=False, **kw)


def test_core_first_then_product_green(tmp_path, pglite):
    root = _repo(tmp_path, {"core": _CORE, "demo": {
        "001_demo.sql": "CREATE SCHEMA demo;\nCREATE TABLE demo.t (id uuid REFERENCES public.noctus_users(id));",
    }})
    r = _replay(root, "demo")
    assert r["status"] == "green", r


def test_comment_begin_in_history_does_not_wipe_earlier_objects(tmp_path, pglite):
    root = _repo(tmp_path, {"core": _CORE, "demo": {
        "001_demo.sql": "-- open\nBEGIN;\nCREATE TABLE public.kept (id int);\nSELECT * FROM public.nope;\nCOMMIT;",
        "002_demo.sql": "INSERT INTO public.kept VALUES (1);",
    }}, {"demo": {"residue": [{"file": "001_demo.sql", "error": 'relation "public.nope" does not exist',
                               "count": 1, "remediate": "migration-chain-rebaseline"}]}})
    r = _replay(root, "demo")
    assert r["status"] == "green", mr.format_report(r)


def test_unknown_failure_is_red_known_is_green_and_resolved_is_reported(tmp_path, pglite):
    chains = {"core": _CORE, "demo": {"001_demo.sql": "ALTER TABLE public.ghost ADD COLUMN x int;"}}
    red = _replay(_repo(tmp_path / "a", chains), "demo")
    assert red["status"] == "red"
    assert red["products"][0]["new_failures"][0]["file"] == "001_demo.sql"

    residue = {"file": "001_demo.sql", "error": 'relation "public.ghost" does not exist',
               "count": 1, "remediate": "migration-chain-rebaseline"}
    green = _replay(_repo(tmp_path / "b", chains, {"demo": {"residue": [residue]}}), "demo")
    assert green["status"] == "green"

    fixed = {"core": _CORE, "demo": {"001_demo.sql": "SELECT 1;"}}
    pruned = _replay(_repo(tmp_path / "c", fixed, {"demo": {"residue": [residue]}}), "demo")
    assert pruned["status"] == "green"
    assert pruned["products"][0]["resolved_residue"][0]["file"] == "001_demo.sql"


def test_changed_file_must_apply_twice(tmp_path, pglite):
    root = _repo(tmp_path, {"core": _CORE, "demo": {
        "001_demo.sql": "CREATE SCHEMA demo;",
        "002_demo.sql": "CREATE TABLE demo.t (id int);",
    }})
    target = "products/demo/backend/migrations/002_demo.sql"
    r = _replay(root, "demo", [target])
    assert r["status"] == "red"
    (failure,) = r["products"][0]["target_failures"]
    assert failure["phase"] == "reapply" and failure["code"] == "42P07"

    (root / target).write_text("CREATE TABLE IF NOT EXISTS demo.t (id int);", encoding="utf-8")
    assert _replay(root, "demo", [target])["status"] == "green"


def test_residue_without_declared_destination_is_refused(tmp_path, pglite):
    root = _repo(tmp_path, {"core": _CORE, "demo": {"001_demo.sql": "SELECT 1;"}},
                 {"demo": {"residue": [{"file": "001_demo.sql", "error": "x", "remediate": "someday"}]}})
    r = _replay(root, "demo")
    assert r["status"] == "inconclusive"
    assert "NOC-REMEDIATE" in r["products"][0]["error"]


def test_harness_that_cannot_run_is_inconclusive_never_green(tmp_path):
    root = _repo(tmp_path, {"core": _CORE, "demo": {"001_demo.sql": "SELECT 1;"}})
    r = _replay(root, "demo", node_bin=str(tmp_path / "no-such-node"))
    assert r["status"] == "inconclusive"


def test_products_for_paths_maps_migrations_and_config_only():
    assert mr.products_for_paths([
        "products/igig/backend/migrations/040_x.sql",
        "products/igig/backend/migration-replay.json",
        "products/core/backend/app/main.py",
        "products/igig/backend/migrations/sqlite/001.sql",
    ]) == ["igig"]


# ── a freshly scaffolded product ─────────────────────────────────────────────

def test_scaffolded_product_chain_is_green_and_idempotent(tmp_path, pglite, monkeypatch):
    """A new product's FIRST migration commit makes every one of its files a
    target (applied whole, then a second time). The scaffold copies
    templates/product-seed/ — whose 001/003 diverge from the applied (immutable)
    seed copies precisely so they re-apply cleanly (templates/product-seed-
    divergences.json). Real scaffold, real core chain, real template."""
    from tools.noctus.dev import scaffold as scaffold_module

    async def _no_llm(template_content, **_kwargs):
        return None
    monkeypatch.setattr(scaffold_module, "llm_rewrite_file_content", _no_llm)  # self-patch-ok: declared LLM seam (prose only, not under test)

    repo = Path(REPO_ROOT)
    core = tmp_path / "products" / mr.CORE / "backend"
    shutil.copytree(repo / mr._migration_dir(mr.CORE), core / "migrations")
    core_cfg = repo / "products" / mr.CORE / "backend" / mr.CONFIG_NAME
    if core_cfg.exists():
        shutil.copy(core_cfg, core / mr.CONFIG_NAME)

    slug = "replay-probe"
    result = scaffold_module.scaffold_product(
        "Replay Probe", slug, "replay_probe", 8990, 8991, brief={},
        products_dir=tmp_path / "products", template_dir=repo / "templates" / "product-seed",
    )
    assert result.get("created") is True, result
    targets = [f"{mr._migration_dir(slug)}/{name}" for name, _ in mr.chain_files(tmp_path, slug)]
    assert f"{mr._migration_dir(slug)}/001_{slug}.sql" in targets
    assert f"{mr._migration_dir(slug)}/003_examples.sql" in targets

    r = _replay(tmp_path, slug, targets)
    assert r["status"] == "green", mr.format_report(r)


# ── the real chains ──────────────────────────────────────────────────────────

def test_active_chains_replay_green_against_their_residue(pglite):
    from tools.noctus.dev.product_scope import read_active_scope

    r = mr.migration_replay(read_active_scope(Path(REPO_ROOT)))
    assert r["status"] == "green", mr.format_report(r)


def test_sw_231_v1_goes_red_with_23514_and_the_fix_goes_green(pglite):
    """The bug this gate exists for: 231 v1 ran its backfill under the CHECK it
    was replacing and prod refused it (23514, 2026-10-10). The SW fixture holds
    the bare-digit rows prod held."""
    v1 = (_FIXTURES / "sw_231_v1_backfill_under_old_check.sql.txt").read_text(encoding="utf-8")
    red = mr.migration_replay(paths=[_SW_231], overrides={_SW_231: v1})
    assert red["status"] == "red"
    (failure,) = red["products"][0]["target_failures"]
    assert failure["code"] == "23514" and failure["phase"] == "apply"

    green = mr.migration_replay(paths=[_SW_231])
    assert green["status"] == "green", mr.format_report(green)
