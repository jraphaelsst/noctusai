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

**Declared divergences.** A template file that must NOT mirror the seed is
listed in ``templates/product-seed-divergences.json`` (one entry per file,
each with a one-line rationale). The sync leaves those template files
untouched, and the drift keeper (:func:`check_seed_template_sync`) skips
their content but still requires them to exist. Today's entries: the seed's
own 001/003 migrations are applied in prod (ledger-checksummed ⇒ immutable),
while the template copies must be idempotent for ``migration_replay``.
KB § PATTERNS/backend/migration-chain-replay.md § The seed template.

``dry=True`` mirrors the script's ``--dry`` (reports, mutates nothing).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
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
# migration-checksum-ack.json pins THIS product's prod ledger state (ledger_checksums.py);
# a freshly scaffolded product has no applied history to acknowledge.
_TEMPLATE_EXTRA_EXCLUDES = _BACKUP_EXCLUDES | {"package-lock.json", "migration-checksum-ack.json"}

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

# The named seam where the template is ALLOWED to diverge from the seed.
# Data, not code: the sync and the drift keeper both read it, so neither can
# grow a private `if path == ...` exception the other does not know about.
DIVERGENCES_REL = Path("templates") / "product-seed-divergences.json"


def load_divergences(root: Path) -> dict[str, str]:
    """``{template-relative path: rationale}`` from the declared divergence list.

    A missing file means "no declared divergences" (synthetic test trees);
    the keeper separately refuses a real template without one. A malformed
    entry raises — a divergence without a rationale is a silent fork.
    """
    path = root / DIVERGENCES_REL
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for entry in data.get("divergences", []):
        rel = str(entry.get("path") or "").strip()
        why = str(entry.get("rationale") or "").strip()
        if not rel or not why or rel.startswith("/") or ".." in Path(rel).parts:
            raise ValueError(
                f"{DIVERGENCES_REL}: every divergence needs a template-relative "
                f"`path` and a one-line `rationale` (got {entry!r})"
            )
        out[rel] = why
    return out


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

    # `_REPO / "seed" / "lib"` names the seed DIRECTORY at the repo root —
    # it is the same path for every product and must NOT become
    # {{SCHEMA_NAME}}. It only survived this long because `products/seed/`
    # has schema "seed", so the wrong substitution was invisible there;
    # the first product scaffolded with any other schema got a conftest.py
    # pointing at `<repo>/<schema>/lib/backend`, which does not exist
    # (surfaced by igig, 2026-08-09). Protect the path idiom across the
    # blanket schema rewrite below, then restore it.
    _SEED_DIR_SENTINEL = "\x00SEED_DIR\x00"
    text = re.sub(
        r'(/\s*)"seed"(\s*/)',
        lambda m: f'{m.group(1)}{_SEED_DIR_SENTINEL}{m.group(2)}',
        text,
    )

    text = text.replace('"seed"', '"{{SCHEMA_NAME}}"')
    text = text.replace("'seed'", "'{{SCHEMA_NAME}}'")
    text = text.replace(_SEED_DIR_SENTINEL, '"seed"')
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
            r"container_name: dev-noctus-seed$",
            "container_name: dev-noctus-{{PRODUCT_SLUG}}",
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
        # this port is a faithful 1:1 of the script.
        #
        # This branch USED to say Dockerfile placeholderization was "owned
        # by propagate-dockerfiles.sh". No such file exists in scripts/ —
        # so the real answer was "nobody", and the seed's identity shipped
        # verbatim into the first product scaffolded after the gap opened
        # (igig, 2026-08-09: PRODUCT_SLUG=seed, container dead on arrival).
        # The template Dockerfile therefore keeps the seed's LITERALS, and
        # `scaffold_product` rewrites them per product via its
        # `dockerfile_rewrites` map. That is the owner. Fleet-wide keeper:
        # seed/lib/backend/tests/config/test_per_product_dockerfile_identity.py
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
        # `\bseed\b` is a BARE-WORD regex — deliberately broad so it
        # catches every quoting style a migration author might use for
        # the schema literal (`seed.table`, `seed`.invitations, etc.).
        # Applied to the WHOLE file that breadth also rewrites the
        # English WORD "seed" inside `--`-comment prose, producing
        # nonsense like "the {{SCHEMA_NAME}} → templates/product-
        # {{SCHEMA_NAME}} sync" (found in the template's own
        # 002/004/005 migrations — the comment never mentioned the
        # schema at all, it meant the literal word "seed"). Restrict the
        # substitution to non-comment lines: a line whose STRIPPED form
        # starts with `--` is a full-line SQL comment and is copied
        # through untouched. This does not handle a trailing inline
        # comment on a code line (`ALTER ... ; -- seed note`) — no
        # instance of that shape exists in the current seed migrations
        # (verified empirically), so a narrower per-line split isn't
        # warranted; if one appears, this comment is the pointer to
        # revisit.
        lines = text.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.strip().startswith("--"):
                continue
            line = re.sub(r"\bseed\b", "{{SCHEMA_NAME}}", line)
            line = line.replace("idx_seed_", "idx_{{SCHEMA_NAME}}_")
            lines[i] = line
        text = "".join(lines)

    return text


def _is_text_file(p: Path) -> bool:
    if p.suffix in _TEXT_SUFFIXES:
        return True
    return p.name.endswith(".env.example")


def _placeholderize_tree(tree: Path) -> None:
    """Apply :func:`_apply_placeholders` to every text file under ``tree``."""
    for p in tree.rglob("*"):
        if not p.is_file():
            continue
        if ".backup" in p.relative_to(tree).parts:
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


def _tree_files(tree: Path, excludes: set[str], *, git_root: Path | None = None) -> set[str]:
    """Relative file paths under ``tree``. With ``git_root``, only files git
    would commit (tracked + untracked-not-ignored) — so a local build cache in
    the working tree (``.ruff_cache``, ``tsbuildinfo``…) is not reported as drift."""
    candidates: list[Path]
    if git_root is not None:
        proc = subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard", "--", str(tree)],
            cwd=git_root, capture_output=True, text=True,
        )
        if proc.returncode == 0:
            candidates = [git_root / line for line in proc.stdout.splitlines() if line]
        else:
            candidates = list(tree.rglob("*"))
    else:
        candidates = list(tree.rglob("*"))
    out: set[str] = set()
    for p in candidates:
        rel = p.relative_to(tree)
        if _excluded(rel.parts, excludes) or _is_egg_info(rel.parts):
            continue
        if p.is_file() or p.is_symlink():
            out.add(rel.as_posix())
    return out


def check_seed_template_sync(repo_root: Path | None = None) -> list[dict]:
    """Drift keeper: ``templates/product-seed/`` == the seed rendered by this sync.

    Renders ``products/seed/`` exactly as :func:`sync_seed_template` would
    (copy + placeholderize, in a temp dir) and diffs it against the checked-
    in template. Declared divergences (``templates/product-seed-divergences.
    json``) are exempt from the CONTENT comparison only — each must still
    exist in the template, and must still name a file the seed ships (a
    divergence from nothing is a stale entry).
    """
    root = Path(repo_root) if repo_root else Path(REPO_ROOT)
    seed = root / "products" / "seed"
    template = root / "templates" / "product-seed"
    if not seed.is_dir() or not template.is_dir():
        return []

    def issue(rel: str, text: str) -> dict:
        return {
            "keeper": "check_seed_template_sync",
            "severity": "high",
            "file": f"templates/product-seed/{rel}" if rel else str(DIVERGENCES_REL),
            "issue": text,
        }

    issues: list[dict] = []
    if not (root / DIVERGENCES_REL).is_file():
        issues.append(issue("", (
            f"{DIVERGENCES_REL} is missing — the declared seed↔template divergence "
            "list is gone, so the next sync would overwrite the idempotent template "
            "migrations with the seed's applied (non-idempotent) ones."
        )))
    try:
        divergences = load_divergences(root)
    except (ValueError, json.JSONDecodeError) as exc:
        return issues + [issue("", f"{DIVERGENCES_REL} unreadable: {exc}")]

    with tempfile.TemporaryDirectory(prefix="seed-template-render-") as tmp:
        rendered = Path(tmp) / "product-seed"
        _copy_tree(seed, rendered, _TEMPLATE_EXTRA_EXCLUDES)
        _placeholderize_tree(rendered)
        git_root = root if (root / ".git").exists() else None
        seed_files = _tree_files(seed, _TEMPLATE_EXTRA_EXCLUDES, git_root=git_root)
        want = {r for r in _tree_files(rendered, _TEMPLATE_EXTRA_EXCLUDES) if r in seed_files}
        have = _tree_files(template, _TEMPLATE_EXTRA_EXCLUDES, git_root=git_root)

        for rel in sorted(divergences):
            if rel not in have:
                issues.append(issue(rel, (
                    f"declared divergence `{rel}` is missing from the template "
                    f"(rationale: {divergences[rel]}). Restore it, or drop the "
                    f"entry from {DIVERGENCES_REL}."
                )))
            if rel not in want:
                issues.append(issue(rel, (
                    f"declared divergence `{rel}` no longer exists in products/seed/ "
                    f"— a divergence from nothing is a stale entry; drop it from "
                    f"{DIVERGENCES_REL}."
                )))
        sync_hint = (
            "Edit products/seed/ and let the sync regenerate the template "
            "(`python mcp/noctusai/cli.py --sync-seed-template`); a template file "
            f"that must differ is declared in {DIVERGENCES_REL}."
        )
        for rel in sorted(want - have - set(divergences)):
            issues.append(issue(rel, f"`{rel}` is in products/seed/ but not in the template. {sync_hint}"))
        for rel in sorted(have - want - set(divergences)):
            issues.append(issue(rel, f"`{rel}` is in the template but not in products/seed/. {sync_hint}"))
        for rel in sorted((want & have) - set(divergences)):
            if (rendered / rel).read_bytes() != (template / rel).read_bytes():
                issues.append(issue(rel, f"`{rel}` differs from the seed's rendering. {sync_hint}"))
    return issues


def sync_seed_template(
    dry: bool = False,
    worktree_path: str | None = None,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Sync products/seed → templates/product-seed with placeholderization.

    ``repo_root`` is the explicit-root seam (tests, synthetic trees); callers
    inside a git worktree pass ``worktree_path`` instead.

    Returns ``{ok, dry, steps, validation, seed, template, message}``.
    """
    if repo_root is not None:
        root = Path(repo_root)
    else:
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
        try:
            for rel in load_divergences(root):
                steps.append(f"Would keep declared divergence {rel} (template copy untouched)")
        except (ValueError, json.JSONDecodeError) as exc:
            return {"ok": False, "dry": True, "steps": steps, "error": str(exc)}
        return {
            "ok": True,
            "dry": True,
            "steps": steps,
            "validation": [],
            "seed": str(seed),
            "template": str(template),
            "message": "Dry run complete — no changes made.",
        }

    try:
        divergences = load_divergences(root)
    except (ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "dry": False, "steps": steps, "error": str(exc)}
    stashed: dict[str, bytes | None] = {
        rel: ((template / rel).read_bytes() if (template / rel).is_file() else None)
        for rel in divergences
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
    _placeholderize_tree(template)
    steps.append("Replaced product values with placeholders")

    # ─── Step 3b: restore the declared divergences ───────────────────
    # The seed's rendering of a divergent path is discarded and the
    # template's own copy put back. A declared path whose template copy is
    # MISSING is not papered over with the seed's version (that would
    # silently undo the divergence): the rendered copy is removed and the
    # sync reports not-ok, so the drift keeper's existence leg blocks.
    divergence_errors: list[str] = []
    for rel, body in stashed.items():
        target = template / rel
        if body is None:
            if target.exists():
                target.unlink()
            divergence_errors.append(
                f"declared divergence {rel} is missing from the template — "
                f"restore it (or drop its entry from {DIVERGENCES_REL})"
            )
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    if stashed:
        steps.append(
            f"Kept {len(stashed) - len(divergence_errors)} declared divergence(s) "
            f"from {DIVERGENCES_REL}"
        )

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
        "ok": errors == 0 and not divergence_errors,
        "dry": False,
        "steps": steps,
        "validation": validation,
        "missing_placeholders": errors,
        "divergence_errors": divergence_errors,
        "seed": str(seed),
        "template": str(template),
        "message": (
            "; ".join(divergence_errors)
            if divergence_errors
            else "Sync complete!"
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


__all__ = [
    "DIVERGENCES_REL",
    "EXPECTED_PLACEHOLDERS",
    "check_seed_template_sync",
    "load_divergences",
    "register",
    "sync_seed_template",
]
