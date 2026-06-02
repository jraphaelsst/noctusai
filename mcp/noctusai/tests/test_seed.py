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

from tools.noctus.seed._filewalk import (
    SKIP_DIR_NAMES,
    SKIP_FILENAMES,
    SKIP_FILE_SUFFIXES,
    walk_files,
)
from tools.noctus.seed.absorb_file import absorb_file
from tools.noctus.seed.audit_drift import audit_drift
from tools.noctus.seed.list_capabilities import list_capabilities
from tools.noctus.seed.report import report
from tools.noctus.seed.scan_fusions import (
    _parse_tool_file,
    _score_pair,
    scan_fusions,
)
from tools.noctus.seed.scan_optimizations import scan_optimizations
from tools.noctus.seed.scan_repetition import scan_repetition
from tools.noctus.seed.search_capabilities import search_capabilities
from tools.noctus.seed.specify_capability import specify_capability


# ─── _filewalk ─────────────────────────────────────────────────────────────


class TestWalkFiles:
    """Shared file-walk helper used by scan_repetition + audit_drift (and
    the future absorb_file). Pruning at directory level + extension /
    filename filters; tolerant on missing roots; honours per-call
    extra-skip overrides.
    """

    def test_yields_regular_files(self, tmp_path):
        (tmp_path / "a.py").write_text("x")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.txt").write_text("y")
        results = sorted(p.relative_to(tmp_path).as_posix() for p in walk_files(tmp_path))
        assert results == ["a.py", "sub/b.txt"]

    def test_prunes_default_skip_dirs(self, tmp_path):
        (tmp_path / "src" / "real.tsx").parent.mkdir(parents=True)
        (tmp_path / "src" / "real.tsx").write_text("ok")
        for skip in ("node_modules", "__pycache__", "dist", ".pytest_cache"):
            (tmp_path / skip).mkdir()
            (tmp_path / skip / "should-not-appear.tsx").write_text("noise")
        results = {p.relative_to(tmp_path).as_posix() for p in walk_files(tmp_path)}
        assert results == {"src/real.tsx"}

    def test_prunes_default_skip_filenames(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "package-lock.json").write_text("{}")
        (tmp_path / ".DS_Store").write_text("\x00")
        names = {p.name for p in walk_files(tmp_path)}
        assert names == {"package.json"}

    def test_prunes_default_skip_suffixes(self, tmp_path):
        (tmp_path / "main.py").write_text("ok")
        (tmp_path / "main.pyc").write_text("bytecode")
        (tmp_path / "img.png").write_text("\x89PNG")
        (tmp_path / "font.woff2").write_text("font-bytes")
        names = {p.name for p in walk_files(tmp_path)}
        assert names == {"main.py"}

    def test_extra_skip_dirs_extend_default(self, tmp_path):
        (tmp_path / "src" / "kept.ts").parent.mkdir(parents=True)
        (tmp_path / "src" / "kept.ts").write_text("ok")
        (tmp_path / "playwright-report").mkdir()
        (tmp_path / "playwright-report" / "noise.html").write_text("<>")
        defaults_only = list(walk_files(tmp_path))
        assert all("playwright-report" not in p.parts for p in defaults_only)
        extras = list(walk_files(tmp_path, extra_skip_dirs=frozenset({"src"})))
        names = {p.name for p in extras}
        assert "kept.ts" not in names

    def test_extra_skip_suffixes_extend_default(self, tmp_path):
        (tmp_path / "doc.md").write_text("# md")
        (tmp_path / "doc.txt").write_text("txt")
        baseline = {p.suffix for p in walk_files(tmp_path)}
        assert {".md", ".txt"} <= baseline
        filtered = {p.suffix for p in walk_files(tmp_path, extra_skip_suffixes=frozenset({".md"}))}
        assert ".md" not in filtered
        assert ".txt" in filtered

    def test_extra_skip_filenames_extend_default(self, tmp_path):
        (tmp_path / "keep.ts").write_text("ok")
        (tmp_path / "drop-me.ts").write_text("noise")
        names = {p.name for p in walk_files(tmp_path, extra_skip_filenames=frozenset({"drop-me.ts"}))}
        assert names == {"keep.ts"}

    def test_missing_root_yields_nothing_no_raise(self, tmp_path):
        results = list(walk_files(tmp_path / "does_not_exist"))
        assert results == []

    def test_root_is_a_file_yields_nothing_no_raise(self, tmp_path):
        f = tmp_path / "notadir.txt"
        f.write_text("ok")
        results = list(walk_files(f))
        assert results == []

    def test_default_constants_have_expected_shape(self):
        assert "node_modules" in SKIP_DIR_NAMES
        assert "__pycache__" in SKIP_DIR_NAMES
        assert "dist" in SKIP_DIR_NAMES
        assert ".png" in SKIP_FILE_SUFFIXES
        assert ".pyc" in SKIP_FILE_SUFFIXES
        assert "package-lock.json" in SKIP_FILENAMES


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


class TestSpecifyCapability:
    """Pure-data planner — picks the right layer based on the capability's
    shape flags, returns checklist + canonical-shape requirements. No file
    scaffolding (the agent does that with the output as a guide)."""

    def test_io_flag_forces_integrations_layer(self):
        result = specify_capability(
            "WhatsAppSender",
            description="Send messages via WAHA",
            needs_io=True,
        )
        assert result["suggested_layer"] == "integrations"
        assert "Protocol" in result["shape_requirements"][0]
        assert any("Fake" in r for r in result["shape_requirements"])
        assert any("Real" in r for r in result["shape_requirements"])
        assert any("factory" in r.lower() for r in result["shape_requirements"])
        # Reference doc surfaces in shape requirements.
        assert any("seed-fake-real-adapter" in r for r in result["shape_requirements"])

    def test_framework_hook_flag_forces_api_layer(self):
        result = specify_capability(
            "create_correlation_middleware",
            framework_hook=True,
        )
        assert result["suggested_layer"] == "api"
        assert any("dep" in r.lower() or "request time" in r.lower()
                   for r in result["shape_requirements"])

    def test_pure_logic_flag_suggests_primitives(self):
        result = specify_capability("format_brl_currency", pure_logic=True)
        assert result["suggested_layer"] == "primitives"
        assert any("No IO" in r for r in result["shape_requirements"])

    def test_test_only_flag_forces_testing_layer(self):
        result = specify_capability("FakeChatProvider", test_only=True)
        assert result["suggested_layer"] == "testing"

    def test_default_falls_back_to_domain(self):
        # No flags set → default layer is domain (cross-product business
        # logic with no IO or framework hook).
        result = specify_capability("compute_progress")
        assert result["suggested_layer"] == "domain"

    def test_io_takes_precedence_over_pure_logic(self):
        # When flags conflict, IO wins (the canonical shape requirement
        # is the most consequential).
        result = specify_capability("X", needs_io=True, pure_logic=True)
        assert result["suggested_layer"] == "integrations"

    def test_test_only_takes_precedence_over_io(self):
        # test_only is checked first because a test fixture even of an IO
        # adapter belongs in testing/, not integrations/.
        result = specify_capability("FakeWhatsApp", needs_io=True, test_only=True)
        assert result["suggested_layer"] == "testing"

    def test_import_path_template_includes_layer(self):
        result = specify_capability("foo", pure_logic=True)
        assert result["import_path_template"].startswith("noctusai_lib.primitives.")
        assert result["import_path_template"].endswith(".foo")

    def test_checklist_starts_with_cross_check(self):
        result = specify_capability("foo")
        # The first checklist item must direct the agent to list_capabilities
        # — the seed-first / no-duplication anchor.
        assert "list_capabilities" in result["checklist"][0]

    def test_cross_check_field_surfaces_separately(self):
        result = specify_capability("foo")
        assert "list_capabilities" in result["cross_check"]


class TestAbsorbFile:
    """`noctus.seed.absorb_file` lifts a duplicated file from products into
    seed; deletes other-product copies; optionally rewrites imports.
    Refuses on byte-divergence (would lose content) — safety contract.
    """

    def _setup_workspace(self, tmp_path):
        products_dir = tmp_path / "products"
        repo_root = tmp_path
        return products_dir, repo_root

    def test_happy_path_moves_and_deletes(self, tmp_path):
        products_dir, repo_root = self._setup_workspace(tmp_path)
        identical = "export const X = 1;\n"
        _make_product(products_dir, "alpha", {"frontend/src/components/ui/x.ts": identical})
        _make_product(products_dir, "beta", {"frontend/src/components/ui/x.ts": identical})
        _make_product(products_dir, "gamma", {"frontend/src/components/ui/x.ts": identical})

        result = absorb_file(
            "frontend/src/components/ui/x.ts",
            "seed/framework/frontend/src/components/ui/x.ts",
            products_dir=products_dir,
            repo_root=repo_root,
        )

        assert "error" not in result, result
        # Seed has the file.
        assert (repo_root / "seed/framework/frontend/src/components/ui/x.ts").read_text() == identical
        # Source product no longer has it.
        assert not (products_dir / "alpha" / "frontend/src/components/ui/x.ts").exists()
        # Other products no longer have it.
        assert not (products_dir / "beta" / "frontend/src/components/ui/x.ts").exists()
        assert not (products_dir / "gamma" / "frontend/src/components/ui/x.ts").exists()
        assert sorted(result["deleted_from"]) == ["beta", "gamma"]
        assert result["source_product"] == "alpha"

    def test_refuses_when_other_product_diverges(self, tmp_path):
        products_dir, repo_root = self._setup_workspace(tmp_path)
        _make_product(products_dir, "alpha", {"x.ts": "version A"})
        _make_product(products_dir, "beta", {"x.ts": "version B — drifted!"})

        result = absorb_file(
            "x.ts", "seed/framework/x.ts",
            products_dir=products_dir, repo_root=repo_root,
        )
        assert "error" in result
        assert "byte-identical" in result["error"]
        # Nothing changed on disk.
        assert (products_dir / "alpha" / "x.ts").exists()
        assert (products_dir / "beta" / "x.ts").exists()
        assert not (repo_root / "seed/framework/x.ts").exists()

    def test_refuses_when_seed_dest_exists_with_different_content(self, tmp_path):
        products_dir, repo_root = self._setup_workspace(tmp_path)
        _make_product(products_dir, "alpha", {"x.ts": "from product"})
        seed_dest = repo_root / "seed/framework/x.ts"
        seed_dest.parent.mkdir(parents=True)
        seed_dest.write_text("PRE-EXISTING DIFFERENT CONTENT")

        result = absorb_file(
            "x.ts", "seed/framework/x.ts",
            products_dir=products_dir, repo_root=repo_root,
        )
        assert "error" in result
        assert "different content" in result["error"]
        # Pre-existing seed file unchanged.
        assert seed_dest.read_text() == "PRE-EXISTING DIFFERENT CONTENT"
        # Source product still has the file.
        assert (products_dir / "alpha" / "x.ts").exists()

    def test_idempotent_when_seed_dest_already_identical(self, tmp_path):
        # When seed already has byte-identical content, the source is just
        # removed (no overwrite, no error) — supports re-running absorb_file.
        products_dir, repo_root = self._setup_workspace(tmp_path)
        identical = "shared\n"
        _make_product(products_dir, "alpha", {"x.ts": identical})
        seed_dest = repo_root / "seed/framework/x.ts"
        seed_dest.parent.mkdir(parents=True)
        seed_dest.write_text(identical)

        result = absorb_file(
            "x.ts", "seed/framework/x.ts",
            products_dir=products_dir, repo_root=repo_root,
        )
        assert "error" not in result, result
        assert seed_dest.read_text() == identical  # unchanged
        assert not (products_dir / "alpha" / "x.ts").exists()  # source removed

    def test_explicit_source_product_overrides_default(self, tmp_path):
        products_dir, repo_root = self._setup_workspace(tmp_path)
        identical = "x"
        _make_product(products_dir, "alpha", {"f.ts": identical})
        _make_product(products_dir, "beta", {"f.ts": identical})

        # Default would pick alphabetical first (alpha); override to beta.
        result = absorb_file(
            "f.ts", "seed/framework/f.ts",
            source_product="beta",
            products_dir=products_dir, repo_root=repo_root,
        )
        assert result["source_product"] == "beta"
        assert "alpha" in result["deleted_from"]

    def test_refuses_unknown_source_product(self, tmp_path):
        products_dir, repo_root = self._setup_workspace(tmp_path)
        _make_product(products_dir, "alpha", {"f.ts": "x"})
        result = absorb_file(
            "f.ts", "seed/framework/f.ts",
            source_product="ghost",
            products_dir=products_dir, repo_root=repo_root,
        )
        assert "error" in result
        assert "ghost" in result["error"]

    def test_refuses_when_no_product_has_file(self, tmp_path):
        products_dir, repo_root = self._setup_workspace(tmp_path)
        products_dir.mkdir()
        (products_dir / "alpha").mkdir()
        result = absorb_file(
            "missing.ts", "seed/framework/missing.ts",
            products_dir=products_dir, repo_root=repo_root,
        )
        assert "error" in result
        assert "no product has" in result["error"]

    def test_delete_other_products_false_keeps_copies(self, tmp_path):
        products_dir, repo_root = self._setup_workspace(tmp_path)
        identical = "x\n"
        _make_product(products_dir, "alpha", {"f.ts": identical})
        _make_product(products_dir, "beta", {"f.ts": identical})

        result = absorb_file(
            "f.ts", "seed/framework/f.ts",
            delete_other_products=False,
            products_dir=products_dir, repo_root=repo_root,
        )
        assert "error" not in result, result
        # Source moved out — but other product's copy stayed.
        assert not (products_dir / "alpha" / "f.ts").exists()
        assert (products_dir / "beta" / "f.ts").exists()
        assert result["deleted_from"] == []
        # next_steps surfaces the kept-copies caveat.
        assert any(
            "delete_other_products=False" in s for s in result["next_steps"]
        )

    def test_rewrite_imports_replaces_strings_in_source_files(self, tmp_path):
        products_dir, repo_root = self._setup_workspace(tmp_path)
        identical = "export const Y = 2;\n"
        _make_product(products_dir, "alpha", {
            "frontend/src/components/ui/y.ts": identical,
            "frontend/src/pages/Page.tsx": (
                "import { Y } from '@/components/ui/y';\n"
                "console.log(Y);\n"
            ),
        })
        _make_product(products_dir, "beta", {
            "frontend/src/components/ui/y.ts": identical,
            "frontend/src/main.tsx": (
                'import { Y } from "@/components/ui/y";\n'
                'export default Y;\n'
            ),
        })

        result = absorb_file(
            "frontend/src/components/ui/y.ts",
            "seed/framework/frontend/src/components/ui/y.ts",
            rewrite_imports=[("@/components/ui/y", "@noctusai/seed/components/ui/y")],
            products_dir=products_dir, repo_root=repo_root,
        )

        assert "error" not in result, result
        # Both products' source files were rewritten.
        page = (products_dir / "alpha/frontend/src/pages/Page.tsx").read_text()
        main = (products_dir / "beta/frontend/src/main.tsx").read_text()
        assert "@noctusai/seed/components/ui/y" in page
        assert "@noctusai/seed/components/ui/y" in main
        assert "@/components/ui/y" not in page
        assert "@/components/ui/y" not in main
        # imports_rewritten surfaces what changed.
        assert len(result["imports_rewritten"]) == 2

    def test_handles_single_product_no_others(self, tmp_path):
        # Edge case: only one product has the file. absorb_file should
        # still move it to seed (no other copies to compare/delete).
        products_dir, repo_root = self._setup_workspace(tmp_path)
        _make_product(products_dir, "alpha", {"f.ts": "x"})
        result = absorb_file(
            "f.ts", "seed/framework/f.ts",
            products_dir=products_dir, repo_root=repo_root,
        )
        assert "error" not in result, result
        assert result["source_product"] == "alpha"
        assert result["deleted_from"] == []
        assert (repo_root / "seed/framework/f.ts").exists()


class TestAbsorbFileRespectsTestSeam:
    """Hygiene regression guard — under tmp_path seam, absorb_file must
    NOT touch real REPO_ROOT files."""

    def test_no_real_seed_writes_under_tmp_seam(self, tmp_path):
        real_seed = REPO_ROOT / "seed" / "framework" / "frontend" / "src" / "components" / "ui"
        before = sorted(p.name for p in real_seed.iterdir()) if real_seed.is_dir() else []

        products_dir = tmp_path / "products"
        _make_product(products_dir, "alpha", {"frontend/src/components/ui/hygiene-probe.ts": "x"})
        absorb_file(
            "frontend/src/components/ui/hygiene-probe.ts",
            "seed/framework/frontend/src/components/ui/hygiene-probe.ts",
            products_dir=products_dir,
            repo_root=tmp_path,
        )

        after = sorted(p.name for p in real_seed.iterdir()) if real_seed.is_dir() else []
        assert before == after, (
            "absorb_file wrote to real seed dir under tmp_path seam — "
            f"leaked: {set(after) - set(before)}"
        )


class TestAuditDriftPlaceholderMasking:
    """When mask_placeholders=True (default), the template's mechanical
    placeholders are substituted with each product's resolved metadata
    BEFORE diffing. So files that ONLY differ in successful substitution
    don't surface as drift — placeholder noise no longer dominates the
    signal (Gamma's 2026-05-10 finding from the drift convergence report)."""

    def test_substituted_placeholders_count_as_identical(self, tmp_path):
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        # Template has ALL the mechanical placeholders.
        template_content = (
            "# {{PRODUCT_NAME}}\n"
            "Slug: {{PRODUCT_SLUG}}\n"
            "Schema: {{SCHEMA_NAME}}\n"
            "Backend port: {{BACKEND_PORT}}\n"
            "Frontend port: {{FRONTEND_PORT}}\n"
            "Icon: {{PRODUCT_ICON}}\n"
        )
        _make_template_file(template_root, "README.md", template_content)
        # Product has the substituted version (what scaffold's mechanical
        # pass would produce). Set up start.sh so metadata resolves.
        (tmp_path / "start.sh").write_text(
            '# BEGIN_PRODUCTS_REGISTRY\n'
            'PRODUCTS=(\n'
            '  "alpha-product:Alpha Product:8001:8101"\n'
            ')\n'
            '# END_PRODUCTS_REGISTRY\n'
        )
        product_content = (
            "# Alpha Product\n"
            "Slug: alpha-product\n"
            "Schema: alpha_product\n"
            "Backend port: 8001\n"
            "Frontend port: 8101\n"
            "Icon: Box\n"
        )
        _make_product(products_dir, "alpha-product", {"README.md": product_content})

        result = audit_drift(template_root=template_root, products_dir=products_dir)
        entry = next(e for e in result["files"] if e["rel_path"] == "README.md")
        assert entry["products"][0]["status"] == "identical", entry
        assert entry["products"][0]["drift_lines"] == 0

    def test_real_drift_still_surfaces_after_masking(self, tmp_path):
        # Same setup as above, but product has ONE extra real-content line
        # on top of the substituted placeholders.
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        template_content = "# {{PRODUCT_NAME}}\nSlug: {{PRODUCT_SLUG}}\n"
        _make_template_file(template_root, "README.md", template_content)
        (tmp_path / "start.sh").write_text(
            '# BEGIN_PRODUCTS_REGISTRY\n'
            'PRODUCTS=(\n'
            '  "alpha-product:Alpha Product:8001:8101"\n'
            ')\n'
            '# END_PRODUCTS_REGISTRY\n'
        )
        product_content = (
            "# Alpha Product\n"
            "Slug: alpha-product\n"
            "## Custom Section\n"  # ← real per-product addition
            "Some product-specific content here.\n"
        )
        _make_product(products_dir, "alpha-product", {"README.md": product_content})

        result = audit_drift(template_root=template_root, products_dir=products_dir)
        entry = next(e for e in result["files"] if e["rel_path"] == "README.md")
        assert entry["products"][0]["status"] == "small_drift"
        # Drift count reflects the 2 added lines, not the 2 substituted lines.
        assert entry["products"][0]["drift_lines"] == 2

    def test_mask_placeholders_false_disables_substitution(self, tmp_path):
        # With masking disabled, the substituted-but-otherwise-identical
        # product file shows as drift (raw diff).
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        template_content = "# {{PRODUCT_NAME}}\n"
        _make_template_file(template_root, "README.md", template_content)
        product_content = "# Alpha Product\n"
        _make_product(products_dir, "alpha-product", {"README.md": product_content})

        result = audit_drift(
            template_root=template_root,
            products_dir=products_dir,
            mask_placeholders=False,
        )
        entry = next(e for e in result["files"] if e["rel_path"] == "README.md")
        # Without masking, the 1-line difference is real drift.
        assert entry["products"][0]["status"] == "small_drift"
        assert entry["products"][0]["drift_lines"] == 2  # 1 line removed + 1 added

    def test_metadata_falls_back_when_start_sh_absent(self, tmp_path):
        # No start.sh — metadata derives from slug only. Substitution still
        # works for slug-only placeholders.
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        _make_template_file(template_root, "config.py", "schema = '{{SCHEMA_NAME}}'\n")
        _make_product(
            products_dir, "my-product",
            {"config.py": "schema = 'my_product'\n"},
        )

        result = audit_drift(template_root=template_root, products_dir=products_dir)
        entry = next(e for e in result["files"] if e["rel_path"] == "config.py")
        # SCHEMA_NAME defaults to slug.replace("-", "_"); substituted
        # template equals product file → identical.
        assert entry["products"][0]["status"] == "identical"


# ─── tailwind.config.factory.ts (TS source — text-asserted) ────────────────


from settings import REPO_ROOT  # noqa: E402  — imported here so earlier tests don't need it


_TAILWIND_FACTORY_PATH = (
    REPO_ROOT / "seed" / "framework" / "frontend" / "tailwind.config.factory.ts"
)


def _read_tailwind_factory() -> str:
    """Read the TS factory text or skip the test if the file is absent.

    The factory is a TypeScript source file, so we cannot import it from
    Python. We assert structural properties on the text instead. When the
    seed structure changes (file moved or renamed), the test skips
    gracefully rather than failing — the drift-tests catch staleness."""
    if not _TAILWIND_FACTORY_PATH.is_file():
        pytest.skip(
            f"tailwind.config.factory.ts not present at "
            f"{_TAILWIND_FACTORY_PATH} — seed factory not shipped yet"
        )
    return _TAILWIND_FACTORY_PATH.read_text(encoding="utf-8")


class TestTailwindConfigFactory:
    """Structural assertions on ``seed/framework/frontend/tailwind.config.factory.ts``.

    The factory is the canonical Tailwind config builder consumed by every
    product (`export default createTailwindConfig()`). These tests pin its
    public shape so removals / renames break loudly — rather than silently
    breaking every product's Tailwind build."""

    def test_default_content_includes_index_html(self):
        """The default content glob array MUST list ``./index.html``.

        Every product's Vite entry is ``index.html``; if Tailwind doesn't
        scan it, classes referenced from there get JIT-pruned. This is the
        most common silent breakage when refactoring the factory."""
        text = _read_tailwind_factory()
        # Locate DEFAULT_CONTENT array literal and assert ./index.html is in it.
        assert "DEFAULT_CONTENT" in text, "factory must export a DEFAULT_CONTENT array"
        assert '"./index.html"' in text, (
            'DEFAULT_CONTENT must include "./index.html" — every product '
            "Vite entry is index.html"
        )

    def test_factory_exports_create_tailwind_config(self):
        """The public function ``createTailwindConfig`` MUST be exported.

        Products import this by name from
        ``seed/framework/frontend/tailwind.config.factory``. Renaming or
        removing the export breaks every product's tailwind.config.ts."""
        text = _read_tailwind_factory()
        # Match either `export function createTailwindConfig` or
        # `export const createTailwindConfig =`. We don't pin the exact
        # signature shape — only the name + export-ness.
        has_export_fn = "export function createTailwindConfig" in text
        has_export_const = "export const createTailwindConfig" in text
        has_export_default_fn = "export default function createTailwindConfig" in text
        assert has_export_fn or has_export_const or has_export_default_fn, (
            "factory must export `createTailwindConfig` as a function or const"
        )

    def test_default_plugins_include_tailwindcss_animate(self):
        """The default plugins MUST include ``tailwindcss-animate``.

        Every product's design system relies on the animate plugin via
        shadcn/ui components. Dropping this default breaks animations
        platform-wide silently (no error — components just stop animating)."""
        text = _read_tailwind_factory()
        # Either CommonJS `require("tailwindcss-animate")` or ESM
        # `import animate from "tailwindcss-animate"` are valid shapes.
        has_require = 'require("tailwindcss-animate")' in text or "require('tailwindcss-animate')" in text
        has_import = 'from "tailwindcss-animate"' in text or "from 'tailwindcss-animate'" in text
        assert has_require or has_import, (
            "factory must reference `tailwindcss-animate` (the animate "
            "plugin every product relies on)"
        )

    def test_options_interface_accepts_extra_content_and_extra_plugins(self):
        """The ``createTailwindConfig`` options MUST expose ``extraContent``
        and ``extraPlugins`` — the two named seams products use to extend
        the factory without forking. Removing either forces products into a
        structural fork (own tailwind.config.ts not built on the factory)."""
        text = _read_tailwind_factory()
        assert "extraContent" in text, (
            "factory options must expose `extraContent` — the named seam "
            "products use to add their own scan globs"
        )
        assert "extraPlugins" in text, (
            "factory options must expose `extraPlugins` — the named seam "
            "products use to add their own Tailwind plugins"
        )

    def test_default_content_includes_seed_lib_glob(self):
        """The default content array MUST include the seed-lib design-system
        glob so classes used by shared components get scanned. Without this,
        every product would need to add the glob themselves — drift-prone."""
        text = _read_tailwind_factory()
        # The factory lives in seed/framework/frontend/, so the seed-lib
        # design-system folder is at "../../lib/frontend/src/**/*.{ts,tsx}".
        # We accept either a relative path with three `..` segments
        # (../../../seed/lib/...) — when consumed from a product's
        # frontend/ — or a two-`..` path when the factory paths are
        # already factory-relative.
        # To stay tolerant of either resolution scheme, just look for the
        # canonical fragment "seed/lib/frontend/src/**/*.{ts,tsx}" or, if
        # the factory uses factory-relative paths, "lib/frontend/src/**/*.{ts,tsx}".
        canonical = "seed/lib/frontend/src/**/*.{ts,tsx}"
        factory_relative = "lib/frontend/src/**/*.{ts,tsx}"
        assert canonical in text or factory_relative in text, (
            f"DEFAULT_CONTENT must include the seed-lib design-system glob "
            f"({canonical!r} or {factory_relative!r}); without it shared "
            f"component classes get JIT-pruned"
        )


# ─── report (rollup) ───────────────────────────────────────────────────────


class TestReport:
    """Rollup that cross-references scan_repetition + audit_drift into a
    prioritized triage queue. P0 = highest leverage (one absorb move
    closes both gaps); P5 = review intent only."""

    def test_p0_when_byte_identical_n3_and_template_drifts(self, tmp_path):
        """P0 — file byte_identical across N≥3 products AND template ships
        it with ≥1 product drifting. One move resolves duplication AND
        template-drift convergence."""
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        product_content = "shared = True\n"
        template_content = "shared = False\n"  # template drifts vs products
        _make_template_file(template_root, "backend/app/foo.py", template_content)
        _make_product(products_dir, "alpha", {"backend/app/foo.py": product_content})
        _make_product(products_dir, "beta", {"backend/app/foo.py": product_content})
        _make_product(products_dir, "gamma", {"backend/app/foo.py": product_content})

        result = report(template_root=template_root, products_dir=products_dir)
        item = next(it for it in result["items"] if it["rel_path"] == "backend/app/foo.py")
        assert item["priority"] == "P0"
        assert item["scan_classification"] == "byte_identical"
        assert item["scan_occurrences"] == 3
        assert item["in_template"] is True
        assert item["suggested_action"] == "absorb_and_push_template"
        assert item["suggested_destination"].startswith("seed/framework/")

    def test_p1_when_byte_identical_n3_and_no_template_match(self, tmp_path):
        """P1 — byte_identical N≥3 but file isn't tracked in template.
        Recurrence rule MUST formalize."""
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        identical = "x = 1\n"
        # Template root exists but doesn't ship this rel_path.
        _make_template_file(template_root, "unrelated.py", "noop\n")
        _make_product(products_dir, "alpha", {"shared.py": identical})
        _make_product(products_dir, "beta", {"shared.py": identical})
        _make_product(products_dir, "gamma", {"shared.py": identical})

        result = report(template_root=template_root, products_dir=products_dir)
        item = next(it for it in result["items"] if it["rel_path"] == "shared.py")
        assert item["priority"] == "P1"
        assert item["in_template"] is False
        assert item["suggested_action"] == "absorb_to_seed"

    def test_p2_when_byte_identical_n2(self, tmp_path):
        """P2 — N=2 byte_identical hits the recurrence rule's triage
        threshold (formalize / refactor / accept)."""
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        _make_template_file(template_root, "unrelated.py", "noop\n")
        same = "shared = 1\n"
        _make_product(products_dir, "alpha", {"helper.py": same})
        _make_product(products_dir, "beta", {"helper.py": same})

        result = report(template_root=template_root, products_dir=products_dir)
        item = next(it for it in result["items"] if it["rel_path"] == "helper.py")
        assert item["priority"] == "P2"
        assert item["scan_occurrences"] == 2
        assert item["suggested_action"] == "triage"

    def test_p3_when_near_identical(self, tmp_path):
        """P3 — near_identical means small per-product drift; reconcile
        before absorbing."""
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        _make_template_file(template_root, "unrelated.py", "noop\n")
        base = "\n".join(f"line_{i}" for i in range(50)) + "\n"
        _make_product(products_dir, "alpha", {"file.py": base + "# alpha\n"})
        _make_product(products_dir, "beta", {"file.py": base + "# beta\n"})

        result = report(template_root=template_root, products_dir=products_dir)
        item = next(it for it in result["items"] if it["rel_path"] == "file.py")
        assert item["priority"] == "P3"
        assert item["scan_classification"] == "near_identical"
        assert item["suggested_action"] == "converge_then_absorb"

    def test_p4_when_template_ships_but_product_missing(self, tmp_path):
        """P4 — template ships file, ≥1 product is missing it. Push the
        missing product to inherit (no scan signal because no duplication
        exists yet)."""
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        _make_template_file(template_root, "backend/app/required.py", "x = 1\n")
        # Two products: one HAS it, one doesn't.
        _make_product(products_dir, "alpha", {"backend/app/required.py": "x = 1\n"})
        (products_dir / "beta").mkdir(parents=True)

        result = report(template_root=template_root, products_dir=products_dir)
        item = next(
            it for it in result["items"] if it["rel_path"] == "backend/app/required.py"
        )
        assert item["priority"] == "P4"
        assert item["suggested_action"] == "scaffold_missing"
        # `beta` should show as missing; `alpha` as identical.
        statuses = item["drift_status_per_product"]
        assert statuses["beta"] == "missing"
        assert statuses["alpha"] == "identical"

    def test_p5_when_divergent_scan_or_large_drift(self, tmp_path):
        """P5 — divergent scan OR template large_drift. Likely intentional
        divergence; review and catalog."""
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        _make_template_file(template_root, "unrelated.py", "noop\n")
        # Divergent scan group (two products with totally different content).
        _make_product(products_dir, "alpha", {"div.py": "alpha\nspecific\nlogic\n"})
        _make_product(products_dir, "beta", {"div.py": "totally\ndifferent\ncode\n"})

        result = report(template_root=template_root, products_dir=products_dir)
        item = next(it for it in result["items"] if it["rel_path"] == "div.py")
        assert item["priority"] == "P5"
        assert item["scan_classification"] == "divergent"
        assert item["suggested_action"] == "review_intent"

    def test_items_sorted_priority_then_occurrences(self, tmp_path):
        """Output ordering: P0 first, then P1, ..., P5; within a band,
        higher occurrence count first."""
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        # P0: byte_identical N=3 + template drifts.
        _make_template_file(template_root, "p0.py", "template\n")
        _make_product(products_dir, "alpha", {"p0.py": "shared\n"})
        _make_product(products_dir, "beta", {"p0.py": "shared\n"})
        _make_product(products_dir, "gamma", {"p0.py": "shared\n"})
        # P2: byte_identical N=2.
        _make_product(products_dir, "alpha", {"p2.py": "two\n"})
        _make_product(products_dir, "beta", {"p2.py": "two\n"})

        result = report(template_root=template_root, products_dir=products_dir)
        priorities_in_order = [it["priority"] for it in result["items"]]
        # Find indices of p0 and p2 entries.
        p0_idx = next(i for i, it in enumerate(result["items"]) if it["rel_path"] == "p0.py")
        p2_idx = next(i for i, it in enumerate(result["items"]) if it["rel_path"] == "p2.py")
        assert p0_idx < p2_idx, (
            f"P0 must come before P2 in items list; got order {priorities_in_order}"
        )

    def test_skips_drift_only_files_with_no_action(self, tmp_path):
        """Files where audit_drift saw only `identical` or `small_drift`
        across every product — and no scan duplication — produce no
        actionable item; counted as `skipped_no_action` in summary."""
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        _make_template_file(template_root, "boring.py", "y = 1\n")
        _make_product(products_dir, "alpha", {"boring.py": "y = 1\n"})  # identical

        result = report(template_root=template_root, products_dir=products_dir)
        rel_paths = {it["rel_path"] for it in result["items"]}
        assert "boring.py" not in rel_paths
        assert result["summary"]["skipped_no_action"] >= 1

    def test_summary_counts_match_items(self, tmp_path):
        """summary[Pn_count] equals the number of items with that priority."""
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        _make_template_file(template_root, "unrelated.py", "noop\n")
        # Make one P1 (byte_identical N=3, no template).
        _make_product(products_dir, "alpha", {"a.py": "x\n"})
        _make_product(products_dir, "beta", {"a.py": "x\n"})
        _make_product(products_dir, "gamma", {"a.py": "x\n"})
        # Make one P2 (byte_identical N=2, no template).
        _make_product(products_dir, "alpha", {"b.py": "y\n"})
        _make_product(products_dir, "beta", {"b.py": "y\n"})

        result = report(template_root=template_root, products_dir=products_dir)
        s = result["summary"]
        # Cross-check: per-priority counts sum to total_items.
        per_priority_total = sum(s[f"P{i}_count"] for i in range(6))
        assert per_priority_total == s["total_items"]
        # The two synthetic groups land as P1 + P2.
        assert s["P1_count"] >= 1
        assert s["P2_count"] >= 1

    def test_max_items_caps_returned_list_but_not_summary(self, tmp_path):
        """`max_items` truncates the items list but summary counts still
        reflect the full result (so the caller can see what was capped)."""
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        _make_template_file(template_root, "unrelated.py", "noop\n")
        for n, slug in enumerate(["alpha", "beta", "gamma"]):
            _make_product(products_dir, slug, {
                f"f{i}.py": f"{i}\n" for i in range(5)
            })

        result = report(
            template_root=template_root, products_dir=products_dir, max_items=2,
        )
        assert len(result["items"]) == 2
        # Summary counts the FULL result (not just the cap).
        assert result["summary"]["total_items"] >= 2

    def test_propagates_scan_root_missing_error(self, tmp_path):
        """When scan_repetition can't find products_dir, surface the error
        rather than crashing."""
        result = report(
            template_root=tmp_path,
            products_dir=tmp_path / "does_not_exist",
        )
        assert "error" in result
        assert "products_dir not found" in result["error"]

    def test_propagates_template_root_missing_error(self, tmp_path):
        """When audit_drift can't find template_root, surface the error."""
        products_dir = tmp_path / "products"
        products_dir.mkdir()
        result = report(
            template_root=tmp_path / "no_template",
            products_dir=products_dir,
        )
        assert "error" in result
        assert "template_root not found" in result["error"]

    def test_upstream_summaries_round_trip(self, tmp_path):
        """`upstream` field exposes the raw summaries of both upstream
        tools so the caller can verify the rollup didn't drop signal."""
        template_root = tmp_path / "template"
        products_dir = tmp_path / "products"
        _make_template_file(template_root, "x.py", "x\n")
        _make_product(products_dir, "alpha", {"x.py": "x\n"})

        result = report(template_root=template_root, products_dir=products_dir)
        assert "scan_summary" in result["upstream"]
        assert "audit_summary" in result["upstream"]
        assert result["upstream"]["audit_summary"]["files_audited"] == 1


# ─── scan_fusions (meta-detector) ──────────────────────────────────────────


def _make_tool_file(
    tools_dir: Path,
    rel_path: str,
    *,
    tool_name: str,
    description: str,
    params: list[str],
    impl_returns_block: str = "",
    impl_function_name: str | None = None,
    extra_imports: list[str] | None = None,
) -> Path:
    """Synthesize a minimal tool .py file matching the FastMCP shape that
    scan_fusions parses. The decorated `_shim` delegates to a same-module
    impl whose docstring carries the Returns: block.
    """
    impl_name = impl_function_name or rel_path.replace("/", "_").rsplit(".", 1)[0]
    imports = "\n".join(extra_imports or [])
    params_signature = ", ".join(f"{p}=None" for p in params)
    params_passthrough = ", ".join(f"{p}={p}" for p in params)
    docstring = f'"""Impl.\n\n    Returns:\n{impl_returns_block}\n    """'
    source = f"""
{imports}


def {impl_name}({params_signature}) -> dict:
    {docstring}
    return {{}}


def register(server) -> None:
    @server.tool(
        name="{tool_name}",
        description=({description!r}),
    )
    def _shim({params_signature}) -> dict:
        return {impl_name}({params_passthrough})
"""
    target = tools_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.strip() + "\n", encoding="utf-8")
    return target


class TestScanFusionsParser:
    """The parser pulls tool name, params, return-keys, and description
    nouns out of every `.py` file under tools_dir."""

    def test_extracts_name_params_and_return_keys(self, tmp_path):
        path = _make_tool_file(
            tmp_path, "scan_foo.py",
            tool_name="noctus.demo.scan_foo",
            description="Find recurring blocks across products.",
            params=["min_count", "products_dir"],
            impl_returns_block="""\
        ``{
          "groups": [...],
          "rel_path": str,
          "summary": {...},
        }``""",
        )
        metas = _parse_tool_file(path)
        assert len(metas) == 1
        m = metas[0]
        assert m.name == "noctus.demo.scan_foo"
        assert m.namespace == "noctus.demo"
        assert m.params == frozenset({"min_count", "products_dir"})
        # `summary` is a generic key — should be filtered out.
        assert "summary" not in m.return_keys
        assert "groups" in m.return_keys
        assert "rel_path" in m.return_keys

    def test_classifies_read_only_vs_mutation(self, tmp_path):
        # Read-only tool: description has no mutation verbs.
        ro = _make_tool_file(
            tmp_path, "scan_ro.py",
            tool_name="noctus.demo.scan_ro",
            description="Find duplicated files. Read-only diagnostic.",
            params=["x"],
        )
        # Mutation tool: description says "moves" / "deletes".
        mu = _make_tool_file(
            tmp_path, "absorb_mu.py",
            tool_name="noctus.demo.absorb_mu",
            description="Moves files into seed. Deletes duplicate copies.",
            params=["x"],
        )
        ro_meta = _parse_tool_file(ro)[0]
        mu_meta = _parse_tool_file(mu)[0]
        assert ro_meta.is_read_only is True
        assert mu_meta.is_read_only is False

    def test_noun_in_description_does_not_trip_mutation_detector(self, tmp_path):
        """`absorption` (noun) does NOT match `absorbs` (verb). Word
        boundaries + verb-form list keep nouns from false-tripping."""
        path = _make_tool_file(
            tmp_path, "scan_absorption.py",
            tool_name="noctus.demo.scan_absorption",
            description="Surfaces candidates for seed absorption. Read-only.",
            params=["x"],
        )
        meta = _parse_tool_file(path)[0]
        assert meta.is_read_only is True, (
            "the noun 'absorption' must not match the verb pattern; only "
            "'absorbs' / 'absorbing' should classify a tool as mutation"
        )


class TestScanFusionsScoring:
    """Scoring blend rewards return-key overlap (canonical fusion shape),
    param overlap, and shared domain vocabulary; same-namespace adds a
    small fixed bonus."""

    def test_strong_pair_scores_high(self, tmp_path):
        # Two read-only tools in the same namespace, sharing return keys
        # AND parameters — should score well above 0.50.
        a = _make_tool_file(
            tmp_path, "scan_a.py",
            tool_name="noctus.demo.scan_a",
            description="Scan products for duplicates. Read-only.",
            params=["min_count", "products_dir"],
            impl_returns_block="""\
        ``{
          "rel_path": str,
          "scanned_products": [...],
          "groups": [...],
        }``""",
        )
        b = _make_tool_file(
            tmp_path, "scan_b.py",
            tool_name="noctus.demo.scan_b",
            description="Scan products for drift. Read-only.",
            params=["min_count", "products_dir"],
            impl_returns_block="""\
        ``{
          "rel_path": str,
          "scanned_products": [...],
          "files": [...],
        }``""",
        )
        meta_a = _parse_tool_file(a)[0]
        meta_b = _parse_tool_file(b)[0]
        score, signals = _score_pair(meta_a, meta_b)
        assert score > 0.5
        assert signals["same_namespace"] is True
        assert "rel_path" in signals["return_keys_intersection"]
        assert "scanned_products" in signals["return_keys_intersection"]
        assert "min_count" in signals["param_intersection"]

    def test_weak_pair_scores_low(self, tmp_path):
        """Different namespaces, no shared params, no shared keys, no
        shared vocab → near-zero score."""
        a = _make_tool_file(
            tmp_path, "scan_a.py",
            tool_name="noctus.demo.scan_a",
            description="Apple banana cherry.",
            params=["alpha"],
        )
        b = _make_tool_file(
            tmp_path, "build_b.py",
            tool_name="noctus.other.build_b",
            description="Xenon yttrium zirconium.",
            params=["omega"],
        )
        meta_a = _parse_tool_file(a)[0]
        meta_b = _parse_tool_file(b)[0]
        score, _ = _score_pair(meta_a, meta_b)
        assert score < 0.10


class TestScanFusionsIntegration:
    """End-to-end through `scan_fusions` against synthetic tool trees."""

    def test_returns_pair_above_threshold(self, tmp_path):
        _make_tool_file(
            tmp_path, "scan_a.py",
            tool_name="noctus.demo.scan_a",
            description="Scan products for duplicates. Read-only.",
            params=["min_count", "products_dir"],
            impl_returns_block='        ``{"rel_path": str, "groups": [...]}``',
        )
        _make_tool_file(
            tmp_path, "scan_b.py",
            tool_name="noctus.demo.scan_b",
            description="Scan products for drift. Read-only.",
            params=["min_count", "products_dir"],
            impl_returns_block='        ``{"rel_path": str, "files": [...]}``',
        )
        result = scan_fusions(tools_dir=tmp_path, min_score=0.30)
        names = {(p["tool_a"], p["tool_b"]) for p in result["pairs"]}
        assert ("noctus.demo.scan_a", "noctus.demo.scan_b") in names

    def test_namespace_filter_isolates_a_namespace(self, tmp_path):
        _make_tool_file(
            tmp_path, "a.py",
            tool_name="noctus.demo.scan_a",
            description="Read-only scan products.",
            params=["x"],
        )
        _make_tool_file(
            tmp_path, "b.py",
            tool_name="noctus.demo.scan_b",
            description="Read-only scan products.",
            params=["x"],
        )
        _make_tool_file(
            tmp_path, "c.py",
            tool_name="noctus.other.scan_c",
            description="Read-only scan products.",
            params=["x"],
        )
        result = scan_fusions(
            tools_dir=tmp_path, min_score=0.0, namespace_filter="noctus.demo",
        )
        for pair in result["pairs"]:
            assert pair["tool_a"].startswith("noctus.demo.")
            assert pair["tool_b"].startswith("noctus.demo.")

    def test_require_both_read_only_filter(self, tmp_path):
        # One read-only, one mutation. With the filter on (default), the
        # pair shouldn't surface; with it off, it should.
        _make_tool_file(
            tmp_path, "ro.py",
            tool_name="noctus.demo.scan_ro",
            description="Read-only scan products.",
            params=["x"],
        )
        _make_tool_file(
            tmp_path, "mu.py",
            tool_name="noctus.demo.absorb_mu",
            description="Moves files into seed. Deletes copies.",
            params=["x"],
        )
        ro_only = scan_fusions(
            tools_dir=tmp_path, min_score=0.0, require_both_read_only=True,
        )
        all_pairs = scan_fusions(
            tools_dir=tmp_path, min_score=0.0, require_both_read_only=False,
        )
        assert len(all_pairs["pairs"]) >= len(ro_only["pairs"])
        # The mutation pair MUST be absent in the read-only-only result.
        ro_pair_names = {(p["tool_a"], p["tool_b"]) for p in ro_only["pairs"]}
        assert ("noctus.demo.absorb_mu", "noctus.demo.scan_ro") not in ro_pair_names
        assert ("noctus.demo.scan_ro", "noctus.demo.absorb_mu") not in ro_pair_names

    def test_filters_existing_fusion_when_one_imports_other(self, tmp_path):
        _make_tool_file(
            tmp_path, "scan_a.py",
            tool_name="noctus.demo.scan_a",
            description="Read-only scan products.",
            params=["x"],
        )
        # Tool B imports A's module — that's an existing fusion.
        _make_tool_file(
            tmp_path, "scan_b.py",
            tool_name="noctus.demo.scan_b",
            description="Read-only scan products.",
            params=["x"],
            extra_imports=["from . import scan_a"],
        )
        result = scan_fusions(tools_dir=tmp_path, min_score=0.0)
        names = {(p["tool_a"], p["tool_b"]) for p in result["pairs"]}
        assert ("noctus.demo.scan_a", "noctus.demo.scan_b") not in names
        assert ("noctus.demo.scan_b", "noctus.demo.scan_a") not in names
        assert result["summary"]["existing_fusions_skipped"] >= 1

    def test_filters_existing_fusion_when_third_tool_jointly_imports(self, tmp_path):
        # A and B don't import each other, but C imports both — completed
        # fusion. The pair (A, B) shouldn't surface as a new opportunity.
        _make_tool_file(
            tmp_path, "scan_a.py",
            tool_name="noctus.demo.scan_a",
            description="Read-only scan products.",
            params=["x"],
        )
        _make_tool_file(
            tmp_path, "scan_b.py",
            tool_name="noctus.demo.scan_b",
            description="Read-only scan products.",
            params=["x"],
        )
        _make_tool_file(
            tmp_path, "rollup_c.py",
            tool_name="noctus.demo.rollup_c",
            description="Compose a + b. Read-only.",
            params=["x"],
            extra_imports=[
                "from . import scan_a",
                "from . import scan_b",
            ],
        )
        result = scan_fusions(tools_dir=tmp_path, min_score=0.0)
        names = {frozenset({p["tool_a"], p["tool_b"]}) for p in result["pairs"]}
        assert frozenset({"noctus.demo.scan_a", "noctus.demo.scan_b"}) not in names

    def test_missing_tools_dir_returns_empty_no_raise(self, tmp_path):
        result = scan_fusions(tools_dir=tmp_path / "does_not_exist", min_score=0.0)
        assert result["scanned_files"] == 0
        assert result["tools_indexed"] == 0
        assert result["pairs"] == []

    def test_max_pairs_caps_returned_list(self, tmp_path):
        # Generate enough synthetic tools that there are >5 pairs above
        # threshold, then cap at 3.
        for i in range(5):
            _make_tool_file(
                tmp_path, f"scan_{i}.py",
                tool_name=f"noctus.demo.scan_{i}",
                description="Read-only scan products.",
                params=["min_count", "products_dir"],
                impl_returns_block='        ``{"rel_path": str, "groups": [...]}``',
            )
        result = scan_fusions(tools_dir=tmp_path, min_score=0.0, max_pairs=3)
        assert len(result["pairs"]) <= 3
        assert result["summary"]["pairs_above_threshold"] >= 3

    def test_summary_score_distribution_bucketed(self, tmp_path):
        for i in range(3):
            _make_tool_file(
                tmp_path, f"scan_{i}.py",
                tool_name=f"noctus.demo.scan_{i}",
                description="Read-only scan products.",
                params=["min_count"],
            )
        result = scan_fusions(tools_dir=tmp_path, min_score=0.0)
        # Distribution buckets are strings of form "0.30-0.40".
        for k in result["summary"]["score_distribution"]:
            assert "-" in k
            lo, hi = k.split("-")
            float(lo); float(hi)


class TestScanFusionsLiveTree:
    """Smoke test against the actual mcp/noctusai/tools/noctus tree.
    Confirms the parser handles the live shapes without errors and that
    well-known fusion candidates surface with sane signals."""

    def test_live_tree_parses_without_error(self):
        result = scan_fusions(min_score=0.0, max_pairs=200)
        assert result["scanned_files"] > 0
        assert result["tools_indexed"] > 0
        assert isinstance(result["pairs"], list)

    def test_canonical_pair_filtered_as_existing_fusion(self):
        """`scan_repetition` + `audit_drift` ARE the canonical fusion (already
        composed by `report`). Should be filtered out of the candidates list."""
        result = scan_fusions(min_score=0.0, max_pairs=2000)
        names = {frozenset({p["tool_a"], p["tool_b"]}) for p in result["pairs"]}
        assert frozenset({
            "noctus.seed.scan_repetition", "noctus.seed.audit_drift",
        }) not in names
        # And the existing-fusion counter saw at least the report-comprises
        # — so the filter is firing.
        assert result["summary"]["existing_fusions_skipped"] > 0


class TestScanFusionsScope:
    """`scope` switches the detection axis: cross_file (default) finds
    rollup-compose candidates; same_file finds subsume/merge candidates;
    all returns both. Each pair carries a loc_estimate distinguishing
    COMPOSE (no LoC savings) from SUBSUME (real merge savings)."""

    def test_default_scope_is_cross_file(self, tmp_path):
        # Two tools in different files — should surface in default scope.
        _make_tool_file(
            tmp_path, "a.py",
            tool_name="noctus.demo.scan_a",
            description="Read-only scan products.",
            params=["min_count"],
            impl_returns_block='        ``{"rel_path": str, "groups": [...]}``',
        )
        _make_tool_file(
            tmp_path, "b.py",
            tool_name="noctus.demo.scan_b",
            description="Read-only scan products.",
            params=["min_count"],
            impl_returns_block='        ``{"rel_path": str, "files": [...]}``',
        )
        result = scan_fusions(tools_dir=tmp_path, min_score=0.30)
        assert result["summary"]["scope"] == "cross_file"
        names = {(p["tool_a"], p["tool_b"]) for p in result["pairs"]}
        assert ("noctus.demo.scan_a", "noctus.demo.scan_b") in names

    def test_same_file_scope_returns_intra_file_pairs(self, tmp_path):
        """Two tools in ONE file — invisible in cross_file scope, visible
        in same_file scope, classified as `subsume` regime with
        nonzero LoC savings."""
        # Synthesize a file with two @server.tool decorators.
        path = tmp_path / "twin.py"
        path.write_text(
            'def impl_a(min_count=None) -> dict:\n'
            '    """Impl A.\n\n    Returns:\n        ``{"rel_path": str, "groups": [...]}``\n    """\n'
            '    return {}\n'
            '\n'
            'def impl_b(min_count=None) -> dict:\n'
            '    """Impl B.\n\n    Returns:\n        ``{"rel_path": str, "files": [...]}``\n    """\n'
            '    return {}\n'
            '\n'
            'def register(server) -> None:\n'
            '    @server.tool(name="noctus.demo.scan_a", description="Read-only scan products.")\n'
            '    def _shim_a(min_count=None) -> dict:\n'
            '        return impl_a(min_count=min_count)\n'
            '    @server.tool(name="noctus.demo.scan_b", description="Read-only scan products.")\n'
            '    def _shim_b(min_count=None) -> dict:\n'
            '        return impl_b(min_count=min_count)\n'
        )
        cross = scan_fusions(tools_dir=tmp_path, min_score=0.0, scope="cross_file")
        same = scan_fusions(tools_dir=tmp_path, min_score=0.0, scope="same_file")

        # Cross-file scope: no candidates (both in same file).
        cross_names = {frozenset({p["tool_a"], p["tool_b"]}) for p in cross["pairs"]}
        assert frozenset({"noctus.demo.scan_a", "noctus.demo.scan_b"}) not in cross_names

        # Same-file scope: pair surfaces, classified as subsume.
        same_names = {frozenset({p["tool_a"], p["tool_b"]}) for p in same["pairs"]}
        assert frozenset({"noctus.demo.scan_a", "noctus.demo.scan_b"}) in same_names
        pair = next(p for p in same["pairs"]
                    if frozenset({p["tool_a"], p["tool_b"]}) == frozenset({"noctus.demo.scan_a", "noctus.demo.scan_b"}))
        assert pair["same_file"] is True
        assert pair["loc_estimate"]["merge_kind"] == "subsume"

    def test_all_scope_returns_both_axes(self, tmp_path):
        # File 1: two tools (intra-file pair).
        path = tmp_path / "twin.py"
        path.write_text(
            'def impl_a(x=None) -> dict:\n'
            '    """A.\n\n    Returns:\n        ``{"rel_path": str}``\n    """\n'
            '    return {}\n'
            'def impl_b(x=None) -> dict:\n'
            '    """B.\n\n    Returns:\n        ``{"rel_path": str}``\n    """\n'
            '    return {}\n'
            'def register(server) -> None:\n'
            '    @server.tool(name="noctus.demo.scan_a", description="Read-only scan products.")\n'
            '    def _a(x=None) -> dict:\n'
            '        return impl_a(x=x)\n'
            '    @server.tool(name="noctus.demo.scan_b", description="Read-only scan products.")\n'
            '    def _b(x=None) -> dict:\n'
            '        return impl_b(x=x)\n'
        )
        # File 2: a third tool in a different file (cross-file pair with each).
        _make_tool_file(
            tmp_path, "c.py",
            tool_name="noctus.demo.scan_c",
            description="Read-only scan products.",
            params=["x"],
            impl_returns_block='        ``{"rel_path": str}``',
        )
        result = scan_fusions(tools_dir=tmp_path, min_score=0.0, scope="all")
        same_file_pairs = [p for p in result["pairs"] if p["same_file"]]
        cross_file_pairs = [p for p in result["pairs"] if not p["same_file"]]
        assert same_file_pairs, "all scope must include intra-file pairs"
        assert cross_file_pairs, "all scope must include cross-file pairs"

    def test_loc_estimate_compose_vs_subsume(self, tmp_path):
        """A weak cross-file pair should land in COMPOSE regime (savings=0);
        a strong same-file pair should land in SUBSUME (savings>0)."""
        # Strong same-file pair.
        path = tmp_path / "twin.py"
        path.write_text(
            'def impl_a(min_count=None, products_dir=None) -> dict:\n'
            '    """A.\n\n    Returns:\n        ``{"rel_path": str, "groups": [...], "scanned_products": []}``\n    """\n'
            '    x = 1\n    y = 2\n    z = 3\n    return {}\n'
            'def impl_b(min_count=None, products_dir=None) -> dict:\n'
            '    """B.\n\n    Returns:\n        ``{"rel_path": str, "groups": [...], "scanned_products": []}``\n    """\n'
            '    x = 1\n    y = 2\n    z = 3\n    return {}\n'
            'def register(server) -> None:\n'
            '    @server.tool(name="noctus.demo.scan_a", description="Read-only scan products.")\n'
            '    def _a(min_count=None, products_dir=None) -> dict:\n'
            '        return impl_a(min_count=min_count, products_dir=products_dir)\n'
            '    @server.tool(name="noctus.demo.scan_b", description="Read-only scan products.")\n'
            '    def _b(min_count=None, products_dir=None) -> dict:\n'
            '        return impl_b(min_count=min_count, products_dir=products_dir)\n'
        )
        result = scan_fusions(tools_dir=tmp_path, min_score=0.0, scope="same_file")
        pair = next(p for p in result["pairs"]
                    if frozenset({p["tool_a"], p["tool_b"]}) == frozenset({"noctus.demo.scan_a", "noctus.demo.scan_b"}))
        assert pair["loc_estimate"]["merge_kind"] == "subsume"
        assert pair["loc_estimate"]["estimated_savings_loc"] > 0
        assert pair["loc_estimate"]["a_impl_loc"] >= 1
        assert pair["loc_estimate"]["b_impl_loc"] >= 1

    def test_summary_carries_savings_aggregates(self, tmp_path):
        path = tmp_path / "twin.py"
        path.write_text(
            'def impl_a(x=None) -> dict:\n'
            '    """A.\n\n    Returns:\n        ``{"rel_path": str}``\n    """\n'
            '    return {}\n'
            'def impl_b(x=None) -> dict:\n'
            '    """B.\n\n    Returns:\n        ``{"rel_path": str}``\n    """\n'
            '    return {}\n'
            'def register(server) -> None:\n'
            '    @server.tool(name="noctus.demo.scan_a", description="Read-only scan products.")\n'
            '    def _a(x=None) -> dict:\n'
            '        return impl_a(x=x)\n'
            '    @server.tool(name="noctus.demo.scan_b", description="Read-only scan products.")\n'
            '    def _b(x=None) -> dict:\n'
            '        return impl_b(x=x)\n'
        )
        result = scan_fusions(tools_dir=tmp_path, min_score=0.0, scope="same_file")
        s = result["summary"]
        assert "estimated_savings_loc_total" in s
        assert "subsume_candidates_count" in s
        assert "compose_candidates_count" in s
        assert s["subsume_candidates_count"] >= 1

    def test_invalid_scope_returns_error(self, tmp_path):
        result = scan_fusions(tools_dir=tmp_path, scope="bogus")
        assert "error" in result["summary"]
        assert "invalid scope" in result["summary"]["error"]
        assert result["pairs"] == []


# ─── scan_optimizations (trio: optimization scope) ─────────────────────────


def _write_py(tmp_path: Path, rel: str, source: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(source, encoding="utf-8")
    return p


class TestScanOptimizationsDeadFunction:
    """`dead_function` flags module-level defs with NO in-file references
    AND no cross-file references in the scanned tree."""

    def test_flags_truly_unreferenced_function(self, tmp_path):
        _write_py(tmp_path, "lone.py", '''
def _used() -> int:
    return 1

def _orphan_helper_with_some_body() -> int:
    """Vestigial — not called."""
    a = 1
    b = 2
    return a + b

x = _used()
''')
        result = scan_optimizations(tools_dir=tmp_path, min_severity="info")
        names = [f["name"] for f in result["findings"] if f["detector"] == "dead_function"]
        assert "_orphan_helper_with_some_body" in names
        assert "_used" not in names

    def test_skips_function_referenced_in_sibling_file(self, tmp_path):
        # File A defines walk_files; File B imports it. walk_files must
        # NOT be flagged dead even though file A has no in-file callers.
        _write_py(tmp_path, "_filewalk.py", '''
def walk_files(root):
    """Used by sibling modules."""
    return []
''')
        _write_py(tmp_path, "scan.py", '''
from ._filewalk import walk_files

def find_stuff():
    return walk_files(".")
''')
        result = scan_optimizations(tools_dir=tmp_path, min_severity="info")
        names = [f["name"] for f in result["findings"] if f["detector"] == "dead_function"]
        assert "walk_files" not in names, (
            "cross-file imports must prevent the dead_function false positive"
        )

    def test_skips_framework_dispatched_names(self, tmp_path):
        # `register` is in _FRAMEWORK_NAMES — never flagged dead even
        # without callers in the scanned tree.
        _write_py(tmp_path, "tool.py", '''
def register(server):
    pass
''')
        result = scan_optimizations(tools_dir=tmp_path, min_severity="info")
        names = [f["name"] for f in result["findings"] if f["detector"] == "dead_function"]
        assert "register" not in names

    def test_skips_decorated_functions(self, tmp_path):
        # Decorated functions are presumed used by their decorator
        # framework (e.g. @app.get('/foo')).
        _write_py(tmp_path, "tool.py", '''
def server():
    pass

@server.tool(name="foo")
def _shim_with_no_callers():
    return None
''')
        result = scan_optimizations(tools_dir=tmp_path, min_severity="info")
        names = [f["name"] for f in result["findings"] if f["detector"] == "dead_function"]
        assert "_shim_with_no_callers" not in names


class TestScanOptimizationsSingleCallHelper:
    """`single_call_helper` flags private functions called once and small
    enough that inlining helps."""

    def test_flags_small_single_call_private(self, tmp_path):
        _write_py(tmp_path, "x.py", '''
def _helper():
    a = 1
    b = 2
    return a + b

def use():
    return _helper()
''')
        result = scan_optimizations(tools_dir=tmp_path, min_severity="info")
        names = [f["name"] for f in result["findings"] if f["detector"] == "single_call_helper"]
        assert "_helper" in names

    def test_skips_large_helper_above_25_loc(self, tmp_path):
        # A 30-LoC helper carries cognitive value even with one caller.
        body = "\n".join(f"    line_{i} = {i}" for i in range(30))
        _write_py(tmp_path, "x.py", f'''
def _big_helper():
{body}
    return line_29

def use():
    return _big_helper()
''')
        result = scan_optimizations(tools_dir=tmp_path, min_severity="info")
        names = [f["name"] for f in result["findings"] if f["detector"] == "single_call_helper"]
        assert "_big_helper" not in names

    def test_does_not_flag_public_function(self, tmp_path):
        # Public (no leading underscore) functions might be exported.
        # The single_call_helper detector only targets `_*` privates.
        _write_py(tmp_path, "x.py", '''
def public_helper():
    a = 1
    return a + 1

def use():
    return public_helper()
''')
        result = scan_optimizations(tools_dir=tmp_path, min_severity="info")
        names = [f["name"] for f in result["findings"] if f["detector"] == "single_call_helper"]
        assert "public_helper" not in names

    def test_does_not_flag_multi_call_helper(self, tmp_path):
        _write_py(tmp_path, "x.py", '''
def _shared():
    return 42

def a():
    return _shared()

def b():
    return _shared()
''')
        result = scan_optimizations(tools_dir=tmp_path, min_severity="info")
        names = [f["name"] for f in result["findings"] if f["detector"] == "single_call_helper"]
        assert "_shared" not in names


class TestScanOptimizationsWrapperOnly:
    """`wrapper_only` flags functions whose entire body is a passthrough
    `return inner(*params)` without transforming args or return."""

    def test_flags_pure_passthrough(self, tmp_path):
        _write_py(tmp_path, "x.py", '''
def inner(a, b):
    return a + b

def wrapper(a, b):
    return inner(a, b)

def use():
    return wrapper(1, 2)
''')
        result = scan_optimizations(tools_dir=tmp_path, min_severity="info")
        names = [f["name"] for f in result["findings"] if f["detector"] == "wrapper_only"]
        assert "wrapper" in names

    def test_does_not_flag_function_with_logic(self, tmp_path):
        _write_py(tmp_path, "x.py", '''
def inner(a, b):
    return a + b

def transformer(a, b):
    if a < 0:
        a = 0
    return inner(a, b)

def use():
    return transformer(1, 2)
''')
        result = scan_optimizations(tools_dir=tmp_path, min_severity="info")
        names = [f["name"] for f in result["findings"] if f["detector"] == "wrapper_only"]
        assert "transformer" not in names


class TestScanOptimizationsAPI:
    """API-level: include_detectors / min_severity / max_findings caps,
    invalid input handling."""

    def test_include_detectors_runs_only_requested(self, tmp_path):
        _write_py(tmp_path, "x.py", '''
def _orphan():
    a = 1
    b = 2
    return a + b
''')
        result = scan_optimizations(
            tools_dir=tmp_path,
            include_detectors=["wrapper_only"],
            min_severity="info",
        )
        # No wrapper_only findings in this file, so empty; but no errors.
        for f in result["findings"]:
            assert f["detector"] == "wrapper_only"

    def test_invalid_detector_returns_error(self, tmp_path):
        result = scan_optimizations(
            tools_dir=tmp_path,
            include_detectors=["bogus_detector"],
        )
        assert "error" in result["summary"]
        assert "unknown detector" in result["summary"]["error"]

    def test_invalid_min_severity_returns_error(self, tmp_path):
        result = scan_optimizations(
            tools_dir=tmp_path,
            min_severity="bogus_level",
        )
        assert "error" in result["summary"]
        assert "invalid min_severity" in result["summary"]["error"]

    def test_min_severity_filters_lower_levels(self, tmp_path):
        # Single-call helper ≤ 10 LoC produces a warning-level finding.
        _write_py(tmp_path, "x.py", '''
def _small():
    a = 1
    return a + 1

def use():
    return _small()
''')
        warning_only = scan_optimizations(tools_dir=tmp_path, min_severity="warning")
        info_or_above = scan_optimizations(tools_dir=tmp_path, min_severity="info")
        # info threshold returns ≥ what warning threshold returns.
        assert len(info_or_above["findings"]) >= len(warning_only["findings"])

    def test_max_findings_caps_returned_list(self, tmp_path):
        for i in range(5):
            _write_py(tmp_path, f"x{i}.py", f'''
def _h{i}():
    a = 1
    return a + 1

def use{i}():
    return _h{i}()
''')
        result = scan_optimizations(tools_dir=tmp_path, max_findings=2)
        assert len(result["findings"]) == 2
        # Summary counts the FULL pre-cap result.
        assert result["summary"]["total_findings"] >= 2

    def test_summary_aggregates_match_findings(self, tmp_path):
        _write_py(tmp_path, "x.py", '''
def _orphan_a():
    a = 1
    return a + 1

def _orphan_b():
    a = 1
    return a + 1
''')
        result = scan_optimizations(tools_dir=tmp_path, min_severity="info")
        # by_detector counts must sum to total_findings.
        s = result["summary"]
        assert sum(s["by_detector"].values()) == s["total_findings"]
        assert sum(s["by_severity"].values()) == s["total_findings"]


class TestScanOptimizationsLiveTree:
    """Smoke test against the live mcp/noctusai/tools/noctus tree."""

    def test_live_tree_runs_without_error(self):
        result = scan_optimizations(min_severity="warning", max_findings=10)
        assert result["scanned_files"] > 0
        # Some by_detector keys must be present (any) but total may be 0
        # — both are acceptable.
        assert isinstance(result["findings"], list)
        assert "estimated_savings_loc_total" in result["summary"]


# ─── search_capabilities ───────────────────────────────────────────────────


def _synthetic_repo(tmp_path: Path) -> Path:
    """Build a minimal synthetic repo tree (lib + framework) for test seam."""
    lib_root = tmp_path / "seed" / "lib" / "backend" / "noctusai_lib"
    fw_root = tmp_path / "seed" / "framework" / "backend" / "noctusai_seed"

    # integrations layer — youtube-like module
    (lib_root / "integrations" / "youtube").mkdir(parents=True)
    (lib_root / "integrations" / "youtube" / "protocol.py").write_text(
        '"""YouTube integration module."""\n\n'
        "class YoutubeClient:\n"
        '    """YouTube Data API v3 client contract."""\n'
        "    pass\n",
        encoding="utf-8",
    )
    (lib_root / "integrations" / "youtube" / "factory.py").write_text(
        '"""Factory for YoutubeClient."""\n\n'
        "def make_youtube_client():\n"
        '    """Create a configured YoutubeClient."""\n'
        "    pass\n",
        encoding="utf-8",
    )

    # domain layer — helper
    (lib_root / "domain" / "helpers").mkdir(parents=True)
    (lib_root / "domain" / "helpers" / "text.py").write_text(
        '"""Text utilities."""\n\n'
        "def truncate(text: str, limit: int = 100) -> str:\n"
        '    """Truncate a string to limit characters."""\n'
        "    return text[:limit]\n",
        encoding="utf-8",
    )

    # framework module
    fw_root.mkdir(parents=True)
    (fw_root / "app.py").write_text(
        '"""App factory."""\n\n'
        "def create_product_app(name: str) -> object:\n"
        '    """Create a product FastAPI application."""\n'
        "    pass\n",
        encoding="utf-8",
    )

    return tmp_path


def _synthetic_tools(tmp_path: Path) -> Path:
    """Build a minimal synthetic tools dir with two fake MCP tools."""
    tools_dir = tmp_path / "tools" / "noctus" / "dev"
    tools_dir.mkdir(parents=True)

    (tools_dir / "task_branch.py").write_text(
        '"""noctus.dev.task_branch tool."""\n\n'
        "def task_branch(action: str, branch: str = \"\") -> dict:\n"
        '    """Start or finish a task branch in the repository.\n\n'
        "    Returns:\n"
        '        ``{"branch": str, "worktree": str}``\n'
        '    """\n'
        "    return {}\n\n"
        "def register(server) -> None:\n"
        "    @server.tool(\n"
        '        name="noctus.dev.task_branch",\n'
        '        description="Start or finish a task branch in the repository.",\n'
        "    )\n"
        "    def _shim(action: str, branch: str = \"\") -> dict:\n"
        "        return task_branch(action=action, branch=branch)\n",
        encoding="utf-8",
    )
    (tools_dir / "kb_search.py").write_text(
        '"""noctus.dev.kb_search tool."""\n\n'
        "def kb_search(query: str, limit: int = 10) -> dict:\n"
        '    """Search knowledge base articles by keyword.\n\n'
        "    Returns:\n"
        '        ``{"results": [...], "total": int}``\n'
        '    """\n'
        "    return {}\n\n"
        "def register(server) -> None:\n"
        "    @server.tool(\n"
        '        name="noctus.dev.kb_search",\n'
        '        description="Search knowledge base articles by keyword.",\n'
        "    )\n"
        "    def _shim(query: str, limit: int = 10) -> dict:\n"
        "        return kb_search(query=query, limit=limit)\n",
        encoding="utf-8",
    )

    return tmp_path / "tools"


class TestSearchCapabilitiesSearch:
    """Mode=search over synthetic seams — no real-repo writes."""

    def test_search_returns_lib_hits(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        result = search_capabilities(query="youtube", surface="lib", repo_root=repo)
        assert result["mode"] == "search"
        assert result["total_matched"] >= 2
        names = [r["import_path"] for r in result["results"]]
        assert any("YoutubeClient" in n for n in names)
        assert any("make_youtube_client" in n for n in names)

    def test_search_returns_mcp_hits(self, tmp_path):
        tools = _synthetic_tools(tmp_path)
        result = search_capabilities(query="task", surface="mcp", tools_root=tools)
        assert result["mode"] == "search"
        assert result["total_matched"] >= 1
        names = [r["tool_name"] for r in result["results"]]
        assert "noctus.dev.task_branch" in names

    def test_search_surface_all_merges_both(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        tools = _synthetic_tools(tmp_path)
        # query="branch" matches both lib framework app AND mcp task_branch
        result = search_capabilities(
            query="branch", surface="all", repo_root=repo, tools_root=tools
        )
        surfaces = {r["surface"] for r in result["results"]}
        assert "mcp" in surfaces

    def test_empty_query_returns_all_bounded_by_limit(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        result = search_capabilities(query="", surface="lib", limit=3, repo_root=repo)
        assert result["returned"] <= 3

    def test_limit_cap_respected_and_dropped_reported(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        result_all = search_capabilities(query="", surface="lib", limit=200, repo_root=repo)
        total = result_all["total_matched"]
        result_capped = search_capabilities(query="", surface="lib", limit=2, repo_root=repo)
        assert result_capped["returned"] == 2
        if total > 2:
            assert result_capped["dropped"] == total - 2

    def test_layer_filter_restricts_to_layer(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        result = search_capabilities(query="", surface="lib", layer="integrations", repo_root=repo)
        for r in result["results"]:
            assert r["layer"] == "integrations"

    def test_kind_filter_restricts_to_kind(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        result = search_capabilities(query="", surface="lib", kind="class", repo_root=repo)
        for r in result["results"]:
            assert r["kind"] == "class"

    def test_namespace_filter_restricts_to_namespace(self, tmp_path):
        tools = _synthetic_tools(tmp_path)
        result = search_capabilities(
            query="", surface="mcp", namespace="noctus.dev", tools_root=tools
        )
        for r in result["results"]:
            assert r["namespace"].startswith("noctus.dev")

    def test_search_result_lib_row_shape(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        result = search_capabilities(query="truncate", surface="lib", repo_root=repo)
        assert result["total_matched"] >= 1
        row = result["results"][0]
        assert "surface" in row and row["surface"] == "lib"
        assert "import_path" in row
        assert "kind" in row
        assert "layer" in row
        assert "summary" in row
        assert "score" in row

    def test_search_result_mcp_row_shape(self, tmp_path):
        tools = _synthetic_tools(tmp_path)
        result = search_capabilities(query="knowledge", surface="mcp", tools_root=tools)
        assert result["total_matched"] >= 1
        row = result["results"][0]
        assert row["surface"] == "mcp"
        assert "tool_name" in row
        assert "namespace" in row
        assert "summary" in row
        assert "score" in row

    def test_no_results_for_unknown_query(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        tools = _synthetic_tools(tmp_path)
        result = search_capabilities(
            query="xyzzy_not_real_capability_9999",
            surface="all",
            repo_root=repo,
            tools_root=tools,
        )
        assert result["total_matched"] == 0
        assert result["results"] == []
        assert result["dropped"] == 0

    def test_results_ranked_by_score_desc(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        result = search_capabilities(query="youtube", surface="lib", repo_root=repo)
        scores = [r["score"] for r in result["results"]]
        assert scores == sorted(scores, reverse=True)


class TestSearchCapabilitiesSummary:
    def test_summary_lib_has_expected_keys(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        result = search_capabilities(mode="summary", surface="lib", repo_root=repo)
        assert result["mode"] == "summary"
        lib = result["lib"]
        assert "total" in lib
        assert "by_layer" in lib
        assert "by_kind" in lib
        assert lib["total"] > 0

    def test_summary_mcp_has_expected_keys(self, tmp_path):
        tools = _synthetic_tools(tmp_path)
        result = search_capabilities(mode="summary", surface="mcp", tools_root=tools)
        assert result["mode"] == "summary"
        mcp = result["mcp"]
        assert "total" in mcp
        assert "by_namespace" in mcp
        assert mcp["total"] == 2
        assert "noctus.dev" in mcp["by_namespace"]

    def test_summary_all_returns_both(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        tools = _synthetic_tools(tmp_path)
        result = search_capabilities(
            mode="summary", surface="all", repo_root=repo, tools_root=tools
        )
        assert "lib" in result
        assert "mcp" in result

    def test_summary_lib_counts_match_totals(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        result = search_capabilities(mode="summary", surface="lib", repo_root=repo)
        lib = result["lib"]
        by_layer_sum = sum(lib["by_layer"].values())
        # framework counts under "framework" key in by_layer
        assert by_layer_sum == lib["total"]

    def test_summary_layer_filter_reduces_total(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        all_result = search_capabilities(mode="summary", surface="lib", repo_root=repo)
        integrations_result = search_capabilities(
            mode="summary", surface="lib", layer="integrations", repo_root=repo
        )
        assert integrations_result["lib"]["total"] <= all_result["lib"]["total"]


class TestSearchCapabilitiesDetail:
    def test_detail_lib_found_exact(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        result = search_capabilities(
            mode="detail",
            query="noctusai_lib.integrations.youtube.protocol.YoutubeClient",
            surface="lib",
            repo_root=repo,
        )
        assert result["mode"] == "detail"
        assert result["found"] is True
        item = result["item"]
        assert item["import_path"] == "noctusai_lib.integrations.youtube.protocol.YoutubeClient"
        assert item["kind"] == "class"
        assert item["layer"] == "integrations"
        assert "YouTube Data API" in item["docstring"]
        assert "class YoutubeClient" in item["signature"]

    def test_detail_lib_function_has_signature(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        result = search_capabilities(
            mode="detail",
            query="noctusai_lib.integrations.youtube.factory.make_youtube_client",
            surface="lib",
            repo_root=repo,
        )
        assert result["found"] is True
        item = result["item"]
        assert "make_youtube_client" in item["signature"]
        assert item["docstring"]

    def test_detail_mcp_found_exact(self, tmp_path):
        tools = _synthetic_tools(tmp_path)
        result = search_capabilities(
            mode="detail",
            query="noctus.dev.task_branch",
            surface="mcp",
            tools_root=tools,
        )
        assert result["found"] is True
        item = result["item"]
        assert item["tool_name"] == "noctus.dev.task_branch"
        assert "task_branch" in item["signature"]
        assert item["docstring"]

    def test_detail_not_found_returns_false(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        result = search_capabilities(
            mode="detail",
            query="noctusai_lib.does_not_exist.SomeMissingClass",
            surface="lib",
            repo_root=repo,
        )
        assert result["found"] is False
        assert result["item"] is None

    def test_detail_empty_query_returns_error(self, tmp_path):
        repo = _synthetic_repo(tmp_path)
        result = search_capabilities(mode="detail", query="", surface="lib", repo_root=repo)
        assert result["found"] is False
        assert "error" in result

    def test_detail_surface_all_tries_lib_then_mcp(self, tmp_path):
        """surface=all should find lib entries when they match."""
        repo = _synthetic_repo(tmp_path)
        tools = _synthetic_tools(tmp_path)
        result = search_capabilities(
            mode="detail",
            query="noctusai_lib.domain.helpers.text.truncate",
            surface="all",
            repo_root=repo,
            tools_root=tools,
        )
        assert result["found"] is True
        assert result["surface"] == "lib"


class TestSearchCapabilitiesLiveTree:
    """Smoke tests against the real repo — no writes, bounded output."""

    def test_live_search_youtube_returns_lib_hits(self):
        result = search_capabilities(query="youtube", surface="lib", limit=10)
        assert result["total_matched"] >= 4  # YoutubeClient + variants
        assert all(r["surface"] == "lib" for r in result["results"])

    def test_live_summary_mcp_counts_200plus_tools(self):
        result = search_capabilities(mode="summary", surface="mcp")
        assert result["mcp"]["total"] >= 100  # live tree has 218+ tools

    def test_live_detail_task_branch(self):
        result = search_capabilities(
            mode="detail", query="noctus.dev.task_branch", surface="mcp"
        )
        assert result["found"] is True
        item = result["item"]
        assert "task_branch" in item["signature"].lower()
        assert item["docstring"]

    def test_live_summary_lib_total_plausible(self):
        result = search_capabilities(mode="summary", surface="lib")
        # Should be several hundred public symbols across 6 layers + framework
        assert result["lib"]["total"] >= 200

    def test_live_search_never_exceeds_limit(self):
        result = search_capabilities(query="", surface="all", limit=25)
        assert result["returned"] <= 25

    def test_live_dropped_reported_honestly(self):
        result = search_capabilities(query="", surface="all", limit=5)
        assert result["returned"] == 5
        assert result["dropped"] == result["total_matched"] - 5
