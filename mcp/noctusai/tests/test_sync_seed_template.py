"""sync_seed_template — native port parity vs scripts/sync-seed-template.sh.

Asserts the placeholder mapping table + ordering, the build-artifact
exclusion set, the .backup preservation behaviour, the validation pass,
and the --dry contract — on a synthetic seed tree with the module's
REPO_ROOT monkeypatched.
"""
from __future__ import annotations

import json
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


def test_sql_comments_are_not_over_substituted(tmp_path, monkeypatch):
    """The bare-word `\\bseed\\b` regex used for .sql files must not rewrite
    the English word "seed" inside `--`-comment prose. Regression for the
    templates/product-seed/backend/migrations/002/004/005.sql defect: a
    comment like "the seed → templates/product-seed sync" became "the
    {{SCHEMA_NAME}} → templates/product-{{SCHEMA_NAME}} sync" — nonsense,
    since the comment was talking about the seed product/directory, not
    the schema literal. A comment-line (stripped form starts with `--`)
    must survive verbatim; a code line's `seed` schema references still
    get placeholderized correctly."""
    _mk_seed(tmp_path)
    seed = tmp_path / "products" / "seed"
    (seed / "backend" / "migrations" / "002_comment_case.sql").write_text(
        "-- Lockstep with the seed-team-router (see the seed → templates/\n"
        "-- product-seed sync for background).\n"
        "--\n"
        "-- This migration propagates to every new product via the seed\n"
        "-- sync (see pre-commit hook).\n"
        "\n"
        "ALTER TABLE seed.invitations ADD COLUMN IF NOT EXISTS x TEXT;\n"
        "CREATE INDEX idx_seed_org ON seed.t (org);\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sst, "REPO_ROOT", tmp_path)
    r = sst.sync_seed_template(dry=False)
    assert r["ok"] is True, r

    sql = (
        tmp_path
        / "templates"
        / "product-seed"
        / "backend"
        / "migrations"
        / "002_comment_case.sql"
    ).read_text()

    # Comment lines survive VERBATIM — "seed" stays "seed", never rewritten.
    assert "-- Lockstep with the seed-team-router (see the seed → templates/" in sql
    assert "-- product-seed sync for background).\n" in sql
    assert "-- This migration propagates to every new product via the seed" in sql
    assert "-- sync (see pre-commit hook).\n" in sql
    assert "{{SCHEMA_NAME}}" not in sql.split("\n\n")[0]

    # Code lines still get the schema literal placeholderized correctly.
    assert "ALTER TABLE {{SCHEMA_NAME}}.invitations" in sql
    assert "idx_{{SCHEMA_NAME}}_org" in sql
    assert "{{SCHEMA_NAME}}.t" in sql


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


# ── declared divergences (templates/product-seed-divergences.json) ──────────

_DIVERGENT = "backend/migrations/001_seed.sql"
_IDEMPOTENT = "CREATE SCHEMA IF NOT EXISTS {{SCHEMA_NAME}};\n"


def _declare(root: Path, *paths: str) -> None:
    (root / "templates").mkdir(parents=True, exist_ok=True)
    (root / sst.DIVERGENCES_REL).write_text(json.dumps({"divergences": [
        {"path": p, "rationale": "seed copy applied in prod, template copy idempotent"} for p in paths
    ]}), encoding="utf-8")


def _synced(root: Path) -> Path:
    """Seed + a fresh sync + an idempotent hand-written divergent template file."""
    _mk_seed(root)
    assert sst.sync_seed_template(dry=False, repo_root=root)["ok"] is True
    tpl = root / "templates" / "product-seed"
    (tpl / _DIVERGENT).write_text(_IDEMPOTENT, encoding="utf-8")
    _declare(root, _DIVERGENT)
    return tpl


def test_sync_keeps_a_declared_divergence(tmp_path):
    tpl = _synced(tmp_path)
    r = sst.sync_seed_template(dry=False, repo_root=tmp_path)
    assert r["ok"] is True, r
    assert (tpl / _DIVERGENT).read_text(encoding="utf-8") == _IDEMPOTENT
    # Everything NOT declared is still re-rendered from the seed.
    assert '"{{SCHEMA_NAME}}"' in (tpl / "backend" / "app" / "main.py").read_text()


def test_sync_refuses_to_backfill_a_missing_declared_divergence(tmp_path):
    tpl = _synced(tmp_path)
    (tpl / _DIVERGENT).unlink()
    r = sst.sync_seed_template(dry=False, repo_root=tmp_path)
    assert r["ok"] is False
    assert _DIVERGENT in r["message"]
    # Not silently replaced by the seed's (non-idempotent) rendering.
    assert not (tpl / _DIVERGENT).exists()


def test_divergence_without_rationale_is_refused(tmp_path):
    _mk_seed(tmp_path)
    (tmp_path / "templates").mkdir()
    (tmp_path / sst.DIVERGENCES_REL).write_text(
        json.dumps({"divergences": [{"path": _DIVERGENT}]}), encoding="utf-8")
    r = sst.sync_seed_template(dry=False, repo_root=tmp_path)
    assert r["ok"] is False and "rationale" in r["error"]


def test_keeper_clean_after_sync_with_declared_divergence(tmp_path):
    _synced(tmp_path)
    assert sst.check_seed_template_sync(tmp_path) == []


def test_keeper_flags_undeclared_template_edit(tmp_path):
    tpl = _synced(tmp_path)
    (tpl / "backend" / "app" / "main.py").write_text("hand edit\n", encoding="utf-8")
    (issue,) = sst.check_seed_template_sync(tmp_path)
    assert issue["file"] == "templates/product-seed/backend/app/main.py"
    assert issue["severity"] == "high"


def test_keeper_flags_missing_declared_divergence(tmp_path):
    tpl = _synced(tmp_path)
    (tpl / _DIVERGENT).unlink()
    (issue,) = sst.check_seed_template_sync(tmp_path)
    assert "missing from the template" in issue["issue"]


def test_keeper_flags_stale_divergence_entry(tmp_path):
    tpl = _synced(tmp_path)
    (tpl / "backend" / "migrations" / "099_gone.sql").write_text("SELECT 1;\n", encoding="utf-8")
    _declare(tmp_path, _DIVERGENT, "backend/migrations/099_gone.sql")
    (issue,) = sst.check_seed_template_sync(tmp_path)
    assert "no longer exists in products/seed/" in issue["issue"]


def test_keeper_flags_missing_divergence_list(tmp_path):
    _synced(tmp_path)
    (tmp_path / sst.DIVERGENCES_REL).unlink()
    issues = sst.check_seed_template_sync(tmp_path)
    assert any(i["file"] == str(sst.DIVERGENCES_REL) for i in issues)


def test_real_template_matches_seed_plus_declared_divergences():
    """The checked-in tree: template == rendered seed, outside the declared list."""
    from settings import REPO_ROOT

    assert sst.check_seed_template_sync(Path(REPO_ROOT)) == []
    assert set(sst.load_divergences(Path(REPO_ROOT))) == {
        "backend/migrations/001_seed.sql", "backend/migrations/003_examples.sql",
    }
