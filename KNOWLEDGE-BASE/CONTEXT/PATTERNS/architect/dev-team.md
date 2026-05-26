# dev-team — agno multi-agent dev team (engine + product)

> The repo's reusable agno multi-agent dev team. Two layers: a reusable
> **engine** at `dev_team/` and a **product** at `products/dev-team/`.
> Shipped 2026-05-04 by `projects/agno-dev-team-rollout/` (master-tree
> with 8 parallel engineers, see `KB § PATTERNS/architect/master-tree-parallel-batches.md`).
>
> The team is *ready to fire* — imports cleanly without an API key, all
> smoke + integration tests green — but does not call any LLM until the
> user flips the switch (`ANTHROPIC_API_KEY` set + an explicit
> invocation that is not `dry_run=True`).

---

## 1. When to use it

The dev_team is a **dev-process tool**, not a product feature.

Use it when:
- You want to dispatch a real-LLM dev team on a task from inside Claude
  Code: type *"use the agno team here for this: <task>"* — the
  trigger fires `noctus.team.run`.
- You're running headless evals across providers (Opus / Sonnet / Codex
  / Gemini) and want per-agent telemetry.
- You're building a control surface (the product frontend at
  `products/dev-team/frontend/` IS that surface for v1).

Do NOT use it for:
- Per-product agentic features — those belong in the product's own
  service layer, not the dev_team. The dev_team is shared dev tooling.
- Real-time chat — agno's `Team.run` is request/response, not
  streaming-conversational.
- Anything that should not be measurable per-turn — telemetry capture
  is on by default and writes to a SQLite event store.

---

## 2. Two-layer architecture

```
dev_team/                     ← engine (repo root)
  src/dev_team/
    leader.py / team.py       ← agno Team + Leader factories
    agents/<11>.py            ← role-specific build_<agent>(charter, …)
    teams/<3>.py              ← design_review / code_review / incident_response sub-teams
    charters/                 ← Layer 1 shared.md + Layer 2 per-role *.md
    tools/                    ← 15-tool catalog + per-agent allowlists
    memory/                   ← shared project + per-agent craft (file-backed; SQLite for state)
    telemetry/                ← agno-hook capture + SQLite store + rollups
    configs/                  ← default.yaml (Opus+Sonnet) + commented codex/gemini templates
    eval/                     ← configurable eval harness
    mcp_facade.py             ← MCP-facing operations (run/status/route/metrics/configure)
    cli.py                    ← `python -m dev_team run "<task>"`

products/dev-team/            ← product (multi-tenant FastAPI + Vite/React via seed)
  backend/
    app/api/                  ← /agents, /metrics, /configs, /run wrappers
    app/services/             ← engine bridge + telemetry mirror
    migrations/               ← dev_team_telemetry_events Postgres table
  frontend/                   ← 3-page MVP: Agents grid, Agent Detail (recharts), Run Task

mcp/noctusai/tools/noctus/team/   ← MCP exposure (6 tools)
  run.py / status.py / route.py / metrics.py / agent_metrics.py / configure.py
```

**Engine consumed twice.** The CLI and the MCP tools both import
`dev_team.mcp_facade` directly (single in-process call). The product
backend wraps the same facade behind FastAPI endpoints — same engine,
two surfaces, identical behavior.

---

## 3. The "switch flip" UX

By design, no LLM call fires until the user flips the switch:

| State | Behavior |
|---|---|
| `ANTHROPIC_API_KEY` unset | `noctus.team.run(task=…)` → `{"status": "switch-not-flipped"}` |
| Key set, `dry_run=True` | Build the team, return assembled member list, no LLM call |
| Key set, `dry_run=False` | Run the team, capture telemetry, return Leader's user-facing summary |

This means: the package can ship into prod safely. Smoke tests green,
import-clean, no spend. First real call is an explicit user decision.

---

## 4. Public surface

### Engine

```python
from dev_team import build_team, build_leader, load_charter, MemoryStore
from dev_team.mcp_facade import run_team, get_status, route_task, get_metrics

team = build_team()                          # all 11 specialists + leader + 3 sub-teams
result = team.run(task="…")                  # only fires LLM if key + not dry-run
envelope = run_team(task="…", dry_run=True)  # MCP-shaped envelope (the canonical API)
```

### MCP (`noctus.team.*`)

| Tool | Input | Output |
|---|---|---|
| `noctus.team.run` | `task, project?, config?, dry_run?` | `{status, summary, …}` |
| `noctus.team.status` | `project?` | `{snapshot}` |
| `noctus.team.route` | `task` | `{recommended, rationale}` |
| `noctus.team.metrics` | `scope?` | `{rollup}` |
| `noctus.team.agent_metrics` | `name, scope?` | `{rollup}` |
| `noctus.team.configure` | `name, model?, provider?, config?` | new cfg |

All wrap `dev_team.mcp_facade` via lazy imports inside the FastMCP
handler (cold-start stays light; agno only loads when invoked).

### Product backend (FastAPI)

`GET /api/agents`, `GET /api/agents/{name}/metrics`, `GET /api/metrics`,
`POST /api/run`, `GET/PATCH /api/configs/{name}`. All authenticated
via the seed's `make_get_current_user_org` factory. Schema:
`dev_team`. Default backend port: 8009.

### Product frontend (Vite/React)

Three pages: **Agents grid** (11 cards), **Agent Detail** (recharts
time-series + recent-events table + config form), **Run Task**
(textarea → `POST /api/run` → result envelope). Default frontend
port: 8123.

---

## 5. Telemetry — per-turn measurability

Every agent turn writes a row to `dev_team/src/dev_team/memory/store/telemetry.sqlite`:

```sql
events(
  id, timestamp, project, config_name, agent_name, sub_team,
  turn_index, input_tokens, output_tokens, total_cost_usd,
  latency_ms, tool_calls, outcome, output_chars, task_hash
)
```

Capture is via two wrappers — `TelemetryWrappedTeam` and
`wrap_agent_run` — because agno 2.6.4 does not yet expose a
first-class post-turn hook. Both intercept `run()`, time it, extract
usage, write the event. When agno gains hooks, the wrapper internals
swap; the `register_team_hooks` / `register_agent_hooks` public
surface stays.

Rollups in `telemetry/rollups.py`:
- `get_metrics(scope)` — totals + per-agent counts/cost/latency.
- `get_agent_metrics(name, scope)` — events / cost / avg latency /
  success rate / tool-call distribution for one agent.

`scope` accepts `None` (all-time), a project slug, or `last_N_days`.

The product backend mirrors this schema into Postgres
(`dev_team_telemetry_events`) for multi-instance prod safety; the
engine's local SQLite stays for CLI / MCP usage.

---

## 6. Charters — two-layer prompt structure

| Layer | File | Token budget | Purpose |
|---|---|---|---|
| Layer 1 | `charters/shared.md` | ~1.5K | All 22 CLAUDE.md §1 rules + the "Your role" handoff |
| Layer 2 | `charters/<role>.md` | ~1-1.2K | Role-specific responsibilities + tool guidance |

Loader: `dev_team.agents.base.load_charter(role)` reads
`<CHARTER_DIR>/<role>.md`. Test isolation uses module-level
`CHARTER_DIR` / `SHARED_CHARTER_FILE` setters (no monkeypatching of
`load_charter` itself — compliant with `feedback_no_monkeypatching_in_tests`).

11 roles: `leader`, `solution_architect`, `backend_engineer`,
`frontend_engineer`, `code_reviewer`, `security_engineer`,
`devops_engineer`, `qa_engineer`, `ux_designer`, `product_manager`,
`technical_writer`. 3 sub-teams: `design_review_team`,
`code_review_team`, `incident_response_team`.

---

## 7. Tools — 15-tool catalog + per-agent allowlists

`tools/allowlists.py` declares an 11×15 matrix. `_RESOLVERS` maps each
tool name to a callable. Per-agent allowlists prevent (e.g.) the UX
designer from firing `keeper_review` or the technical writer from
running `edit_files(mode="ast")`.

Notable shapes:
- **`edit_files(mode="ast")` is the SOLE write-side code-edit path.**
  Calling with any other mode raises a clear ValueError pointing to
  `KB § PATTERNS/common/ast.md`. The AST-first rule is wired structurally at
  the tool layer, not just by convention.
- **`web_search` is env-gated**: stub raises `NotImplementedError` if
  `SERPER_API_KEY` unset; live path imports `requests` lazily.
- **`ast_typescript`** is stubbed (ts-morph runs in Node, not Python).
  Follow-up: `dev_team.tools.ts_bridge` invoking a small Node script
  via subprocess.

The four `tools/noctus/dev/{recurrence, compliance, review, proposals}`
wrappers add `mcp/noctusai/` to `sys.path` lazily via
`tools/_mcp_path.py` — keeps dev_team's import-time path clean; only
fires when a wrapper is actually called.

---

## 8. Configs — provider-agnostic + mutable

`configs/default.yaml` ships the Opus+Sonnet mix per the design
reference. `codex-eval.yaml` and `gemini-eval.yaml` ship as commented
templates (no eval runs).

Loader: `dev_team.configs.load_config(name)` /
`save_config(name, cfg)`. The MCP `noctus.team.configure` tool calls
`save_config`. The product backend's `PATCH /api/configs/{name}`
endpoint wraps the same.

Eval harness in `eval/harness.py` accepts an injected `team_builder`
keyword — DI doubles as the test-mode switch. With the default
builder, the `ANTHROPIC_API_KEY` guard fires; with an injected
builder, the harness runs without keys (no monkeypatching of dev_team's
own code).

---

## 9. How to extend

| Want to | Do |
|---|---|
| Add a new role | New charter `.md` + new `agents/<name>.py` with `build_<name>(charter, …)` + add to `agents/__init__.py` exports + extend allowlist matrix + extend `team.py::build_team` |
| Add a new tool | New `tools/<tool>.py` with the resolver function + register in `_RESOLVERS` + add to allowlist matrix |
| Add a new sub-team | New `teams/<name>_team.py` + add to `teams/__init__.py` exports |
| Add a new MCP tool around the engine | New `mcp/noctusai/tools/noctus/team/<name>.py` with `RunInput` / `RunOutput` Pydantic + `register(server)` + add to `team/__init__.py::register_all` |
| Swap the LLM provider | New `configs/<name>.yaml` (start from a template) + invoke with `--config <name>` (CLI) or `config="<name>"` (MCP) |

---

## 10. Wiring recipe — installing the package locally

```bash
cd dev_team/
python3.11 -m venv .venv
.venv/bin/pip install -e ".[testing]"           # engine + agno + tests
.venv/bin/pip install --no-deps -e ../seed/lib/backend  # noctusai_lib (deps already installed by seed/lib's pyproject)
.venv/bin/pip install libcst                    # AST tool
.venv/bin/pytest -q                             # 167/167 should pass
python -m dev_team --help                       # CLI entry
```

For the product:

```bash
cd products/dev-team/backend
python3.11 -m venv .venv
.venv/bin/pip install --no-deps -e ../../../seed/lib/backend ../../../seed/framework/backend ../../../dev_team
.venv/bin/pip install fastapi pydantic pydantic-settings supabase==2.9.1 PyJWT slowapi sentry-sdk pytest httpx anthropic pyyaml agno google-api-python-client google-auth google-genai jinja2 openai redis
.venv/bin/pytest tests/ -q

cd ../frontend
npm install
npx vite build
npm test
```

---

## 11. Anti-patterns

- **Treating dev_team as a product primitive.** It's not. It does NOT
  inherit from `noctusai_lib` product factories. It consumes
  `noctusai_lib.config.settings` + `noctusai_lib.primitives.timeutil`
  + `noctusai_lib.testing` and that's it. Don't add it to
  `noctusai_lib`.
- **Per-product dev_team instances.** "Deploy this team across N
  products" is the slip phrase per `feedback_replication_to_seed_slip`
  — the team is one shared instance, not per-product. The recurrence
  rule applies INSIDE the team (charter shapes, tool wrappers, memory
  IO, telemetry capture) but the team itself ships once.
- **Making real LLM calls in CI.** Gated behind `DEV_TEAM_LIVE=1` env
  var; default test mode mocks. Do not unset the gate without an
  explicit user-approved live-spend test plan.
- **Monkeypatching dev_team modules in tests.** Use the module-level
  setters (`set_store_root`, `set_db_path`, `CHARTER_DIR`,
  `SHARED_CHARTER_FILE`) and DI-keyword overrides
  (`team_builder=` in the eval harness) instead. External
  integrations (agno, anthropic) MAY be patched at the wrap boundary
  per the `unittest.mock.patch.object` carve-out.

---

## 12. Where to look next

- Project: `projects/agno-dev-team-rollout/` (or its archived copy in
  `archive/projects/2026-05-04/`) for the rollout playbook + findings.
- Engine entry: `dev_team/src/dev_team/__init__.py` (lazy attrs) →
  `team.py::build_team` for the assembly.
- MCP entry: `mcp/noctusai/tools/noctus/team/__init__.py::register_all`.
- Product entry: `products/dev-team/backend/app/main.py` (built via
  seed factory) → `app/api/` for endpoints.
- Telemetry schema: `dev_team/src/dev_team/telemetry/store.py`.

Memory entry: `feedback_dev_team_ready_to_fire.md`.
