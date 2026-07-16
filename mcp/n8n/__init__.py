"""`mcp/n8n` — self-hosted n8n connector MCP (workflow-ops surface).

A connector-MCP server (composes `mcp/_kit`, same shape as
`mcp/github` / `mcp/vista`) that exposes the **n8n workflow facilities
needed to manage + debug workflows on a self-hosted instance** —
workflow listing/inspection, execution history, and (the debugging
core) the full error payload of a failed execution — as LLM-callable
`n8n.<service>.<action>` tools.

It talks to the n8n **public REST API** (`/api/v1`, header
`X-N8N-API-KEY`) through `noctusai_lib.integrations.n8n`'s `N8nClient`
Protocol (Fake/Real, `mcp/n8n/client.get_client()` — the DI seam every
tool builds through; no connector-side HTTP). The API key is a secret
and lives in the connector's own co-located `mcp/n8n/.env`
(gitignored) — NOT the product/root `.env` — per the "every connector
owns its own auth store" design principle (`KB § INTEGRATIONS
/vista.md § 1`).

Writes (`activate` / `deactivate` / …) follow the confirm-then-execute
gate (status 412, no side-effect). Missing config / adapter failure is
a typed, never-faked signal (gated-capability honesty, CLAUDE.md §1).
See `mcp/n8n/README.md`.
"""
__version__ = "0.1.0"
