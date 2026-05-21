# `mcp/hostinger` — Hostinger Developers API connector MCP

## What this is

A connector-MCP server exposing the **Hostinger VPS facilities** as
LLM-callable `hostinger.<service>.<action>` tools. **Composes `mcp/_kit`**
(same shape as `mcp/n8n` / `mcp/waha` / `mcp/github` / `mcp/vista`):
bootstrap, settings, registry, error envelope, in-tree seed pin — all
inherited.

Talks to the Hostinger Developers API (`https://developers.hostinger.com`,
header `Authorization: Bearer <token>`) via the single
`hostinger.api.request_json` stdlib-`urllib` seam (no extra deps).
Hostinger paths are **absolute** (`/api/vps/v1/...`) — no `/api/v1`-style
suffix to normalize (like WAHA, unlike n8n).

> **Cloudflare WAF — the `User-Agent` is load-bearing.** The host sits
> behind Cloudflare, which **403-bans the default `Python-urllib/x.y`
> user-agent** (Error 1010 "browser_signature_banned") *before auth is
> even evaluated*. `request_json` therefore sends a browser-style
> `User-Agent` on every call — this is a connectivity prerequisite, not
> impersonation. Verified live 2026-05-21: default UA → 403; browser UA
> → 200.

## Tool surface

| Tool | Kind | Hostinger endpoint |
|---|---|---|
| `hostinger.vps.list` | READ | `GET /api/vps/v1/virtual-machines` |
| `hostinger.vps.get` | READ | `GET /api/vps/v1/virtual-machines/{id}` |
| `hostinger.vps.metrics` | READ | `GET /api/vps/v1/virtual-machines/{id}/metrics` (needs `date_from`/`date_to`) |
| `hostinger.vps.actions` | READ | `GET /api/vps/v1/virtual-machines/{id}/actions` |
| `hostinger.vps.restart` | WRITE/POWER — confirm (412) | `POST /api/vps/v1/virtual-machines/{id}/restart` |
| `hostinger.vps.start` | WRITE/POWER — confirm (412) | `POST /api/vps/v1/virtual-machines/{id}/start` |
| `hostinger.vps.stop` | WRITE/POWER — confirm (412), **strongest** | `POST /api/vps/v1/virtual-machines/{id}/stop` |
| `hostinger.diagnostics.connection_status` | READ | `GET .../virtual-machines` probe |

`stop` is the **strongest gate** — it takes the server down (every
service it hosts goes offline until a `start`). All power tools are
confirm-then-execute (`KB § PATTERNS/llm-bot-security.md`): `confirm`
omitted/false ⇒ typed error `status 412`, NO side-effect; the gate
message states the concrete effect.

`vps.metrics` requires both `date_from` and `date_to` (ISO 8601, e.g.
`2026-05-20T00:00:00Z`); omitting them is an upstream 422, surfaced as a
typed never-faked error. `vps.actions` is paginated
(`{data:[...], meta:{...}}`); the tool returns `actions` + `meta`.

## Gated-capability honesty

`hostinger.diagnostics.connection_status` classifies the dependency:
not-**configured** (no token → 424) · host **unreachable** (network
failure → 502) · token **rejected** (401/403 → `authenticated=false`) ·
**ok** (200 → `vm_count`). Never faked; the server boots cleanly with no
config.

## Config (`mcp/hostinger/.env` or env) — SECRET lives here

| Var | Meaning | Default |
|---|---|---|
| `HOSTINGER_API_TOKEN` | Bearer token (`Authorization: Bearer`) — **secret** | — (required) |

Co-located `.env` (gitignored), **independent of the product/root
`.env`** — "every connector owns its own auth store" (`KB §
INTEGRATIONS/vista.md § 1`). The base URL is fixed
(`https://developers.hostinger.com`); no per-tenant host. Issue/rotate
the token in hPanel → API.

## Registration (user-gated — add only with explicit user approval)

`.mcp.json` add is **user-gated** (MCP keep-list rule, CLAUDE.md §1).
Reuses the `mcp/noctusai/.venv` interpreter (has `mcp`; this connector
adds no deps). Add this block to the `mcpServers` object in
`.mcp.json` (replace `<repo root>` with the absolute repo path):

```json
"hostinger": {
  "command": "mcp/noctusai/.venv/bin/python",
  "args": ["mcp/hostinger/server.py"],
  "cwd": "<repo root>"
}
```

## Tests

```
mcp/noctusai/.venv/bin/python -m pytest mcp/hostinger/tests/ -q
```

No network — pure validation or `unittest.mock.patch` on
`hostinger.api.request_json` (and `urllib.request.urlopen` for the
UA-header pin). Pins the tool-name set, dotted naming, the confirm gate
(incl. the strongest-gate `stop`, no side-effect), the Cloudflare
User-Agent header + Bearer auth, gated-capability honesty (424 +
connection_status quad-state), and the live-verified read shapes
(list array / get object / actions `{data,meta}` / metrics dict). 18
green at build.

## Deferred — v2 surface (mapped, not yet wrapped)

v1 covers **VPS** only. The Hostinger Developers API also exposes
**domains / DNS / billing / hosting / email** — deferred to a v2
project (`accept-with-rationale`: file when a consumer needs it). See
`KB § MCP-SERVERS/hostinger.md § Deferred v2 surface`.
