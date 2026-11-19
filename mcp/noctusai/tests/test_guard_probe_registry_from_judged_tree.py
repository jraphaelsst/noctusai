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
    _tree(tmp_path, 'REGISTERED_GUARD_NAMES = frozenset({"zz_branch_only_guard"})\n')
    assert C.check_migration_guard_has_probe(repo_root=tmp_path, paths=[REL]) == []


def test_branch_registry_cannot_change_keeper_logic(tmp_path):
    # a branch registry naming a different guard does not silence this one
    _tree(tmp_path, 'REGISTERED_GUARD_NAMES = frozenset({"something_else"})\n')
    assert len(C.check_migration_guard_has_probe(repo_root=tmp_path, paths=[REL])) == 1


def test_broken_branch_registry_falls_back_to_toolkit_set(tmp_path):
    _tree(tmp_path, "raise RuntimeError('boom')\n")
    assert len(C.check_migration_guard_has_probe(repo_root=tmp_path, paths=[REL])) == 1
