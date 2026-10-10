"""`check_product_declared_imports` — product runtime imports + implied deps
must be declared for the IMAGE (product requirements.txt + seed pyprojects).
Synthetic trees; the 2026-10-10 core python-multipart crash-loop is the case."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import compliance as c  # noqa: E402

SEED_PYPROJECT = '[project]\nname = "noctusai-lib"\ndependencies = ["fastapi>=0.121.0", "httpx>=0.27"]\n'


def _tree(tmp_path: Path, app_files: dict[str, str], requirements: str, slug: str = "p") -> Path:
    lib = tmp_path / "seed/lib/backend"
    (lib / "noctusai_lib").mkdir(parents=True, exist_ok=True)
    (lib / "noctusai_lib/__init__.py").write_text("")
    (lib / "pyproject.toml").write_text(SEED_PYPROJECT)
    backend = tmp_path / "products" / slug / "backend"
    for rel, text in {"app/__init__.py": "", **app_files}.items():
        (backend / rel).parent.mkdir(parents=True, exist_ok=True)
        (backend / rel).write_text(text)
    (backend / "requirements.txt").write_text(requirements)
    return tmp_path


def _findings(root: Path, slug: str = "p") -> list[dict]:
    return c._product_declared_imports_findings(root, [root / "products" / slug])


class TestCheckProductDeclaredImports:
    def test_fastapi_form_without_python_multipart_is_a_finding(self, tmp_path):
        root = _tree(tmp_path, {"app/routers/t.py": "from fastapi import APIRouter, File, Form, UploadFile\n"},
                     "-e seed/lib/backend\n")
        issues = _findings(root)
        assert len(issues) == 1  # one per missing distribution, not per name
        assert "python-multipart" in issues[0]["issue"] and issues[0]["severity"] == "high"
        assert issues[0]["file"] == "products/p/backend/app/routers/t.py"

    def test_declared_python_multipart_is_clean(self, tmp_path):
        root = _tree(tmp_path, {"app/routers/t.py": "from fastapi import Form\n"},
                     "python-multipart>=0.0.9  # Form\n")
        assert _findings(root) == []

    def test_emailstr_satisfied_by_pydantic_email_extra(self, tmp_path):
        root = _tree(tmp_path, {"app/s.py": "from pydantic import EmailStr\n"}, "pydantic[email]==2.13.4\n")
        assert _findings(root) == []
        root2 = _tree(tmp_path / "b", {"app/s.py": "from pydantic import EmailStr\n"}, "pydantic==2.13.4\n")
        assert "email-validator" in _findings(root2)[0]["issue"]

    def test_undeclared_third_party_import_is_a_finding(self, tmp_path):
        root = _tree(tmp_path, {"app/x.py": "import anyio\n"}, "fastapi\n")
        assert "imports `anyio`" in _findings(root)[0]["issue"]

    def test_seed_pyproject_deps_count_as_declared(self, tmp_path):
        root = _tree(tmp_path, {"app/x.py": "import httpx\nimport fastapi\n"}, "-e seed/lib/backend\n")
        assert _findings(root) == []

    def test_requirements_include_is_followed(self, tmp_path):
        root = _tree(tmp_path, {"app/x.py": "import anyio\n"}, "-r extra.txt\n")
        (root / "products/p/backend/extra.txt").write_text("anyio>=3.6.2,<5\n")
        assert _findings(root) == []

    def test_import_name_alias_map_applies(self, tmp_path):
        root = _tree(tmp_path, {"app/x.py": "import jwt\nimport yaml\n"}, "PyJWT==2.14.0\nPyYAML\n")
        assert _findings(root) == []

    def test_stdlib_firstparty_guarded_and_type_checking_are_exempt(self, tmp_path):
        root = _tree(tmp_path, {"app/x.py": (
            "import json\nfrom app.y import z\nfrom noctusai_lib import q\nfrom . import w\n"
            "try:\n    import optional_thing\nexcept ImportError:\n    optional_thing = None\n"
            "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import sqlalchemy\n")}, "fastapi\n")
        assert _findings(root) == []

    def test_tests_dir_is_out_of_scope(self, tmp_path):
        root = _tree(tmp_path, {}, "fastapi\n")
        (root / "products/p/backend/tests").mkdir()
        (root / "products/p/backend/tests/test_x.py").write_text("import pytest_undeclared\n")
        assert _findings(root) == []

    def test_paths_scope_to_staged_products_but_seed_manifest_keeps_fleet(self, tmp_path):
        root = _tree(tmp_path, {"app/x.py": "import anyio\n"}, "fastapi\n", slug="a")
        _tree(root, {"app/x.py": "import anyio\n"}, "fastapi\n", slug="b")
        # No deploy/fleet/active-scope.txt ⇒ filter_active fails toward coverage.
        assert {i["product"] for i in c.check_product_declared_imports(root)} == {"a", "b"}
        assert {i["product"] for i in c.check_product_declared_imports(
            root, paths=["products/a/backend/app/x.py"])} == {"a"}
        assert {i["product"] for i in c.check_product_declared_imports(
            root, paths=["seed/lib/backend/pyproject.toml"])} == {"a", "b"}
