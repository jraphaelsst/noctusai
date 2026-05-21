"""`mcp/cloudflare` — Cloudflare API v4 connector MCP.

A connector-MCP server (composes `mcp/_kit`, same shape as
`mcp/n8n` / `mcp/waha` / `mcp/hostinger` / `mcp/github` / `mcp/vista`)
that exposes the **Cloudflare DNS / zone / tunnel facilities** as
LLM-callable `cloudflare.<service>.<action>` tools — list/inspect zones,
manage DNS records, and manage Cloudflare Tunnels (cfd_tunnel) +
their ingress configurations.

It talks to the Cloudflare API v4
(`https://api.cloudflare.com/client/v4`, header `Authorization: Bearer
<token>`) through the single `cloudflare.api.request_json`
stdlib-`urllib` seam (no extra deps — mirrors how `mcp/n8n` /
`mcp/waha` / `mcp/hostinger` wrap `urllib`). Cloudflare's own WAF
403-bans the default urllib User-Agent (the just-built `mcp/hostinger`
hit this against a Cloudflare-fronted host), so the seam sends a
browser-style `User-Agent` on every call — a connectivity prerequisite.

Cloudflare wraps every response in a fixed envelope
(`{success, errors, messages, result, result_info}`); the seam treats
`success:false` as an error (surfacing `errors[].code` + `message`) and
returns `result` on success — never a fabricated success.

The API token is a secret and lives in the connector's own co-located
`mcp/cloudflare/.env` (gitignored), NOT the product/root `.env`, per
the "every connector owns its own auth store" principle
(`KB § INTEGRATIONS/vista.md § 1`). The account id (account-scoped
tunnel endpoints) lives there too — it is not a secret.

Write tools (zones.create, dns.create/update/delete, tunnel.create/
delete/update_config) follow the confirm-then-execute gate (status 412,
no side-effect); `dns.delete_record` and `tunnel.delete` are the
strongest gates (outward-facing / irreversible). Missing config /
unreachable host / rejected token / `success:false` is a typed,
never-faked signal (gated-capability honesty, CLAUDE.md §1). See
`mcp/cloudflare/README.md`.
"""
__version__ = "0.1.0"
