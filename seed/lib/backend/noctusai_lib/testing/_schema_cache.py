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


def _find_repo_root(start: Path | None = None, *, module_file: str | None = None) -> Path:
    """Locate the repo whose migrations describe the schema under test.

    🔴 THE ORDER HERE IS THE WHOLE POINT, TWICE NOW — both times the
    failure was SILENT.

    Round 1 (2026-08-23, ledger `bb371551`): this used to walk up from
    `__file__` with `NOCTUSAI_REPO_ROOT` as a last resort. A worktree's
    test suite, invoked WITHOUT PYTHONPATH scoped at the worktree, ended
    up importing the PRIMARY checkout's `noctusai_lib` — so `__file__`
    landed in the primary, `get_schema_map()` parsed the primary's
    migrations, and a column that existed only in the worktree's own
    migration was quietly unknown to the validator instead of failing.
    The fix at the time swapped the order to prefer `Path.cwd()` over
    `Path(__file__)`, reasoning cwd is "right in a worktree and identical
    to `__file__` elsewhere."

    Round 2 (2026-09-18): that reasoning broke the INVERSE case. Invoke
    pytest with an absolute path into a worktree's test file while the
    shell's cwd is still the PRIMARY checkout, using the sanctioned
    worktree-scoped invocation (`noctus.dev.pytest(worktree_path=...)`,
    which scopes PYTHONPATH so the worktree's OWN `noctusai_lib` is
    imported — not the shared venv's editable primary copy). `__file__`
    now correctly lands in the worktree; cwd does not, but it was checked
    FIRST, so it won — the mock built its schema from the primary's
    migrations while validating the worktree's code. Two failures
    (`MockSchemaError: ... has no column ...`) that did not exist running
    the exact same tests from inside the worktree.

    The invariant that survives BOTH incidents: `Path(__file__)` is not a
    guess, it is a FACT about which copy of `noctusai_lib` the interpreter
    actually loaded — Python's import system caches one location per
    package in `sys.modules`, so whatever behaviour is executing IS that
    tree's code, by construction. `Path.cwd()` is pure ambient shell
    state and carries no such guarantee in either direction. Round 1's
    failure was not really "`__file__` is wrong" — it was "PYTHONPATH
    wasn't scoped, so the worktree's OWN `noctusai_lib` was never
    imported at all," a real bug one layer down that reordering only
    papered over. The sanctioned invocation path fixes that layer
    directly (KB § PATTERNS/common/methodology-execution-discipline.md
    § "resolve the root from the artefact under evaluation, never from
    the ambient cwd" — the same family as verdict-channel integrity and
    stale-interpreter detection: `migrate_product` reading the primary
    checkout and `absorption_tracking`'s asymmetry are instances 1-2 of
    the SAME root-resolution-from-cwd shape; this is 3 and 4 — N≥3, MUST
    formalize).

    So resolution is now, in order:

    1. `NOCTUSAI_REPO_ROOT` — an explicit answer wins over any guess.
    2. `start`, when the caller supplies one (advanced callers only —
       `get_schema_map()` itself does not).
    3. This file's own enclosing repo (`Path(__file__)`) — the artefact
       actually under evaluation, not the ambient invocation location.
    4. `Path.cwd()` — last resort, kept for callers with no better signal.

    Silence is what made round 2 cost an hour, so (3) and (4) are no
    longer allowed to disagree quietly: when both resolve to DIFFERENT
    valid repo roots, a WARNING names both and states which one won, so a
    future mismatch is visible in the test run itself instead of
    surfacing as a confusing `MockSchemaError` an hour later.

    `module_file` is a test-only DI seam (defaults to this module's real
    `__file__`) — tests exercising the file-vs-cwd precedence inject a
    fake location through it rather than monkeypatching `__file__` on the
    live module (KB § PATTERNS/backend/di-test-seam.md).
    """
    explicit = os.environ.get("NOCTUSAI_REPO_ROOT")
    if explicit:
        return Path(explicit).resolve()

    if start is not None:
        found = _walk_up_for_root(start)
        if found is not None:
            return found

    file_root = _walk_up_for_root(Path(module_file if module_file is not None else __file__))
    cwd_root = _walk_up_for_root(Path.cwd())

    if file_root is not None and cwd_root is not None and file_root != cwd_root:
        logger.warning(
            "mock-schema: repo-root candidates disagree — this module's own "
            "location resolves to %s, the current working directory resolves "
            "to %s. Trusting %s (the tree whose noctusai_lib is ACTUALLY "
            "loaded — Python caches one location per package, so this is a "
            "fact about what's executing, not a guess). If that's wrong for "
            "your invocation, set NOCTUSAI_REPO_ROOT explicitly.",
            file_root, cwd_root, file_root,
        )

    if file_root is not None:
        return file_root
    if cwd_root is not None:
        return cwd_root

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
