"""Deny dispatching an EXECUTOR subagent with no worktree to work in.

An executor (backend/frontend/devops-engineer, engineer-seed) writes code; an
executor launched with neither `isolation: "worktree"` nor a brief naming an
EXISTING `.claude/worktrees/<slug>` directory writes into whatever tree the
caller sits in — the shared primary on `dev` (CLAUDE.md §1 self-branching).
Gate at the dispatch, not at the first write.

The EXECUTOR set is DERIVED from `.claude/agents/*.md`: a file whose frontmatter
`description` contains the word EXECUTOR. Never a hand-listed constant.

Stdlib-only (runs under the hook's bare `python3`). Pure functions: `decide`
takes `agents_dir` / `roots` parameters (the test seam) — no patching needed.
KB § PATTERNS/common/self-branching-mode.md §11.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_DISPATCH_TOOLS = {"Agent", "Task"}
_EXECUTOR_RE = re.compile(r"\bEXECUTOR\b")
_WT_RE = re.compile(r"(?P<abs>/[^\s'\"`()<>]*?)?\.claude/worktrees/(?P<slug>[A-Za-z0-9._-]+)")


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    out: dict[str, str] = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def executor_names(agents_dir: Path) -> set[str]:
    names: set[str] = set()
    for f in sorted(agents_dir.glob("*.md")):
        fm = _frontmatter(f.read_text(encoding="utf-8"))
        if _EXECUTOR_RE.search(fm.get("description", "")):
            names.add(fm.get("name") or f.stem)
    return names


def _referenced_worktree_exists(prompt: str, roots: list[Path]) -> bool:
    for m in _WT_RE.finditer(prompt):
        slug = m.group("slug")
        abs_prefix = m.group("abs")
        if abs_prefix is not None and abs_prefix:
            if (Path(abs_prefix) / ".claude" / "worktrees" / slug).is_dir():
                return True
        for root in roots:
            if (root / ".claude" / "worktrees" / slug).is_dir():
                return True
    return False


def decide(
    tool_name: str,
    tool_input: dict[str, Any] | None,
    agents_dir: Path,
    roots: list[Path],
) -> dict[str, Any] | None:
    """None to allow; `{"reason": ...}` to deny."""
    if tool_name not in _DISPATCH_TOOLS:
        return None
    tool_input = tool_input or {}
    subagent = tool_input.get("subagent_type")
    if not isinstance(subagent, str) or subagent not in executor_names(agents_dir):
        return None
    if tool_input.get("isolation") == "worktree":
        return None
    prompt = tool_input.get("prompt")
    if isinstance(prompt, str) and _referenced_worktree_exists(prompt, roots):
        return None
    return {
        "reason": (
            f"REFUSED — executor subagent '{subagent}' dispatched without a worktree: "
            "`isolation` is not \"worktree\" and the brief names no existing "
            "`.claude/worktrees/<slug>` directory, so it would write into the caller's "
            "tree (CLAUDE.md §1 self-branching). First run "
            "`noctus.dev.task_branch action=start slug=<slug> confirm=True`, then name the "
            "worktree path (.claude/worktrees/<slug>) in the brief — or pass "
            "`isolation: \"worktree\"`."
        )
    }
