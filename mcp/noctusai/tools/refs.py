"""`noctusai_refs` — find all references to a slug / path / symbol across
the repo. Used before deleting a project folder, renaming a module, or
cleaning up after a closed initiative.

Replaces the manual `grep -rln "<pattern>" CLAUDE.md KNOWLEDGE-BASE
projects products/*/projects mcp` ritual that was run 8× during the
2026-04-28 closed-folder cleanup. Returns structured matches grouped by
file with line numbers + context.

**What it scans (in order):**
- `CLAUDE.md`, `OPENAI.md`, `LGPD-WARNINGS.md` (root-level docs)
- `KNOWLEDGE-BASE/**/*.md`
- `projects/**/PROJECT.md` + `products/*/projects/**/PROJECT.md` + `core/projects/**/PROJECT.md`
- `mcp/**/*.py` + `mcp/**/*.md`
- `seed/**/*.py` + `seed/**/*.ts` + `seed/**/*.tsx`
- `products/**/*.py` + `products/**/*.ts` + `products/**/*.tsx`
- `scripts/**/*` (sh + py)
- `templates/**/*.md`

**Excludes:** `node_modules/`, `.venv/`, `venv/`, `dist/`, `__pycache__/`,
`.git/`, image/binary files. The exclusion list mirrors `.gitignore`
spirit + adds vendored deps that grep would otherwise traverse forever.

**Pattern shape:** literal string match (case-sensitive) by default.
Future expansion: regex mode via `regex=True` kwarg if recurrence rule
trips at N=3+ usages needing it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]


# Directories to skip during the walk. Matches `.gitignore` spirit + vendored
# deps that grep would traverse forever.
_EXCLUDED_DIRS: set[str] = {
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".git",
    ".github",
    ".claude",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "playwright-report",
    "test-results",
}

# File extensions to scan. Anything not in this list is skipped (binaries,
# images, lock files, generated artifacts).
_SCANNED_EXTENSIONS: set[str] = {
    ".md",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".sh",
    ".sql",
    ".toml",
    ".json",  # for package.json / pyproject.toml metadata
    ".yaml",
    ".yml",
}


@dataclass
class Match:
    """One match — file path + line number + line content."""
    file: str
    line: int
    text: str


@dataclass
class RefsResult:
    """Result of a `find_refs` call."""
    pattern: str
    total_files: int  # files scanned (post-filter)
    total_matches: int
    matches: list[Match]

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern,
            "total_files": self.total_files,
            "total_matches": self.total_matches,
            "matches_by_file": _group_by_file(self.matches),
        }


def _group_by_file(matches: Iterable[Match]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for m in matches:
        grouped.setdefault(m.file, []).append({"line": m.line, "text": m.text})
    return grouped


def _should_skip_dir(name: str) -> bool:
    return name.startswith(".") or name in _EXCLUDED_DIRS


def _walk_repo(root: Path) -> Iterable[Path]:
    """Recursive walk skipping excluded dirs + non-scannable extensions."""
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        # Skip if any parent dir is excluded.
        try:
            relative_parts = path.relative_to(root).parts
        except ValueError:
            logger.warning("refs: path outside repo root, skipping: %s", path)
            continue
        if any(_should_skip_dir(part) for part in relative_parts[:-1]):
            continue
        if path.suffix.lower() not in _SCANNED_EXTENSIONS:
            continue
        yield path


def find_refs(pattern: str, repo_root: Path | None = None) -> RefsResult:
    """Find every line containing `pattern` (literal, case-sensitive)
    across the repo. Returns structured matches.
    """
    root = repo_root or REPO_ROOT
    matches: list[Match] = []
    files_scanned = 0
    if not pattern:
        return RefsResult(pattern=pattern, total_files=0, total_matches=0, matches=[])

    for path in _walk_repo(root):
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning("refs: cannot read %s (%s), skipping", path, exc)
            continue
        files_scanned += 1
        if pattern not in content:
            continue
        try:
            relative = str(path.relative_to(root))
        except ValueError:
            logger.warning("refs: path outside repo root, using absolute: %s", path)
            relative = str(path)
        for lineno, line in enumerate(content.splitlines(), start=1):
            if pattern in line:
                # Truncate long lines (300 chars) so output stays readable.
                text = line if len(line) <= 300 else line[:297] + "..."
                matches.append(Match(file=relative, line=lineno, text=text.strip()))
    return RefsResult(
        pattern=pattern,
        total_files=files_scanned,
        total_matches=len(matches),
        matches=matches,
    )


def register(server) -> None:
    @server.tool(
        name="noctusai_refs",
        description=(
            "Find every reference to a literal pattern across CLAUDE.md / KB / "
            "projects / mcp / seed / products. Replaces the manual `grep -rln` ritual "
            "run before deletes / renames / closures."
        ),
    )
    def _refs(pattern: str) -> dict:
        return find_refs(pattern).to_dict()
