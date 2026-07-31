"""Hierarchical tool registry for the n8n connector MCP server.

Aggregation trio built once by `_kit.registry.build_registry` (shared
across every connector MCP). Tool naming follows the dotted convention
`n8n.<service>.<action>`.

LEAF_MODULES: `workflow` (list/get/activate/deactivate/update/create/
delete/set_tags), `execution` (history + failure diagnosis + delete),
`tag` (tag catalog), `credential` (create/delete/schema — so workflows
stop hard-coding secrets inline; no list/get by n8n design),
`diagnostics` (config/reachability signal). Every leaf builds its
client through `mcp/n8n/client.get_client()` and talks to n8n via
`noctusai_lib.integrations.n8n`'s `N8nClient` Protocol (Fake/Real,
shared with every other seed consumer) — no connector-side HTTP.
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import credential, diagnostics, execution, tag, workflow

LEAF_MODULES = (credential, diagnostics, execution, tag, workflow)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
