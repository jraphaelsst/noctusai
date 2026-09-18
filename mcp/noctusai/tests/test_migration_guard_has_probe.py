"""Regression tests for
``noctus.dev.compliance.check_migration_guard_has_probe`` — the
gate↔methodology-sync backstop for ``noctus.dev.verify_db_guards``.

THE RULE THIS KEEPER ENFORCES: a migration that ships a genuine guard
(a trigger function that RAISEs, a named CHECK/UNIQUE constraint) must
have a corresponding ``GuardProbe`` registered — otherwise the guard is
"structurally verified" only, exactly the class of bug ``verify_db_guards``
exists to catch (structure-green is not behaviour-green).

All tests operate against an isolated ``tmp_path`` tree, never the real
repo, so this file cannot trip on the platform's own (large, unretrofitted)
migration corpus — matching ``test_storage_bucket_public_keeper.py``'s own
hermetic-tmp-path idiom. One test DOES exercise the real
``products/social-wiring/backend/migrations/136_...`` file, diff-scoped via
``paths=``, to prove the shipped registry actually covers what it claims.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "seed" / "lib" / "backend"))

from tools.noctus.dev.compliance import (  # noqa: E402
    _detect_guard_objects,
    check_migration_guard_has_probe,
)


def _write_migration(root: Path, product: str, filename: str, sql: str) -> Path:
    mig_dir = root / "products" / product / "backend" / "migrations"
    mig_dir.mkdir(parents=True, exist_ok=True)
    path = mig_dir / filename
    path.write_text(sql, encoding="utf-8")
    return path


_TRIGGER_GUARD_SQL = """
CREATE OR REPLACE FUNCTION fake_schema.widgets_protege()
  RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status IS DISTINCT FROM NEW.status THEN
    RAISE EXCEPTION 'widgets: status nao pode ser alterado';
  END IF;
  RETURN NEW;
END;
$$;
"""

_PASSIVE_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION fake_schema.set_updated_at()
  RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;
"""

_CHECK_CONSTRAINT_SQL = """
CREATE TABLE fake_schema.widgets (
    id UUID PRIMARY KEY,
    status TEXT NOT NULL,
    CONSTRAINT widgets_status_check CHECK (status IN ('a', 'b'))
);
"""

_ADD_CONSTRAINT_SQL = """
ALTER TABLE fake_schema.widgets
    ADD CONSTRAINT widgets_qty_check CHECK (qty >= 0);
"""

_UNIQUE_INDEX_SQL = """
CREATE UNIQUE INDEX idx_widgets_org_slug ON fake_schema.widgets (org_id, slug);
"""


class TestDetectGuardObjects:
    def test_finds_a_raising_trigger_function(self):
        guards = _detect_guard_objects(_TRIGGER_GUARD_SQL)
        assert {"guard_name": "widgets_protege", "kind": "trigger_function"} in guards

    def test_ignores_a_passive_trigger_function_with_no_raise(self):
        """An `updated_at`-style trigger is not a GUARD — it refuses
        nothing, so it must never demand a behaviour probe."""
        guards = _detect_guard_objects(_PASSIVE_TRIGGER_SQL)
        assert guards == []

    def test_finds_an_inline_check_constraint(self):
        guards = _detect_guard_objects(_CHECK_CONSTRAINT_SQL)
        assert {"guard_name": "widgets_status_check", "kind": "check_constraint"} in guards

    def test_finds_an_alter_table_add_constraint_check(self):
        guards = _detect_guard_objects(_ADD_CONSTRAINT_SQL)
        assert {"guard_name": "widgets_qty_check", "kind": "check_constraint"} in guards

    def test_finds_a_unique_index(self):
        guards = _detect_guard_objects(_UNIQUE_INDEX_SQL)
        assert {"guard_name": "idx_widgets_org_slug", "kind": "unique_constraint"} in guards

    def test_a_comment_mentioning_create_trigger_is_never_a_false_positive(self):
        """Statement-scoped detection (via migration_parser._walk_statements),
        not a naive grep — a comment CITING the shape must never trip it."""
        sql = "-- CREATE TRIGGER example, RAISE EXCEPTION for illustration only\nSELECT 1;"
        assert _detect_guard_objects(sql) == []

    def test_a_string_literal_mentioning_raise_exception_is_never_a_false_positive(self):
        sql = (
            "CREATE TABLE fake_schema.notes (\n"
            "    id UUID PRIMARY KEY,\n"
            "    body TEXT DEFAULT 'this text says RAISE EXCEPTION but is just data'\n"
            ");\n"
        )
        assert _detect_guard_objects(sql) == []


class TestCheckMigrationGuardHasProbe:
    def test_flags_an_unregistered_trigger_guard(self, tmp_path):
        _write_migration(tmp_path, "fake-product", "001_fake.sql", _TRIGGER_GUARD_SQL)
        findings = check_migration_guard_has_probe(
            repo_root=tmp_path,
            paths=["products/fake-product/backend/migrations/001_fake.sql"],
        )
        assert len(findings) == 1
        assert "widgets_protege" in findings[0]["issue"]
        assert findings[0]["severity"] == "high"

    def test_flags_an_unregistered_check_constraint(self, tmp_path):
        _write_migration(tmp_path, "fake-product", "001_fake.sql", _CHECK_CONSTRAINT_SQL)
        findings = check_migration_guard_has_probe(
            repo_root=tmp_path,
            paths=["products/fake-product/backend/migrations/001_fake.sql"],
        )
        assert len(findings) == 1
        assert "widgets_status_check" in findings[0]["issue"]

    def test_does_not_flag_a_passive_trigger_or_ungated_table(self, tmp_path):
        _write_migration(tmp_path, "fake-product", "001_fake.sql", _PASSIVE_TRIGGER_SQL)
        findings = check_migration_guard_has_probe(
            repo_root=tmp_path,
            paths=["products/fake-product/backend/migrations/001_fake.sql"],
        )
        assert findings == []

    def test_dedupes_the_same_guard_name_within_one_file(self, tmp_path):
        """CREATE OR REPLACE FUNCTION appearing twice in one file (a
        genuine, if unusual, shape) must not double-report."""
        sql = _TRIGGER_GUARD_SQL + "\n" + _TRIGGER_GUARD_SQL
        _write_migration(tmp_path, "fake-product", "001_fake.sql", sql)
        findings = check_migration_guard_has_probe(
            repo_root=tmp_path,
            paths=["products/fake-product/backend/migrations/001_fake.sql"],
        )
        assert len(findings) == 1

    def test_paths_none_means_nothing_to_scan_in_an_empty_tree(self, tmp_path):
        """paths=None is the full-tree audit mode (never wired into any
        whole-platform sweep — same posture as check_storage_bucket_public);
        an empty tmp tree has nothing to find either way."""
        (tmp_path / "products").mkdir()
        findings = check_migration_guard_has_probe(repo_root=tmp_path, paths=None)
        assert findings == []

    def test_paths_scoping_ignores_files_outside_the_staged_set(self, tmp_path):
        """A pre-existing unregistered guard in a DIFFERENT, un-staged
        migration file must not surface — diff-scoping, not amnesty for
        the file itself (re-touching it would re-surface it)."""
        _write_migration(tmp_path, "fake-product", "001_fake.sql", _TRIGGER_GUARD_SQL)
        _write_migration(tmp_path, "fake-product", "002_other.sql", "SELECT 1;")
        findings = check_migration_guard_has_probe(
            repo_root=tmp_path,
            paths=["products/fake-product/backend/migrations/002_other.sql"],
        )
        assert findings == []

    def test_an_allowlisted_guard_name_is_not_flagged(self, tmp_path, monkeypatch):
        from tools.noctus.dev import compliance as C

        rel = "products/fake-product/backend/migrations/001_fake.sql"
        monkeypatch.setattr(
            C, "_GUARD_PROBE_ALLOWLIST",
            ((rel, "widgets_protege", "test-only exemption with a rationale"),),
        )
        _write_migration(tmp_path, "fake-product", "001_fake.sql", _TRIGGER_GUARD_SQL)
        findings = check_migration_guard_has_probe(repo_root=tmp_path, paths=[rel])
        assert findings == []

    def test_the_shipped_registry_covers_the_real_migration_136(self):
        """The seeded probes actually cover what they claim to: running
        the keeper diff-scoped to the REAL, on-disk
        136_matricula_ruido_e_abertura.sql (the file
        noctus.dev.verify_db_guards's registry was built against) must
        find zero unregistered guards."""
        rel = "products/social-wiring/backend/migrations/136_matricula_ruido_e_abertura.sql"
        findings = check_migration_guard_has_probe(repo_root=REPO_ROOT, paths=[rel])
        assert findings == [], findings
