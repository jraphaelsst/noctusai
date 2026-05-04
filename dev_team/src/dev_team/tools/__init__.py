"""dev_team tool catalog.

15 tools (per design-reference.md §3) with per-agent allowlists at
:mod:`dev_team.tools.allowlists`. Each tool module exports a
``build_<tool>_tool()`` factory; allowlists.tools_for(name) returns the
list of tool callables a given role may use.

Most tools are thin wrappers over existing ``noctus.dev.*`` MCP tools —
we don't re-implement what the dev MCP already exposes.
"""

from __future__ import annotations

from dev_team.tools.allowlists import TOOL_ALLOWLIST, tools_for

__all__ = ["TOOL_ALLOWLIST", "tools_for"]
