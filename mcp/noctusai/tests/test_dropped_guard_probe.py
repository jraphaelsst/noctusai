"""A staged migration that drops a guard whose behaviour probe is still registered is refused at commit.

Regression (2026-11-09): agents 071 dropped two unique indexes whose probes stayed in DEFAULT_REGISTRY; the
DB-guard replay went red only in the merge queue."""
from __future__ import annotations

from tools.noctus.dev import compliance as C
from tools.noctus.dev.verify_db_guards import REGISTERED_GUARD_NAMES

GUARD = sorted(REGISTERED_GUARD_NAMES)[0]


def _write(root, sql: str) -> str:
    d = root / "products" / "demo" / "backend" / "migrations"
    d.mkdir(parents=True, exist_ok=True)
    (d / "002_drop.sql").write_text(sql, encoding="utf-8")
    return "products/demo/backend/migrations/002_drop.sql"


def test_dropping_a_probed_guard_is_flagged(tmp_path):
    rel = _write(tmp_path, f"DROP INDEX IF EXISTS demo.{GUARD};\n")
    findings = C.check_migration_guard_has_probe(repo_root=tmp_path, paths=[rel])
    assert len(findings) == 1 and GUARD in findings[0]["issue"] and "Retire the probe" in findings[0]["issue"]


def test_dropping_an_unprobed_index_passes(tmp_path):
    rel = _write(tmp_path, "DROP INDEX IF EXISTS demo.idx_never_probed_zz;\n")
    assert C.check_migration_guard_has_probe(repo_root=tmp_path, paths=[rel]) == []


def test_drop_then_recreate_in_the_same_file_is_a_redefinition_not_a_drop():
    content = f"DROP INDEX IF EXISTS demo.{GUARD};\nCREATE UNIQUE INDEX {GUARD} ON demo.t (a);\n"
    assert C._dropped_guards_still_probed(content, "x.sql", "demo", frozenset({GUARD})) == []


def test_constraint_and_trigger_drops_are_seen():
    content = "ALTER TABLE demo.t DROP CONSTRAINT IF EXISTS ck_zz;\nDROP TRIGGER guard_zz ON demo.t;\n"
    got = C._dropped_guards_still_probed(content, "x.sql", "demo", frozenset({"ck_zz", "guard_zz"}))
    assert sorted(f["issue"].split("`")[1] for f in got) == ["ck_zz", "guard_zz"]
