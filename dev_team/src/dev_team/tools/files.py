"""File I/O tools — `read_files`, `write_files`, `edit_files`.

Per design-reference.md §3:
- ``write_files`` is restricted to implementer roles (allowlist enforced).
- ``edit_files`` MUST be AST-driven; regex edits are forbidden
  (`feedback_ast_first`).

Path safety: writes are confined to the repo root. Symlink-escapes refused.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from dev_team.tools._mcp_path import repo_root


def _resolve_within_repo(path: str) -> Path:
    """Return absolute path under the repo root or raise ValueError."""
    root = repo_root().resolve()
    candidate = (root / path).resolve()
    if not str(candidate).startswith(str(root)):
        raise ValueError(
            f"path {path!r} escapes the repo root {root}; refusing."
        )
    return candidate


def read_files(paths: Iterable[str]) -> dict[str, str]:
    """Read multiple files, return ``{path: contents}``.

    Args:
        paths: Iterable of repo-relative or absolute paths under the repo root.

    Returns:
        Dict mapping the input path to file contents.

    Raises:
        FileNotFoundError: any of the paths does not exist.
        ValueError: any path escapes the repo root.
    """
    out: dict[str, str] = {}
    for path in paths:
        target = _resolve_within_repo(path)
        if not target.exists():
            raise FileNotFoundError(f"file not found: {path}")
        out[path] = target.read_text(encoding="utf-8")
    return out


def write_files(files: Mapping[str, str]) -> dict[str, str]:
    """Write multiple files. Creates parent directories as needed.

    Args:
        files: ``{path: content}`` map. Paths must resolve under the repo root.

    Returns:
        Dict ``{path: "ok"}`` for successful writes.

    Raises:
        ValueError: any path escapes the repo root.
    """
    out: dict[str, str] = {}
    for path, content in files.items():
        target = _resolve_within_repo(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        out[path] = "ok"
    return out


def edit_files(
    edits: Iterable[Mapping[str, Any]],
    *,
    mode: str = "ast",
) -> list[dict[str, Any]]:
    """AST-driven edits across one or more files.

    Args:
        edits: Iterable of edit dicts. Each MUST specify the AST action
            (e.g. ``{"path": "...", "action": "rename", "old": "x", "new": "y"}``).
            See :mod:`dev_team.tools.ast_tools` for the canonical action list.
        mode: MUST be ``"ast"``. Regex / sed / plain string-replace are
            refused per `feedback_ast_first` — code edits go through libcst /
            ts-morph.

    Raises:
        ValueError: ``mode`` is not ``"ast"``.

    Returns:
        List of per-edit result dicts (delegates to ``ast_tools``).
    """
    if mode != "ast":
        raise ValueError(
            f"edit_files requires mode='ast'; got {mode!r}. "
            "Regex / sed / plain-string code edits are forbidden "
            "(see KB § PATTERNS/ast.md). Use mode='ast' with libcst / ts-morph."
        )
    from dev_team.tools.ast_tools import apply_edit

    return [apply_edit(edit) for edit in edits]


def build_read_files_tool(**kwargs) -> Callable:
    return read_files


def build_write_files_tool(**kwargs) -> Callable:
    return write_files


def build_edit_files_tool(**kwargs) -> Callable:
    return edit_files


__all__ = [
    "read_files",
    "write_files",
    "edit_files",
    "build_read_files_tool",
    "build_write_files_tool",
    "build_edit_files_tool",
]
