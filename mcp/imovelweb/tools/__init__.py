"""Hierarchical tool registry for the ImovelWeb connector MCP server.

Aggregation trio built by `_kit.registry.build_registry`. Tool naming
follows the 3-segment dotted convention `imovelweb.<service>.<action>`.

LEAF_MODULES:
- `contract`    — the INBOUND callback contract: describe / validate /
                  diff the observed corpus. Zero IO, no credentials.
- `diagnostics` — configuration state, endpoint probe, endpoint catalog,
                  and the vendor's own generated OpenAPI spec.
- `callbacks`   — the self-served registration. Integrator-wide, so every
                  write is confirm-gated and read back.
- `leads`       — the pull side: reconciliation reads and enrichment.
- `agencies`    — who is authorized to us; the tenant-resolution key.
- `sandbox`     — ask the vendor to push a synthetic delivery at us.
- `webhook`     — our own receiver: record what arrives, rehearse what
                  should, and measure against the 1.5-second budget.

No connector-side HTTP for the vendor API: the client lives in
`noctusai_lib.integrations.imovelweb` and is shared with the product
receiver, so the map an agent reads and the code that runs in production
are the same module. (`webhook.simulate` and `diagnostics.probe` /
`.fetch_swagger` do open sockets, but at OUR receiver and at a public
unauthenticated spec endpoint respectively — never at the credentialed
API.)
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import agencies, callbacks, contract, diagnostics, leads, sandbox, webhook

LEAF_MODULES = (agencies, callbacks, contract, diagnostics, leads, sandbox, webhook)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
