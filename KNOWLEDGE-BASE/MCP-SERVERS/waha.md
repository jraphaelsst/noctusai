# WAHA connector MCP — `mcp/waha`

> The **self-hosted WAHA (WhatsApp HTTP API) ops surface** exposed as
> LLM-callable tools: session lifecycle (list/get/me/start/stop/restart/
> logout), messaging (send_text/list/chats), server health, and a
> tri-state connection diagnostic. Talks to the WAHA HTTP API
> (`X-Api-Key`, no `/api/v1` prefix). Composes `mcp/_kit` (same shape
> as n8n/github/vista). Built 2026-05-19 (was a *planned* server).

## Why it exists

WAHA drives the WhatsApp side of n8n flows (e.g. the `Matrícula
Extractor Agent`). When a WAHA session goes `STOPPED`/`FAILED` the
n8n webhook still fires with junk payloads (the bug
`KB § MCP-SERVERS/n8n.md` first-use diagnosed). Operating WAHA from an
agent — checking session status, restarting a stuck worker — needed a
real tool surface. The WAHA dashboard conflates "host down" and "wrong
key" into one error; this connector's diagnostic disambiguates them.

## Tool surface (`waha.<service>.<action>`, 3-segment dotted)

| Tool | Kind | WAHA endpoint |
|---|---|---|
| `waha.session.list` | READ | `GET /api/sessions?all=true` |
| `waha.session.get` | READ | `GET /api/sessions/{name}` |
| `waha.session.me` | READ | `GET /api/sessions/{name}/me` |
| `waha.session.start` | WRITE 🔒 | `POST /api/sessions/{name}/start` |
| `waha.session.stop` | WRITE 🔒 | `POST /api/sessions/{name}/stop` |
| `waha.session.restart` | WRITE 🔒 | `POST /api/sessions/{name}/restart` |
| `waha.session.logout` | WRITE 🔒 hard-to-reverse | `POST /api/sessions/{name}/logout` |
| `waha.message.send_text` | WRITE 🔒 **outward-facing** | `POST /api/sendText` |
| `waha.message.list` | READ | `GET /api/{session}/chats/{chatId}/messages` |
| `waha.chat.list` | READ | `GET /api/{session}/chats` |
| `waha.server.version` | READ | `GET /api/server/version` |
| `waha.server.status` | READ | `GET /api/server/status` |
| `waha.server.ping` | READ (unauth) | `GET /ping` |
| `waha.diagnostics.connection_status` | READ | `/ping` → `/api/sessions` |

- Writes: confirm-then-execute. `confirm` ≠ true ⇒ typed `status 412`,
  ¬ side-effect. `send_text` = strongest gate (a sent WhatsApp message
  is irreversible); `logout` hard-to-reverse (re-pair needs a QR scan,
  a human dashboard action — ¬ an API call).
- **Stuck-worker recipe**: `session.get` → `session.restart`
  (confirm=true) → `session.get`. `SCAN_QR_CODE` ⇒ pairing lost ⇒
  human QR scan in the WAHA dashboard.

## Architecture

- Composes `_kit`: `configure_stderr_logging` · `run_stdio_server`
  (PyPI-`mcp`-shadow + in-tree seed pin) · `make_get_settings` ·
  `build_registry` · `typed_error`.
- **External seam** = `waha.api.request_json` (stdlib `urllib`, zero
  deps — mirrors n8n). Single HTTP boundary; tests
  `patch("waha.api.request_json")` (external-service patch sanctioned,
  CLAUDE.md §1). `require_auth=False` path for the unauthenticated
  `/ping` so the diagnostic separates "host down" from "key wrong".
- No `/api/v1` prefix — `normalize_base_url` only strips a trailing
  slash (WAHA paths are absolute).

## Gated-capability honesty (tri-state)

`waha.diagnostics.connection_status` resolves the WAHA dashboard's
conflated error into: not-**configured** (424) · host **down**
(unauth `/ping` fails) · key **rejected** (authed `/api/sessions`
401/403) · all-green (`authenticated=true`, `session_count`). Never
faked; boots clean with no config.

## Config — SECRET in the connector's own `.env`

`mcp/waha/.env` (gitignored) — `WAHA_BASE_URL` (instance root, no
`/api/v1`) + `WAHA_API_KEY` (the `X-Api-Key` = server's
`WHATSAPP_API_KEY`). Co-located, **independent of the product/root
`.env`** (every-connector-owns-its-auth-store, `KB §
INTEGRATIONS/vista.md § 1`). Session name defaults to `default`.

## Registration

On the **MCP keep-list** (user-approved 2026-05-19) ∧ registered in
`.mcp.json` (gitignored — registration is local-only). Reuses the
`mcp/noctusai/.venv` interpreter (has `mcp`; connector adds no deps).

## Tests

`mcp/noctusai/.venv/bin/python -m pytest mcp/waha/tests/ -q` — no
network; pins tool-name set, dotted naming, confirm gate (incl.
outward-facing send_text, ¬ side-effect), ping/auth tri-state,
chatId resolution, registry coherence. 12 green at build.
