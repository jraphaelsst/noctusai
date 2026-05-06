"""Shared file-walk helpers for ``noctus.seed.*`` tools.

Three tools (``scan_repetition``, ``audit_drift``, and the future
``absorb_file``) walk the same product/template trees and need the same
skip lists. Extracted here at N=2 (between ``scan_repetition`` and
``audit_drift``) so the third caller doesn't trigger DRY mandatory
formalization later — get the shape right early.

Public API:
- :data:`SKIP_DIR_NAMES` — directories to never descend into.
- :data:`SKIP_FILE_SUFFIXES` — file extensions to never read.
- :data:`SKIP_FILENAMES` — specific file basenames to never read.
- :func:`walk_files` — yield non-skipped files under a root, with
  directory pruning.

Each consumer can extend the defaults via local sets if it needs stricter
filters; the defaults match the platform-wide shape (Python / TypeScript
projects, Vite + node_modules + dist artifacts).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


# Directories that are NEVER absorption / drift candidates — generated,
# vendored, or product-by-definition. Pruning happens at descent, so these
# subtrees don't even get walked.
SKIP_DIR_NAMES: frozenset[str] = frozenset({
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".backup",
    "playwright-report",
    "test-results",
    ".pytest_cache",
    ".venv",
    "venv",
    ".egg-info",
    "coverage",
    ".turbo",
    ".next",
})

# Binary / generated file extensions — comparing bytes is meaningful but
# diffing or text-grouping is not, so we skip outright.
SKIP_FILE_SUFFIXES: frozenset[str] = frozenset({
    ".pyc",
    ".lock",
    ".log",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".pdf", ".zip", ".gz", ".tar", ".bz2",
    ".woff", ".woff2", ".ttf", ".otf",
    ".mp3", ".mp4", ".webm", ".mov",
    ".so", ".dylib", ".dll", ".class",
})

# Specific filenames that are always either generated or platform-noise —
# duplication between products there is meaningless.
SKIP_FILENAMES: frozenset[str] = frozenset({
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    ".DS_Store",
})


def walk_files(
    root: Path,
    *,
    extra_skip_dirs: frozenset[str] = frozenset(),
    extra_skip_suffixes: frozenset[str] = frozenset(),
    extra_skip_filenames: frozenset[str] = frozenset(),
) -> Iterable[Path]:
    """Yield every regular file under ``root`` that survives the skip lists.

    Pruning is applied at directory descent so we never recurse into
    ``node_modules`` etc. Extension and filename filters apply at file
    visit time.

    Args:
        root: Walk root. If not a directory, yields nothing (no-raise).
        extra_skip_dirs: Additional directory names beyond
            :data:`SKIP_DIR_NAMES`.
        extra_skip_suffixes: Additional file extensions beyond
            :data:`SKIP_FILE_SUFFIXES`.
        extra_skip_filenames: Additional basenames beyond
            :data:`SKIP_FILENAMES`.
    """
    if not root.is_dir():
        return

    skip_dirs = SKIP_DIR_NAMES | extra_skip_dirs
    skip_suffixes = SKIP_FILE_SUFFIXES | extra_skip_suffixes
    skip_filenames = SKIP_FILENAMES | extra_skip_filenames

    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except (OSError, PermissionError):
            continue
        for entry in entries:
            if entry.name in skip_dirs:
                continue
            if entry.is_dir():
                stack.append(entry)
            elif entry.is_file():
                if entry.name in skip_filenames:
                    continue
                if entry.suffix.lower() in skip_suffixes:
                    continue
                yield entry
