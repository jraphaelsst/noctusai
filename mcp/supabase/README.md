# `mcp/supabase` — Supabase Management API connector MCP

## What this is

A connector-MCP server exposing the **Supabase Management API** (run
SQL, inspect/operate a project) as LLM-callable
`supabase.<service>.<action>` tools. **Composes `mcp/_kit`** (same shape
as `mcp/cloudflare` / `mcp/n8n` / `mcp/waha` / `mcp/hostinger` /
`mcp/github` / `mcp/vista`): bootstrap, settings, registry, error
envelope, in-tree seed pin — all inherited.

Talks to the Supabase Management API (`https://api.supabase.com`, header
`Authorization: Bearer <token>`) via the single `supabase.api.request_json`
stdlib-`urllib` seam (no extra deps). Paths are **absolute** (`/v1/projects`,
`/v1/projects/{ref}/database/query`) — no `/api/v1`-style suffix to
normalize (like WAHA/hostinger/cloudflare, unlike n8n).

> **Why it exists.** It lets the user run SQL + inspect/operate their
> Supabase project from home WITHOUT the `claude.ai`-managed
> `mcp__claude_ai_Supabase__*` connector — using a self-owned Personal
> Access Token in the connector's own auth store.

> **No envelope.** Unlike Cloudflare (which wraps every response in
> `{success, errors, result}`), the Supabase Management API returns the
> resource JSON directly (a project object, an array of projects, a query
> result-set). The seam just parses + returns the body; the truth of
> success/failure is the HTTP status (a non-2xx is surfaced as a typed
> `SupabaseApiError` carrying the upstream status — never a fabricated
> success).

> **No WAF UA trick.** `api.supabase.com` is NOT behind a Cloudflare WAF
> that bans the default urllib UA (unlike the Cloudflare-fronted hosts
> `mcp/hostinger` / `mcp/cloudflare` hit), so a plain descriptive
> `User-Agent` suffices — no browser impersonation header.

## Tool surface

| Tool | Kind | Supabase endpoint |
|---|---|---|
| `supabase.project.list` | READ | `GET /v1/projects` |
| `supabase.project.get` | READ | `GET /v1/projects/{ref}` |
| `supabase.db.query` | READ free / WRITE confirm (412) | `POST /v1/projects/{ref}/database/query` `{query, read_only}` |
| `supabase.db.list_tables` | READ | `db.query` → `information_schema.tables` |
| `supabase.db.list_schemas` | READ | `db.query` → `information_schema.schemata` |
| `supabase.migration.list` | READ | `GET /v1/projects/{ref}/database/migrations` |
| `supabase.migration.apply` | WRITE — confirm (412) | `POST /v1/projects/{ref}/database/migrations` `{query, name}` |
| `supabase.diagnostics.connection_status` | READ | `GET /v1/projects` probe |

### `db.query` — the core, with a BEST-EFFORT read/write gate

`supabase.db.query` runs raw SQL. A **pure read** (leading keyword ∈
{`SELECT`, `EXPLAIN`, `SHOW`, `WITH`, `TABLE`, `VALUES`}, after stripping
leading comments) runs **free**. **Anything else**
(INSERT/UPDATE/DELETE/DDL/CALL/TRUNCATE/...) is treated as a write and is
**confirm-gated** (`confirm` omitted/false ⇒ typed error `status 412`, NO
side-effect). The connector also passes the heuristic verdict to Supabase
as the endpoint's `read_only` flag (server-side double-guard on reads).

> **Honesty about the heuristic.** The leading-keyword check is a
> **convenience guard, NOT a security boundary** — a `WITH ... DELETE`, a
> writable function call, or a multi-statement batch can still mutate
> while *looking* like a read. When in doubt the caller should pass
> `confirm=true` deliberately. This is the gated-capability-honesty
> contract (CLAUDE.md §1): we surface the limit rather than over-promise.

`db.list_tables` / `db.list_schemas` are convenience reads built ON TOP
OF `db.query` against `information_schema` (no confirm; pure reads).

### Migrations

`migration.list` reads the applied-migration history; `migration.apply`
(confirm-gated) runs migration SQL against the **live** database AND
records it in the history. These endpoints are **stable in the Supabase
Management API v1 OpenAPI spec** (verified 2026-05-21 against
`https://api.supabase.com/api/v1-json`: `GET` + `POST` on
`/v1/projects/{ref}/database/migrations`). `db.query` also covers ad-hoc
DDL — use `migration.apply` when you want it recorded in the history.

### Project scoping

`db.*`, `migration.*`, and `project.get` are **project-scoped**. Each
accepts an explicit `project_ref` arg (wins) and otherwise defaults to
the connector's `SUPABASE_PROJECT_REF`. With neither ⇒ a typed
never-faked **424** (we never build a malformed path). `project.list` is
NOT project-scoped (needs only the token).

## Gated-capability honesty

`supabase.diagnostics.connection_status` classifies the dependency via a
`GET /v1/projects` probe: not-**configured** (no token → 424) · host
**unreachable** (network failure → 502) · token **rejected** (401/403 →
`authenticated=false`) · **ok** (2xx → `authenticated=true`). Also
reports `project_ref_present` (the project-scoped tools default to it).
Never faked; the server boots cleanly with no config.

## Config (`mcp/supabase/.env` or env) — SECRET lives here

| Var | Meaning | Default |
|---|---|---|
| `SUPABASE_ACCESS_TOKEN` | Personal Access Token (`Authorization: Bearer`) — **secret, high-privilege** | — (required) |
| `SUPABASE_PROJECT_REF` | default project ref for project-scoped tools — not a secret | — (optional; per-call override) |

Co-located `.env` (gitignored), **independent of the product/root
`.env`** — "every connector owns its own auth store" (`KB §
INTEGRATIONS/vista.md § 1`). The base URL is fixed
(`https://api.supabase.com`). Create a Personal Access Token at
`https://supabase.com/dashboard/account/tokens` (Account → Access Tokens
→ Generate new token). A PAT carries your **full account scope** across
the Management API (there is no per-resource scoping on a PAT) — treat it
as a high-privilege secret. Find the project ref at Project Settings →
General → Reference ID, or via `supabase.project.list`.

## Registration (user-gated — add only with explicit user approval)

`.mcp.json` add is **user-gated** (MCP keep-list rule, CLAUDE.md §1).
Reuses the `mcp/noctusai/.venv` interpreter (has `mcp`; this connector
adds no deps). Add this block to the `mcpServers` object in `.mcp.json`
(replace `<repo root>` with the absolute repo path):

```json
"supabase": {
  "command": "mcp/noctusai/.venv/bin/python",
  "args": ["mcp/supabase/server.py"],
  "cwd": "<repo root>"
}
```

## Tests

```
mcp/noctusai/.venv/bin/python -m pytest mcp/supabase/tests/ -q
```

No network — pure validation or `unittest.mock.patch` on
`supabase.api.request_json` (and `urllib.request.urlopen` for the
header + HTTP-error pins). Pins the tool-name set, dotted naming, the
confirm gate (db.query write + migration.apply refuse with no
side-effect; db.query read runs free), the best-effort SQL read/write
heuristic, the Bearer + plain-UA header, the HTTP-error status/message
pass-through, project-ref resolution (arg wins; missing ⇒ 424), and
gated-capability honesty (424 + connection_status tri-state).
**23 green at build.**

> **Live validation deferred.** There is no live token at build
> (`mcp/supabase/.env` `SUPABASE_ACCESS_TOKEN` is empty — the user pastes
> a Personal Access Token later). Endpoint shapes were verified against
> the live Supabase Management API v1 OpenAPI spec
> (`https://api.supabase.com/api/v1-json`); end-to-end live probing is
> deferred until the token is added (then run
> `supabase.diagnostics.connection_status` + the read tools).

## Deferred — v2 surface (mapped, not yet wrapped)

v1 covers **projects · raw SQL (db.query) · tables/schemas listing ·
migrations** — the run-SQL-from-home need. The Management API also
exposes branches, edge functions, secrets, storage, auth config,
advisors, logs, API keys, etc. Triage = accept-with-rationale: file a v2
project when a consumer needs one (same shape as how
WAHA/n8n/hostinger/cloudflare grew their tool sets on demand). Adding
them is mechanical — a new leaf module per surface composing the same
`api.request_json` seam + confirm-gates on the writes. See
`KB § MCP-SERVERS/supabase.md § Deferred v2 surface`.
