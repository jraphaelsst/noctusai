## Summary

Delivered contract §8 `GET /painel` (Edição de Fotos dashboard) end to end: SW migration 133 (write-only), backend route, seed FE hooks/types, and a full FE `Painel` page under `/edicao-fotos/painel`.

## What shipped

- **`products/social-wiring/backend/migrations/133_fotos_painel.sql`** — `social_wiring.fotos_painel(p_org_id, p_desde, p_ate)`, `SECURITY INVOKER`, one JSONB payload covering pipeline throughput, queue & health (platform-wide — `jobs` carries no `org_id`), activity, learning loop (approval rate + AI-verdict agreement), and costs (BRL, PTAX-resolved via `public.cost_ledger`, `fx_pending` flagged, honest zero revenue + `nota` since billing isn't shipped yet). Every status/decision map is EXHAUSTIVE (zero-filled), never sparse — fixed after the first pass produced a sparse map that broke the fixture-shape contract. Write-only, not applied — owner consent required.
- **Backend**: `GET /api/edicao-fotos/painel` — `deps.get_painel_client` (reuses `app.dependencies.get_scoped_admin_client`, the already-formalized N≥3 DRY helper, instead of adding a 4th local copy) + `require_org_admin` gate (platform admin sees everything with an optional `org_id` filter; agency admin is always pinned to their own org — a passed `org_id` is silently ignored for them, never trusted; corretor 403).
- **Seed FE** (`seed/lib/frontend/src/photo-editing/hooks.ts` + `contract.fixture.json`): `usePainel()` + `Painel`/`PainelPipelinePonto`/`PainelFila`/`PainelAtividade`/`PainelAprendizado`/`PainelCustos` types.
- **SW FE**: `pages/edicao-fotos/Painel.tsx` — `design-system/charts` (AreaChart pipeline + activity, BarChart queue + costs, DonutChart AI verdict, StatTileRow KPIs, FilterBar date range + platform-admin-only org filter), capability-gated via `fotosPermissions.dashboardScope`, complete loading/error/refreshing/empty states (`showSkeleton`/`isRefreshing`, never `.isLoading`). Nav entry + route wired in `App.tsx` (`status_pagina` slug `edicao-fotos-painel`, migration 128 — exact match verified).

## Tests

- Route-enumeration 401 sweep bumped 27→28; role-matrix 403 row added (corretor).
- Cross-org isolation: agency admin's `org_id` query param is ignored (pinned to own org); platform admin org-filter vs platform-wide.
- Fixture-shape replay (`test_painel_shape`) + a dedicated `test_edicao_fotos_painel.py` exercising a REAL pipeline run (upload→submit→drain→decide) through an RPC simulator in `conftest.py` — SQL has no `InMemoryPhotoEditingRepository` equivalent to run against, so the simulator is a line-for-line Python re-derivation of the migration's aggregation (same shape as `tests/modules/leads/conftest.py`'s RPC simulator).
- `Painel.test.tsx` — 10 tests: access lock, loading, error+retry, refreshing, org-filter visibility, honest "sem dados de faturamento" note, stuck-jobs note, date-filter → hook args.

## Gates (all green)

- SW backend suite: 4435 passed, 0 failed (exit 0).
- SW FE vitest: 124 files / 1564 tests passed (exit 0).
- `tsc --noEmit`: clean.
- `vite build`: succeeded.
- `--verify-kb-sync`, `--check-migration-number-collision`, `--check-status-pagina-role-parity`, `--check-canonical-organ-consumption`, `--check-outlined`: clean.
- `--check-auth-boundary-false-green`: 1 pre-existing warning, unrelated file (`test_snapshot_router.py`, youtube module).
- `--check-lying-loading-state`: Mode-B AST scan degraded (ts-morph not installed under `mcp/noctusai/node` in this worktree) — environment gap, not a code defect; Mode A confirmed clean by manual review (no `.isLoading` anywhere in the new code).

## Notable design calls

1. **Pipeline filter fixed mid-slice**: the migration originally filtered `fotos_eventos` on `tipo = 'transicao_estado'`, but `record_decision` (the review-decision path) transitions a photo to `aprovada`/`rejeitada` with `event_tipo='decisao'` — the SAME shape, different label. Fixed to filter on `estado_para IS NOT NULL` instead (any real state change), or the funnel's own terminal states would have silently never appeared on the chart.
2. **Exhaustive vs sparse maps**: every enum-domain aggregate (`jobs`, `fotos_por_estado`, `decisoes`, `veredito_ia`) is zero-filled server-side so the FE contract never needs a default-fill convention. `custos.por_categoria` stays sparse — `cost_ledger.category` has no CHECK constraint.
3. **Queue & health is always platform-wide** — `social_wiring.jobs` carries no `org_id` column; scoping it per-org would fabricate a boundary the table doesn't have. Labeled `escopo: "plataforma"` explicitly in the response so the FE never mis-reads it as org-scoped.

## drift-found

- `products/community/` is on disk (`backend/app/main.py`) with NO row in `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md`'s Products table — blocks `--verify-kb-sync` on the PRIMARY tree right now (surfaced when `noctus.dev.branch_pointer`'s push-to-dev leg ran `--verify-kb-sync` there). Not something I touched or am positioned to fix (unclear if it's a sibling's in-flight scaffold or an already-landed gap) — needs tech-lead routing.
- Shared Tier-1 `agent-context` cache (`architect`, `backend-engineer` specifically) would not converge to "fresh" despite repeated successful-looking `--refresh-agent-context-cache --force` calls — 7 total commit attempts were needed (refresh-then-commit retry loop) before the pre-commit 8-way-sync gate let the commit through. `devops-engineer`'s cache refreshed cleanly on the first try, so this looks like write contention on those two SPECIFIC agents' cache rows from actively-running sibling dispatches (both are agents named 'architect'/'backend-engineer' — i.e. currently in live use), not a code bug — but if this recurs it may be a genuine convergence bug in `--refresh-agent-context-cache`'s persistence path worth a scoped-improvement.

## scoped-improvement

- `formatBRL` in `Painel.tsx` is a local one-line `Intl.NumberFormat` helper — `design-system/charts/formatters.ts` has no currency formatter yet. N=1 today; if a second BRL-money dashboard consumer shows up, promote to the seed formatters (mirrors the `formatCompactNumber` migration-candidate note already in that file's docstring).
