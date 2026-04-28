"""Tests for `check_frontend_config_paths` — the keeper detector that
flags stale relative paths to `seed/` in `vite.config.ts` /
`tailwind.config.ts` / `postcss.config.js`. Prevents recurrence of the
2026-04-20 seed-relocation bug class that broke core's frontend build.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.compliance import (
    _SEED_RELATIVE_PATH_PATTERN,
    _glob_prefix_resolves,
    _resolves_via_module_resolution,
    check_frontend_config_paths,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTS_DIR = REPO_ROOT / "products"


def _write_frontend_config(tmp_path: Path, vite: str | None = None,
                           tailwind: str | None = None,
                           postcss: str | None = None) -> Path:
    """Lay out a fake product with selected frontend config files."""
    product = tmp_path / "fake-product"
    (product / "frontend").mkdir(parents=True)
    if vite is not None:
        (product / "frontend" / "vite.config.ts").write_text(vite)
    if tailwind is not None:
        (product / "frontend" / "tailwind.config.ts").write_text(tailwind)
    if postcss is not None:
        (product / "frontend" / "postcss.config.js").write_text(postcss)
    return product


class TestRegexMatching:
    def _matches(self, content: str) -> list[str]:
        return [m.group(1) for m in _SEED_RELATIVE_PATH_PATTERN.finditer(content)]

    def test_matches_literal_seed_import(self):
        assert self._matches('import x from "../../../seed/frontend/framework/vite.config.factory";') == [
            "../../../seed/frontend/framework/vite.config.factory"
        ]

    def test_matches_glob_with_braces_and_stars(self):
        assert self._matches('"../../../seed/frontend/lib/src/**/*.{ts,tsx}"') == [
            "../../../seed/frontend/lib/src/**/*.{ts,tsx}"
        ]

    def test_matches_terminal_seed(self):
        assert self._matches('path: "../../../seed"') == ["../../../seed"]

    def test_rejects_docs_seed_md(self):
        # `seed.md` is not a path to the seed directory; regex requires
        # `seed/` (with trailing slash) or terminal `seed`.
        assert self._matches('"../../docs/seed.md"') == []

    def test_rejects_seed_loader_string(self):
        # Plugin name "seed-loader" has no leading dot — not a relative path.
        assert self._matches('plugin: "seed-loader"') == []

    def test_rejects_bare_seed_string(self):
        # Bare "seed" with no leading `.` — could be anything; not a path.
        assert self._matches('tag: "seed"') == []

    def test_rejects_partial_seed_match_in_filename(self):
        # `seed-data.ts` contains `seed` but not as a directory marker.
        assert self._matches('"./components/seed-data.ts"') == []


class TestModuleResolution:
    def test_literal_existing_file_resolves(self, tmp_path):
        f = tmp_path / "module.ts"
        f.write_text("")
        assert _resolves_via_module_resolution(tmp_path / "module") is True

    def test_literal_with_explicit_extension_resolves(self, tmp_path):
        f = tmp_path / "module.ts"
        f.write_text("")
        assert _resolves_via_module_resolution(tmp_path / "module.ts") is True

    def test_directory_with_index_resolves(self, tmp_path):
        d = tmp_path / "pkg"
        d.mkdir()
        (d / "index.ts").write_text("")
        assert _resolves_via_module_resolution(tmp_path / "pkg") is True

    def test_missing_target_does_not_resolve(self, tmp_path):
        assert _resolves_via_module_resolution(tmp_path / "nope") is False

    def test_compound_extension_handled(self, tmp_path):
        # `vite.config.factory.ts` — the seed's actual filename pattern.
        # Naive `with_suffix(".ts")` would convert `.factory` → `.ts`;
        # the resolver must append rather than replace.
        f = tmp_path / "vite.config.factory.ts"
        f.write_text("")
        assert _resolves_via_module_resolution(tmp_path / "vite.config.factory") is True


class TestGlobPrefix:
    def test_existing_prefix_directory_resolves(self, tmp_path):
        d = tmp_path / "src"
        d.mkdir()
        glob = str(d / "**" / "*.{ts,tsx}")
        assert _glob_prefix_resolves(glob) is True

    def test_missing_prefix_directory_does_not_resolve(self, tmp_path):
        glob = str(tmp_path / "missing-dir" / "**" / "*.ts")
        assert _glob_prefix_resolves(glob) is False


class TestCompliantConfigs:
    def test_synthetic_compliant_layout(self, tmp_path):
        # Mock seed at <tmp>/seed/frontend/framework/vite.config.factory.ts
        seed_factory = tmp_path / "seed" / "frontend" / "framework"
        seed_factory.mkdir(parents=True)
        (seed_factory / "vite.config.factory.ts").write_text("")
        # Build product at <tmp>/products/fake-product/frontend/
        product = tmp_path / "products" / "fake-product"
        (product / "frontend").mkdir(parents=True)
        (product / "frontend" / "vite.config.ts").write_text(
            'import { x } from "../../../seed/frontend/framework/vite.config.factory";'
        )
        assert check_frontend_config_paths(product) == []

    def test_all_real_products_pass(self):
        for d in sorted(PRODUCTS_DIR.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            issues = check_frontend_config_paths(d)
            assert issues == [], f"{d.name} flagged: {issues}"


class TestViolations:
    def test_broken_vite_path_flagged(self, tmp_path):
        # Right product layout, wrong path depth — simulates the post-2026-04-20-move bug.
        seed_factory = tmp_path / "seed" / "frontend" / "framework"
        seed_factory.mkdir(parents=True)
        (seed_factory / "vite.config.factory.ts").write_text("")
        product = tmp_path / "products" / "fake-product"
        (product / "frontend").mkdir(parents=True)
        # Path uses ../../seed/ (one too few) instead of ../../../seed/
        (product / "frontend" / "vite.config.ts").write_text(
            'import { x } from "../../seed/frontend/framework/vite.config.factory";'
        )
        issues = check_frontend_config_paths(product)
        assert len(issues) == 1
        assert issues[0]["product"] == "fake-product"
        assert issues[0]["file"] == "frontend/vite.config.ts"
        assert issues[0]["severity"] == "critical"
        assert "../../seed/frontend/framework/vite.config.factory" in issues[0]["issue"]
        assert "Frontend will fail to build" in issues[0]["issue"]

    def test_broken_tailwind_glob_flagged(self, tmp_path):
        # Glob prefix points at a directory that doesn't exist.
        product = tmp_path / "products" / "fake-product"
        (product / "frontend").mkdir(parents=True)
        (product / "frontend" / "tailwind.config.ts").write_text(
            'export default { content: ["../../../seed/frontend/lib/src/**/*.{ts,tsx}"] };'
        )
        issues = check_frontend_config_paths(product)
        assert len(issues) == 1
        assert issues[0]["file"] == "frontend/tailwind.config.ts"

    def test_multiple_broken_paths_each_flagged(self, tmp_path):
        product = tmp_path / "products" / "fake-product"
        (product / "frontend").mkdir(parents=True)
        (product / "frontend" / "vite.config.ts").write_text("""
import a from "../../seed/foo";
import b from "../../seed/bar";
""")
        issues = check_frontend_config_paths(product)
        assert len(issues) == 2


class TestEdgeCases:
    def test_missing_all_config_files_skips_silently(self, tmp_path):
        product = tmp_path / "no-frontend-product"
        (product / "frontend").mkdir(parents=True)
        assert check_frontend_config_paths(product) == []

    def test_postcss_with_no_seed_refs_is_clean(self, tmp_path):
        # Postcss configs typically don't reference seed; detector should
        # find zero matches and return empty.
        product = _write_frontend_config(tmp_path, postcss="""
export default { plugins: { tailwindcss: {}, autoprefixer: {} } };
""")
        assert check_frontend_config_paths(product) == []

    def test_non_seed_relative_imports_ignored(self, tmp_path):
        # Imports of OTHER relative paths (not targeting seed/) are ignored.
        product = _write_frontend_config(tmp_path, vite="""
import a from "./local-helper";
import b from "../sibling";
import c from "@noctusai/seed/foo";
""")
        # The third one starts with `@` not `.`; regex requires leading dot.
        assert check_frontend_config_paths(product) == []
