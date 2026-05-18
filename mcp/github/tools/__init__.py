"""Hierarchical tool registry for the GitHub connector MCP server.

Aggregation trio built once by `_kit.registry.build_registry` (shared
across every connector MCP). Tool naming follows the dotted convention
`github.<service>.<action>`.

LEAF_MODULES: `pr` (PR lifecycle + CI checks), `repo` (repo
introspection), `diagnostics` (the `gh`-dependency / auth signal).
All leaves wrap the operator's authenticated `gh` CLI via the single
`github.gh.run_gh` subprocess seam.
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import diagnostics, pr, repo

LEAF_MODULES = (diagnostics, pr, repo)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
