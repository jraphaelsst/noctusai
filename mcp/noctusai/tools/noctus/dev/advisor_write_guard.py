"""Keep a spec-writing ADVISOR's `Write` inside its spec/notes paths (owner decision D34, 2026-11-09).

`product-manager`, `product-architect` and `product-designer` carry the `Write` tool so they can author spec / notes /
mockup files, but their agent files promise "never product/seed source, KB, config or git". Before this guard that
promise was prompt-only. A subagent's tool call reaches the PreToolUse hook with `agent_type` in the payload, which is
the attribution a branch-level keeper cannot have (the tech-lead commits their files from its own branch).

An advisor-writer is DERIVED from `.claude/agents/*.md`: frontmatter `tools` lists `Write` AND `description` says
ADVISOR (never a hand-listed constant; a fourth such agent is covered the day its file lands). Allowed write targets:
  - any path under a `scratchpad/` directory (the dir the brief names), and
  - `projects/<slug>/spec/...` (product-designer: `projects/<slug>/mockups/...`; table `ALLOWED_SUBDIRS`).
Anything else is a finding. Verdict is `{"reason": ...}` to deny, None to allow; the HOOK decides shadow vs enforce
(`MODE`), so this module stays a pure function.

Stdlib-only (runs under the hook's bare `python3`). KB § PATTERNS/common/gate-methodology-sync.md.
"""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
# warn-first (owner: start in shadow like check_decision_log_schema). Promote to "enforce" on evidence from
# `noctus.dev.gate_alignment walls` (a shadow warn on a path the agent legitimately needed = widen the allowlist).
MODE = "shadow"
ALLOWED_SUBDIRS: dict[str, tuple[str, ...]] = {"product-designer": ("mockups",)}
DEFAULT_SUBDIRS = ("spec",)
_ADVISOR_RE = re.compile(r"\bADVISOR\b")


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


def advisor_writers(agents_dir: Path) -> set[str]:
    names: set[str] = set()
    for f in sorted(agents_dir.glob("*.md")):
        fm = _frontmatter(f.read_text(encoding="utf-8"))
        tools = {t.strip() for t in fm.get("tools", "").split(",")}
        if "Write" in tools and _ADVISOR_RE.search(fm.get("description", "")):
            names.add(fm.get("name") or f.stem)
    return names


def _allowed(path: str, agent: str, roots: list[Path]) -> bool:
    p = PurePosixPath(path)
    parts = p.parts
    if ".." in parts:
        return False
    if "scratchpad" in parts[:-1]:
        return True
    rel = p
    if p.is_absolute():
        rel = None
        for r in roots:
            try:
                rel = p.relative_to(PurePosixPath(str(r)))
                break
            except ValueError:
                continue
        if rel is None:  # absolute and outside every repo root and not a scratchpad: not a spec path
            return False
    rp = rel.parts
    # strip a leading `.claude/worktrees/<slug>/` so a worktree-relative spec path counts the same
    if len(rp) > 3 and rp[0] == ".claude" and rp[1] == "worktrees":
        rp = rp[3:]
    subdirs = ALLOWED_SUBDIRS.get(agent, DEFAULT_SUBDIRS)
    return len(rp) >= 4 and rp[0] == "projects" and rp[2] in subdirs


def decide(tool_name: str, tool_input: dict[str, Any] | None, agent_type: str | None, agents_dir: Path,
           roots: list[Path]) -> dict[str, Any] | None:
    """None to allow; `{"reason": ..., "agent": ..., "target": ...}` for a write outside the advisor's paths."""
    if tool_name not in WRITE_TOOLS or not agent_type:
        return None
    if agent_type not in advisor_writers(agents_dir):
        return None
    target = (tool_input or {}).get("file_path") or (tool_input or {}).get("notebook_path")
    if not isinstance(target, str) or not target:
        return {"reason": f"advisor '{agent_type}' called {tool_name} with no file_path; cannot judge, refusing.",
                "agent": agent_type, "target": ""}
    if _allowed(target, agent_type, roots):
        return None
    sub = "/".join(ALLOWED_SUBDIRS.get(agent_type, DEFAULT_SUBDIRS))
    return {"reason": (f"advisor '{agent_type}' may Write only spec/notes files: under the scratchpad directory its "
                       f"brief names, or projects/<slug>/{sub}/ — not '{target}'. Never product/seed source, KB, "
                       "config or git (its agent file). Return the content to the tech-lead instead."),
            "agent": agent_type, "target": target}
