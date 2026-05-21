# `mcp/cloudflare` — Cloudflare API v4 connector MCP

## What this is

A connector-MCP server exposing the **Cloudflare DNS / zone / tunnel
facilities** as LLM-callable `cloudflare.<service>.<action>` tools.
**Composes `mcp/_kit`** (same shape as `mcp/n8n` / `mcp/waha` /
`mcp/hostinger` / `mcp/github` / `mcp/vista`): bootstrap, settings,
registry, error envelope, in-tree seed pin — all inherited.

Talks to the Cloudflare API v4
(`https://api.cloudflare.com/client/v4`, header `Authorization: Bearer
<token>`) via the single `cloudflare.api.request_json` /
`request_envelope` stdlib-`urllib` seam (no extra deps). Cloudflare
paths are **absolute** (`/zones`, `/accounts/{id}/cfd_tunnel`) — no
`/api/v1`-style suffix to normalize (like WAHA/hostinger, unlike n8n).

> **Why it exists.** The `claude.ai`-managed Cloudflare connector
> doesn't do DNS / zone / tunnel operations — which our domain
> migration needs — so we wrap the Cloudflare API v4 ourselves.

> **Cloudflare envelope.** Every response is wrapped in
> `{success, errors, messages, result, result_info}`. The seam treats a
> 200-OK with `success:false` as a failure (surfacing the first
> `errors[].code` + `message` — never a fabricated success) and returns
> `result` on success. `request_envelope` keeps `result_info`
> (pagination) for list reads; `request_json` unwraps `result`.

> **Cloudflare WAF — the `User-Agent` is load-bearing.** Cloudflare's
> own edge WAF can 403-ban the default `Python-urllib/x.y` user-agent
> *before auth is even evaluated* (the just-built `mcp/hostinger` hit
> exactly this against a Cloudflare-fronted host). `request_json`
> therefore sends a browser-style `User-Agent` on every call — a
> connectivity prerequisite, not impersonation.

## Tool surface

| Tool | Kind | Cloudflare endpoint |
|---|---|---|
| `cloudflare.zones.list` | READ | `GET /zones` (optional `?name=`) |
| `cloudflare.zones.get` | READ | `GET /zones/{zone_id}` |
| `cloudflare.zones.create` | WRITE — confirm (412) | `POST /zones` `{name, account:{id}, type}` |
| `cloudflare.dns.list_records` | READ | `GET /zones/{zone_id}/dns_records` (`?type=&name=`) |
| `cloudflare.dns.get_record` | READ | `GET /zones/{zone_id}/dns_records/{id}` |
| `cloudflare.dns.create_record` | WRITE — confirm (412) | `POST /zones/{zone_id}/dns_records` |
| `cloudflare.dns.update_record` | WRITE — confirm (412) | `PATCH /zones/{zone_id}/dns_records/{id}` |
| `cloudflare.dns.delete_record` | WRITE — confirm (412), **strongest** | `DELETE /zones/{zone_id}/dns_records/{id}` |
| `cloudflare.tunnel.list` | READ | `GET /accounts/{account_id}/cfd_tunnel` |
| `cloudflare.tunnel.get` | READ | `GET /accounts/{account_id}/cfd_tunnel/{id}` |
| `cloudflare.tunnel.get_config` | READ | `GET .../cfd_tunnel/{id}/configurations` |
| `cloudflare.tunnel.create` | WRITE — confirm (412) | `POST /accounts/{account_id}/cfd_tunnel` `{name, config_src}` |
| `cloudflare.tunnel.delete` | WRITE — confirm (412), **strongest** | `DELETE /accounts/{account_id}/cfd_tunnel/{id}` |
| `cloudflare.tunnel.update_config` | WRITE — confirm (412) | `PUT .../cfd_tunnel/{id}/configurations` `{config:{ingress:[...]}}` |
| `cloudflare.diagnostics.connection_status` | READ | `GET /user/tokens/verify` probe |

`dns.delete_record` and `tunnel.delete` are the **strongest gates** —
outward-facing / irreversible (the public DNS record / the tunnel +
credentials are destroyed; resolution / routes break immediately). All
writes are confirm-then-execute (`KB § PATTERNS/llm-bot-security.md`):
`confirm` omitted/false ⇒ typed error `status 412`, NO side-effect; the
gate message states the concrete effect.

`tunnel.*` is **account-scoped** (`/accounts/{account_id}/...`) — it
needs `CLOUDFLARE_ACCOUNT_ID`; missing it ⇒ a typed never-faked 424
(we never build a malformed path). `zones.create` likewise needs an
account id (arg or env). `tunnel.update_config` (PUT) **replaces** the
whole ingress rule set — always `tunnel.get_config` first and keep that
as a rollback snapshot; the last ingress rule MUST be a catch-all
(service-only, e.g. `{"service":"http_status:404"}`).

## Gated-capability honesty

`cloudflare.diagnostics.connection_status` classifies the dependency via
a `GET /user/tokens/verify` probe: not-**configured** (no token → 424) ·
host **unreachable** (network failure → 502) · token **rejected** (401
or a `success:false` envelope → `authenticated=false`) · **ok** (200 →
`token_status`, e.g. `active`). Also reports `account_id_present` (the
tunnel tools need it). Never faked; the server boots cleanly with no
config.

## Config (`mcp/cloudflare/.env` or env) — SECRET lives here

| Var | Meaning | Default |
|---|---|---|
| `CLOUDFLARE_API_TOKEN` | scoped Bearer token (`Authorization: Bearer`) — **secret** | — (required) |
| `CLOUDFLARE_ACCOUNT_ID` | account id for account-scoped tunnel endpoints — not a secret | — (required for tunnel.* / zones.create) |

Co-located `.env` (gitignored), **independent of the product/root
`.env`** — "every connector owns its own auth store" (`KB §
INTEGRATIONS/vista.md § 1`). The base URL is fixed
(`https://api.cloudflare.com/client/v4`). Create a **scoped** token at
`https://dash.cloudflare.com/profile/api-tokens` with:

- **Zone : DNS : Edit** (DNS record list/get/create/update/delete)
- **Zone : Zone : Read** (zone list/get) **+ Edit** (zone create)
- **Account : Cloudflare Tunnel : Edit** (tunnel list/get/create/delete/config)

(+ **Account : Email Routing : Edit** later for the deferred v2 surface.)

## Registration (user-gated — add only with explicit user approval)

`.mcp.json` add is **user-gated** (MCP keep-list rule, CLAUDE.md §1).
Reuses the `mcp/noctusai/.venv` interpreter (has `mcp`; this connector
adds no deps). Add this block to the `mcpServers` object in
`.mcp.json` (replace `<repo root>` with the absolute repo path):

```json
"cloudflare": {
  "command": "mcp/noctusai/.venv/bin/python",
  "args": ["mcp/cloudflare/server.py"],
  "cwd": "<repo root>"
}
```

## Tests

```
mcp/noctusai/.venv/bin/python -m pytest mcp/cloudflare/tests/ -q
```

No network — pure validation or `unittest.mock.patch` on
`cloudflare.api.request_json` / `request_envelope` (and
`urllib.request.urlopen` for the UA-header + envelope pins). Pins the
tool-name set, dotted naming, the confirm gate (ALL writes, incl. the
strongest gates `dns.delete_record` + `tunnel.delete`, no side-effect),
the Cloudflare User-Agent header + Bearer auth, the `success:false`
envelope → typed-error-with-cf_code, account-scoped-needs-account-id,
gated-capability honesty (424 + connection_status quad-state), and the
documented read shapes. **25 green at build.**

> **Live validation deferred.** There is no live token at build
> (`mcp/cloudflare/.env` `CLOUDFLARE_API_TOKEN` is empty — the user
> pastes a scoped token later). Endpoint shapes were verified against
> the official Cloudflare API v4 docs (via `search_cloudflare_documentation`
> + the public reference); end-to-end live probing is deferred until the
> token is added (then run `cloudflare.diagnostics.connection_status` +
> the read tools, as the rotation runbook §4 describes).

## Deferred — v2 surface (mapped, not yet wrapped)

v1 covers **zones / DNS records / tunnels** — the domain-migration
need. The Cloudflare API also exposes **Email Routing** (catch-all /
rule-based forwarding) and **Registrar** (domain registration /
transfer), plus page rules, WAF, R2, Workers, etc. Triage =
accept-with-rationale: file a v2 project when a consumer needs one (same
shape as how WAHA/n8n/hostinger grew their tool sets on demand). Adding
them is mechanical — a new leaf module per surface composing the same
`api.request_json` seam + confirm-gates on the writes. See
`KB § MCP-SERVERS/cloudflare.md § Deferred v2 surface`.
