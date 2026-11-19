"""The probe-registry keeper reads the registry DATA from the tree being judged (hooks run the primary's toolkit).

Regression (S4/S9, 2026-11): a branch adding a GuardProbe for its own new migration could not pass
`check_migration_guard_has_probe` under the primary's toolkit and needed NOCTUS_HOOK_OWN_TOOLKIT."""
from __future__ import annotations

from tools.noctus.dev import compliance as C

SQL = "ALTER TABLE demo.t ADD CONSTRAINT zz_branch_only_guard CHECK (a > 0);\n"
REL = "products/demo/backend/migrations/001_x.sql"


def _tree(root, registry_src: str | None):
    d = root / "products" / "demo" / "backend" / "migrations"
    d.mkdir(parents=True)
    (d / "001_x.sql").write_text(SQL, encoding="utf-8")
    if registry_src is not None:
        t = root / "mcp" / "noctusai" / "tools" / "noctus" / "dev"
        t.mkdir(parents=True)
        (t / "verify_db_guards.py").write_text(registry_src, encoding="utf-8")


def test_unregistered_guard_is_flagged_without_branch_registry(tmp_path):
    _tree(tmp_path, None)
    assert len(C.check_migration_guard_has_probe(repo_root=tmp_path, paths=[REL])) == 1


def test_branch_registry_probe_satisfies_the_keeper(tmp_path):
    _tree(tmp_path, 'P = GuardProbe(id="x", guard_name="zz_branch_only_guard")\n')
    assert C.check_migration_guard_has_probe(repo_root=tmp_path, paths=[REL]) == []


def test_branch_registry_cannot_change_keeper_logic(tmp_path):
    _tree(tmp_path, 'P = GuardProbe(id="x", guard_name="something_else")\n')
    assert len(C.check_migration_guard_has_probe(repo_root=tmp_path, paths=[REL])) == 1


def test_non_literal_guard_name_is_not_registered(tmp_path):
    _tree(tmp_path, 'N = "zz_branch_only_guard"\nP = GuardProbe(id="x", guard_name=N)\n')
    assert len(C.check_migration_guard_has_probe(repo_root=tmp_path, paths=[REL])) == 1


def test_unparseable_branch_registry_falls_back_to_toolkit_set(tmp_path):
    _tree(tmp_path, "def (:\n")
    assert len(C.check_migration_guard_has_probe(repo_root=tmp_path, paths=[REL])) == 1


def test_import_time_side_effect_in_branch_file_is_never_executed(tmp_path):
    marker = tmp_path / "executed.flag"
    _tree(tmp_path, (
        "from tools.noctus.dev import compliance as C\n"
        "C.check_migration_guard_has_probe = lambda *a, **k: []\n"
        f"open({str(marker)!r}, 'w').write('x')\n"
    ))
    assert len(C.check_migration_guard_has_probe(repo_root=tmp_path, paths=[REL])) == 1
    assert not marker.exists()
