# `mcp/waha` — WAHA (WhatsApp HTTP API) connector MCP

## What this is

A connector-MCP server exposing a **self-hosted WAHA instance's
session + messaging + server facilities** as LLM-callable
`waha.<service>.<action>` tools. **Composes `mcp/_kit`** (same shape
as `mcp/n8n` / `mcp/github` / `mcp/vista`): bootstrap, settings,
registry, error envelope, in-tree seed pin — all inherited.

Talks to the WAHA **HTTP API** (header `X-Api-Key`) via the single
`waha.api.request_json` stdlib-`urllib` seam (no extra deps). WAHA has
**no `/api/v1` prefix** — paths are absolute (`/ping`, `/api/sessions`,
`/api/sendText`); `/ping` is the one unauthenticated endpoint.

## Tool surface

| Tool | Kind | WAHA endpoint |
|---|---|---|
| `waha.session.list` | READ | `GET /api/sessions?all=true` |
| `waha.session.get` | READ | `GET /api/sessions/{name}` |
| `waha.session.me` | READ | `GET /api/sessions/{name}/me` |
| `waha.session.start` | WRITE — confirm (412) | `POST /api/sessions/{name}/start` |
| `waha.session.stop` | WRITE — confirm (412) | `POST /api/sessions/{name}/stop` |
| `waha.session.restart` | WRITE — confirm (412) | `POST /api/sessions/{name}/restart` |
| `waha.session.logout` | WRITE — confirm (412), hard-to-reverse | `POST /api/sessions/{name}/logout` |
| `waha.message.send_text` | WRITE — confirm (412), **outward-facing** | `POST /api/sendText` |
| `waha.message.list` | READ | `GET /api/{session}/chats/{chatId}/messages` |
| `waha.chat.list` | READ | `GET /api/{session}/chats` |
| `waha.server.version` | READ | `GET /api/server/version` |
| `waha.server.status` | READ | `GET /api/server/status` |
| `waha.server.ping` | READ (unauthenticated) | `GET /ping` |
| `waha.diagnostics.connection_status` | READ | `/ping` then `/api/sessions` |

`send_text` is the **strongest gate** — a sent WhatsApp message can't
be unsent. All writes are confirm-then-execute (`KB §
PATTERNS/llm-bot-security.md`): `confirm` omitted/false ⇒ typed error
`status 412`, NO side-effect.

**Stuck/STOPPED worker recipe:** `waha.session.get` (read status) →
`waha.session.restart` (confirm=true) → `waha.session.get` again. If
status is `SCAN_QR_CODE`, the pairing was lost — that needs a human QR
scan in the WAHA dashboard (not an API action).

## Gated-capability honesty

`waha.diagnostics.connection_status` disambiguates the three states the
WAHA dashboard conflates into one "not connected / wrong key" error:
not-**configured** (424) vs host **down** (unauthenticated `/ping`
fails) vs key **rejected** (authed call 401/403). Never faked; the
server boots cleanly with no config.

## Config (`mcp/waha/.env` or env) — SECRET lives here

| Var | Meaning | Default |
|---|---|---|
| `WAHA_BASE_URL` | instance root (no `/api/v1`) | — (required) |
| `WAHA_API_KEY` | WAHA `X-Api-Key` — **secret** | — (required) |

Co-located `.env` (gitignored), **independent of the product/root
`.env`** — "every connector owns its own auth store" (`KB §
INTEGRATIONS/vista.md § 1`). Session name defaults to `default`.

## Registration (user-gated)

On the MCP keep-list (user-approved 2026-05-19). `.mcp.json` reuses the
`mcp/noctusai/.venv` interpreter (has `mcp`; this connector adds no
deps):

```json
"waha": { "command": "mcp/noctusai/.venv/bin/python",
          "args": ["mcp/waha/server.py"], "cwd": "<repo root>" }
```

## Tests

```
mcp/noctusai/.venv/bin/python -m pytest mcp/waha/tests/ -q
```

No network — pure validation or `unittest.mock.patch` on
`waha.api.request_json`. Pins the tool-name set, dotted naming, the
confirm gate (incl. outward-facing send_text, no side-effect), the
ping/auth tri-state honesty, chatId resolution, registry coherence.
