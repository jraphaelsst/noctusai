"""Regression guard: build_server() must register EVERY tool.

Root cause (2026-06-03): newer mcp/pydantic builds a structured-output pydantic
model FROM each tool's return annotation and raises PydanticUserError on any
non-BaseModel return (`list[...]`, `dict | list`, …). Because `register_all`
registers tools in one loop, the FIRST such tool aborted the loop → the ENTIRE
server came up with a truncated tool set (or none), and every
`*_tool_in_server_registry` test failed. `build_server` now defaults
`structured_output=False` fleet-wide (the toolkit returns plain JSON, not
BaseModels), so a list/union return annotation is informational, not a schema
source. These tests pin that contract so a future tool returning `list[...]`
can never silently truncate the registry again.
"""
from __future__ import annotations


def test_build_server_registers_full_tool_set():
    from server import build_server

    s = build_server()
    tools = s._tool_manager._tools
    # The toolkit ships 200+ tools; a structured-output abort historically
    # truncated this to a partial set. Guard generously.
    assert len(tools) > 200, f"only {len(tools)} tools registered — register_all likely aborted early"


def test_list_returning_tools_are_registered():
    """The tools whose return annotation is a bare `list[...]` / union were the
    ones that aborted registration. They MUST all be present."""
    from server import build_server

    s = build_server()
    tools = s._tool_manager._tools
    # representative list/union-returning tools across modules
    for name in (
        "noctus.dev.kb_search",          # -> list[dict]
        "noctus.dev.code_search",        # -> list[dict]
        "noctus.dev.absorption_query",   # -> list[dict]
        "noctus.dev.keeper_pattern_list",  # -> list[str]
        "noctus.dev.archive",            # downstream of the abort point
    ):
        assert name in tools, f"{name} missing — structured-output abort regression"
