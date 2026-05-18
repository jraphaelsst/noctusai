"""Hierarchical tool registry for the Vista MCP server.

Per `KB § PATTERNS/mcp-tool-conventions.md § 3`, each leaf module exports
`register(server)`; the aggregation trio is now built once by
`_kit.registry.build_registry` (shared across every connector MCP) and
re-exported here unchanged.

Tool naming follows the dotted convention: `vista.<service>.<action>`.
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import imoveis, usuarios, agencias, clientes, corretores, diagnostics


LEAF_MODULES = (imoveis, usuarios, agencias, clientes, corretores, diagnostics)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
