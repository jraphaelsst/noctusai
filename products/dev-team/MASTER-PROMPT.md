# MASTER-PROMPT — products/dev-team

> **Audience.** Future Claude Code session touching `products/dev-team/`.
> Read this before editing anything here.

## What this product is

A thin FastAPI + Vite/React product that exposes the **engine at `dev_team/`**
(repo root) over an authenticated REST API + MVP web UI. The engine is the
real thing — 11 agno specialists, telemetry, configs, MCP tools. This product
is the **multi-tenant face** of the engine.

**Read first:**
- `projects/agno-dev-team-rollout/PROJECT.md` — full design (§4 product
  evolution, §5 architecture, §5.4 telemetry schema).
- `dev_team/MASTER-PROMPT.md` — the engine you wrap.
- `seed/framework/backend/noctusai_seed/app.py` — `create_product_app`
  signature this product calls.

## Rules for this product

1. **API endpoints wrap `dev_team.mcp_facade` — never re-implement engine
   logic in product code.** The wrap layer (`app/services/dev_team_proxy.py`)
   adds per-tenant scoping (`org_id` from auth) and adapts return shapes for
   the frontend; the team-running, metrics, and config logic live in
   `dev_team/`.
2. **Every telemetry write is tagged with the caller's `org_id`.** The
   engine's SQLite store stays as the single-tenant local store; this
   product mirrors the schema in Postgres (`dev_team.dev_team_telemetry_events`)
   under RLS.
3. **`/api/run` defers the activation gate to the engine.** When
   `ANTHROPIC_API_KEY` is absent, the engine returns a "switch-not-flipped"
   envelope; the API just passes that through with a 200 (it's not an error,
   it's design — the team is import-clean, the user just hasn't flipped the
   switch).
4. **Auth via seed.** `from app.dependencies import get_current_user, get_org_id`
   — never roll your own JWT logic. The seed wires `auth.get_user(token)`
   against Supabase.
5. **No engine modifications from here.** If the wrap surface is wrong,
   amend `dev_team/src/dev_team/mcp_facade.py` (engine), then re-wrap.
   Product code never edits the engine.
6. **Migrations land in `products/dev-team/backend/migrations/`** with the
   `dev_team` schema. Apply via Supabase MCP first, then commit the SQL
   file (per `feedback_mcp_migrations_mirror_file`).

## API contract (locked)

```
POST   /api/run                     {task, project?, config?}  → run envelope
GET    /api/agents                  → [{name, model, last_24h_events,
                                        last_24h_cost, success_rate}, ...11]
GET    /api/agents/{name}/metrics?scope=…
                                    → {agent, scope, events, cost,
                                        avg_latency, success_rate,
                                        tool_call_distribution,
                                        recent_events: [...50]}
GET    /api/metrics?scope=…         → engine.metrics_snapshot(scope)
GET    /api/configs                 → [{name, summary}, ...]
GET    /api/configs/{name}          → full config dict
PATCH  /api/configs/{name}          {agent_name, model?, provider?}
                                    → updated config dict
```

All routes are 401 without `Authorization: Bearer <jwt>`. All routes are
401/403 if the user lacks an `org_id` claim.

## Wrap-surface convention

`app/services/dev_team_proxy.py` is the single chokepoint between product
HTTP routes and the engine. Every endpoint imports from here, NOT directly
from `dev_team.*`. This keeps:

- **Test isolation:** `patch.object(app.services.dev_team_proxy, "<fn>", ...)`
  in tests instead of patching engine internals.
- **Per-tenant injection:** the proxy is the place to inject `org_id`
  scoping when the engine grows multi-tenant primitives.
- **Engine evolution insulation:** if the engine's facade signature changes,
  one file changes here, not 4 routers.
