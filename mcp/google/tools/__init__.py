"""Hierarchical tool registry for the Google connector MCP server.

Each leaf module exports the uniform `HANDLERS` / `tool_descriptors()` /
`register(server)` contract; the aggregation trio is built once by the
shared `_kit.registry.build_registry` (same composition vista uses).

Tool naming follows the dotted convention: `google.<service>.<action>`.
"""
from __future__ import annotations

from _kit.registry import build_registry

from tools import calendar, drive, maps, youtube


LEAF_MODULES = (calendar, maps, youtube, drive)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
