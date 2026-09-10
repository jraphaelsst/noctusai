"""`check_seed_declared_imports` — every runtime import in a seed package must
name a distribution that package's own pyproject declares.

WHY (2026-09-10). The direct generalisation of the `bcrypt` incident one day
earlier: `noctusai_seed.apply_sqlite_migrations` imported bcrypt, no manifest
anywhere declared it, and it resolved for as long as it did only because
something else in the environment happened to supply it. The seed-test CI jobs
now catch that class — but ONLY where a test exercises the import. An
undeclared import on an untested path stays invisible, and `noctusai_lib` is
installed into every product image, so invisible means "breaks at boot, in
prod, on the first image built without the accidental provider".

First run found four, two of them the exact same shape:
  apscheduler  module-level in `noctusai_lib.api.scheduler` — resolved only
               because the ROOT requirements.txt happened to list it
  starlette    imported directly by `noctusai_seed.app`, declared only in
               seed/lib — resolved transitively through fastapi
  postgrest    module-level in `noctusai_lib.testing.mocks` — a DIRECT import
               of a supabase sub-dependency, the same assumption that cost the
               2026-07-12 erp outage when a rebuild floated gotrue
  pytest       module-level in `noctusai_lib.testing` — honestly an extra

🔴 The two assertions that carry the weight are
`TestGuardedImportsAreOptional::test_a_try_guarded_import_is_not_a_finding` and
`test_an_unguarded_import_of_the_same_module_IS_a_finding`. Together they pin
the actual predicate: what makes an import mandatory is that it cannot degrade.
If the first ever fails, the keeper has started flagging correctly-optional
dependencies and will be silenced by exemptions; if the second ever passes,
it has stopped catching the bug it was built for.

→ KB § PATTERNS/devops/product-lockfile-and-slug-drift.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_seed_declared_imports  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

_PYPROJECT = """\
[project]
name = "noctusai-lib"
version = "0.1.0"
dependencies = [
    "fastapi>=0.121.0",
    "PyJWT>=2.9.0",
    "pdfminer.six>=20231228",
]
"""


def _mk_pkg(root: Path, layer: str, pkg: str, *, pyproject: str = _PYPROJECT) -> Path:
    backend = root / "seed" / layer / "backend"
    pkg_dir = backend / pkg
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text("")
    (backend / "pyproject.toml").write_text(pyproject)
    return pkg_dir


class TestCheckSeedDeclaredImports:
    """The canonical `Test<detector>` name — `check_detector_has_regression_test`
    matches detectors to tests by CLASS name, so this is what makes the keeper
    discoverable. True-positive shapes live here."""

    def test_an_undeclared_module_level_import_is_flagged(self, tmp_path):
        pkg = _mk_pkg(tmp_path, "lib", "noctusai_lib")
        (pkg / "scheduler.py").write_text("import apscheduler\n")

        issues = check_seed_declared_imports(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "high"
        assert "apscheduler" in issues[0]["issue"]

    def test_an_undeclared_import_inside_a_function_is_still_flagged(self, tmp_path):
        """The bcrypt shape exactly: a lazy import is still a hard dependency —
        it just fails later, in whichever code path first reaches it."""
        pkg = _mk_pkg(tmp_path, "framework", "noctusai_seed")
        (pkg / "migrations.py").write_text(
            "def hash_it(pw):\n    import bcrypt\n    return bcrypt.hashpw(pw)\n"
        )

        issues = check_seed_declared_imports(tmp_path)
        assert [i["file"].endswith("migrations.py") for i in issues] == [True], issues
        assert "bcrypt" in issues[0]["issue"]

    def test_a_declared_import_is_clean(self, tmp_path):
        pkg = _mk_pkg(tmp_path, "lib", "noctusai_lib")
        (pkg / "api.py").write_text("import fastapi\nfrom fastapi import APIRouter\n")

        assert check_seed_declared_imports(tmp_path) == []

    def test_both_seed_packages_are_covered(self, tmp_path):
        _mk_pkg(tmp_path, "lib", "noctusai_lib")
        (tmp_path / "seed/lib/backend/noctusai_lib/a.py").write_text("import redis\n")
        _mk_pkg(tmp_path, "framework", "noctusai_seed")
        (tmp_path / "seed/framework/backend/noctusai_seed/b.py").write_text("import redis\n")

        issues = check_seed_declared_imports(tmp_path)
        assert len(issues) == 2, issues


class TestGuardedImportsAreOptional:
    """🔴 The predicate itself: an import is mandatory when it cannot degrade."""

    def test_a_try_guarded_import_is_not_a_finding(self, tmp_path):
        """`networkx`, `resend` and one `postgrest` site are genuinely optional —
        try/except ImportError WITH a real fallback. Flagging these would make
        the keeper noisy, and a noisy keeper gets silenced by exemptions until
        it no longer catches anything."""
        pkg = _mk_pkg(tmp_path, "lib", "noctusai_lib")
        (pkg / "cluster.py").write_text(
            "def cluster(g):\n"
            "    try:\n"
            "        import networkx as nx\n"
            "        return nx.Graph()\n"
            "    except ImportError:\n"
            "        return None\n"
        )

        assert check_seed_declared_imports(tmp_path) == []

    def test_an_unguarded_import_of_the_same_module_IS_a_finding(self, tmp_path):
        """The other half of the pair. Same module, no guard — now it can raise
        at import time and nothing can catch it, so it must be declared. If this
        ever passes, the keeper has stopped catching the bug it exists for."""
        pkg = _mk_pkg(tmp_path, "lib", "noctusai_lib")
        (pkg / "cluster.py").write_text("import networkx as nx\n")

        issues = check_seed_declared_imports(tmp_path)
        assert len(issues) == 1, issues
        assert "networkx" in issues[0]["issue"]

    def test_a_type_checking_import_is_not_a_finding(self, tmp_path):
        """Never executed at runtime, so it can never raise ModuleNotFoundError."""
        pkg = _mk_pkg(tmp_path, "lib", "noctusai_lib")
        (pkg / "types.py").write_text(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    import sqlalchemy\n"
        )

        assert check_seed_declared_imports(tmp_path) == []


class TestNameResolution:
    def test_import_name_differing_from_distribution_name_is_resolved(self, tmp_path):
        """`fitz` is PyMuPDF, `jwt` is PyJWT, `pdfminer` is pdfminer.six. A bare
        string compare would report all three and teach people to ignore this."""
        pkg = _mk_pkg(tmp_path, "lib", "noctusai_lib")
        (pkg / "auth.py").write_text("import jwt\n")
        (pkg / "pdf.py").write_text("from pdfminer.high_level import extract_text\n")

        assert check_seed_declared_imports(tmp_path) == []

    def test_stdlib_and_relative_and_self_imports_are_never_findings(self, tmp_path):
        pkg = _mk_pkg(tmp_path, "lib", "noctusai_lib")
        (pkg / "x.py").write_text(
            "import os\nimport asyncio\nfrom __future__ import annotations\n"
            "from . import y\nfrom noctusai_lib.z import thing\n"
        )

        assert check_seed_declared_imports(tmp_path) == []

    def test_a_consumer_provided_module_is_not_a_dependency(self, tmp_path):
        """`noctusai_lib.testing.fixtures` imports `app.rate_limit` inside a
        fixture on purpose — it runs only in a test session that has the PRODUCT
        app importable. The seed cannot depend on its own consumer."""
        pkg = _mk_pkg(tmp_path, "lib", "noctusai_lib")
        (pkg / "fixtures.py").write_text(
            "def reset():\n    from app.rate_limit import limiter\n    limiter.reset()\n"
        )

        assert check_seed_declared_imports(tmp_path) == []

    def test_an_optional_dependency_group_counts_as_declared(self, tmp_path):
        """`pytest` lives in a `testing` extra rather than forcing pytest into
        every product image. Counting extras keeps that honest instead of
        pushing people to satisfy the gate the wrong way."""
        pyproject = _PYPROJECT + '\n[project.optional-dependencies]\ntesting = ["pytest>=7.0"]\n'
        pkg = _mk_pkg(tmp_path, "lib", "noctusai_lib", pyproject=pyproject)
        (pkg / "fixtures.py").write_text("import pytest\n")

        assert check_seed_declared_imports(tmp_path) == []


class TestLiveRepo:
    def test_the_real_repo_is_clean(self):
        """The gate must hold on the tree that ships it — otherwise the commit
        adding the keeper also adds a standing failure."""
        assert check_seed_declared_imports(REPO) == []
