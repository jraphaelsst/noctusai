"""Hierarchical tool registry for the Hostinger connector MCP server.

Aggregation trio built once by `_kit.registry.build_registry` (shared
across every connector MCP). Tool naming follows the dotted convention
`hostinger.<service>.<action>`.

LEAF_MODULES: `vps` (list/get/metrics/actions reads + restart/start/stop
power writes), `diagnostics` (configured/reachable/authenticated
quad-state signal). All leaves talk to the Hostinger Developers API via
the single `hostinger.api.request_json` seam.
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import diagnostics, vps

LEAF_MODULES = (diagnostics, vps)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
