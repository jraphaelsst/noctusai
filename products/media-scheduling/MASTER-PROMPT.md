# Media Scheduling — MASTER-PROMPT

> Authoritative development guide for the seed reference product.

## Purpose

Minimal reference implementation proving the NoctusAI seed framework works end-to-end. The simplest possible product — just the spine, no domain logic. When the seed breaks, the framework broke. When creating a new product, the seed is the pattern to follow.

## Architecture

**Born from the seed framework.** This product has ZERO domain code. Everything comes from the framework.

### Backend (19 lines in main.py)

```
products/media-scheduling/backend/app/
  main.py              → create_product_app("Media Scheduling", "media_scheduling", settings)
  config.py            → SeedSettings(ProductSettings) — no extra fields
  database.py          → create_database_module(settings, "media_scheduling")
  dependencies.py      → create_dependencies(db)
  rate_limit.py        → create_product_limiter(settings)
  routers/             → EMPTY — framework provides health, team, notifications
```

### Frontend (App.tsx uses framework factories)

```
products/media-scheduling/frontend/src/
  App.tsx              → createProductApp() + createProductLayout()
  vite.config.ts       → createViteConfig({ port: 8130 }) — 3 lines
  pages/               → Dashboard (stack status), Equipe (team), Landing, Login, etc.
  hooks/               → useNotificacoes (from seed lib)
  components/          → NotificationBell, ErrorBoundary, AuthProvider (from seed lib)
  NO Layout.tsx        → framework provides it via createProductLayout()
```

### Database

Schema: `seed` — only `status_pagina` (feature flags) and `invitations` (team invites). Zero domain tables.

## What the framework provides automatically

- `/api/health` — health check
- `/api/team` — team management (invite, accept, list, cancel, remove)
- `/api/notificacoes` — notification proxy to core
- `/api/llm/providers`, `/api/llm/models`, `/api/llm/preferences` — shared LLM router from `noctusai_seed.llm_router`
- Multi-provider LLM access: `create_product_app()` auto-wires `configure_credentials()` + `configure_llm(default_llm_config())` + `shutdown_llm()` in lifespan. Products inherit `noctusai_lib.llm.chat_completion` / `generate_embedding` / `transcribe_audio` / `analyze_image` with zero plumbing. Override only when the product needs different defaults: `create_product_app(..., llm_config=default_llm_config(default_chat_model="gpt-4o"))`.
- CORS, Sentry, exception handlers, middleware, rate limiting, logging
- Sidebar, Header, AppShell, page status filtering, SSO context, trial/license warnings
- TooltipProvider, QueryClientProvider, AuthProvider, ErrorBoundary, Suspense

## Template Auto-Sync

The seed is the source for `templates/product-seed/`. Post-commit hook runs `scripts/sync-seed-template.sh`:
1. Copies seed → template
2. Replaces values with `{{PLACEHOLDERS}}`
3. Template always in sync

Do NOT edit `templates/product-seed/` directly.

## Rules

- Keep the seed minimal — zero domain logic
- Any new framework feature must work in the seed first
- Changes to the seed propagate to the template automatically
- All tests must stay green; treat any red as a framework regression first

## Testing

```bash
cd products/media-scheduling/backend && pytest
cd products/media-scheduling/frontend && npx vite build  # must build clean
```

## Dependencies

- Backend: `noctusai_lib` (code library) + `noctusai_seed` (framework)
- Frontend: `@noctusai/lib` (code library) + `@noctusai/seed` (framework)

## Methodology evolution — 2026-05-11

Active rules this product exercises as the seed reference. Pointers, not bodies — open the KB doc on demand.

- **Codification pipeline (4 stages).** New rules walk Stage 1 (emerges) → Stage 2 (memory) → Stage 3 (KB pattern + CLAUDE.md pointer) → Stage 4 (`check_*` keeper detector + colocated regression test). When the seed gains a new convention, route it through the stages — don't stall at memory. → `KB § CONTEXT/PATTERNS/methodology-codification-pipeline.md`
- **Doc-code coherence.** Any tool / detector / flag change updates its doc surfaces (KB pattern docs, Situation→Tool maps, CLAUDE.md pointers, INDEX.md, `--help`, per-product README/MASTER-PROMPT references) in the **same commit**. "Later" is forbidden. Discovery: `grep -rn "<tool-name>" KNOWLEDGE-BASE/ CLAUDE.md CLAUDE/ products/*/MASTER-PROMPT.md`. → `CLAUDE.md §1` + codification candidate `check_doc_tool_reference_drift`.
- **Keeper grew to 32 detectors.** Live list via `noctus.dev.outline_python mcp/noctusai/tools/noctus/dev/compliance.py`. New since seed reference last refresh include `check_doc_tool_reference_drift`, `check_detector_has_regression_test`, `check_section_7_placeholder_consistency`, `check_mcp_write_tool_worktree_arg`, `check_mcp_path_via_settings`, `check_auth_dep_anti_pattern`, `check_no_silent_ok_comment`, `check_pipefail_grep_q`, `check_slowapi_with_pep563`, `check_test_status_assertion`. Each ships a colocated `Test<CamelCase>` regression — meta-detector enforces.
- **Seed mock predicate fix (commit `f3aabfd`).** `_eval_is` now dispatches PostgREST IS-NULL sentinels (`"null"`/`"true"`/`"false"`) with soft compat for literal-string equality; `_FilterMixin.not_` is an actual negator. Test predicates against the seed `MockSupabaseClient` now match production PostgREST semantics — fixture data must use real values, not literal-string shims.
- **Canonical rate-limit policies.** `noctusai_lib.api.rate_limit_policies` exports named buckets (`DEFAULT_AI_RL` / `DEFAULT_AUTH_RL` / `DEFAULT_WEBHOOK_RL` / `DEFAULT_PORTAL_RL`). Replaces N=10+ products' hard-coded `@limiter.limit("30/minute")` literals. Tune at the seed; products inherit. Shape invariant enforced by regression test.
- **Bootstrap auto-hydrate.** `scripts/bootstrap-worktree.sh` runs pre-hydrate cleanup of stale `.claude/worktrees/agent-*/` (companion to disk-usage monitor at ≥80%). Sibling-workspace bootstrap drops Docker + start.sh/stop.sh + scaffolded skeletons day-one; `docker compose up` is the deploy drill.

## Local notes — media-scheduling specific

- **OAuth credentials shape is single-tenant.** Route filters `oauth_credentials` by `.eq("provider", "google")` + `.limit(1)` with no `org_id` filter (per route docstring). Test fixtures MUST seed `provider="google"` for `MockSupabaseClient` predicate filtering to match. Engineer S landed the fixture fix in commit `d3b46c6` (single test affected).
- **Calibration: callsite count is a loose upper bound.** The 28-callsite tally for the seed mock predicate fix over-projected actual failures by ~28× — count-of-callsites is a worst-case ceiling, not a forecast. When estimating latent-fix wave scope, read the fixture shape against the route's actual predicate, not callsite totals.
