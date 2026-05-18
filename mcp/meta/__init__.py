"""`mcp/meta` — Meta-family connector MCP server.

Composes `mcp/_kit` (the shared connector-MCP boilerplate) the same way
`mcp/vista` does. Vendor-private logic stays here; the kit owns the
generic stdio bootstrap + per-tenant settings + registry + error
envelope.

SHIPPED THIS WAVE — the WhatsApp slice only:
- `meta.whatsapp.send_text`     — outbound, confirm-gated side-effect.
- `meta.whatsapp.parse_inbound` — pure WAHA-payload parse, no side-effect.

NOT shipped (verify-the-seed-ships-it gap — see `mcp/meta/README.md`):
`meta.facebook.*`, `meta.instagram.*`, `meta.diagnostics.*` depend on
`noctusai_lib.integrations.meta` (Graph-API adapter + value objects)
which does NOT exist in the tree. Shipping them would mean
re-implementing the adapter connector-side — a structural fork the
brief explicitly forbids. Surfaced as a Wave 3 blocker.
"""
