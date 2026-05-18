"""noctus.dev.sync_seed_template — native port of scripts/sync-seed-template.sh.

Syncs the live seed product (``products/seed/``) to the template
(``templates/product-seed/``) by copying files and replacing
product-specific values with ``{{PLACEHOLDERS}}``.

Behaviour-preserving vs the retired shell script:

  1. Backup current seed   → ``products/seed/.backup/``
  2. Backup current template → ``templates/product-seed/.backup/``
  3. Copy seed → template (excluding build artifacts)
  4. Replace product values with placeholders (SAME ordering + regexes)
  5. Validate expected placeholders exist

``dry=True`` mirrors the script's ``--dry`` (reports, mutates nothing).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from settings import REPO_ROOT
from workspace import resolve_caller_root

# Directories/files never copied into the backup or template (mirrors
# the rsync --exclude set; package-lock.json is template-only excluded).
_BACKUP_EXCLUDES = {
    ".backup",
    "node_modules",
    "__pycache__",
    ".env",
    "venv",
    "dist",
    ".pytest_cache",
}
_TEMPLATE_EXTRA_EXCLUDES = _BACKUP_EXCLUDES | {"package-lock.json"}

# Text-file extensions processed by the placeholder pass (mirrors the
# `find ... \( -name "*.py" -o ... \)` filter; ``.env.example`` matched
# by suffix below).
_TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".json",
    ".md",
    ".sql",
    ".css",
    ".html",
    ".yml",
    ".yaml",
    ".toml",
    ".cfg",
    ".txt",
}

EXPECTED_PLACEHOLDERS = (
    "{{PRODUCT_NAME}}",
    "{{SCHEMA_NAME}}",
    "{{BACKEND_PORT}}",
    "{{FRONTEND_PORT}}",
)

# Validation grep restricted to these extensions (mirrors the shell
# `grep -r --include=` set).
_VALIDATE_SUFFIXES = {".py", ".ts", ".tsx", ".json", ".sql"}


def _excluded(rel_parts: tuple[str, ...], excludes: set[str]) -> bool:
    return any(part in excludes for part in rel_parts)


def _is_egg_info(rel_parts: tuple[str, ...]) -> bool:
    # rsync `--exclude='*.egg-info'` matches any path component.
    return any(part.endswith(".egg-info") for part in rel_parts)


def _copy_tree(src: Path, dst: Path, excludes: set[str]) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for p in src.rglob("*"):
        rel = p.relative_to(src)
        parts = rel.parts
        if _excluded(parts, excludes) or _is_egg_info(parts):
            continue
        target = dst / rel
        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif p.is_file() or p.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target, follow_symlinks=False)


def _apply_placeholders(text: str, filename: str, is_compose: bool, is_dockerfile: bool) -> str:
    """Port of the per-file perl substitution block — SAME ORDER."""
    # Order matters: longest match first.
    text = text.replace("Seed Product", "{{PRODUCT_NAME}}")
    text = text.replace("seed-product", "{{PRODUCT_SLUG}}")
    text = text.replace('"seed"', '"{{SCHEMA_NAME}}"')
    text = text.replace("'seed'", "'{{SCHEMA_NAME}}'")
    text = text.replace("Sprout", "{{PRODUCT_ICON}}")
    text = re.sub(r"\b8004\b", "{{BACKEND_PORT}}", text)
    text = re.sub(r"\b8100\b", "{{FRONTEND_PORT}}", text)

    if is_compose:
        text = text.replace("noctus-seed-", "noctus-{{PRODUCT_SLUG}}-")
        text = re.sub(r"\bseed-backend\b", "{{PRODUCT_SLUG}}-backend", text)
        text = re.sub(r"\bseed-frontend\b", "{{PRODUCT_SLUG}}-frontend", text)
        text = re.sub(r"\bseed-tunnel\b", "{{PRODUCT_SLUG}}-tunnel", text)
        text = re.sub(r"\bseed-net\b", "{{PRODUCT_SLUG}}-net", text)
        text = re.sub(r"\btunnel-seed\b", "tunnel-{{PRODUCT_SLUG}}", text)
        text = text.replace("products/seed/", "products/{{PRODUCT_SLUG}}/")
        text = text.replace("noctus-seed-backend", "noctus-{{PRODUCT_SLUG}}-backend")
        text = text.replace("noctus-seed-frontend", "noctus-{{PRODUCT_SLUG}}-frontend")
        # Single-container shape: dash-less service/container/image forms.
        text = text.replace("\n  seed:\n", "\n  {{PRODUCT_SLUG}}:\n")
        text = text.replace("\n      seed:\n", "\n      {{PRODUCT_SLUG}}:\n")
        text = re.sub(
            r"container_name: noctus-seed$",
            "container_name: noctus-{{PRODUCT_SLUG}}",
            text,
            flags=re.MULTILINE,
        )
        text = text.replace(
            "image: ghcr.io/jraphaelsst/noctus-seed:",
            "image: ghcr.io/jraphaelsst/noctus-{{PRODUCT_SLUG}}:",
        )
        text = text.replace(
            "--url http://seed:", "--url http://{{PRODUCT_SLUG}}:"
        )

    if is_dockerfile:
        # PARITY-DEAD: scripts/sync-seed-template.sh's `find` name-filter
        # never matches a bare `Dockerfile` (only the listed extensions),
        # so the shell's Dockerfile perl branch never executes either.
        # Kept (and never reached — _is_text_file excludes Dockerfile) so
        # this port is a faithful 1:1 of the script. Dockerfile
        # placeholderization is owned by propagate-dockerfiles.sh.
        text = text.replace("products/seed/", "products/{{PRODUCT_SLUG}}/")
        text = re.sub(r"PRODUCT_SLUG=seed\b", "PRODUCT_SLUG={{PRODUCT_SLUG}}", text)
        text = re.sub(r"PRODUCT_PORT=8004\b", "PRODUCT_PORT={{BACKEND_PORT}}", text)
        text = text.replace('title="noctus-seed"', 'title="noctus-{{PRODUCT_SLUG}}"')
        text = re.sub(
            r"^# seed — CANONICAL thin product image \(the reference every product mirrors\)\.$",
            "# {{PRODUCT_SLUG}} — thin product image (FROM the shared seed bases; per-product specifics only).",
            text,
            flags=re.MULTILINE,
        )

    if filename in ("README.md", "MASTER-PROMPT.md"):
        text = text.replace("products/seed/", "products/{{PRODUCT_SLUG}}/")
        text = text.replace("`seed`", "`{{SCHEMA_NAME}}`")

    if filename.endswith(".sql"):
        text = re.sub(r"\bseed\b", "{{SCHEMA_NAME}}", text)
        text = text.replace("idx_seed_", "idx_{{SCHEMA_NAME}}_")

    return text


def _is_text_file(p: Path) -> bool:
    if p.suffix in _TEXT_SUFFIXES:
        return True
    return p.name.endswith(".env.example")


def sync_seed_template(
    dry: bool = False, worktree_path: str | None = None
) -> dict[str, Any]:
    """Sync products/seed → templates/product-seed with placeholderization.

    Returns ``{ok, dry, steps, validation, seed, template, message}``.
    """
    root = resolve_caller_root(worktree_path) if worktree_path else Path(REPO_ROOT)
    seed = root / "products" / "seed"
    template = root / "templates" / "product-seed"
    steps: list[str] = []

    if not seed.is_dir():
        return {
            "ok": False,
            "dry": dry,
            "steps": steps,
            "error": f"Seed product not found at {seed}",
        }

    if dry:
        steps.append("DRY RUN — no files will be modified")
        steps.append(f"Would backup {seed} → {seed}/.backup")
        if template.is_dir():
            steps.append(f"Would backup {template} → {template}/.backup")
        steps.append(f"Would copy {seed} → {template}")
        steps.append(
            "Would replace: Seed Product→{{PRODUCT_NAME}}, "
            "seed→{{SCHEMA_NAME}}, 8004→{{BACKEND_PORT}}, "
            "8100→{{FRONTEND_PORT}}, Sprout→{{PRODUCT_ICON}}"
        )
        return {
            "ok": True,
            "dry": True,
            "steps": steps,
            "validation": [],
            "seed": str(seed),
            "template": str(template),
            "message": "Dry run complete — no changes made.",
        }

    # ─── Step 1: backup seed (and template if present) ───────────────
    _copy_tree(seed, seed / ".backup", _BACKUP_EXCLUDES)
    steps.append("Backed up seed → .backup/")
    if template.is_dir():
        _copy_tree(template, template / ".backup", _BACKUP_EXCLUDES)
        steps.append("Backed up product-seed → .backup/")

    # ─── Step 2: preserve template .backup, copy seed → template ─────
    preserved_backup: Path | None = None
    template_backup = template / ".backup"
    if template_backup.is_dir():
        preserved_backup = root / "templates" / "_noctus_template_backup_tmp"
        if preserved_backup.exists():
            shutil.rmtree(preserved_backup)
        shutil.move(str(template_backup), str(preserved_backup))

    _copy_tree(seed, template, _TEMPLATE_EXTRA_EXCLUDES)

    if preserved_backup is not None:
        dest = template / ".backup"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(preserved_backup), str(dest))
    steps.append("Copied seed → template")

    # ─── Step 3: placeholderize ──────────────────────────────────────
    for p in template.rglob("*"):
        if not p.is_file():
            continue
        if ".backup" in p.relative_to(template).parts:
            continue
        if not _is_text_file(p):
            continue
        try:
            original = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        name = p.name
        is_compose = "docker-compose" in name and name.endswith(".yml")
        is_dockerfile = name == "Dockerfile"
        updated = _apply_placeholders(original, name, is_compose, is_dockerfile)
        if updated != original:
            p.write_text(updated, encoding="utf-8")
    steps.append("Replaced product values with placeholders")

    # ─── Step 4: validate ────────────────────────────────────────────
    validation: list[dict[str, Any]] = []
    errors = 0
    for placeholder in EXPECTED_PLACEHOLDERS:
        count = 0
        for p in template.rglob("*"):
            if not p.is_file() or p.suffix not in _VALIDATE_SUFFIXES:
                continue
            if ".backup" in p.relative_to(template).parts:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            count += text.count(placeholder)
        validation.append({"placeholder": placeholder, "count": count})
        if count == 0:
            errors += 1

    return {
        "ok": errors == 0,
        "dry": False,
        "steps": steps,
        "validation": validation,
        "missing_placeholders": errors,
        "seed": str(seed),
        "template": str(template),
        "message": (
            "Sync complete!"
            if errors == 0
            else f"{errors} placeholder(s) missing — template may be incomplete"
        ),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.sync_seed_template",
        description=(
            "Native sync of products/seed → templates/product-seed with "
            "{{PLACEHOLDER}} substitution + validation (no shell "
            "subprocess; ports scripts/sync-seed-template.sh exactly). "
            "`dry=True` reports the plan without mutating. Pass "
            "worktree_path when called from inside a git worktree. "
            "Pre-commit invokes this when products/seed/ is staged."
        ),
    )
    def _sync_seed_template(
        dry: bool = False, worktree_path: str | None = None
    ) -> dict:
        return sync_seed_template(dry=dry, worktree_path=worktree_path)


__all__ = ["sync_seed_template", "EXPECTED_PLACEHOLDERS", "register"]
