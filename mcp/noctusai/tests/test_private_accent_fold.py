"""Tests for `check_private_accent_fold` (DRY keeper)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_private_accent_fold  # noqa: E402

COPY = (
    "import unicodedata\n"
    "def _sem_acento(t):\n"
    "    d = unicodedata.normalize('NFKD', t)\n"
    "    return ''.join(c for c in d if not unicodedata.combining(c))\n"
)
CANON = "seed/lib/backend/noctusai_lib/primitives/accents.py"


def _write(root: Path, rel: str, text: str) -> None:
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")


def _awake(root: Path, *slugs: str) -> None:
    _write(root, "deploy/fleet/active-scope.txt", "\n".join(slugs) + "\n")


class TestPrivateAccentFold:
    def test_awake_product_copy_flagged(self, tmp_path):
        _awake(tmp_path, "awake")
        _write(tmp_path, "products/awake/backend/app/services/s.py", COPY)
        issues = check_private_accent_fold(repo_root=tmp_path)
        assert [(i["product"], i["file"], i["severity"]) for i in issues] == [
            ("awake", "products/awake/backend/app/services/s.py:3", "high"),
        ]

    def test_nfd_and_seed_copy_flagged(self, tmp_path):
        _awake(tmp_path, "awake")
        _write(tmp_path, "products/awake/backend/app/a.py",
               "import unicodedata as u\nx = u.normalize('NFD', 'á')\n")
        _write(tmp_path, "seed/lib/backend/noctusai_lib/domain/x.py", COPY)
        assert len(check_private_accent_fold(repo_root=tmp_path)) == 2

    def test_canonical_and_named_exceptions_allowed(self, tmp_path):
        _awake(tmp_path, "social-wiring")
        _write(tmp_path, CANON, COPY)
        _write(tmp_path, "seed/lib/backend/noctusai_lib/domain/real_estate/imovel.py", COPY)
        _write(tmp_path, "products/social-wiring/backend/app/modules/leads/services/dimensions_service.py", COPY)
        assert check_private_accent_fold(repo_root=tmp_path) == []

    def test_nfc_consumer_tests_and_asleep_clean(self, tmp_path):
        _awake(tmp_path, "awake")
        _write(tmp_path, "products/awake/backend/app/s.py",
               "import unicodedata\nfrom noctusai_lib.primitives.accents import fold_accents\n"
               "y = unicodedata.normalize('NFC', 'x')\n")
        _write(tmp_path, "products/awake/backend/app/tests/t.py", COPY)
        _write(tmp_path, "products/sleepy/backend/app/s.py", COPY)
        assert check_private_accent_fold(repo_root=tmp_path) == []
