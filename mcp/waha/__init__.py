"""`mcp/waha` — WAHA (WhatsApp HTTP API) connector MCP.

A connector-MCP server (composes `mcp/_kit`, same shape as
`mcp/n8n` / `mcp/github` / `mcp/vista`) that exposes a **self-hosted
WAHA instance's session + messaging + server facilities** as
LLM-callable `waha.<service>.<action>` tools — list/inspect/start/
stop/restart/logout WhatsApp sessions, send text, list chats/messages,
server health.

It talks to the WAHA **HTTP API** (header `X-Api-Key`) through the
single `waha.api.request_json` stdlib-`urllib` seam (no extra deps —
mirrors how `mcp/n8n` wraps `urllib` and `mcp/github` wraps stdlib
`subprocess`). The API key is a secret and lives in the connector's
own co-located `mcp/waha/.env` (gitignored), NOT the product/root
`.env`, per the "every connector owns its own auth store" principle
(`KB § INTEGRATIONS/vista.md § 1`).

Writes (session start/stop/restart/logout, send_text) follow the
confirm-then-execute gate (status 412, no side-effect); `send_text` is
outward-facing (a real WhatsApp message) so it is the strongest gate.
Missing config / unreachable host / rejected key is a typed,
never-faked signal (gated-capability honesty, CLAUDE.md §1). See
`mcp/waha/README.md`.
"""
__version__ = "0.1.0"
