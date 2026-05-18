"""Hierarchical tool registry for the Meta connector MCP server.

Aggregation trio built once by `_kit.registry.build_registry` (shared
across every connector MCP). Tool naming follows the dotted convention
`meta.<service>.<action>`.

LEAF_MODULES is the WhatsApp slice only this wave. `facebook`,
`instagram`, `diagnostics` leaves are intentionally absent — their
backing seed package (`noctusai_lib.integrations.meta`) does not exist;
see `mcp/meta/README.md`. They drop in here unchanged once the seed
adapter ships.
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import whatsapp

LEAF_MODULES = (whatsapp,)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
