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


def _find_repo_root(start: Path | None = None) -> Path:
    """Walk up from start (default: this file) looking for a `products/` dir sibling
    to a `CLAUDE.md` — our repo-root shape."""
    candidate = (start or Path(__file__)).resolve()
    for parent in [candidate] + list(candidate.parents):
        if (parent / "CLAUDE.md").is_file() and (parent / "products").is_dir():
            return parent
    # Fallback: env override for non-standard layouts / test harnesses.
    env_root = os.environ.get("NOCTUSAI_REPO_ROOT")
    if env_root:
        return Path(env_root).resolve()
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
