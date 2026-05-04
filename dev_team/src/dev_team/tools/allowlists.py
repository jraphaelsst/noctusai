"""Per-agent tool allowlists — the 11×15 matrix.

Per design-reference.md §3, every role gets a curated subset of the
15-tool catalog. The Leader has delegation tools the specialists don't;
write_files is restricted to the implementer roles; etc.

This module is the SOURCE OF TRUTH for "what tools may agent X call."
Engineers building tool implementations register them here so the
matrix stays declarative and testable.
"""

from __future__ import annotations

from typing import Callable, Mapping

from dev_team.agents.base import AgentName

# Build-functions are filled in by the tools/B2-engineer-B work. Until
# then, the allowlist values are tool NAMES (strings); tools_for() will
# resolve to callables once the modules ship.
TOOL_ALLOWLIST: Mapping[AgentName, tuple[str, ...]] = {
    "leader": (
        "read_kb",
        "read_memory",
        "write_memory",
        "delegate",
        "invoke_subteam",
    ),
    "product_manager": (
        "read_kb",
        "read_memory",
        "write_memory",
        "web_search",
        "read_files",
    ),
    "ux_designer": (
        "read_kb",
        "read_memory",
        "write_memory",
        "web_search",
        "read_files",
    ),
    "solution_architect": (
        "read_kb",
        "read_memory",
        "write_memory",
        "read_files",
        "recurrence_scan",
        "keeper_validate",
        "ast_python",
        "ast_typescript",
    ),
    "backend_engineer": (
        "read_kb",
        "read_memory",
        "write_memory",
        "read_files",
        "write_files",
        "edit_files",
        "shell",
        "recurrence_scan",
        "ast_python",
    ),
    "frontend_engineer": (
        "read_kb",
        "read_memory",
        "write_memory",
        "read_files",
        "write_files",
        "edit_files",
        "shell",
        "recurrence_scan",
        "ast_typescript",
    ),
    "devops_engineer": (
        "read_kb",
        "read_memory",
        "write_memory",
        "read_files",
        "write_files",
        "edit_files",
        "shell",
        "ast_python",
        "ast_typescript",
    ),
    "security_engineer": (
        "read_kb",
        "read_memory",
        "write_memory",
        "read_files",
        "keeper_validate",
        "keeper_review",
        "web_search",
        "recurrence_scan",
    ),
    "qa_engineer": (
        "read_kb",
        "read_memory",
        "write_memory",
        "read_files",
        "write_files",
        "edit_files",
        "shell",
        "recurrence_scan",
        "ast_python",
        "ast_typescript",
    ),
    "code_reviewer": (
        "read_kb",
        "read_memory",
        "write_memory",
        "read_files",
        "recurrence_scan",
        "keeper_validate",
        "file_proposal",
    ),
    "technical_writer": (
        "read_kb",
        "read_memory",
        "write_memory",
        "read_files",
        "write_files",
        "edit_files",
    ),
}


def tools_for(name: AgentName) -> list[Callable]:
    """Resolve the role's allowlisted tool names to actual callables.

    Returns an EMPTY list if the tool implementations haven't shipped yet
    (the smoke test asserts the matrix is declared but does NOT require
    every callable to be wired — that's the job of tools/<name>.py
    modules in B2).

    Engineers building tool modules should append a build-function entry
    to ``_RESOLVERS`` below as they ship each tool.
    """
    names = TOOL_ALLOWLIST.get(name, ())
    return [_RESOLVERS[t]() for t in names if t in _RESOLVERS]


# Filled in by B2-engineer-B. Stub for now so smoke tests run.
_RESOLVERS: dict[str, Callable] = {}


__all__ = ["TOOL_ALLOWLIST", "tools_for"]
