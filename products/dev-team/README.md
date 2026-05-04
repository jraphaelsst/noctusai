# dev-team — agno multi-agent dev team product

> **Two-layer architecture.** The reusable engine lives at the repo root in
> `dev_team/` (consumed by CLI + MCP + this product). This product wraps the
> engine with auth + multi-tenant + RLS + a REST API + a 3-page frontend.
>
> See `projects/agno-dev-team-rollout/PROJECT.md` §4 for the full design.

## What this is

A NoctusAI product that exposes the agno multi-agent dev team to authenticated
users via a REST API and an MVP web UI. The engine itself (11 specialists,
3 sub-teams, 15-tool catalog, telemetry layer, provider-agnostic configs)
ships once at `dev_team/` and is consumed by:

- **CLI** — `python -m dev_team run "<task>"`
- **MCP** — `noctus.team.{run, status, route, metrics, agent_metrics, configure}`
- **This product** — `/api/run`, `/api/agents`, `/api/agents/{name}/metrics`,
  `/api/metrics`, `/api/configs`, `/api/configs/{name}` (REST + web UI)

The product backend is the multi-tenant face of the engine — every API call
runs through seed auth (`get_current_user` + JWT-derived `org_id`), every
telemetry write is tagged with the caller's `org_id`, and Postgres RLS on
`dev_team.dev_team_telemetry_events` enforces per-org isolation.

## Architecture

- **Engine:** `dev_team/` (repo root) — Python package, agno `Team` + memory
  + telemetry + tools + configs. Local SQLite for telemetry stays for CLI /
  MCP single-tenant usage.
- **Backend:** `products/dev-team/backend/` — FastAPI via `create_product_app`
  (seed factory). Routes under `/api/`. Wraps `dev_team.mcp_facade` for the
  team operations + `dev_team.configs` for the config CRUD.
- **Frontend:** `products/dev-team/frontend/` — Vite/React via
  `createProductApp` (seed factory). 3 pages: Agents grid / Agent detail /
  Run task.
- **Multi-tenancy:** every event written with `org_id` from the JWT; reads
  scoped via Supabase RLS.

## Quick start

```bash
# Install deps (root + product)
pip install -r requirements.txt
pip install -r products/dev-team/backend/requirements.txt

# Make the engine importable
pip install -e dev_team/

# Apply migrations
# (run the SQL files in products/dev-team/backend/migrations/ via the
#  Supabase MCP or psql against the dev_team schema)

# Dev server
cd products/dev-team/backend
bash start.sh   # uvicorn app.main:app --reload --port 8009

# Tests
pytest tests/ -v
```

## API

| Route | Method | Purpose |
|---|---|---|
| `/api/run` | POST | Fire the team. Body: `{task, project?, config?}` |
| `/api/agents` | GET | 11 agents with snapshot metrics (last-24h events / cost / success-rate) |
| `/api/agents/{name}/metrics` | GET | Per-agent rollup + last-50 events |
| `/api/metrics` | GET | Global metrics rollup (`?scope=…`) |
| `/api/configs` | GET | List configs + summary of each |
| `/api/configs/{name}` | GET | Full config dict |
| `/api/configs/{name}` | PATCH | Update one agent's `model` / `provider`. Body: `{agent_name, model?, provider?}` |

All routes require `Authorization: Bearer <jwt>`. Auth + org-scoping handled
by seed (`noctusai_seed.create_dependencies`).

## Switch-flip behavior

If `ANTHROPIC_API_KEY` is not set on the backend process, `POST /api/run`
returns a `{"status": "switch-not-flipped", ...}` envelope rather than 5xxing.
Mirror of `dev_team.mcp_facade.run_team`'s carve-out — the team is always
import-clean and ready; activation is a one-time env-var flip.

## Pointers

- Master plan — `projects/agno-dev-team-rollout/PROJECT.md`
- Engine — `dev_team/README.md` + `dev_team/MASTER-PROMPT.md`
- Seed factory — `seed/framework/backend/noctusai_seed/app.py::create_product_app`
- Telemetry schema — `projects/agno-dev-team-rollout/PROJECT.md` §5.4
