"""Hierarchical tool registry for the Vista MCP server.

Per `KB § PATTERNS/mcp-tool-conventions.md § 3`, each leaf module exports
`register(server)`; this module's `register_all(server)` calls them all
once at server startup.

Tool naming follows the dotted convention: `vista.<service>.<action>`.
"""
from __future__ import annotations

from . import imoveis, usuarios, agencias, clientes, corretores, diagnostics


LEAF_MODULES = (imoveis, usuarios, agencias, clientes, corretores, diagnostics)


def all_handlers() -> dict:
    """Aggregate {tool_name: async-handler} across every leaf module."""
    out: dict = {}
    for mod in LEAF_MODULES:
        out.update(mod.HANDLERS)
    return out


def all_descriptors():
    """Aggregate Tool descriptors across every leaf module."""
    out = []
    for mod in LEAF_MODULES:
        out.extend(mod.tool_descriptors())
    return out


def register_all(server) -> None:
    """Compatibility entry — server.py uses `all_handlers()` / `all_descriptors()`."""
    for mod in LEAF_MODULES:
        mod.register(server)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
