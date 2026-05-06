"""Tests for ``noctus.seed.*`` MCP tools — the seed-system absorption +
capability tools.

Read-only diagnostics: scan_repetition, list_capabilities, audit_drift.
All tests use synthetic fixtures via the tools' ``products_dir=`` /
``template_root=`` / ``repo_root=`` test seams — no real-repo writes."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.seed.audit_drift import audit_drift
from tools.noctus.seed.list_capabilities import list_capabilities
from tools.noctus.seed.scan_repetition import scan_repetition


# ─── scan_repetition ───────────────────────────────────────────────────────


def _make_product(products_dir: Path, slug: str, files: dict[str, str]) -> Path:
    """Helper: write a synthetic product tree under ``products_dir/<slug>/``."""
    product_root = products_dir / slug
    for rel_path, content in files.items():
        path = product_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return product_root


class TestScanRepetition:
    def test_empty_products_dir_returns_empty_groups(self, tmp_path):
        products_dir = tmp_path / "products"
        products_dir.mkdir()
        result = scan_repetition(products_dir=products_dir)
        assert result["scanned_products"] == []
        assert result["groups"] == []

    def test_byte_identical_classification(self, tmp_path):
        products_dir = tmp_path / "products"
        identical = "module.exports = { plugins: [] };\n"
        _make_product(products_dir, "alpha", {"frontend/postcss.config.js": identical})
        _make_product(products_dir, "beta", {"frontend/postcss.config.js": identical})
        _make_product(products_dir, "gamma", {"frontend/postcss.config.js": identical})

        result = scan_repetition(products_dir=products_dir)
        assert "alpha" in result["scanned_products"]
        groups = [g for g in result["groups"] if g["rel_path"] == "frontend/postcss.config.js"]
        assert len(groups) == 1
        g = groups[0]
        assert g["classification"] == "byte_identical"
        assert g["occurrences"] == 3
        assert sorted(g["products"]) == ["alpha", "beta", "gamma"]
        assert g["similarity"] == 1.0
        assert g["suggested_destination"] == "seed/framework/frontend/postcss.config.js"

    def test_near_identical_classification(self, tmp_path):
        # Three near-identical configs — one tiny per-file tweak each.
        base = "\n".join(f"line_{i}" for i in range(50)) + "\n"
        products_dir = tmp_path / "products"
        _make_product(products_dir, "alpha", {"backend/app/responses.py": base + "# alpha\n"})
        _make_product(products_dir, "beta", {"backend/app/responses.py": base + "# beta\n"})
        _make_product(products_dir, "gamma", {"backend/app/responses.py": base + "# gamma\n"})

        result = scan_repetition(products_dir=products_dir, near_identical_threshold=0.9)
        groups = [g for g in result["groups"] if g["rel_path"] == "backend/app/responses.py"]
        assert len(groups) == 1
        g = groups[0]
        assert g["classification"] == "near_identical"
        assert g["similarity"] >= 0.9
        assert g["similarity"] < 1.0

    def test_divergent_classification(self, tmp_path):
        products_dir = tmp_path / "products"
        _make_product(products_dir, "alpha", {"backend/app/services/foo.py": "alpha\nspecific\nlogic\n"})
        _make_product(products_dir, "beta", {"backend/app/services/foo.py": "totally\ndifferent\ncode\n"})

        result = scan_repetition(products_dir=products_dir, near_identical_threshold=0.95)
        groups = [g for g in result["groups"] if g["rel_path"] == "backend/app/services/foo.py"]
        assert len(groups) == 1
        assert groups[0]["classification"] == "divergent"

    def test_min_products_threshold(self, tmp_path):
        products_dir = tmp_path / "products"
        # Only TWO products share the file.
        identical = "shared\n"
        _make_product(products_dir, "alpha", {"frontend/x.css": identical})
        _make_product(products_dir, "beta", {"frontend/x.css": identical})

        # Default min_products=2 → group surfaces.
        r2 = scan_repetition(products_dir=products_dir, min_products=2)
        assert any(g["rel_path"] == "frontend/x.css" for g in r2["groups"])

        # min_products=3 → group filtered out.
        r3 = scan_repetition(products_dir=products_dir, min_products=3)
        assert not any(g["rel_path"] == "frontend/x.css" for g in r3["groups"])

    def test_skips_node_modules_and_dist(self, tmp_path):
        products_dir = tmp_path / "products"
        _make_product(products_dir, "alpha", {
            "frontend/src/App.tsx": "console.log('app');\n",
            "frontend/node_modules/lib/index.js": "vendor\n",
            "frontend/dist/bundle.js": "built\n",
        })
        _make_product(products_dir, "beta", {
            "frontend/src/App.tsx": "console.log('app');\n",
            "frontend/node_modules/lib/index.js": "vendor\n",
            "frontend/dist/bundle.js": "built\n",
        })
        result = scan_repetition(products_dir=products_dir)
        paths = {g["rel_path"] for g in result["groups"]}
        assert "frontend/src/App.tsx" in paths
        assert "frontend/node_modules/lib/index.js" not in paths
        assert "frontend/dist/bundle.js" not in paths

    def test_skips_lockfiles_and_binaries(self, tmp_path):
        products_dir = tmp_path / "products"
        _make_product(products_dir, "alpha", {
            "frontend/package-lock.json": '{"foo": 1}',
            "backend/Dockerfile": "FROM python\n",
            "frontend/public/icon.png": "PNG_BYTES",
        })
        _make_product(products_dir, "beta", {
            "frontend/package-lock.json": '{"foo": 1}',
            "backend/Dockerfile": "FROM python\n",
            "frontend/public/icon.png": "PNG_BYTES",
        })
        result = scan_repetition(products_dir=products_dir)
        paths = {g["rel_path"] for g in result["groups"]}
        assert "backend/Dockerfile" in paths
        assert "frontend/package-lock.json" not in paths
        assert "frontend/public/icon.png" not in paths

    def test_summary_counts_match_groups(self, tmp_path):
        products_dir = tmp_path / "products"
        _make_product(products_dir, "alpha", {"a/b.txt": "x", "a/c.txt": "diff_alpha"})
        _make_product(products_dir, "beta", {"a/b.txt": "x", "a/c.txt": "diff_beta_totally"})

        result = scan_repetition(products_dir=products_dir)
        s = result["summary"]
        assert s["byte_identical_count"] == sum(1 for g in result["groups"] if g["classification"] == "byte_identical")
        assert s["divergent_count"] == sum(1 for g in result["groups"] if g["classification"] == "divergent")
        assert s["total_groups"] == len(result["groups"])


# ─── list_capabilities ─────────────────────────────────────────────────────


def _seed_lib_module(repo_root: Path, layer: str, module_name: str, body: str) -> Path:
    """Write a synthetic noctusai_lib module at the right layered path."""
    target = repo_root / "seed" / "lib" / "backend" / "noctusai_lib" / layer / f"{module_name}.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


def _seed_framework_module(repo_root: Path, module_name: str, body: str) -> Path:
    target = repo_root / "seed" / "framework" / "backend" / "noctusai_seed" / f"{module_name}.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


class TestListCapabilities:
    def test_extracts_public_function_with_docstring(self, tmp_path):
        _seed_framework_module(tmp_path, "factory", '''"""Factory module."""

def create_thing(x: int) -> int:
    """Build a thing for the consumer."""
    return x


def _private_helper():
    """Should not surface."""
    pass
''')
        result = list_capabilities(repo_root=tmp_path)
        names = [cap["name"] for cap in result["framework"]]
        assert "create_thing" in names
        assert "_private_helper" not in names
        # Summary captured the first-line docstring.
        cap = next(c for c in result["framework"] if c["name"] == "create_thing")
        assert cap["summary"] == "Build a thing for the consumer."
        assert cap["kind"] == "function"
        assert cap["import_path"] == "noctusai_seed.factory.create_thing"

    def test_extracts_classes_and_constants(self, tmp_path):
        _seed_framework_module(tmp_path, "config", '''"""Config module."""

DEFAULT_TIMEOUT = 30
_INTERNAL = 5

class Settings:
    """Base settings."""
    pass
''')
        result = list_capabilities(repo_root=tmp_path)
        names = {cap["name"] for cap in result["framework"]}
        assert "Settings" in names
        assert "DEFAULT_TIMEOUT" in names
        assert "_INTERNAL" not in names

    def test_groups_library_by_six_layers(self, tmp_path):
        _seed_lib_module(tmp_path, "primitives", "ids", "def make_id():\n    \"\"\"Mint an ID.\"\"\"\n    pass\n")
        _seed_lib_module(tmp_path, "domain", "metas", "def compute_progress():\n    \"\"\"Compute.\"\"\"\n    pass\n")
        _seed_lib_module(tmp_path, "api", "auth", "def verify_token():\n    \"\"\"Verify.\"\"\"\n    pass\n")

        result = list_capabilities(repo_root=tmp_path)
        assert {c["name"] for c in result["library"]["primitives"]} == {"make_id"}
        assert {c["name"] for c in result["library"]["domain"]} == {"compute_progress"}
        assert {c["name"] for c in result["library"]["api"]} == {"verify_token"}
        assert result["library"]["config"] == []
        assert result["summary"]["library_counts"]["primitives"] == 1
        assert result["summary"]["total"] == 3

    def test_empty_seed_returns_zero_counts(self, tmp_path):
        result = list_capabilities(repo_root=tmp_path)
        assert result["framework"] == []
        assert result["summary"]["framework_count"] == 0
        assert result["summary"]["total"] == 0

    def test_skips_files_with_syntax_errors(self, tmp_path):
        _seed_framework_module(tmp_path, "broken", "this is not valid python @@@")
        # Should not raise — invalid file silently yields no capabilities.
        result = list_capabilities(repo_root=tmp_path)
        assert result["framework"] == []


# ─── audit_drift ───────────────────────────────────────────────────────────


def _make_template_file(template_root: Path, rel_path: str, content: str) -> None:
    target = template_root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


class TestAuditDrift:
    def test_identical_when_bytes_match(self, tmp_path):
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        content = "x = 1\ny = 2\n"
        _make_template_file(template_root, "backend/app/foo.py", content)
        _make_product(products_dir, "alpha", {"backend/app/foo.py": content})

        result = audit_drift(template_root=template_root, products_dir=products_dir)
        entry = next(e for e in result["files"] if e["rel_path"] == "backend/app/foo.py")
        assert entry["products"][0]["status"] == "identical"
        assert entry["products"][0]["drift_lines"] == 0

    def test_small_drift_threshold(self, tmp_path):
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        template_content = "\n".join(f"line_{i}" for i in range(50)) + "\n"
        # Product changes ONE line.
        product_content = template_content.replace("line_0", "line_zero_changed")
        _make_template_file(template_root, "frontend/src/App.tsx", template_content)
        _make_product(products_dir, "alpha", {"frontend/src/App.tsx": product_content})

        result = audit_drift(
            template_root=template_root,
            products_dir=products_dir,
            drift_threshold_lines=20,
        )
        entry = next(e for e in result["files"] if e["rel_path"] == "frontend/src/App.tsx")
        assert entry["products"][0]["status"] == "small_drift"
        assert 0 < entry["products"][0]["drift_lines"] <= 20

    def test_large_drift_above_threshold(self, tmp_path):
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        template_content = "\n".join(f"line_{i}" for i in range(50)) + "\n"
        # Product changes EVERY line.
        product_content = "\n".join(f"changed_{i}" for i in range(50)) + "\n"
        _make_template_file(template_root, "backend/app/main.py", template_content)
        _make_product(products_dir, "alpha", {"backend/app/main.py": product_content})

        result = audit_drift(
            template_root=template_root,
            products_dir=products_dir,
            drift_threshold_lines=20,
        )
        entry = next(e for e in result["files"] if e["rel_path"] == "backend/app/main.py")
        assert entry["products"][0]["status"] == "large_drift"
        assert entry["products"][0]["drift_lines"] > 20

    def test_missing_when_file_absent_from_product(self, tmp_path):
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        _make_template_file(template_root, "backend/app/foo.py", "x = 1\n")
        # Product exists but doesn't have the file.
        (products_dir / "alpha").mkdir(parents=True)

        result = audit_drift(template_root=template_root, products_dir=products_dir)
        entry = next(e for e in result["files"] if e["rel_path"] == "backend/app/foo.py")
        assert entry["products"][0]["status"] == "missing"
        assert entry["products"][0]["drift_lines"] == -1

    def test_summary_counts_match_per_pair(self, tmp_path):
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        _make_template_file(template_root, "a.py", "same\n")
        _make_template_file(template_root, "b.py", "template\n")
        _make_product(products_dir, "alpha", {
            "a.py": "same\n",       # identical
            "b.py": "drifted\n",    # small_drift (1 line)
        })
        _make_product(products_dir, "beta", {
            "a.py": "same\n",       # identical
            # b.py absent → missing
        })

        result = audit_drift(template_root=template_root, products_dir=products_dir)
        s = result["summary"]
        assert s["files_audited"] == 2
        assert s["identical_count"] == 2
        assert s["small_drift_count"] == 1
        assert s["missing_count"] == 1
        assert s["large_drift_count"] == 0

    def test_missing_template_root_returns_error(self, tmp_path):
        result = audit_drift(
            template_root=tmp_path / "does_not_exist",
            products_dir=tmp_path,
        )
        assert "error" in result
        assert "template_root not found" in result["error"]
