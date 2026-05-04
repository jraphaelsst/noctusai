# agno-dev-team-rollout — Master-Tree Project

> **What this is.** The master orchestrator for shipping the agno multi-agent dev team as a **measurable, customizable MVP product** in this repo. Promoted 2026-05-04 from `agno-dev-team-future-direction` (deferred) to active master-tree on user signal: *"yes please do that, then ram through it all, deliver 100%. use the new methodology to help you parallelizing batches and gaining some speed. also keep in mind that this agno team must be setup as a ready-to-fire tool, only by a switch to use."* + *"build this team to be measurable…"* + *"actually, let's transform this into an actual product, yea? recall what i said before and build a product for me on that. refactor this project so we dont lose what we already have done, but yes EVOLVE it into an mvp product."*
>
> **End state.** Two-layer architecture:
> 1. **Engine** at `dev_team/` (repo root) — reusable agno team factory + memory + telemetry + tools. Consumed by CLI, MCP, and the product backend.
> 2. **Product** at `products/dev-team/` — full FastAPI + Vite/React product inheriting from seed (`create_product_app` / `createProductApp`). MVP frontend ships 3 pages: Agents grid, Agent Detail (time-series charts + config form), Run Task. Backend exposes REST API wrapping the engine, with auth + multi-tenant + RLS via seed.
>
> Agent-callable surface: user types *"use the agno team here for this <task>"* in Claude Code → MCP `noctus.team.run` fires the engine. Or visits the product frontend → web UI fires the engine via product backend. Same engine, two surfaces.
>
> **Not used today.** No production calls; no LLM bills. The team must IMPORT cleanly, INSTANTIATE without an API key, and pass smoke tests. First real LLM call is a future user decision (the "switch flip").

- **Created:** 2026-05-04
- **Last updated:** 2026-05-04
- **Status:** **Closed ✅ — B0/B1/B2 + B5 all green; KB pattern doc + memory entry + CLAUDE.md pointer landed; tests 167/167 (engine), 25/25 (MCP), 17 + 2 skipped (product backend), 9/9 (product frontend); frontend build green; KB sync ✓.**
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Related docs:** `design-reference.md` (sibling 469-line spec, copied for posterity since `automations/` will be deleted), `live-patterns-log.md`, `cross-product-absorption-catalog.md`, `design-batch-aggregator.md`, `findings.md`. KB pattern: `KB § PATTERNS/master-tree-parallel-batches.md`.
- **Project slug:** `agno-dev-team-rollout` — cross-cutting platform-tooling. Lives at `projects/<slug>/`.
- **Branch:** `agno-dev-team-rollout` (master). Engineer worktrees branch from this per `KB § PATTERNS/branching-and-merging.md § 11.1`.

---

## 1. Context & Purpose

The user has been designing an 11-specialist hybrid agno team in a sibling lab repo (`~/Documents/repository/NoctusAI/automations/`). The 469-line spec at `automations/KNOWLEDGE-BASE/CONTEXT/07-DEV-TEAM.md` is complete on paper; **no Python implementation exists yet**. The sibling repo is also slated for deletion once absorptions complete.

This project ships the implementation INSIDE `noctusai/`, with the user-added requirement of **measurability** — every agent turn captured as telemetry so the user can evaluate per-agent performance and customize behavior:

- **Real agno code** that imports `from agno.team import Team` etc.
- **11 specialist agents** with two-layer charters (~1.5K shared + ~1-2K role).
- **15-tool catalog** with per-agent allowlists.
- **3 sub-teams** (`design_review_team`, `code_review_team`, `incident_response_team`).
- **Hybrid memory** (shared project + per-agent craft).
- **Telemetry capture** — every agent turn written to a SQLite store: tokens / cost / latency / tool calls / outcome / sub-team participation.
- **Metrics rollups** — per-agent + global rollups queryable from CLI / API / MCP.
- **REST API** — localhost-bound FastAPI for `/metrics`, `/agents/{name}/metrics`, `/configs`, `PATCH /configs/{name}`. Foundation for a future dashboard UI.
- **Provider-agnostic YAML config** mutable via API / MCP (default Opus+Sonnet mix; eval templates ready).
- **CLI v1** (`python -m dev_team run "<task>"`).
- **MCP tools** (`noctus.team.{run, status, route, metrics, agent_metrics, configure}`) so Claude Code fires + measures + customizes the team without scaffolding.
- **Smoke tests** that prove the team instantiates without an API key + the metrics surface returns sane defaults.

**Implementation gate:** the user said "not used now, but ready when I flip the switch." So scope is: scaffold + wire + import-clean + measurability + smoke-test. Real LLM calls deferred until user signals.

---

## 2. Confirmed constraints

- *"yes please do that, then ram through it all, deliver 100%."* — User authorized scaffolding + execution in one go. Phase-by-phase pause cadence overridden for this project (with the per-batch local commit gate still binding).
- *"use the new methodology to help you parallelizing batches and gaining some speed."* — Master-tree mechanics apply: parallel engineer dispatch in single tool-use turns, live-patterns-log as shared scratchpad, sync-gates pre/mid/post.
- *"this agno team must be setup as a ready-to-fire tool, only by a switch to use."* — End-state UX: trigger phrase → MCP call → team executes. No setup work between user signal and execution.
- *"build this team to be measurable…I can see, evaluate and modify their behaviour…through a control interface and see/evaluate their performance through numbers and graphs."* — Telemetry layer + REST API + MCP exposure are FOUNDATIONAL, not optional. Dashboard UI deferred to a follow-up project.
- *"skip the visual interface for now. Let's keep only with the metrics, as we grow on information, we may add graphs."* — UI carve-out confirmed; data layer must be solid so future UI is bolted-on cleanly.
- *"Maybe as a mcp utility, i dont know. You decide whats best."* — MCP-first per `feedback_mcp_first`. Ships as `noctus.team.*` tools on the existing `mcp/noctusai/` server (NOT a new MCP server — extending the living organism per `KB § PATTERNS/mcp-tool-conventions.md § 0`).
- *"Enable architect mode and start planning the dispatch of agents so we can speed up the project. Please see the branching methodology and other possible useful features."* — Architect mode active: orchestrator (this session) plans + dispatches; engineers (subagents) build in branched worktrees per `KB § PATTERNS/branching-and-merging.md § 11.1`.

---

## 3. Master-tree fit declaration

**Strict pattern fit:** the master-tree-parallel-batches pattern (`KB § PATTERNS/master-tree-parallel-batches.md`) is for N≥2 sister products with same-shape phases. This rollout is **one deliverable** (the dev_team/ package) decomposed into parallelizable subsystems — not N sister products.

**Adaptation in use:** master-tree **mechanics** apply (live-patterns-log, parallel engineer dispatch via single tool-use turns, sync-gates) WITHOUT filing 6 separate child PROJECT.md files. Children = engineer briefs in §6 below + worktree-isolated dispatches via the Agent tool. This is a deliberate adaptation — honest about the pattern fit, faithful to the speed mechanism.

The pattern's "When NOT to use" §10 lists "single-product project" first; this adaptation respects that by NOT pretending to ship 6 sister products. It uses the dispatch shape (parallel engineers in worktrees) without the full master-tree bureaucracy.

---

## 3a. Seed-first analysis

The dev_team package is a **dev-process tool**, not a product. It does not inherit from `seed/lib/backend/noctusai_lib/`'s product factories (`create_product_app`). It DOES consume noctusai_lib pieces where available:

- **`noctusai_lib.config.settings`** — read API keys + provider config from the same env shape products use.
- **`noctusai_lib.primitives.timeutil`** — for memory + telemetry timestamps.
- **`noctusai_lib.testing`** — for mock builders in smoke tests.

It does NOT add to noctusai_lib because the dev_team is not a product-facing primitive.

**Seed-first slip-check:** "deploy this team across N products" would be a slip phrase — the team is one shared instance, not per-product. The recurrence rule applies INSIDE the team (charter shapes, tool wrappers, memory IO, telemetry capture) but the team itself ships once.

---

## 4. Scope

### Product evolution (2026-05-04, post-B1)

User pivoted: *"transform this into an actual product, yea? … EVOLVE it into an mvp product."*

**Resolved architecture:** keep the `dev_team/` engine package (B1 scaffold preserved); add a NEW product at `products/dev-team/` that consumes the engine via standard product wiring. Engineer G ships product backend; engineer H ships product frontend MVP. No B1 work is discarded — the engine becomes a dependency of the product backend.

**MVP frontend (3 pages, recharts for charts):**
1. **Agents grid** — 11 cards, each: name / model / last-24h events / last-24h cost / success rate.
2. **Agent Detail** — time-series charts (cost / latency / events / success rate), recent-50 events table, config form (model + provider).
3. **Run Task** — textarea + submit → calls `/api/run` → shows team output + per-agent breakdown.

**MVP backend endpoints:**
- `GET /api/agents` — list with snapshot metrics.
- `GET /api/agents/{name}/metrics?scope=…` — per-agent rollup + last 50 events.
- `GET /api/metrics?scope=…` — global rollup.
- `POST /api/run` — fire team, return result envelope.
- `GET /api/configs` + `GET /api/configs/{name}` + `PATCH /api/configs/{name}` — config CRUD.

**Migrations:** Postgres `dev_team_telemetry_events` table mirroring engine's SQLite schema (so prod is multi-instance-safe; engine SQLite stays for local CLI / MCP usage).

### In scope (this rollout)
- Python package `dev_team/` with src layout, `__main__.py`, `cli.py`.
- 11 agent module files + shared base + shared charter loader.
- 12 charter `.md` files (Layer 1 shared + Layer 2 role × 11).
- 15-tool catalog modules + per-agent allowlist matrix.
- 3 sub-team modules.
- Memory layer (shared project + per-agent craft, file-backed; SQLite for state).
- **Telemetry layer** — agno hook integration + SQLite event store + rollup queries.
- **REST API** — FastAPI app for `/metrics`, `/agents/{name}/metrics`, `/configs`, `PATCH /configs/{name}`, `POST /eval/run`. Localhost-only by default.
- `configs/default.yaml` (Opus+Sonnet mix per sibling spec §9) + commented `codex-eval.yaml` + `gemini-eval.yaml` templates.
- Eval harness skeleton (configurable runner, no real comparisons yet).
- MCP exposure: `noctus.team.{run, status, route, metrics, agent_metrics, configure}` tools at `mcp/noctusai/tools/noctus/team/`.
- CLI: `python -m dev_team run "<task>" [--project <slug>] [--config <name>]`.
- Smoke test in `dev_team/tests/test_smoke.py` that imports + instantiates without an API key.
- README + MASTER-PROMPT for the package (per `feedback_readme_master_prompt`).
- KB pattern doc at `KB § PATTERNS/dev-team.md`.
- Three-way sync (KB + topical CLAUDE/<topic>.md + memory entry).

### Out of scope (deferred, named destinations)
- ~~**Visual dashboard UI** — confirmed deferred.~~ **REINSTATED** as MVP product frontend (3-page minimum). User pivoted 2026-05-04.
- **Real LLM calls in CI** — gated behind `DEV_TEAM_LIVE=1` env var; default test mode mocks.
- **Production deploy** — local-first; deploy is a follow-up.
- **MCP-server-only interface** (sibling's "Option B") — CLI v1 ships now; MCP server interface around the team itself is deferred. The `noctus.team.*` tools ARE the MCP surface in v1.
- **Cross-agent memory reads** — defaults to own-craft-only; cross-read flag deferred.
- **Provider mix beyond Anthropic** — Codex / Gemini configs ship as commented templates, no eval runs.

---

## 5. Architecture / Data Model

### 5.1 Package layout

```
dev_team/
├── pyproject.toml              # agno + pydantic + pyyaml + fastapi deps
├── README.md
├── MASTER-PROMPT.md
├── requirements.txt
├── src/dev_team/
│   ├── __init__.py             # lazy attrs: build_team, build_leader, MemoryStore, …
│   ├── __main__.py             # python -m dev_team
│   ├── cli.py                  # argparse entrypoint
│   ├── leader.py               # Team Leader factory (E)
│   ├── team.py                 # dev_team Team factory + recommend_route (E)
│   ├── mcp_facade.py           # MCP-facing operations (run/status/route/metrics/configure) (B1)
│   ├── agents/
│   │   ├── __init__.py         # (B1)
│   │   ├── base.py             # generic build_agent + charter loader (B1)
│   │   └── <10 specialists>.py # (E)
│   ├── teams/
│   │   ├── __init__.py         # (B1 stub; E real)
│   │   ├── design_review_team.py
│   │   ├── code_review_team.py
│   │   └── incident_response_team.py
│   ├── charters/
│   │   ├── __init__.py         # (B1)
│   │   ├── shared.md           # Layer 1, ~1.5K tokens (A)
│   │   └── <11 role charters>.md # (A)
│   ├── tools/
│   │   ├── __init__.py         # (B1)
│   │   ├── allowlists.py       # 11×15 matrix (B1 declared; B fills _RESOLVERS)
│   │   └── <15 tool modules>.py # (B)
│   ├── memory/
│   │   ├── __init__.py         # (B1 stub; C real)
│   │   ├── shared.py           # MemoryStore (C)
│   │   ├── craft.py            # per-agent <agent>.md (C)
│   │   └── store/              # data dir
│   ├── telemetry/
│   │   ├── __init__.py         # (B1 stub; C real)
│   │   ├── capture.py          # capture_event + agno hook integration (C)
│   │   ├── store.py            # SQLite schema + connection (C)
│   │   └── rollups.py          # get_metrics + get_agent_metrics (C)
│   ├── configs/
│   │   ├── __init__.py         # (B1 stub; D real)
│   │   ├── loader.py           # load_config / save_config (D)
│   │   ├── default.yaml        # Opus+Sonnet mix (D)
│   │   ├── codex-eval.yaml     # commented template (D)
│   │   └── gemini-eval.yaml    # commented template (D)
│   ├── eval/
│   │   ├── __init__.py         # (B1 stub; D real)
│   │   └── harness.py          # configurable runner (D)
│   └── api/
│       ├── __init__.py         # (B1 stub; D real)
│       ├── server.py           # FastAPI build_app (D)
│       ├── routes_metrics.py   # /metrics + /agents/{name}/metrics (D)
│       └── routes_configs.py   # GET/PATCH /configs (D)
└── tests/
    ├── __init__.py             # (B1)
    ├── test_smoke.py           # B1 contract checkpoint (✅ 11/11)
    ├── test_charters.py        # (A)
    ├── test_tools.py           # (B)
    ├── test_memory_io.py       # (C)
    ├── test_telemetry.py       # (C)
    ├── test_config_loader.py   # (D)
    ├── test_api.py             # (D)
    └── test_team_assembly.py   # (E)
```

(B1) = orchestrator-shipped contract / stub. (A)/(B)/(C)/(D)/(E)/(F) = which engineer ships.

### 5.2 MCP exposure

```
mcp/noctusai/tools/noctus/team/      # F engineer
├── __init__.py                  # register_all(server) — wires 6 tools
├── run.py                       # noctus.team.run(task, project?, config?) → {summary, status}
├── status.py                    # noctus.team.status() → memory snapshot
├── route.py                     # noctus.team.route(task) → {recommended, rationale}
├── metrics.py                   # noctus.team.metrics(scope?) → global rollup
├── agent_metrics.py             # noctus.team.agent_metrics(name, scope?) → per-agent rollup
└── configure.py                 # noctus.team.configure(name, model?, provider?, config?) → new cfg
```

Plus one-line edit to `mcp/noctusai/tools/noctus/__init__.py::register_all` to call `team.register_all(server)` alongside `dev.register_all(server)`.

### 5.3 The "switch flip" UX

Today (post-rollout): user types in Claude Code conversation:
> *"use the agno team here for this: <task>"*

Claude Code recognizes the trigger and calls `noctus.team.run(task="<task>")`. The MCP tool imports `dev_team.mcp_facade.run_team`, runs the team, returns the Leader's user-facing summary. **Zero setup work** between intent and execution. (To go from "scaffolded" to "live" is a one-time `pip install -e dev_team/` + setting `ANTHROPIC_API_KEY`.)

Customizing an agent: user calls `noctus.team.configure(name="backend_engineer", model="claude-sonnet-4-6")` from a Claude Code session, OR `PATCH http://localhost:PORT/configs/default` from a future dashboard.

Reading metrics: user calls `noctus.team.metrics()` for global, `noctus.team.agent_metrics(name="leader")` for per-agent.

### 5.4 Telemetry schema (SQLite — `dev_team/src/dev_team/memory/store/telemetry.sqlite`)

```sql
CREATE TABLE events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,             -- ISO 8601 UTC
    project         TEXT,                      -- project slug, nullable
    config_name     TEXT NOT NULL,             -- which YAML config was active
    agent_name      TEXT NOT NULL,             -- e.g. "backend_engineer"
    sub_team        TEXT,                      -- "design_review_team" / null
    turn_index      INTEGER NOT NULL,          -- per-task turn counter
    input_tokens    INTEGER NOT NULL,
    output_tokens   INTEGER NOT NULL,
    total_cost_usd  REAL NOT NULL,
    latency_ms      INTEGER NOT NULL,
    tool_calls      TEXT,                      -- JSON list of {name, args, latency_ms}
    outcome         TEXT NOT NULL,             -- "ok" | "error" | "timeout"
    output_chars    INTEGER NOT NULL,
    task_hash       TEXT                       -- sha1 of the task string for grouping
);
CREATE INDEX idx_events_agent ON events(agent_name);
CREATE INDEX idx_events_project ON events(project);
CREATE INDEX idx_events_timestamp ON events(timestamp);

CREATE TABLE schema_version (
    version INTEGER NOT NULL,
    applied_at TEXT NOT NULL
);
```

Rollup queries (in `telemetry/rollups.py`):
- `get_metrics(scope)` — totals + per-agent counts/cost/latency over the scope.
- `get_agent_metrics(name, scope)` — events / cost / avg latency / success rate / tool_call distribution for one agent.

`scope` supports None (all-time), project slug, or `last_N_days`.

---

## 6. Implementation phases — the batch plan

Sequence + parallelism per the adapted master-tree shape. Each "engineer" is an Agent tool dispatch with `isolation: "worktree"`. Master = this orchestrator session.

### Batch B0 ✅ — Audit (orchestrator-direct)
- [x] Confirmed agno on PyPI at 2.6.4; Python 3.14.2 system, repo venv 3.11; MCP requires_python>=3.10.
- [x] Confirmed `noctusai_lib.{config.settings, primitives.*, testing.*}` shapes.
- [x] Confirmed MCP server hierarchical registration (`tools/noctus/__init__.py::register_all`).
- [x] Locked package location (`dev_team/` at repo root) + MCP namespace (`noctus.team.*`).

**Improvements:** `live-patterns-log.md` rows 2-6.

### Batch B1 ✅ — Scaffold (orchestrator-direct)
- [x] Created `dev_team/` directory tree with src layout.
- [x] Shipped `pyproject.toml` (agno + pydantic + pyyaml + anthropic deps).
- [x] Shipped `__init__.py` with PEP 562 lazy attrs; `__main__.py`, `cli.py`.
- [x] Shipped `agents/base.py` (generic build_agent + charter loader) + `agents/__init__.py`.
- [x] Shipped `tools/allowlists.py` with the 11×15 matrix declared (`_RESOLVERS` empty for B engineer to fill).
- [x] Shipped contract stubs: `memory/__init__.py`, `telemetry/__init__.py`, `configs/__init__.py`, `eval/__init__.py`, `api/__init__.py`, `teams/__init__.py`, `team.py`, `leader.py`, `mcp_facade.py`.
- [x] Shipped `tests/test_smoke.py` — 11/11 passing.
- [x] `python -m dev_team --help` works; smoke contract green.
- [x] README.md + MASTER-PROMPT.md.

**Improvements:** captured in `live-patterns-log.md`.

### Batch B2/B3/B4 — PARALLEL (8 engineers, single Agent tool-use turn)

Engineers branch from `agno-dev-team-rollout` master via worktree isolation. Zero file overlap between engineers; contracts shipped in B1 stubs.

**Engine layer (6 engineers — files under `dev_team/` + `mcp/noctusai/tools/noctus/team/`):**
- **A — Charters** (`charters/*.md` + `tests/test_charters.py`)
- **B — Tools catalog** (`tools/*.py` + extends `_RESOLVERS` + `tests/test_tools.py`)
- **C — Memory + Telemetry** (`memory/{shared,craft}.py` + `telemetry/{capture,store,rollups}.py` + tests)
- **D — Configs + Eval** (`configs/{loader,*.yaml}` + `eval/harness.py` + `tests/test_config_loader.py`) — API moved to product backend (engineer G)
- **E — Leader + Team + Sub-teams + 10 Specialists** (`leader.py` + `team.py` + `agents/<10>.py` + `teams/*.py` + tests)
- **F — MCP exposure** (`mcp/noctusai/tools/noctus/team/*` + 1-line edit to `tools/noctus/__init__.py` + `mcp/noctusai/tests/test_team_tools.py`)

**Product layer (2 engineers — files under `products/dev-team/`):**
- **G — Product backend** (`products/dev-team/backend/` — FastAPI via `create_product_app`; REST API wrapping engine; migrations for telemetry events table)
- **H — Product frontend** (`products/dev-team/frontend/` — Vite/React via `createProductApp`; 3 MVP pages + recharts)

**Sync-gate (post-B2/3/4):** orchestrator merges 8 engineer branches into master, walks `live-patterns-log.md`, promotes N≥2 to absorption catalog, runs full smoke + pytest + frontend build, local commit per merged branch.

### Batch B5 ✅ — Final smoke + KB sync + close (orchestrator-direct)
- [x] `cd dev_team && pytest -q` — **167 passed in 20.7s.**
- [x] `cd mcp/noctusai && .venv/bin/pytest tests/test_team_tools.py -q` — **25 passed in 0.22s.**
- [x] `cd products/dev-team/backend && pytest tests/ -q` — **17 passed, 2 skipped.**
- [x] `cd products/dev-team/frontend && npx vite build` — **8 chunks, ✓ built in 1m 34s.**
- [x] `cd products/dev-team/frontend && npm test` — **9 passed across 3 spec files.**
- [x] `bash scripts/verify-kb-sync.sh` — **exit 0, KB sync OK.**
- [x] Authored `KB § PATTERNS/dev-team.md` (the depth doc).
- [x] Added §2 Map pointer in CLAUDE.md → `KB § PATTERNS/dev-team.md` + INDEX.md Layout entry.
- [x] Authored memory entry `feedback_dev_team_ready_to_fire.md` + indexed in `MEMORY.md` Architecture section.
- [x] §6 ↔ §11 self-check; phase headers flipped to ✅; status line in header flipped to Closed.
- [x] `noctus.dev.archive` → `archive/projects/2026-05-04/02-agno-dev-team-rollout/`.
- [ ] Final commit + push — pending user decision on branch strategy (current branch is `findings-close-batch-1d`; original branch in PROJECT.md header was `agno-dev-team-rollout`).

---

## 7. Open questions

1. **Should the dev_team package live in `noctusai_lib/` instead of repo root?** — Decided NO in B0. The dev_team serves the dev process, not products.
2. **Should we ship `/agno-team` slash command in this rollout?** — Decided OUT for v1 (MCP tool is enough; slash command sugar later).
3. **Should the smoke test attempt a mock LLM call?** — YES (B1 stub returns no-LLM; engineer C's tests will mock the anthropic Claude provider for full-flow verification without spend).
4. **Should the dashboard be in scope?** — User confirmed NO; metrics layer only. Dashboard deferred.

## 8. Dependencies & blockers

- agno on PyPI ✅ (2.6.4 confirmed).
- noctusai_lib shapes ✅ (confirmed in B0).
- Multiple parallel agents active — branching-first orchestration handles via worktree isolation.

## 9. Success criteria

1. `python -m dev_team --help` prints usage. ✅ B1
2. `python -c "from dev_team.team import build_team; t = build_team(); print(t)"` succeeds without ANTHROPIC_API_KEY (with mock provider). E
3. `cd dev_team && pytest -q` passes. (engineers + B5)
4. `cd mcp/noctusai && pytest tests/test_team_tools.py -q` passes. (F + B5)
5. `claude mcp list` shows `noctus.team.run`, `noctus.team.status`, `noctus.team.route`, `noctus.team.metrics`, `noctus.team.agent_metrics`, `noctus.team.configure`. (F + B5)
6. `bash scripts/verify-kb-sync.sh` exits 0. (B5)
7. KB pattern doc + topical pointer + memory entry all exist and reference each other. (B5)
8. PROJECT.md §6 ↔ §11 ↔ improvements.md consistent. (B5)
9. Branch `agno-dev-team-rollout` pushed to remote. (B5)
10. User can type *"use the agno team here for this: <task>"* and Claude Code can call the MCP tool. (F + B5)
11. **`noctus.team.metrics()` returns a sane (possibly-empty) rollup dict.** (C + F)
12. **`noctus.team.configure(name="leader", model="claude-haiku-4-5-20251001")` rewrites `configs/default.yaml` and the change is visible in next `noctus.team.run` call.** (D + F)

## 10. How to use this draft

- This master PROJECT.md is the orchestrator's plan. Each engineer dispatched gets a focused brief in their dispatch prompt — they do NOT read this whole doc.
- Findings flow into `live-patterns-log.md` as they happen.
- N≥2 absorption candidates flow into `cross-product-absorption-catalog.md`.
- Design Qs that affect ≥2 engineers flow into `design-batch-aggregator.md`.
- Slips, mistakes, surprising lessons flow into `findings.md` (5 categories per `feedback_knowledge_tracking`).

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-04 | Master-tree promoted from `agno-dev-team-future-direction` deferred draft. Branch `agno-dev-team-rollout` created off `origin/main`. Folder migrated. Master PROJECT.md + scratchpads scaffolded. Architecture decision: `dev_team/` at repo root, MCP exposure via `noctus.team.*`. | claude-opus-4-7 (orchestrator) |
| 2026-05-04 | B0 ✅ audit. agno 2.6.4 on PyPI; noctusai_lib shapes confirmed; MCP register pattern mapped. Naming corrected `noctus.dev.team.*` → `noctus.team.*` (3-segment rule). | orchestrator |
| 2026-05-04 | Scope extended per user: telemetry layer + REST API + 3 metrics-related MCP tools (metrics/agent_metrics/configure). Dashboard UI deferred. Engineer split revised to 6 (was 5). | orchestrator |
| 2026-05-04 | B1 ✅ scaffold + contract stubs. 11/11 smoke tests passing. Package skeleton, CLI, lazy attrs, allowlist matrix declared, all subsystem `__init__.py` modules ship try/except real-import-then-stub pattern so engineers collaborate via stub imports. | orchestrator |
| 2026-05-04 | **PRODUCT EVOLUTION.** User: "transform this into an actual product, yea? … EVOLVE it into an mvp product." Engine stays at `dev_team/` (reuse target); NEW product at `products/dev-team/` with backend (FastAPI via seed) + frontend (Vite/React MVP, 3 pages with recharts) + migrations. Engineer count: 6 → 8 (added G product backend + H product frontend). Dashboard UI re-instated as part of product MVP. | orchestrator |
| 2026-05-04 | **B5 close.** All 8 engineer slots green; full test suite verified post-merge — engine 167/167, MCP team tools 25/25, product backend 17 passed + 2 skipped, product frontend 9/9 + Vite build green. KB pattern doc landed (`KB § PATTERNS/dev-team.md`). CLAUDE.md §2 Map pointer + `INDEX.md` entry added. Memory entry `feedback_dev_team_ready_to_fire.md` filed + indexed. KB sync verified (`scripts/verify-kb-sync.sh` exit 0). Three-way sync complete. Project archived. Parallel-agent collision noted: working tree was switched mid-session from `methodology-fixes-batch-1c-followups` to `findings-close-batch-1d`, B5 doc work was wiped (uncommitted), re-authored cleanly on the new branch. | orchestrator |

## 12. No-leftovers constraint

The sibling lab repo (`~/Documents/repository/NoctusAI/automations/`) will be deleted by the user post-absorption. The 469-line spec has been **copied into `design-reference.md`** at this project's root so the design survives independently. No KB doc landed by this rollout may reference `automations/` paths.
