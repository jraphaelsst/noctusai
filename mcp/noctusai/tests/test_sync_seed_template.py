"""sync_seed_template — native port parity vs scripts/sync-seed-template.sh.

Asserts the placeholder mapping table + ordering, the build-artifact
exclusion set, the .backup preservation behaviour, the validation pass,
and the --dry contract — on a synthetic seed tree with the module's
REPO_ROOT monkeypatched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import sync_seed_template as sst


def _mk_seed(root: Path) -> Path:
    seed = root / "products" / "seed"
    (seed / "backend" / "app").mkdir(parents=True, exist_ok=True)
    (seed / "backend" / "migrations").mkdir(parents=True, exist_ok=True)
    (seed / "frontend" / "src").mkdir(parents=True, exist_ok=True)
    # Files that exercise every placeholder rule.
    (seed / "backend" / "app" / "main.py").write_text(
        'NAME = "Seed Product"\nSCHEMA = "seed"\nPORT = 8004\nFE = 8100\n'
        "ICON = 'Sprout'\n",
        encoding="utf-8",
    )
    (seed / "backend" / "migrations" / "001_seed.sql").write_text(
        "CREATE SCHEMA seed;\nCREATE INDEX idx_seed_org ON seed.t (org);\n",
        encoding="utf-8",
    )
    (seed / "docker-compose.yml").write_text(
        "services:\n  seed:\n    container_name: dev-noctus-seed\n"
        "    image: ghcr.io/jraphaelsst/noctus-seed:latest\n"
        "    command: --url http://seed:8004\n"
        "  tunnel-seed:\n    depends_on:\n      seed:\n        condition: started\n",
        encoding="utf-8",
    )
    (seed / "Dockerfile").write_text(
        "# seed — CANONICAL thin product image (the reference every product mirrors).\n"
        "ARG PRODUCT_SLUG=seed\nARG PRODUCT_PORT=8004\n"
        'LABEL org.opencontainers.image.title="noctus-seed"\n'
        "COPY products/seed/backend /app\n",
        encoding="utf-8",
    )
    (seed / "README.md").write_text(
        "Run `products/seed/backend`. Schema `seed`.\n", encoding="utf-8"
    )
    # Build artifact that MUST be excluded from the template copy.
    nm = seed / "frontend" / "node_modules"
    nm.mkdir(parents=True, exist_ok=True)
    (nm / "junk.js").write_text("// excluded\n", encoding="utf-8")
    (seed / "frontend" / "package-lock.json").write_text("{}\n", encoding="utf-8")
    return seed


def test_dry_run_mutates_nothing(tmp_path, monkeypatch):
    _mk_seed(tmp_path)
    monkeypatch.setattr(sst, "REPO_ROOT", tmp_path)
    r = sst.sync_seed_template(dry=True)
    assert r["ok"] is True and r["dry"] is True
    assert not (tmp_path / "templates" / "product-seed").exists()
    assert any("DRY RUN" in s for s in r["steps"])


def test_placeholder_mapping_exact(tmp_path, monkeypatch):
    _mk_seed(tmp_path)
    monkeypatch.setattr(sst, "REPO_ROOT", tmp_path)
    r = sst.sync_seed_template(dry=False)
    assert r["ok"] is True, r

    tpl = tmp_path / "templates" / "product-seed"
    main_py = (tpl / "backend" / "app" / "main.py").read_text()
    assert '"{{PRODUCT_NAME}}"' in main_py
    assert '"{{SCHEMA_NAME}}"' in main_py
    assert "{{BACKEND_PORT}}" in main_py
    assert "{{FRONTEND_PORT}}" in main_py
    assert "'{{PRODUCT_ICON}}'" in main_py

    sql = (tpl / "backend" / "migrations" / "001_seed.sql").read_text()
    assert "CREATE SCHEMA {{SCHEMA_NAME}};" in sql
    assert "idx_{{SCHEMA_NAME}}_org" in sql
    assert "{{SCHEMA_NAME}}.t" in sql

    compose = (tpl / "docker-compose.yml").read_text()
    assert "\n  {{PRODUCT_SLUG}}:\n" in compose
    assert "container_name: dev-noctus-{{PRODUCT_SLUG}}" in compose
    assert "image: ghcr.io/jraphaelsst/noctus-{{PRODUCT_SLUG}}:latest" in compose
    assert "--url http://{{PRODUCT_SLUG}}:{{BACKEND_PORT}}" in compose
    assert "tunnel-{{PRODUCT_SLUG}}:" in compose
    assert "\n      {{PRODUCT_SLUG}}:\n" in compose

    # PARITY: scripts/sync-seed-template.sh's placeholder `find` filter
    # does NOT include a bare `Dockerfile` (only listed extensions), so
    # the script's Dockerfile-specific perl branch is dead code — the
    # Dockerfile is never placeholderized HERE (propagate-dockerfiles.sh
    # owns that surface). Behaviour-preserving: it stays literal.
    dockerfile = (tpl / "Dockerfile").read_text()
    assert dockerfile.startswith("# seed — CANONICAL")
    assert "ARG PRODUCT_SLUG=seed" in dockerfile
    assert 'title="noctus-seed"' in dockerfile
    assert "COPY products/seed/backend /app" in dockerfile

    readme = (tpl / "README.md").read_text()
    assert "products/{{PRODUCT_SLUG}}/backend" in readme
    assert "Schema `{{SCHEMA_NAME}}`" in readme


def test_build_artifacts_excluded_from_template(tmp_path, monkeypatch):
    _mk_seed(tmp_path)
    monkeypatch.setattr(sst, "REPO_ROOT", tmp_path)
    sst.sync_seed_template(dry=False)
    tpl = tmp_path / "templates" / "product-seed"
    assert not (tpl / "frontend" / "node_modules").exists()
    assert not (tpl / "frontend" / "package-lock.json").exists()
    # .backup created in seed for rollback.
    assert (tmp_path / "products" / "seed" / ".backup").is_dir()


def test_validation_counts_expected_placeholders(tmp_path, monkeypatch):
    _mk_seed(tmp_path)
    monkeypatch.setattr(sst, "REPO_ROOT", tmp_path)
    r = sst.sync_seed_template(dry=False)
    found = {v["placeholder"]: v["count"] for v in r["validation"]}
    for ph in sst.EXPECTED_PLACEHOLDERS:
        assert ph in found
    assert found["{{PRODUCT_NAME}}"] >= 1
    assert found["{{SCHEMA_NAME}}"] >= 1
    assert found["{{BACKEND_PORT}}"] >= 1
    assert found["{{FRONTEND_PORT}}"] >= 1
    assert r["missing_placeholders"] == 0
    assert r["message"] == "Sync complete!"


def test_template_backup_preserved_across_resync(tmp_path, monkeypatch):
    _mk_seed(tmp_path)
    monkeypatch.setattr(sst, "REPO_ROOT", tmp_path)
    tpl = tmp_path / "templates" / "product-seed"
    tpl.mkdir(parents=True, exist_ok=True)
    (tpl / ".backup").mkdir()
    (tpl / ".backup" / "sentinel.txt").write_text("keep-me\n", encoding="utf-8")
    sst.sync_seed_template(dry=False)
    # .backup re-created from the FRESH template copy (step-1 backup of
    # the existing template); the prior hand-placed sentinel is replaced
    # by the script's own backup of the pre-sync template — the contract
    # is that template/.backup survives the rm-and-recopy of step 2.
    assert (tpl / ".backup").is_dir()
