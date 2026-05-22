"""Hierarchical tool registry for the Supabase connector MCP server.

Aggregation trio built once by `_kit.registry.build_registry` (shared
across every connector MCP). Tool naming follows the dotted convention
`supabase.<service>.<action>`.

LEAF_MODULES: `project` (list/get reads), `db` (query — confirm-gated for
writes, free for reads — plus the information_schema-backed list_tables /
list_schemas reads), `migration` (list read + confirm-gated apply write),
`diagnostics` (configured/reachable/authenticated tri-state signal). All
leaves talk to the Supabase Management API
(`https://api.supabase.com`) via the single `supabase.api.request_json`
seam.
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import db, diagnostics, migration, project

LEAF_MODULES = (db, diagnostics, migration, project)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
