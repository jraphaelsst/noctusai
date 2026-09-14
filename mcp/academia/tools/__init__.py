"""Hierarchical tool registry for the academia MCP server.

Per `KB § PATTERNS/architect/mcp-tool-conventions.md § 3`, each leaf
module exports `register(server)`; the aggregation trio is built by
`_kit.registry.build_registry` (shared across every connector MCP) and
re-exported here unchanged.

Tool naming follows the dotted convention: `academia.<service>.<action>`
(CONTRACT §C). `academia.kb.index_sync`, `academia.kb.link_check` and
`academia.roadmap.render` are DEPRECATED and deliberately have no leaf
module — see `KNOWLEDGE-BASE`/CONTRACT §C for the removal rationale.
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import conteudo, decisao, historico, kb, pergunta, pesquisa, projeto

LEAF_MODULES = (kb, decisao, pergunta, historico, projeto, conteudo, pesquisa)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
