"""Rewrite the dispatch of an EXECUTOR subagent that has no worktree to work in (adds `isolation: "worktree"`).

An executor (backend/frontend/devops-engineer, product-engineer) writes code; an
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
# The slug never ENDS in "." — a path closing a sentence ("…/worktrees/foo. Work only…")
# must resolve to `foo`, not the non-existent `foo.` (false refusal seen 2026-11-10).
_WT_RE = re.compile(r"(?P<abs>/[^\s'\"`()<>]*?)?\.claude/worktrees/(?P<slug>[A-Za-z0-9._-]*[A-Za-z0-9_-])")


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
    """None to allow; `{"decision": "allow", "updated_input": ...}` to REWRITE (add `isolation: "worktree"`)."""
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
    # REWRITE, not refuse (2026-11-14): the correct form is known, so produce it. The harness creates
    # a fresh isolated worktree for the subagent; nothing about the brief needs to change.
    return {
        "decision": "allow",
        "updated_input": {**tool_input, "isolation": "worktree"},
        "context": (
            f"[noc-guard:executor-dispatch] REWROTE this dispatch of executor '{subagent}' to "
            "`isolation: \"worktree\"`: the brief named no existing `.claude/worktrees/<slug>` directory, "
            "so the subagent would have written into the caller's tree (CLAUDE.md §1 self-branching). "
            "It now works in its own isolated worktree. To reuse a worktree you already started "
            "(`noctus.dev.task_branch action=start`), name its .claude/worktrees/<slug> path in the brief."
        ),
    }
