"""Hierarchical tool registry for the WAHA connector MCP server.

Aggregation trio built once by `_kit.registry.build_registry` (shared
across every connector MCP). Tool naming follows the dotted convention
`waha.<service>.<action>`.

LEAF_MODULES: `session` (lifecycle), `message` (send/list + chat.list),
`server` (health/version, incl. unauthenticated ping), `diagnostics`
(configured/reachable/authenticated tri-state signal). All leaves talk
to the WAHA HTTP API via the single `waha.api.request_json` seam.
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import diagnostics, message, server, session

LEAF_MODULES = (diagnostics, message, server, session)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
