"""Hierarchical tool registry for the Cloudflare connector MCP server.

Aggregation trio built once by `_kit.registry.build_registry` (shared
across every connector MCP). Tool naming follows the dotted convention
`cloudflare.<service>.<action>`.

LEAF_MODULES: `zones` (list/get reads + create write), `dns`
(list/get reads + create/update/delete writes), `tunnel`
(list/get/get_config reads + create/delete/update_config writes),
`cache` (purge write — edge cache purge by URL or whole-zone),
`diagnostics` (configured/reachable/authenticated quad-state signal).
All leaves talk to the Cloudflare API v4 via the single
`cloudflare.api.request_json` / `request_envelope` seam.
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import cache, diagnostics, dns, rulesets, tunnel, zones

LEAF_MODULES = (cache, diagnostics, dns, rulesets, tunnel, zones)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
