"""dev_team — agno multi-agent dev team for NoctusAI.

Public surface:
    build_team()       -> agno.team.Team           # full dev_team
    build_leader()     -> agno.agent.Agent         # the Team Leader alone
    load_charter(name) -> str                      # markdown charter text
    MemoryStore        -> hybrid memory facade
    AgentName          -> Literal type of the 11 role names

Most callers should use :func:`build_team` and dispatch tasks via
``team.run(task=...)``. The CLI (``python -m dev_team``) and the MCP
tools at ``mcp/noctusai/tools/noctus/team/`` are the two intended
entrypoints.
"""

from __future__ import annotations

__version__ = "0.1.0"

# Lazy-load heavy attrs so `import dev_team` stays cheap even before agno
# / anthropic imports happen. Mirrors noctusai_lib's PEP 562 pattern.
_LAZY = {
    "build_team": ("dev_team.team", "build_team"),
    "build_leader": ("dev_team.leader", "build_leader"),
    "load_charter": ("dev_team.agents.base", "load_charter"),
    "MemoryStore": ("dev_team.memory", "MemoryStore"),
    "AgentName": ("dev_team.agents.base", "AgentName"),
}


def __getattr__(name: str):  # pragma: no cover — exercised via the test suite
    if name in _LAZY:
        module_name, attr = _LAZY[name]
        import importlib

        module = importlib.import_module(module_name)
        value = getattr(module, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'dev_team' has no attribute {name!r}")


def __dir__():
    return sorted(list(globals().keys()) + list(_LAZY.keys()))


__all__ = list(_LAZY.keys())
