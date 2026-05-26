# Supabase connector MCP — `mcp/supabase`

> The **Supabase Management API surface** exposed as LLM-callable tools:
> project list/inspect, raw SQL via `db.query`, tables/schemas listing,
> and migration list/apply — plus a tri-state connection diagnostic.
> Talks to the Supabase Management API (`https://api.supabase.com`,
> `Authorization: Bearer`). Composes `mcp/_kit` (same shape as
> cloudflare/n8n/waha/hostinger/github/vista). Built 2026-05-21.

## Why it exists

It lets the user run SQL ∧ inspect/operate their Supabase project from
home **without** the `claude.ai`-managed `mcp__claude_ai_Supabase__*`
connector — via a **self-owned Personal Access Token** in the connector's
own auth store (every-connector-owns-its-auth-store). The managed
connector is fine in `claude.ai`; this is the noc-runtime equivalent the
operator controls.

## Supabase tooling map — three doors, don't conflate them

There are **three** ways Supabase is touched in this workspace. They overlap (all can run SQL) but serve different sides of the workflow — captured here so the distinction isn't re-explained each time (explanation-as-signal, `KB § 01-PHILOSOPHY.md § Always-hardening`).

| | **Supabase CLI** (`supabase`) | **`mcp/supabase`** (this connector) | **managed `mcp__claude_ai_Supabase__*`** |
|---|---|---|---|
| Who runs it | the human, in a terminal | the agent, from the noc runtime | the agent, in `claude.ai` |
| Primary job | **local dev stack** (`supabase start`) + migrations on your machine | **remote ops** on the cloud project, on-demand | remote ops on the cloud project |
| Talks to | the local Docker stack (+ a linked project) | the Management API (`https://api.supabase.com`, Bearer PAT) | Supabase's hosted MCP |
| Auth store | your machine / `supabase link` | self-owned PAT in `mcp/supabase/.env` | Anthropic-managed OAuth |
| Used in noc for | **Phase 5 dev/prod isolation** (`KB § GUIDES/production-deploy.md`; the local stack = the `dev` target of the `APP_ENV` seam) | "operate the cloud project from home without the managed MCP" | fallback; the dependency we deliberately replaced |

Rule of thumb: **CLI = your hands-on local-dev driver; this MCP = the lever the agent pulls on the live cloud project for you.** Same DB underneath, different door for a different purpose (like `psql` vs a REST admin panel).

## Tool surface (`supabase.<service>.<action>`, 3-segment dotted)

| Tool | Kind | Endpoint wrapped |
|---|---|---|
| `supabase.project.list` | READ | `GET /v1/projects` |
| `supabase.project.get` | READ | `GET /v1/projects/{ref}` |
| `supabase.db.query` | READ free / WRITE 🔒 confirm | `POST /v1/projects/{ref}/database/query` `{query, read_only}` |
| `supabase.db.list_tables` | READ | `db.query` → `information_schema.tables` |
| `supabase.db.list_schemas` | READ | `db.query` → `information_schema.schemata` |
| `supabase.migration.list` | READ | `GET /v1/projects/{ref}/database/migrations` |
| `supabase.migration.apply` | WRITE 🔒 confirm | `POST /v1/projects/{ref}/database/migrations` `{query, name}` |
| `supabase.diagnostics.connection_status` | READ | `GET /v1/projects` probe |

- **`db.query` is the core**, with a **BEST-EFFORT read/write gate**: a
  pure read (leading keyword ∈ {SELECT, EXPLAIN, SHOW, WITH, TABLE,
  VALUES}, after stripping leading comments) runs **free**; ANYTHING
  else (INSERT/UPDATE/DELETE/DDL/CALL/TRUNCATE/...) ⇒ WRITE,
  confirm-then-execute (`KB § PATTERNS/security/llm-bot-security.md`): `confirm` ≠
  true ⇒ typed error `status 412`, ¬ side-effect. The verdict is also
  passed to Supabase as the endpoint's `read_only` flag (server-side
  double-guard on reads).
- ⚠️ **The heuristic is a convenience guard, NOT a security boundary** —
  `WITH ... DELETE`, a writable function call, ∨ a multi-statement batch
  can mutate while *looking* like a read. In doubt ⇒ pass `confirm=true`
  deliberately. Surfacing this limit (¬ over-promising) IS the
  gated-capability-honesty contract (CLAUDE.md §1).
- `db.list_tables` / `db.list_schemas` = convenience reads built ON TOP
  OF `db.query` against `information_schema` (¬ confirm; pure reads;
  list_schemas excludes the pg_/information_schema internals).
- **Migrations** — `migration.list` reads the applied-migration history;
  `migration.apply` (🔒 confirm) runs migration SQL against the LIVE DB
  ∧ records it in the history. `db.query` also covers ad-hoc DDL — use
  `migration.apply` when you want it recorded.
- **Project-scoped tools** (`db.*` + `migration.*` + `project.get`)
  resolve the ref: explicit `project_ref` arg (wins) → connector's
  `SUPABASE_PROJECT_REF` default. With neither ⇒ a typed never-faked
  **424** — we never build a malformed path. `project.list` is ¬
  project-scoped (token only).
- **No envelope** — unlike Cloudflare's `{success, errors, result}`, the
  Management API returns the resource JSON directly (project object,
  array of projects, query result-set). The seam parses + returns the
  body; success/failure truth is the HTTP status (a non-2xx ⇒ typed
  `SupabaseApiError` carrying the upstream status + the `{message}`
  detail — never a fabricated success).
- **Endpoint surface verified against the live Supabase Management API v1
  OpenAPI spec 2026-05-21** (codebase-is-source-of-truth applied to an
  external API — shapes verified via `https://api.supabase.com/api/v1-json`,
  ¬ assumed): `GET /v1/projects` → array of `{id,ref,organization_id,
  name,region,created_at,status,database}` · `GET /v1/projects/{ref}` →
  one project · `POST .../database/query` body `{query (req),
  parameters?, read_only?}` → result-set · `GET .../database/migrations`
  → applied set · `POST .../database/migrations` body `{query (req),
  name?, rollback?}` → applies + records. ✅ **LIVE-validated 2026-05-22**
  (PAT pasted): the `request_json` seam authed OK (5 projects visible) ·
  `project.get` on the default `noctusai` ref · `db.query` read
  (`select count(*) from organizations` → 15) all returned live data
  through the connector's own code path.

## Architecture

- Composes `_kit`: `configure_stderr_logging` · `run_stdio_server`
  (stdio bootstrap, PyPI-`mcp`-shadow + in-tree seed pin) ·
  `make_get_settings` · `build_registry` · `typed_error`. Connector body
  ≈ the leaf tool modules (`project`, `db`, `migration`, `diagnostics`) +
  `api.py` only.
- **External seam** = `supabase.api.request_json` (stdlib `urllib`, zero
  deps — mirrors n8n/waha/hostinger/cloudflare). Single HTTP boundary;
  tests `patch("supabase.api.request_json")` (external-service patch
  sanctioned, CLAUDE.md §1; our code never patched).
- Project-ref resolution is a shared pure `api.resolve_ref(settings,
  passed)` (arg wins → settings default → 424); each leaf wraps it
  reading ITS OWN `get_settings` binding (mirrors cloudflare's per-module
  `_account_id_or_error`) so `patch("<module>.get_settings")` stays honest
  in tests.
- Paths are **absolute** (`/v1/projects`, `/v1/projects/{ref}/...`) —
  `normalize_base_url` only strips a trailing slash ∧ supplies the
  canonical base when unset (like WAHA/hostinger/cloudflare, ¬ n8n's
  `/api/v1` suffix). The base URL is fixed (single public API, ¬
  per-tenant).
- **No WAF UA trick** — `api.supabase.com` is ¬ Cloudflare-WAF-gated
  (unlike the Cloudflare-fronted hosts hostinger/cloudflare hit), so a
  plain descriptive `User-Agent` suffices (¬ a browser impersonation
  header). Auth = `Authorization: Bearer <token>`.

## Gated-capability honesty (tri-state)

`supabase.diagnostics.connection_status` classifies the dependency via a
`GET /v1/projects` probe: not-**configured** (no token → 424) · host
**unreachable** (network failure → 502) · token **rejected** (401 ∨ 403
→ `authenticated=false`, `reachable=true`) · **ok** (2xx →
`authenticated=true`). Also reports `project_ref_present` (the
project-scoped tools default to it). Never faked; boots clean with no
config.

## Config — SECRET in the connector's own `.env`

`mcp/supabase/.env` (gitignored) — `SUPABASE_ACCESS_TOKEN` (the Personal
Access Token, **secret ∧ high-privilege**) + `SUPABASE_PROJECT_REF` (the
default project-scoped ref, ¬ a secret; per-call override). Co-located,
**independent of the product/root `.env`** (every-connector-owns-its-auth-store,
`KB § INTEGRATIONS/vista.md § 1`). The token slot was EMPTY at build; a
real PAT was pasted + wired to `mcp/supabase/.env` 2026-05-22 (default
ref `nyplttplcoyiiqjrvtiw` = `noctusai`) ∧ live-validated (above). ⚠️ That
PAT was pasted in chat → rotate it once home-ops are stable (a
transcript-exposed full-account token). Create/rotate a PAT at
`supabase.com/dashboard/account/tokens` (Account → Access Tokens →
Generate). ⚠️ A PAT carries **full account scope** across the Management
API — there is NO per-resource scoping on a PAT, so treat it as a
high-privilege secret; rotate on any leak. Find the project ref at
Project Settings → General → Reference ID, or via `supabase.project.list`.

## Registration (user-gated)

`.mcp.json` add **only with explicit user approval** (MCP keep-list rule,
CLAUDE.md §1). Reuses the `mcp/noctusai/.venv` interpreter (has `mcp`;
connector adds no deps):

```json
"supabase": { "command": "mcp/noctusai/.venv/bin/python",
              "args": ["mcp/supabase/server.py"], "cwd": "<repo root>" }
```

## Tests

`mcp/noctusai/.venv/bin/python -m pytest mcp/supabase/tests/ -q` — no
network; pins tool-name set, dotted naming, the confirm gate (db.query
write + migration.apply refuse, ¬ side-effect; db.query read runs free),
the best-effort SQL read/write heuristic, the Bearer + plain-UA header,
the HTTP-error status/`{message}` pass-through, project-ref resolution
(arg wins; missing ⇒ 424), ∧ gated-honesty (424 + connection_status
tri-state). 23 green at build.

## Deferred — v2 surface (mapped, ¬ wrapped)

v1 wraps **projects · raw SQL (db.query) · tables/schemas listing ·
migrations** — the run-SQL-from-home need. The Management API also
exposes branches, edge functions, secrets, storage, auth config,
advisors, logs, API keys, page configs, etc. Triage =
accept-with-rationale: file a v2 project when a consumer needs one (same
shape as how WAHA/n8n/hostinger/cloudflare grew their tool sets on
demand). Adding them is mechanical — a new leaf module per surface
composing the same `api.request_json` seam + confirm-gates on the writes.
