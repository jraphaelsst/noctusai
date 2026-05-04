"""KB read tool — `read_kb(path, section?)`.

Per design-reference.md §3:
- Per-agent allowlist + section-anchored + size-capped.
- Path MUST start with `KNOWLEDGE-BASE/` (no escaping the KB root).

We don't enforce per-agent KB allowlists at THIS layer — that's a charter +
allowlist matrix concern. The tool itself only enforces the path root rule
and section anchoring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from dev_team.tools._mcp_path import repo_root


def _resolve_kb_path(path: str) -> Path:
    """Validate and resolve a KB path. Raises ValueError on escape attempts."""
    if not path.startswith("KNOWLEDGE-BASE/"):
        raise ValueError(
            f"read_kb path must start with 'KNOWLEDGE-BASE/' — got {path!r}. "
            "KB reads are scoped to KB; use read_files for repo paths."
        )
    root = repo_root()
    kb_root = root / "KNOWLEDGE-BASE"
    target = (root / path).resolve()
    if not str(target).startswith(str(kb_root.resolve())):
        raise ValueError(
            f"resolved path {target} escapes KNOWLEDGE-BASE/ root — refusing."
        )
    return target


def _extract_section(body: str, section: str) -> str:
    """Return the markdown section starting at the first heading matching
    `section` (case-sensitive substring match against heading text)."""
    lines = body.splitlines()
    out: list[str] = []
    in_section = False
    section_level: int | None = None
    for line in lines:
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            heading_text = line.lstrip("#").strip()
            if not in_section:
                if section in heading_text:
                    in_section = True
                    section_level = level
                    out.append(line)
                continue
            # already in section — stop at next heading at same/higher level
            assert section_level is not None
            if level <= section_level:
                break
            out.append(line)
        elif in_section:
            out.append(line)
    if not in_section:
        raise ValueError(f"section {section!r} not found in KB doc")
    return "\n".join(out)


def read_kb(path: str, section: str | None = None, *, max_chars: int = 60_000) -> str:
    """Read a KB document, optionally scoped to a section.

    Args:
        path: Must start with ``KNOWLEDGE-BASE/`` (e.g. ``KNOWLEDGE-BASE/01-PHILOSOPHY.md``).
        section: Optional heading text substring; returns just that section
            up to the next same-or-higher-level heading.
        max_chars: Hard cap to keep agent context bounded. Defaults to 60K.

    Returns:
        The (possibly section-scoped) markdown body, truncated at ``max_chars``.

    Raises:
        ValueError: path escapes KB or section not found.
        FileNotFoundError: KB file does not exist.
    """
    target = _resolve_kb_path(path)
    if not target.exists():
        raise FileNotFoundError(f"KB doc not found: {path}")
    body = target.read_text(encoding="utf-8")
    if section is not None:
        body = _extract_section(body, section)
    if len(body) > max_chars:
        body = body[:max_chars] + f"\n\n... [truncated at {max_chars} chars]"
    return body


def build_read_kb_tool(**kwargs) -> Callable[..., str]:
    """Return the agno-compatible KB-read tool callable.

    The returned function carries type hints + docstring, which agno reads
    when wiring tool schemas.
    """
    return read_kb


__all__ = ["read_kb", "build_read_kb_tool"]
