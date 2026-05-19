"""Hierarchical tool registry for the n8n connector MCP server.

Aggregation trio built once by `_kit.registry.build_registry` (shared
across every connector MCP). Tool naming follows the dotted convention
`n8n.<service>.<action>`.

LEAF_MODULES: `workflow` (list/get/activate/deactivate/update/create/
delete/set_tags), `execution` (history + failure diagnosis + delete),
`tag` (tag catalog), `diagnostics` (config/reachability signal). All
leaves talk to the n8n REST API via the single `n8n.api.request_json`
HTTP seam.
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import diagnostics, execution, tag, workflow

LEAF_MODULES = (diagnostics, execution, tag, workflow)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
