# 06 — MCP Dev Toolkit

> Platform development tools exposed as an MCP server at `mcp/noctusai/`.
> Tool count is derived from `_tool(` invocations in `mcp/noctusai/server.py::list_tools()`.

## Tools

<!-- kb-counts:start:mcp_tools -->
**35 tools total** (auto-counted from `mcp/noctusai/server.py`).
<!-- kb-counts:end:mcp_tools -->

### Context
- noctusai_agent_context — full platform overview
- noctusai_product_context — product structure + docs

### Products
- noctusai_list_products, noctusai_get_product, noctusai_platform_metrics

### Scaffold
- noctusai_scaffold_product, noctusai_available_ports

### Compliance
- noctusai_validate, noctusai_validate_product
- **Detectors in `tools/compliance.py`** (deterministic, zero-AI):
  - `check_seed_compliance` — verifies `create_product_app()` usage, `-e seed/backend/*` in requirements, no boilerplate routers, `createProductApp/Layout` on frontend. **Tuned by the control-plane classification set `CONTROL_PLANE_PRODUCTS = {"core"}`**: control-plane products legitimately OWN `team` / `notifications` / custom `Layout` (they ARE the identity/team authority), so the "has own team.py / Layout.tsx" warnings are suppressed for them. Consumer products still get flagged. Introduced 2026-04-23 (originating project archived after close) (fold of `keeper-control-plane-classification` backlog).
  - `check_path_references` — catches stale `shared/*` paths that should be `seed/*`.
  - `check_standard_routers_audit` — cross-audits a product's `standard_routers=[...]` opt-in list against real frontend consumption via a curated signal map (`NotificationBell` → `notificacoes`, `/api/team` → `team`, `useLLM*` → `llm`). Flags under-grant (frontend uses → backend opts out → runtime 404s) at `critical` severity; over-grant (backend opts in → no frontend signal → dead router) at `warning`. **Self-provision v2**: AST-parses the `routers=[<mod>.router, ...]` kwarg in `main.py` to detect what the product actually wires, not what files exist in `routers/`. A `team.py` file that isn't wired no longer counts as self-provision — the frontend would still 404. Falls back to filename-based detection when the kwarg is unparseable (variable reference, dynamic). Introduced 2026-04-22; v2 AST upgrade 2026-04-23 (originating projects archived after close).
  - `check_frontend_entrypoint` — verifies the product's frontend actually CALLS `createProductApp(...)`. Two valid shapes: (a) `main.tsx` calls it directly (core pattern); (b) `main.tsx` delegates to `./App.tsx` whose default export calls it (therapy pattern). Rendering a raw `<BrowserRouter>` / `<QueryClientProvider>` tree without routing through the framework is flagged `critical` — the Suspense, error boundary, routing, providers, and auth paths are bypassed. Closes the gap where the App.tsx-scoped check in `check_seed_compliance` never fired on core (core has no App.tsx). Introduced 2026-04-23 (originating project archived after close).
  - `check_out_of_contract_trees` — global repo-root sweep (not per-product). Scans the repo root for directories that look like product trees (have `backend/app/main.py` OR `frontend/src/main.tsx`) but live outside `products/*/`. Excludes known platform dirs (`seed/`, `templates/`, `mcp/`, `KNOWLEDGE-BASE/`, `projects/`, `scripts/`, `venv/`, `.*`). Flags `critical` with a remediation pointer to either migrate to `products/<name>/` via a `<name>-seed-wiring` project or delete if legacy. Guards against future `/adconnect/`-style stray trees. Introduced 2026-04-23 (originating project archived after close).
  - `check_phase_state_consistency` — global walk (not per-product) over every `PROJECT.md` across `projects/`, `products/*/projects/`, `core/projects/`. Flags four §6 ↔ §11 drift classes: (1) §11 says shipped but §6 header lacks `✅`; (2) header has `✅` but sub-tasks remain `- [ ]`; (3) header has `✅` but no `**Improvements:**` block; (4) §11 says shipped + §6 has both unflipped header AND unticked sub-tasks (the dashboard-lying case). Severity `high`. `⏳`/`❌`/`🅿️` icons recognized as legitimate non-shipped states. Also exposed as `python mcp/noctusai/cli.py --check-phase-state` (exit 1 on mismatch); pre-commit hook runs it ONLY when `**/PROJECT.md` is staged. Introduced 2026-04-28 by `keeper-phase-state-consistency-detector` (folder deleted per clean-folder rule). Closes the slip pattern where agents wrote rich §11 entries but forgot to flip §6 checkboxes — documentation alone wasn't sufficient (caught 5+ times in two days); deterministic enforcement now blocks the slip from shipping.

### Review (observation-only — never modifies code)
- noctusai_review — detect seed-compliance issues + surface them for authoring. Three modes:
  - `mode=agent` (default): returns the issue list + a review prompt the in-session agent uses. The agent fills `templates/PROPOSAL-TEMPLATE.md` per issue using session context and files via `noctusai_file_proposal`. Zero LLM cost at this layer.
  - `mode=headless`: OpenAI `gpt-4o-mini` authors proposals (for CI / cron / solo CLI without an agent).
  - `mode=evaluate`: writes OpenAI + agent proposals side-by-side to `products/<product>/proposals/evaluations/<ts>/` for comparison.
  - Replaces the retired `noctusai_heal`. See `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md` for the full protocol (two capture triggers, phase → proposal flow, promote boundary).
- noctusai_proposal_template — return `templates/PROPOSAL-TEMPLATE.md` content so agents get a consistent starting point.
- noctusai_file_proposal — write a filled-template proposal to `products/<product>/proposals/` (keeper, via `product=`) or `projects/<slug>/proposals/` (project-phase, via `project=`).

### Analyzers
- noctusai_analyze, noctusai_analyze_patterns, noctusai_analyze_deps, noctusai_analyze_tests

### AI
- noctusai_ai_discover, noctusai_ai_advisory

### Master Prompts
- noctusai_sync_master_prompt, noctusai_sync_all_master_prompts, noctusai_check_master_prompt

### Testing
- noctusai_run_tests, noctusai_run_all_tests, noctusai_build_frontend, noctusai_build_all_frontends

### Diff & Quality
- noctusai_diff_against_seed, noctusai_find_orphans, noctusai_check_api_consistency

### Proposals
- noctusai_list_proposals, noctusai_accept_proposal, noctusai_reject_proposal

## CLI (for humans)

```bash
python mcp/noctusai/cli.py --validate
python mcp/noctusai/cli.py --review      # observation-only; files LLM-authored proposals, NEVER edits code
python mcp/noctusai/cli.py --analyze
python mcp/noctusai/cli.py --discover
python mcp/noctusai/cli.py --metrics
python mcp/noctusai/cli.py --test
python mcp/noctusai/cli.py --build
python mcp/noctusai/cli.py --proposals
python mcp/noctusai/cli.py --verify-kb-sync
```

## Architecture

```
mcp/noctusai/
  server.py         MCP server
  cli.py            CLI for humans
  tools/            Tool implementations
  .venv/            Separate venv for MCP deps
  README.md
```
