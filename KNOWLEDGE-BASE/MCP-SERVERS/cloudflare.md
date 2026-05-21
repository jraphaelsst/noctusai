# Cloudflare connector MCP — `mcp/cloudflare`

> The **Cloudflare API v4 DNS / zone / tunnel-ops surface** exposed as
> LLM-callable tools: zone list/inspect/create, DNS record CRUD, and
> Cloudflare Tunnel (cfd_tunnel) list/inspect/create/delete + ingress
> config — plus a quad-state connection diagnostic. Talks to the
> Cloudflare API v4 (`https://api.cloudflare.com/client/v4`,
> `Authorization: Bearer`). Composes `mcp/_kit` (same shape as
> n8n/waha/hostinger/github/vista). Built 2026-05-21.

## Why it exists

The `claude.ai`-managed Cloudflare connector doesn't do DNS / zone /
tunnel operations — which our **domain migration** needs — so we wrap
the Cloudflare API v4 ourselves with an operator-issued **scoped** token.
It is the only programmatic path to manage Cloudflare DNS/zones/tunnels
from an agent.

## Tool surface (`cloudflare.<service>.<action>`, 3-segment dotted)

| Tool | Kind | Endpoint wrapped |
|---|---|---|
| `cloudflare.zones.list` | READ | `GET /zones` (optional `?name=`) |
| `cloudflare.zones.get` | READ | `GET /zones/{zone_id}` |
| `cloudflare.zones.create` | WRITE 🔒 confirm | `POST /zones` `{name, account:{id}, type}` |
| `cloudflare.dns.list_records` | READ | `GET /zones/{id}/dns_records` (`?type=&name=`) |
| `cloudflare.dns.get_record` | READ | `GET /zones/{id}/dns_records/{rec}` |
| `cloudflare.dns.create_record` | WRITE 🔒 confirm | `POST /zones/{id}/dns_records` |
| `cloudflare.dns.update_record` | WRITE 🔒 confirm | `PATCH /zones/{id}/dns_records/{rec}` |
| `cloudflare.dns.delete_record` | WRITE 🔒 confirm (**strongest**) | `DELETE /zones/{id}/dns_records/{rec}` |
| `cloudflare.tunnel.list` | READ | `GET /accounts/{acct}/cfd_tunnel` |
| `cloudflare.tunnel.get` | READ | `GET /accounts/{acct}/cfd_tunnel/{t}` |
| `cloudflare.tunnel.get_config` | READ | `GET .../cfd_tunnel/{t}/configurations` |
| `cloudflare.tunnel.create` | WRITE 🔒 confirm | `POST /accounts/{acct}/cfd_tunnel` `{name, config_src}` |
| `cloudflare.tunnel.delete` | WRITE 🔒 confirm (**strongest**) | `DELETE /accounts/{acct}/cfd_tunnel/{t}` |
| `cloudflare.tunnel.update_config` | WRITE 🔒 confirm | `PUT .../cfd_tunnel/{t}/configurations` `{config:{ingress:[...]}}` |
| `cloudflare.diagnostics.connection_status` | READ | `GET /user/tokens/verify` probe |

- Writes: confirm-then-execute (`KB § PATTERNS/llm-bot-security.md`).
  `confirm` ≠ true ⇒ typed error `status 412`, ¬ side-effect; the gate
  message states the concrete effect. `dns.delete_record` ∧
  `tunnel.delete` = **strongest gates** — outward-facing ∧ IRREVERSIBLE
  (the public DNS record / the tunnel + credentials are destroyed;
  resolution / routes break immediately; undo = re-create).
- **Account-scoped tools** (`tunnel.*` + `zones.create`) need
  `CLOUDFLARE_ACCOUNT_ID` (the cfd_tunnel paths are
  `/accounts/{account_id}/...`; zones.create needs the owning account).
  Missing it ⇒ a typed never-faked **424** — we never build a malformed
  path / silently misroute.
- `tunnel.update_config` (`PUT .../configurations`) **replaces** the
  whole ingress rule set — ALWAYS `tunnel.get_config` first ∧ keep that
  JSON as a rollback snapshot. The LAST ingress rule MUST be a
  service-only catch-all (e.g. `{"service":"http_status:404"}`); the
  handler wraps the passed `ingress` list in `{config:{ingress:[...]}}`.
- **Cloudflare envelope** — every response is
  `{success, errors, messages, result, result_info}`. A 200-OK with
  `success:false` is STILL a failure (e.g. validation): the seam raises
  `CloudflareApiError` carrying the first `errors[].code` (`cf_code`) +
  message — never a fabricated success. `request_json` returns `result`;
  `request_envelope` keeps `result_info` (pagination) for list reads.
- **Endpoint surface verified against the official Cloudflare API v4
  docs 2026-05-21** (codebase-is-source-of-truth applied to an external
  API — shapes verified via `search_cloudflare_documentation` + the
  public reference, ¬ assumed): zones create `{name,account:{id},type}`
  → `result` zone · DNS create `{type,name,content,ttl,proxied}` →
  `result` record · DELETE → `result:{id}` · tunnel create
  `{name,config_src:"cloudflare"}` → `result` tunnel (incl. runnable
  `token`) · configs PUT `{config:{ingress:[...]}}` · verify →
  `result:{id,status:"active"}`. ✅ **LIVE-validated 2026-05-21** — during
  the `noctusai.com` production deploy this connector listed zones + **created
  the `noctusai-prod` named tunnel** (`config_src:"local"`) that cloudflared
  runs on the VPS. See `KB § GUIDES/production-deploy.md` (edge option B).

## Architecture

- Composes `_kit`: `configure_stderr_logging` · `run_stdio_server`
  (stdio bootstrap, PyPI-`mcp`-shadow + in-tree seed pin) ·
  `make_get_settings` · `build_registry` · `typed_error`. Connector body
  ≈ the leaf tool modules (`zones`, `dns`, `tunnel`, `diagnostics`) +
  `api.py` only.
- **External seam** = `cloudflare.api.request_json` /
  `request_envelope` (stdlib `urllib`, zero deps — mirrors
  n8n/waha/hostinger). Single HTTP boundary; tests
  `patch("cloudflare.api.request_json")` (external-service patch
  sanctioned, CLAUDE.md §1; our code never patched).
- Paths are **absolute** (`/zones`, `/accounts/{id}/cfd_tunnel`) —
  `normalize_base_url` only strips a trailing slash ∧ supplies the
  canonical base when unset (like WAHA/hostinger, ¬ n8n's `/api/v1`
  suffix). The base URL is fixed (single public API, ¬ per-tenant).

> ⚠️ **Cloudflare WAF — the `User-Agent` is load-bearing.** Cloudflare's
> own edge WAF can 403-ban the default `Python-urllib/x.y` user-agent
> *before auth is evaluated* — it is NOT an auth failure. The just-built
> `mcp/hostinger` hit exactly this against a Cloudflare-fronted host
> (Error 1010, verified live 2026-05-21), so `request_json` sends a
> browser-style `User-Agent` on every call (connectivity prerequisite, ¬
> impersonation). A 403 from this connector can therefore mean *either* a
> WAF block *or* a real upstream auth-denied — the typed-error message
> body carries the upstream detail to disambiguate.

## Gated-capability honesty (quad-state)

`cloudflare.diagnostics.connection_status` classifies the dependency via
a `GET /user/tokens/verify` probe: not-**configured** (no token → 424) ·
host **unreachable** (network failure → 502) · token **rejected** (401
∨ a `success:false` envelope → `authenticated=false`, `reachable=true`)
· **ok** (200 → `token_status`, e.g. `active`). Also reports
`account_id_present` (the tunnel tools need it). Never faked; boots clean
with no config.

## Config — SECRET in the connector's own `.env`

`mcp/cloudflare/.env` (gitignored) — `CLOUDFLARE_API_TOKEN` (the scoped
Bearer token, secret) + `CLOUDFLARE_ACCOUNT_ID`
(`afa8484e8c877416477a638957e5a989` at build — the account-scoped
endpoints' account id, ¬ a secret). Co-located, **independent of the
product/root `.env`** (every-connector-owns-its-auth-store, `KB §
INTEGRATIONS/vista.md § 1`). The token slot was EMPTY at build (the user
pastes it later) ⇒ run the diagnostic + reads once added. Create a
**scoped** token at `dash.cloudflare.com/profile/api-tokens` with:

- **Zone : DNS : Edit** — DNS record list/get/create/update/delete
- **Zone : Zone : Read** (+ **Edit** to create zones) — zone list/get/create
- **Account : Cloudflare Tunnel : Edit** — tunnel list/get/create/delete/config
- (+ **Account : Email Routing : Edit** later for the deferred v2 surface)

Rotate on any leak — `mcp/cloudflare/KEY-ROTATION-RUNBOOK.md` (the first
token is pasted in chat ⇒ treat as compromised, swap to a labeled
least-privilege token).

## Registration (user-gated)

`.mcp.json` add **only with explicit user approval** (MCP keep-list
rule, CLAUDE.md §1). Reuses the `mcp/noctusai/.venv` interpreter (has
`mcp`; connector adds no deps):

```json
"cloudflare": { "command": "mcp/noctusai/.venv/bin/python",
                "args": ["mcp/cloudflare/server.py"], "cwd": "<repo root>" }
```

## Tests

`mcp/noctusai/.venv/bin/python -m pytest mcp/cloudflare/tests/ -q` — no
network; pins tool-name set, dotted naming, confirm gate (ALL writes
incl. the strongest gates `dns.delete_record` + `tunnel.delete`, ¬
side-effect), the Cloudflare User-Agent header + Bearer auth, the
`success:false` envelope → typed-error-with-`cf_code`,
account-scoped-needs-account-id (424), gated-honesty (424 +
connection_status quad-state), ∧ the documented read shapes (zones/DNS
list `result` + `result_info`, tunnel account-path, configs PUT
wrapping). 25 green at build.

## Deferred — v2 surface (mapped, ¬ wrapped)

v1 wraps **zones · DNS records · tunnels** — the domain-migration need.
The Cloudflare API also exposes **Email Routing** (catch-all /
rule-based forwarding) ∧ **Registrar** (domain registration / transfer),
plus page rules, WAF, R2, Workers, DNSSEC, etc. Triage =
accept-with-rationale: file a v2 project when a consumer needs one (same
shape as how WAHA/n8n/hostinger grew their tool sets on demand). Adding
them is mechanical — a new leaf module per surface composing the same
`api.request_json` seam + confirm-gates on the writes.
