"""Hierarchical tool registry for the Meta connector MCP server.

Aggregation trio built once by `_kit.registry.build_registry` (shared
across every connector MCP). Tool naming follows the dotted convention
`meta.<service>.<action>`.

LEAF_MODULES aggregates four leaves: `whatsapp` (WAHA outbound +
inbound parse), `facebook` / `instagram` (Graph read-only Page + IG
surface), `diagnostics` (adapter introspection + OAuth scope
resolution). The Graph leaves wrap `noctusai_lib.integrations.meta`
(present in the tree post social-wiring absorption).
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import ads, diagnostics, facebook, instagram, whatsapp

LEAF_MODULES = (ads, diagnostics, facebook, instagram, whatsapp)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
