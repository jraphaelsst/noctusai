"""`mcp/hostinger` — Hostinger Developers API connector MCP.

A connector-MCP server (composes `mcp/_kit`, same shape as
`mcp/n8n` / `mcp/waha` / `mcp/github` / `mcp/vista`) that exposes the
**Hostinger VPS facilities** as LLM-callable
`hostinger.<service>.<action>` tools — list/inspect virtual machines,
read metrics + action history, and (confirm-gated) restart/start/stop a
VM.

It talks to the Hostinger Developers API
(`https://developers.hostinger.com`, header `Authorization: Bearer
<token>`) through the single `hostinger.api.request_json`
stdlib-`urllib` seam (no extra deps — mirrors how `mcp/n8n` / `mcp/waha`
wrap `urllib`). The host sits behind Cloudflare, so the seam also sends
a browser-style `User-Agent` (required to clear the WAF — see
`api.py`). The token is a secret and lives in the connector's own
co-located `mcp/hostinger/.env` (gitignored), NOT the product/root
`.env`, per the "every connector owns its own auth store" principle
(`KB § INTEGRATIONS/vista.md § 1`).

Power/write tools (restart/start/stop) follow the confirm-then-execute
gate (status 412, no side-effect); `stop` is the strongest gate (it
takes the server down). Missing config / unreachable host / rejected
token is a typed, never-faked signal (gated-capability honesty,
CLAUDE.md §1). See `mcp/hostinger/README.md`.
"""
__version__ = "0.1.0"
