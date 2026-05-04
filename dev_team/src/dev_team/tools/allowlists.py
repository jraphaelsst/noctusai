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


# Filled in by B2-engineer-B. Each entry maps a tool NAME (as it appears in
# TOOL_ALLOWLIST values) to a zero-arg callable returning the agno-tool
# function. The build-functions live in sibling tool modules.
def _build_read_kb():
    from dev_team.tools.kb import build_read_kb_tool

    return build_read_kb_tool()


def _build_read_memory():
    from dev_team.tools.memory_tool import build_read_memory_tool

    return build_read_memory_tool()


def _build_write_memory():
    from dev_team.tools.memory_tool import build_write_memory_tool

    return build_write_memory_tool()


def _build_delegate():
    from dev_team.tools.delegation import build_delegate_tool

    return build_delegate_tool()


def _build_invoke_subteam():
    from dev_team.tools.delegation import build_invoke_subteam_tool

    return build_invoke_subteam_tool()


def _build_read_files():
    from dev_team.tools.files import build_read_files_tool

    return build_read_files_tool()


def _build_write_files():
    from dev_team.tools.files import build_write_files_tool

    return build_write_files_tool()


def _build_edit_files():
    from dev_team.tools.files import build_edit_files_tool

    return build_edit_files_tool()


def _build_shell():
    from dev_team.tools.shell import build_shell_tool

    return build_shell_tool()  # default empty allowlist; role wires its own


def _build_web_search():
    from dev_team.tools.web import build_web_search_tool

    return build_web_search_tool()


def _build_recurrence_scan():
    from dev_team.tools.recurrence import build_recurrence_scan_tool

    return build_recurrence_scan_tool()


def _build_keeper_validate():
    from dev_team.tools.keeper import build_keeper_validate_tool

    return build_keeper_validate_tool()


def _build_keeper_review():
    from dev_team.tools.keeper import build_keeper_review_tool

    return build_keeper_review_tool()


def _build_ast_python():
    from dev_team.tools.ast_tools import build_ast_python_tool

    return build_ast_python_tool()


def _build_ast_typescript():
    from dev_team.tools.ast_tools import build_ast_typescript_tool

    return build_ast_typescript_tool()


def _build_file_proposal():
    from dev_team.tools.proposals import build_file_proposal_tool

    return build_file_proposal_tool()


_RESOLVERS: dict[str, Callable] = {
    "read_kb": _build_read_kb,
    "read_memory": _build_read_memory,
    "write_memory": _build_write_memory,
    "delegate": _build_delegate,
    "invoke_subteam": _build_invoke_subteam,
    "read_files": _build_read_files,
    "write_files": _build_write_files,
    "edit_files": _build_edit_files,
    "shell": _build_shell,
    "web_search": _build_web_search,
    "recurrence_scan": _build_recurrence_scan,
    "keeper_validate": _build_keeper_validate,
    "keeper_review": _build_keeper_review,
    "ast_python": _build_ast_python,
    "ast_typescript": _build_ast_typescript,
    "file_proposal": _build_file_proposal,
}


__all__ = ["TOOL_ALLOWLIST", "tools_for"]
