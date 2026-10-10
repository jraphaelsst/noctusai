"""Tests for `check_private_unique_violation_predicate` (DRY keeper)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_private_unique_violation_predicate  # noqa: E402

COPY = "def _is_unique_violation(exc):\n    return getattr(exc, 'code', None) == '23505'\n"
CANON = "seed/lib/backend/noctusai_lib/primitives/postgrest_errors.py"


def _write(root: Path, rel: str, text: str) -> None:
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")


def _awake(root: Path, *slugs: str) -> None:
    _write(root, "deploy/fleet/active-scope.txt", "\n".join(slugs) + "\n")


class TestPrivateUniqueViolationPredicate:
    def test_awake_product_copy_flagged(self, tmp_path):
        _awake(tmp_path, "awake")
        _write(tmp_path, "products/awake/backend/app/services/s.py", COPY)
        issues = check_private_unique_violation_predicate(repo_root=tmp_path)
        assert [(i["product"], i["file"], i["severity"]) for i in issues] == [
            ("awake", "products/awake/backend/app/services/s.py:1", "high"),
        ]

    def test_duplicate_key_alias_and_seed_copy_flagged(self, tmp_path):
        _awake(tmp_path, "awake")
        _write(tmp_path, "products/awake/backend/app/a.py", "def _is_duplicate_key(e):\n    return True\n")
        _write(tmp_path, "seed/lib/backend/noctusai_lib/domain/x.py", COPY)
        assert len(check_private_unique_violation_predicate(repo_root=tmp_path)) == 2

    def test_canonical_module_allowed(self, tmp_path):
        _awake(tmp_path, "awake")
        _write(tmp_path, CANON, "def is_unique_violation(exc):\n    return True\n")
        assert check_private_unique_violation_predicate(repo_root=tmp_path) == []

    def test_consumer_import_tests_and_asleep_clean(self, tmp_path):
        _awake(tmp_path, "awake")
        _write(tmp_path, "products/awake/backend/app/s.py",
               "from noctusai_lib.primitives.postgrest_errors import is_unique_violation\n")
        _write(tmp_path, "products/awake/backend/app/tests/t.py", COPY)
        _write(tmp_path, "products/sleepy/backend/app/s.py", COPY)
        assert check_private_unique_violation_predicate(repo_root=tmp_path) == []
