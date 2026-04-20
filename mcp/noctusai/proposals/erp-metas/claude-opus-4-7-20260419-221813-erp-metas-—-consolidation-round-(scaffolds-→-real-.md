# Proposal: ERP Metas — consolidation round (scaffolds → real UI + gamification extract + 5b.3 tests)

**Agent:** claude-opus-4-7
**Origin:** project:erp-metas:consolidation-2026-04-19
**Generated:** 2026-04-19 22:18
**Severity:** low
**Effort:** medium
**Affected products:** erp-imobiliario, seed
**Status:** pending

---

## 1. Context

METAS-PLAN.md had shipped backend across all phases (1-11) but frontend was half-finished — 5 scaffold pages, cross-page wiring pending, and Phase 5b.3 realdb tests not yet written. This round turned the 5 scaffolds into real functional UIs, extracted the gamification primitives to the shared design system for cross-product reuse, added the first Phase-10 homepage widget (MetasAgentWidget) to the ERP Dashboard, and wrote 6 realdb tests covering the Phase-5b trigger branches. ERP: 1765✓ / 29 skipped (new realdb tests skip cleanly without Supabase creds). Build green.

---

## 2. Situation

Five systemic observations from the round: (1) the hooks file `useMetasDomain.ts` grew several CRUD mutation hooks that mirror backend endpoints one-to-one — candidate for a `createCrudHooks`-style compression; (2) `MetasAgentWidget` hardcodes the current open period — agents in transition quinzenas may want to see closing/open side-by-side; (3) the three gamification primitives don't share a `thresholds` type — `ScorePill` and `ProgressRing` both accept `{good, warn}` but independently; (4) the ERP team drill-down computes `vgvRealizado` from rankings.vgv — it's the ranking's metric, but a true 'realized VGV' read from `meta_eventos` aggregated by equipe_id_snapshot would be more accurate for partial periods; (5) Phase 5b.3 realdb tests depend on `contratos.tipo_contrato` being one of {'venda','locacao','permuta'} — not enforced by a CHECK constraint, so typos in application code could silently route to 'venda' modalidade.

---

## 3. Proposed Solution

### 3.1 Linkage — why this solution fits this situation

Each improvement either compresses duplicated code, tightens a contract, or closes a small correctness gap exposed during the build-out.

### 3.2 Application instructions

#### 1. Compress Metas CRUD hooks via createCrudHooks

**Linkage:** 15 mutations in useMetasDomain.ts follow identical shape — post/patch/delete + invalidate + toast. Candidate for reuse.

**Steps:**
1. Audit the 15 mutation hooks for exact shape match (they do differ in invalidation keys).
2. Extract 2-3 that match fully to `createCrudHooks` (e.g. equipes basic CRUD).
3. Leave domain-specific ones (upsertMetaEmpresa, fecharPeriodo) as custom.
4. Measure LoC reduction to decide if compressing is worth it.

**Risks:** Low — the hook refactor is test-covered downstream by UI.

*Independent:* can be applied without other bundled improvements.

#### 2. Let MetasAgentWidget accept a periodoId override

**Linkage:** Today it pulls the first open period. Agents in a quinzena closing + a next-open overlap might want to view either.

**Steps:**
1. Add `periodoId?: string` prop
2. When set, resolve that period; else use the current default
3. No UI change unless a consumer passes the prop

**Risks:** None

*Independent:* can be applied without other bundled improvements.

#### 3. Define a shared Thresholds type in design-system/gamification

**Linkage:** ScorePill and ProgressRing both accept `{good, warn}` tuples. A shared `Thresholds` interface keeps them consistent.

**Steps:**
1. Add `export interface Thresholds { good: number; warn: number }` in a new index.ts under `gamification/`
2. Use it in both component prop types
3. Document in the design-system README / KB

**Risks:** None

*Independent:* can be applied without other bundled improvements.

#### 4. Add a CHECK constraint on contratos.tipo_contrato

**Linkage:** Phase 5b's locação trigger hinges on this column. A typo in application code would silently route to 'venda' modalidade, mis-scoring events. A CHECK constraint catches it at write time.

**Steps:**
1. Write migration `019_contratos_tipo_check.sql` adding `CHECK (tipo_contrato IN ('venda','locacao','permuta'))`
2. Apply via Supabase MCP
3. Mirror into the migration file (MCP-migration-mirror rule)

**Risks:** Low — existing rows that fall outside the set would fail. Audit first.

*Independent:* can be applied without other bundled improvements.

#### 5. Expose realized-VGV from meta_eventos for accurate partial-period KPIs

**Linkage:** MetasEquipeDrilldown sums `rankings.vgv` to show realized VGV — that's the ranking view, not a raw aggregate. A dedicated `/api/metas/equipes/:id/resumo` endpoint returning `{meta_vgv, vgv_realizado, eventos_count}` would be more accurate and reusable.

**Steps:**
1. Add service function `resumo_equipe(equipe_id, periodo_id)` in metas_equipe_service
2. Add router endpoint
3. Add `useResumoEquipe` hook
4. Swap MetasEquipeDrilldown's KPIs to use it

**Risks:** Low — new endpoint, no existing contract break.

*Independent:* can be applied without other bundled improvements.

### 3.3 Seed APIs / shared lib involved

N/A — change is local to the product.

### 3.4 Risks before applying

Low — all items are additive or compress-in-place without changing contracts.

### 3.5 Alternatives considered

N/A — the situation dictates the fix.

---

## 4. Effects

When this is applied, these change:

- **Behavior:** Unchanged — optimizations + small correctness tightenings
- **Coverage:** Phase 5b triggers now have realdb test coverage (6 tests)
- **Ergonomics:** Shared gamification primitives available to all products

---

## 5. Acceptance Criteria

- [ ] Fix applied to every affected product (not just the one that triggered detection)
- [ ] `python mcp/noctusai/cli.py --validate` shows 100/100 for the affected product(s)
- [ ] `python mcp/noctusai/cli.py --review --product erp-imobiliario` files no new proposals for this issue
- [ ] Backend tests still pass for the affected product(s)
- [ ] If the change touched shared code, `python mcp/noctusai/cli.py --catalog` shows no new orphans or duplicate candidates
- [ ] Documentation updated KB-first, CLAUDE.md second (per `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md → Docs stay in sync`)
- [ ] `npx vite build` green for every product that imports from `@noctusai/lib/design-system`
- [ ] Phase 5b realdb tests run green against a seeded Supabase with all 6 assertions

---

## 6. Related files

- `products/erp-imobiliario/frontend/src/pages/MetasEmpresa.tsx` — Real UI
- `products/erp-imobiliario/frontend/src/pages/MetasEquipesConfig.tsx` — Real UI
- `products/erp-imobiliario/frontend/src/pages/MetasRegrasConfig.tsx` — Real UI + CalculoConfigCard
- `products/erp-imobiliario/frontend/src/pages/MetasFechamentos.tsx` — Real UI + CSV export
- `products/erp-imobiliario/frontend/src/pages/MetasEquipeDrilldown.tsx` — Real drill-down
- `products/erp-imobiliario/frontend/src/components/MetasAgentWidget.tsx` — Phase 10 homepage widget
- `seed/frontend/lib/src/design-system/gamification/` — RankBadge / ScorePill / ProgressRing
- `products/erp-imobiliario/backend/tests/realdb/test_metas_phase5b.py` — Phase 5b.3 tests
