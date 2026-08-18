"""Hierarchical tool registry for the Trello connector MCP server.

Aggregation trio built by `_kit.registry.build_registry`. Tool naming
follows the 3-segment dotted convention `trello.<service>.<action>`.

LEAF_MODULES:
- `contract`     — zero-IO reads of the vendored OpenAPI spec. The point
                    of this connector (see `mcp/trello/README.md`).
- `diagnostics`  — configuration state + a cheap live probe.
- `boards`       — live READ.
- `lists`        — live READ.
- `cards`        — live READ (list, get) + confirm-gated WRITE
                    (create, update, comment_add).
- `checklists`   — live READ (get) + confirm-gated WRITE (create).
- `labels`       — live READ.
- `actions`      — live READ (a card's comment/activity thread).

18 tools total: 5 contract + 2 diagnostics + 7 live reads + 4 live writes.
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import actions, boards, cards, checklists, contract, diagnostics, labels, lists

LEAF_MODULES = (contract, diagnostics, boards, lists, cards, checklists, labels, actions)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
