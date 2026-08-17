"""Hierarchical tool registry for the OLX connector MCP server.

Aggregation trio built by `_kit.registry.build_registry`. Tool naming
follows the 3-segment dotted convention `olx.<service>.<action>`.

LEAF_MODULES:
- `webhook`     — the INBOUND lead contract: describe / validate /
                  record a real delivery / simulate one / diff the corpus
                  against the contract.
- `leads`       — the OUTBOUND Gestor de Leads push.
- `diagnostics` — configuration state, endpoint probe, endpoint catalog.

No connector-side HTTP for the vendor API: the client lives in
`noctusai_lib.integrations.olx` and is shared with the product receiver,
so the map an agent reads and the code that runs in production are the
same module. (`olx.webhook.simulate` does open a socket, but at OUR
receiver, not at OLX.)
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import diagnostics, leads, webhook

LEAF_MODULES = (diagnostics, leads, webhook)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
