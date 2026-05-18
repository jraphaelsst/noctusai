"""Connector-MCP shared tool-registry aggregation.

Generalized from `mcp/vista/tools/__init__.py`. Per `KB § PATTERNS/
mcp-tool-conventions.md § 3`, each leaf tool module exports:
  - `HANDLERS`            — {dotted_tool_name: async-handler}
  - `tool_descriptors()`  — list[Tool] advertised to the host
  - `register(server)`    — compatibility hook

`build_registry(leaf_modules)` walks that uniform contract once and
returns the `(all_handlers, all_descriptors, register_all)` trio the
connector's `tools/__init__.py` re-exports — byte-for-byte the same
aggregation vista did inline, just parameterized on the module tuple.
"""
from __future__ import annotations

from typing import Callable, Sequence


def build_registry(leaf_modules: Sequence) -> tuple[
    Callable[[], dict],
    Callable[[], list],
    Callable[[object], None],
]:
    """Return `(all_handlers, all_descriptors, register_all)` for the given
    leaf modules. Each module must expose `HANDLERS`, `tool_descriptors()`,
    and `register(server)` — the vista leaf-module contract."""
    modules = tuple(leaf_modules)

    def all_handlers() -> dict:
        """Aggregate {tool_name: async-handler} across every leaf module."""
        out: dict = {}
        for mod in modules:
            out.update(mod.HANDLERS)
        return out

    def all_descriptors() -> list:
        """Aggregate Tool descriptors across every leaf module."""
        out: list = []
        for mod in modules:
            out.extend(mod.tool_descriptors())
        return out

    def register_all(server) -> None:
        """Compatibility entry — servers use all_handlers()/all_descriptors()."""
        for mod in modules:
            mod.register(server)

    return all_handlers, all_descriptors, register_all


__all__ = ["build_registry"]
