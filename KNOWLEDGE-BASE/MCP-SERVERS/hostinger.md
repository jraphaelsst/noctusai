# Hostinger connector MCP — `mcp/hostinger`

> The **Hostinger Developers API VPS-ops surface** exposed as
> LLM-callable tools: virtual-machine list/inspect, time-series metrics,
> action history, and (confirm-gated) restart/start/stop — plus a
> quad-state connection diagnostic. Talks to the Hostinger Developers
> API (`https://developers.hostinger.com`, `Authorization: Bearer`).
> Composes `mcp/_kit` (same shape as n8n/waha/github/vista). Built
> 2026-05-21.

## Why it exists

The Hostinger account hosts a production VPS (`srv1303151.hstgr.cloud`,
id `1303151`, running Coolify). Operating it from an agent — checking
state, reading CPU/RAM metrics, reviewing the action/backup history,
power-cycling a stuck box — needed a real tool surface. Hostinger's
public Developers API is the only programmatic path; the
`claude.ai`-managed connectors don't reach it.

## Tool surface (`hostinger.<service>.<action>`, 3-segment dotted)

| Tool | Kind | Endpoint wrapped |
|---|---|---|
| `hostinger.vps.list` | READ | `GET /api/vps/v1/virtual-machines` (array) |
| `hostinger.vps.get` | READ | `GET /api/vps/v1/virtual-machines/{id}` (object) |
| `hostinger.vps.metrics` | READ | `GET .../{id}/metrics` (needs `date_from`/`date_to`) |
| `hostinger.vps.actions` | READ | `GET .../{id}/actions` (`{data,meta}` paginated) |
| `hostinger.vps.restart` | WRITE/POWER 🔒 confirm | `POST .../{id}/restart` |
| `hostinger.vps.start` | WRITE/POWER 🔒 confirm | `POST .../{id}/start` |
| `hostinger.vps.stop` | WRITE/POWER 🔒 confirm (**strongest**) | `POST .../{id}/stop` |
| `hostinger.diagnostics.connection_status` | READ | `GET .../virtual-machines` probe |

- Writes/power: confirm-then-execute (`KB § PATTERNS/llm-bot-security.md`).
  `confirm` ≠ true ⇒ typed error `status 412`, ¬ side-effect; the gate
  message states the concrete effect. `stop` = **strongest gate** — it
  TAKES THE SERVER DOWN (every service offline until a `start`).
- `vps.metrics` REQUIRES `date_from` ∧ `date_to` (ISO 8601, e.g.
  `2026-05-20T00:00:00Z`); omitting ⇒ upstream 422, surfaced as a typed
  never-faked error (¬ a fabricated empty series). Returns a dict of
  series — `cpu_usage` · `ram_usage` · `disk_space` · `incoming_traffic`
  · `outgoing_traffic` · `uptime` (each `{unit, usage:{ts:value}}`).
- `vps.actions` is paginated `{data:[...], meta:{...}}`; the tool
  returns `actions` (the rows) ∧ `meta` (page info).
- **Endpoint surface probed live 2026-05-21** (codebase-is-source-of-
  truth applied to an external API — shapes verified, ¬ assumed):
  `list`→array · `get`→object · `actions`→`{data,meta}` ·
  `metrics`→series-dict. All four read tools + the diagnostic ran green
  end-to-end against the live token (read-only; power tools NEVER fired
  at the running production box).

## Architecture

- Composes `_kit`: `configure_stderr_logging` · `run_stdio_server`
  (stdio bootstrap, PyPI-`mcp`-shadow + in-tree seed pin) ·
  `make_get_settings` · `build_registry` · `typed_error`. Connector body
  ≈ the leaf tool modules (`vps`, `diagnostics`) + `api.py` only.
- **External seam** = `hostinger.api.request_json` (stdlib `urllib`,
  zero deps — mirrors n8n/waha). Single HTTP boundary; tests
  `patch("hostinger.api.request_json")` (external-service patch
  sanctioned, CLAUDE.md §1; our code never patched).
- Paths are **absolute** (`/api/vps/v1/...`) — `normalize_base_url` only
  strips a trailing slash ∧ supplies the canonical host when unset (like
  WAHA's absolute paths, ¬ n8n's `/api/v1` suffix). The base URL is
  fixed (single public API, ¬ per-tenant).

> ⚠️ **Cloudflare WAF — the `User-Agent` is load-bearing.** The host
> sits behind Cloudflare, which **403-bans the default
> `Python-urllib/x.y` user-agent** (Error 1010
> `browser_signature_banned`) *before auth is evaluated* — it is NOT an
> auth failure. `request_json` sends a browser-style `User-Agent` on
> every call (connectivity prerequisite, ¬ impersonation). Verified live
> 2026-05-21: default UA → 403/1010; browser UA → 200. A 403 from this
> connector can therefore mean *either* a WAF block *or* a real
> upstream auth-denied — the typed-error message body carries the
> upstream detail to disambiguate.

## Gated-capability honesty (quad-state)

`hostinger.diagnostics.connection_status` classifies the dependency via
a single authed probe (no separate unauth liveness endpoint like WAHA's
`/ping`): not-**configured** (no token → 424) · host **unreachable**
(network failure → 502) · token **rejected** (401/403 →
`authenticated=false`, `reachable=true`) · **ok** (200 → `vm_count`).
Never faked; boots clean with no config.

## Config — SECRET in the connector's own `.env`

`mcp/hostinger/.env` (gitignored) — `HOSTINGER_API_TOKEN` (the Bearer
token). Co-located, **independent of the product/root `.env`**
(every-connector-owns-its-auth-store, `KB § INTEGRATIONS/vista.md § 1`).
Issue/rotate in hPanel → API. The token in `.env` at build was a TEMP
chat-pasted value ⇒ **rotate before relying on it** —
`mcp/hostinger/KEY-ROTATION-RUNBOOK.md`.

## Registration (user-gated)

`.mcp.json` add **only with explicit user approval** (MCP keep-list
rule, CLAUDE.md §1). Reuses the `mcp/noctusai/.venv` interpreter (has
`mcp`; connector adds no deps):

```json
"hostinger": { "command": "mcp/noctusai/.venv/bin/python",
               "args": ["mcp/hostinger/server.py"], "cwd": "<repo root>" }
```

## Tests

`mcp/noctusai/.venv/bin/python -m pytest mcp/hostinger/tests/ -q` — no
network; pins tool-name set, dotted naming, confirm gate (incl. the
strongest-gate `stop`, ¬ side-effect), the Cloudflare User-Agent header
+ Bearer auth, gated-honesty (424 + connection_status quad-state), ∧ the
live-verified read shapes (list array / get object / actions `{data,meta}`
/ metrics dict). 18 green at build.

## Deferred — v2 surface (mapped, ¬ wrapped)

v1 wraps **VPS** only — it is the consumer's live need. The Hostinger
Developers API also exposes **domains · DNS · billing · hosting ·
email**. Triage = accept-with-rationale: file a v2 project when a
consumer needs one of those surfaces (same shape as how WAHA/n8n grew
their tool sets on demand). Adding them is mechanical — a new leaf
module per surface composing the same `api.request_json` seam +
confirm-gates on the write actions.
