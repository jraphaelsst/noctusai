"""
Module-level schema cache for MockSupabaseClient validation.

Per `projects/mock-supabase-schema-validation` §7 Q5: rebuild-every-session
unconditionally. Parse cost is <100 ms for the full repo per Phase 0
benchmark. Avoids cache-invalidation failure modes.

The cache is populated once per Python process (first call to
`get_schema_map()`). To force a rebuild (useful only in meta-tests),
call `reset_cache()`.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable

from noctusai_lib.testing.migration_parser import parse_files

logger = logging.getLogger(__name__)

_CACHE: dict[str, set[str]] | None = None


def _discover_migration_files(repo_root: Path) -> list[Path]:
    """Walk `products/*/backend/migrations/*.sql` under a repo root, sorted.

    Sorted so numbered-prefix migrations apply in filename order. Non-migration
    files (mock_matching_seed.sql, etc.) are included — they either define
    tables or don't; harmless.
    """
    products_dir = repo_root / "products"
    if not products_dir.is_dir():
        return []
    files: list[Path] = []
    for product in sorted(products_dir.iterdir()):
        migrations_dir = product / "backend" / "migrations"
        if not migrations_dir.is_dir():
            continue
        files.extend(sorted(migrations_dir.glob("*.sql")))
    return files


def _walk_up_for_root(start: Path) -> Path | None:
    """Nearest ancestor of `start` (inclusive) with our repo-root shape."""
    candidate = start.resolve()
    for parent in [candidate] + list(candidate.parents):
        if (parent / "CLAUDE.md").is_file() and (parent / "products").is_dir():
            return parent
    return None


def _find_repo_root(start: Path | None = None) -> Path:
    """Locate the repo whose migrations describe the schema under test.

    🔴 THE ORDER HERE IS THE WHOLE POINT — it was wrong, and the failure
    was SILENT.

    This used to walk up from `__file__` and treat `NOCTUSAI_REPO_ROOT` as
    a last-resort fallback. Two consequences, both bad:

    1. **The "override" did not override.** The walk from `__file__`
       succeeds in any normal layout, so the env var was only ever read
       when it could not possibly help. Setting it deliberately did
       nothing.

    2. **A worktree validated the PRIMARY checkout's schema.** Running a
       product's tests from `.claude/worktrees/<slug>/` while
       `noctusai_lib` resolved to the primary tree (the default, unless
       PYTHONPATH is pointed at the worktree) made `__file__` land in the
       PRIMARY — so `get_schema_map()` parsed the PRIMARY's migrations. A
       column introduced by a migration that exists ONLY in the worktree
       was therefore unknown to the validator, which quietly skipped the
       assertion instead of failing. Tests went green **for the wrong
       reason** (2026-08-23; ledger `bb371551`).

    So resolution is now, in order:

    1. `NOCTUSAI_REPO_ROOT` — an explicit answer wins over any guess.
    2. The **current working directory's** enclosing repo. This is the
       tree whose migrations the runner meant, because pytest is invoked
       from it; it is right in a worktree and identical to (3) elsewhere.
    3. This file's own enclosing repo — the historical behaviour, kept as
       the fallback for callers with an unrelated cwd.
    """
    explicit = os.environ.get("NOCTUSAI_REPO_ROOT")
    if explicit:
        return Path(explicit).resolve()

    if start is not None:
        found = _walk_up_for_root(start)
        if found is not None:
            return found

    for origin in (Path.cwd(), Path(__file__)):
        found = _walk_up_for_root(origin)
        if found is not None:
            return found

    raise RuntimeError(
        "mock-schema: could not locate repo root (no parent with CLAUDE.md + products/). "
        "Set NOCTUSAI_REPO_ROOT to override."
    )


def get_schema_map() -> dict[str, set[str]]:
    """Return the cached `{qualified_table: {columns}}` map. Builds on first call."""
    global _CACHE
    if _CACHE is None:
        try:
            root = _find_repo_root()
            files = _discover_migration_files(root)
            _CACHE = parse_files(files)
            logger.debug(
                "mock-schema: built cache from %d migration files → %d tables",
                len(files),
                len(_CACHE),
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("mock-schema: cache build failed (%s) — validation disabled", exc)
            _CACHE = {}
    return _CACHE


def reset_cache() -> None:
    """Force the next get_schema_map() call to rebuild. Used by tests that
    assert parsing behavior."""
    global _CACHE
    _CACHE = None


def set_cache_for_tests(mapping: dict[str, set[str]] | dict[str, Iterable[str]]) -> None:
    """Inject a cache directly. Used by unit tests for MockSupabaseClient
    validation that don't want to parse the real migration corpus each run."""
    global _CACHE
    _CACHE = {table: set(cols) for table, cols in mapping.items()}


__all__ = ["get_schema_map", "reset_cache", "set_cache_for_tests"]
