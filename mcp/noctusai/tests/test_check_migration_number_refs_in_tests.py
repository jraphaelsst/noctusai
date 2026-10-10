"""`check_migration_number_refs_in_tests` — ratchet keeper tests (synthetic trees)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import compliance as c  # noqa: E402


def _tree(tmp_path, files: dict[str, str], baseline: dict | None = None):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    if baseline is not None:
        b = tmp_path.joinpath(*c._MNR_BASELINE_REL)
        b.parent.mkdir(parents=True, exist_ok=True)
        b.write_text(json.dumps({"files": baseline}))
    return tmp_path


def _awake(monkeypatch):
    monkeypatch.setattr(c, "_active_product_dirs", lambda d: sorted(p for p in d.iterdir() if p.is_dir()))


T = "products/p/backend/tests/test_x.py"


class TestCheckMigrationNumberRefsInTests:
    """Pins the keeper's true/false-positive shapes and the ratchet (registered for check_detector_has_regression_test)."""
    
    
    def test_flags_number_literal(self, tmp_path, monkeypatch):
        _awake(monkeypatch)
        root = _tree(tmp_path, {T: 'F = "217_thing.sql"\n'})
        issues = c.check_migration_number_refs_in_tests(root)
        assert len(issues) == 1 and issues[0]["severity"] == "high" and issues[0]["file"] == T
    
    
    def test_flags_path_form(self, tmp_path, monkeypatch):
        _awake(monkeypatch)
        root = _tree(tmp_path, {T: 'p = "migrations/217_"\n'})
        assert len(c.check_migration_number_refs_in_tests(root)) == 1
    
    
    def test_suffix_helper_usage_is_clean(self, tmp_path, monkeypatch):
        _awake(monkeypatch)
        root = _tree(tmp_path, {T: 'sql = migration_sql(root, "thing")  # 12 migrations\n'})
        assert c.check_migration_number_refs_in_tests(root) == []
    
    
    def test_baseline_tolerates_then_blocks_growth(self, tmp_path, monkeypatch):
        _awake(monkeypatch)
        root = _tree(tmp_path, {T: '"217_a.sql"\n'}, baseline={T: 1})
        assert c.check_migration_number_refs_in_tests(root) == []
        (root / T).write_text('"217_a.sql"\n"218_b.sql"\n')
        assert len(c.check_migration_number_refs_in_tests(root)) == 1
    
    
    def test_new_file_blocks_even_with_baseline(self, tmp_path, monkeypatch):
        _awake(monkeypatch)
        root = _tree(tmp_path, {T: '"217_a.sql"\n', "products/p/backend/tests/test_new.py": '"300_n.sql"'}, baseline={T: 1})
        issues = c.check_migration_number_refs_in_tests(root)
        assert [i["file"] for i in issues] == ["products/p/backend/tests/test_new.py"]
    
    
    def test_paths_narrow_reporting(self, tmp_path, monkeypatch):
        _awake(monkeypatch)
        root = _tree(tmp_path, {T: '"217_a.sql"'})
        assert c.check_migration_number_refs_in_tests(root, paths=["other.py"]) == []
    
    
    def test_refresh_only_shrinks(self, tmp_path, monkeypatch):
        _awake(monkeypatch)
        root = _tree(tmp_path, {T: '"217_a.sql"\n"218_b.sql"\n', "products/p/backend/tests/test_y.py": '"1_x.sql" "400_y.sql"'})
        assert c.refresh_migration_number_refs_baseline(root) == {T: 2, "products/p/backend/tests/test_y.py": 1}
        (root / T).write_text('"217_a.sql"\n')
        (root / "products/p/backend/tests/test_z.py").write_text('"500_z.sql"')
        assert c.refresh_migration_number_refs_baseline(root) == {T: 1, "products/p/backend/tests/test_y.py": 1}
