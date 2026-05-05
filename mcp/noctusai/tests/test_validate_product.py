"""Tests for `validate_one_product` post-scaffold registration checks.

Phase 3.4 (sh-yt-scaffold-polish, 2026-05-04). The 5 binary checks mirror
`scaffold_product`'s `next_steps`:
  - backend_port_in_start_sh
  - frontend_port_in_start_sh
  - kb_landscape_table
  - products_table_insert
  - vite_factory_product_map

Tests fixture a minimal repo layout under `tmp_path`, point
`validate_one_product` at it via `repo_root=` / `products_dir=` seams,
and assert each check fires correctly when its required artifact is
missing or present.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import _check_post_scaffold, validate_one_product


def _seed_minimal_repo(tmp_path: Path, slug: str) -> dict[str, Path]:
    """Lay down a minimal repo fixture that passes ALL 5 post-scaffold checks.

    Returns the artifact paths so individual tests can selectively unwind
    one entry to assert that specific check fails.
    """
    products_dir = tmp_path / "products"
    products_dir.mkdir()

    # Product tree (placeholder — `_check_post_scaffold` doesn't require
    # specific files inside; check_seed_compliance does, but we don't
    # exercise that under fixture mode).
    product = products_dir / slug
    (product / "backend" / "migrations").mkdir(parents=True)
    (product / "frontend").mkdir(parents=True)

    # 1+2 — start.sh with both backend + frontend wired.
    start_sh = tmp_path / "start.sh"
    start_sh.write_text(
        f"""#!/bin/bash
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
{slug.upper().replace("-", "_")}_BACKEND="$ROOT_DIR/products/{slug}/backend"
"$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8500 --reload --app-dir "${slug.upper().replace("-", "_")}_BACKEND" &
{slug.upper().replace("-", "_")}_FRONTEND="$ROOT_DIR/products/{slug}/frontend"
(cd "${slug.upper().replace("-", "_")}_FRONTEND" && exec npx vite --host 0.0.0.0 --port 8600) &
"""
    )

    # 3 — KB landscape table row.
    kb_dir = tmp_path / "KNOWLEDGE-BASE" / "CONTEXT"
    kb_dir.mkdir(parents=True)
    landscape = kb_dir / "02-LANDSCAPE.md"
    landscape.write_text(
        f"""# 02 — Platform Landscape

## Products

| Product | Path | Description | BE/FE Ports | Schema |
|---------|------|-------------|-------------|--------|
| **My Product** | `products/{slug}/` | Test product | 8500/8600 | `{slug.replace("-", "_")}` |
"""
    )

    # 4 — products-table INSERT in a migration file.
    migration = product / "backend" / "migrations" / "001_register.sql"
    migration.write_text(
        f"""-- Register {slug} in core products
INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES (
    'My Product',
    '{slug}',
    'Test product',
    'X',
    'http://localhost:8600',
    '#abc',
    true
) ON CONFLICT (slug) DO NOTHING;
"""
    )

    # 5 — vite.config.factory.ts PRODUCT_MAP with the slug as comment.
    factory_dir = tmp_path / "seed" / "framework" / "frontend"
    factory_dir.mkdir(parents=True)
    factory = factory_dir / "vite.config.factory.ts"
    factory.write_text(
        f"""// Test factory
const PRODUCT_MAP: Record<number, {{ backend: number; schema: string }}> = {{
  5173: {{ backend: 8000, schema: "public" }},     // Core
  8600: {{ backend: 8500, schema: "test" }},       // {slug}
}};
"""
    )

    return {
        "tmp_path": tmp_path,
        "products_dir": products_dir,
        "product": product,
        "start_sh": start_sh,
        "landscape": landscape,
        "migration": migration,
        "factory": factory,
    }


class TestPostScaffoldHappyPath:
    """All 5 checks pass when every artifact is in place."""

    SLUG = "my-product"

    def test_all_checks_pass(self, tmp_path):
        _seed_minimal_repo(tmp_path, self.SLUG)
        checks = _check_post_scaffold(
            self.SLUG,
            repo_root=tmp_path,
            products_dir=tmp_path / "products",
        )
        # Shape assertion: each entry has the documented keys.
        for c in checks:
            assert set(c.keys()) == {"check", "ok", "error"}, c
        # Aggregate: every check ok.
        assert all(c["ok"] for c in checks), [c for c in checks if not c["ok"]]
        names = {c["check"] for c in checks}
        assert names == {
            "backend_port_in_start_sh",
            "frontend_port_in_start_sh",
            "kb_landscape_table",
            "products_table_insert",
            "vite_factory_product_map",
        }

    def test_validate_one_product_aggregates_post_ok(self, tmp_path):
        _seed_minimal_repo(tmp_path, self.SLUG)
        result = validate_one_product(
            self.SLUG,
            repo_root=tmp_path,
            products_dir=tmp_path / "products",
        )
        # Existing shape preserved.
        assert "score" in result
        assert "issues" in result
        # New keys present.
        assert result["post_scaffold_ok"] is True
        assert isinstance(result["post_scaffold_checks"], list)
        assert len(result["post_scaffold_checks"]) == 5


class TestPostScaffoldFailures:
    """Removing each artifact triggers exactly the corresponding failed check."""

    SLUG = "broken-product"

    def _checks_by_name(self, tmp_path: Path) -> dict[str, dict]:
        checks = _check_post_scaffold(
            self.SLUG,
            repo_root=tmp_path,
            products_dir=tmp_path / "products",
        )
        return {c["check"]: c for c in checks}

    def test_missing_start_sh_backend_wiring(self, tmp_path):
        artifacts = _seed_minimal_repo(tmp_path, self.SLUG)
        # Wipe backend wiring while leaving frontend intact.
        sh = artifacts["start_sh"].read_text()
        # Delete the line containing `--app-dir` for the product.
        new_sh = "\n".join(
            line for line in sh.splitlines()
            if "--app-dir" not in line and f"products/{self.SLUG}/backend" not in line
        )
        artifacts["start_sh"].write_text(new_sh + "\n")
        by_name = self._checks_by_name(tmp_path)
        assert by_name["backend_port_in_start_sh"]["ok"] is False
        assert by_name["backend_port_in_start_sh"]["error"]
        # Frontend still ok.
        assert by_name["frontend_port_in_start_sh"]["ok"] is True

    def test_missing_kb_landscape_row(self, tmp_path):
        artifacts = _seed_minimal_repo(tmp_path, self.SLUG)
        artifacts["landscape"].write_text("# Landscape — no row for our slug\n")
        by_name = self._checks_by_name(tmp_path)
        assert by_name["kb_landscape_table"]["ok"] is False
        assert self.SLUG in by_name["kb_landscape_table"]["error"]

    def test_missing_products_insert(self, tmp_path):
        artifacts = _seed_minimal_repo(tmp_path, self.SLUG)
        artifacts["migration"].unlink()
        by_name = self._checks_by_name(tmp_path)
        assert by_name["products_table_insert"]["ok"] is False
        assert self.SLUG in by_name["products_table_insert"]["error"]

    def test_missing_vite_factory_entry(self, tmp_path):
        artifacts = _seed_minimal_repo(tmp_path, self.SLUG)
        # Strip the slug entry from PRODUCT_MAP.
        fc = artifacts["factory"].read_text()
        fc = "\n".join(line for line in fc.splitlines() if self.SLUG not in line)
        artifacts["factory"].write_text(fc)
        by_name = self._checks_by_name(tmp_path)
        assert by_name["vite_factory_product_map"]["ok"] is False
        assert self.SLUG in by_name["vite_factory_product_map"]["error"]

    def test_missing_start_sh_entirely(self, tmp_path):
        artifacts = _seed_minimal_repo(tmp_path, self.SLUG)
        artifacts["start_sh"].unlink()
        by_name = self._checks_by_name(tmp_path)
        # Both backend + frontend port checks fail when start.sh is missing.
        assert by_name["backend_port_in_start_sh"]["ok"] is False
        assert by_name["frontend_port_in_start_sh"]["ok"] is False
