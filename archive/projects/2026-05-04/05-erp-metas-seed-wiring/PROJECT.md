# erp-metas-seed-wiring — Project Document

> Wiring project for the `erp-imobiliario` consumer of `noctusai_lib.domain.metas`
> (the seed module shipped 2026-05-03 by `metas-domain-seed-absorption`).
> Sister of `pf-metas-seed-wiring` and `daily-life-goals-seed-wiring`,
> dispatched in parallel as Batch 1C of the in-flight-execution-rollout.

- **Created:** 2026-05-04
- **Last updated:** 2026-05-04
- **Status:** Done ✅ — Phase 0 ✅ + Phase 1 ✅ + Phase 2 ✅
- **Owner / stakeholders:** joaoraphaelsst (architect) · Engineer B (this engineer)
- **Related docs:**
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/metas-seed.md` — wiring recipe (seed-side reference).
  - `projects/metas-domain-seed-absorption/proposals/claude-opus-4-7-20260503-end-of-project-bundle.md` — bundled proposal §2.1, §2.2, §2.4.
  - `seed/lib/backend/noctusai_lib/domain/metas/` — the lifted module (commit `09fa759`).
- **Project slug:** `erp-metas-seed-wiring` (intent = `wiring`, lives at `projects/<slug>/` per Engineer 3's plan).

---

## 1. Context & Purpose

The N=3 `metas-domain-seed-absorption` project (PF + ERP + daily-life)
shipped `noctusai_lib.domain.metas` on 2026-05-03 — a pure-domain
primitive containing `compute_progress`, `accumulate_contribution`,
`project_completion_date`, `period_bounds`, `count_business_days`,
`proportional_target`, `next_status` / `from_pt_string` / `to_pt_string`,
plus value objects (`Goal`, `Target`, `Progress`, `Period`,
`Contribution`, `ProgressTransition`), enums (`GoalStatus`,
`PeriodKind`), and the `GoalRepository` Protocol.

The `metas/periods.py` module is a **verbatim port of ERP's
`metas_service.py` math** — `_period_end_date`, `_count_weekdays`,
`_dias_uteis_*`, `_calcular_meta_proporcional` — with `proportional_target`
extending the ERP shape to QUARTERLY. The `period_bounds` helper in the
seed unifies ERP's two parallel implementations: `_period_end_date` in
`metas_service.py` and `quinzena_bounds` / `mes_bounds` /
`trimestre_bounds` in `meta_periodos_service.py`.

This wiring project closes the recurrence by deleting all duplicating
local helpers from `metas_service.py` and `meta_periodos_service.py` and
having both services consume the seed module. ERP-specific keepers stay:
schema names (`metas` / `meta_periodos`; `meta_pretendida` /
`meta_realizada` / `valor_meta`), Supabase persistence + RLS,
`criar_metas_hoje` cron-style batch generator, `gerar_trimestre`
parent-child cascade (N=1).

The win: ERP's metas math becomes a thin boundary mapper over the seed
primitive; future product cycles (e.g. a 4th product) consume the seed
without ERP's helpers needing to be touched again.

---

## 2. Confirmed constraints

Inherited from the dispatch brief and Engineer 3's bundled proposal —
not a fresh user interrogation (parallel batch under master orchestrator).

- **Schema vocabulary stays product-side** — `meta_pretendida` /
  `meta_realizada` / `valor_alvo` / `meta_vgv` / `valor_meta` and the
  table names (`metas`, `meta_periodos`, `metas_empresa`,
  `metas_equipe`) are ERP keepers. *(Boundary-map at the service layer;
  the seed never sees ERP column names.)*
- **`criar_metas_hoje` cron-style batch stays in ERP** —
  `metas_service.criar_metas_hoje` reads `metas_config` and writes
  `metas` per RLS-scoped user. Persistence is product-bound. *(Only
  the date-math + proportional-target arithmetic lifts.)*
- **`gerar_trimestre` parent-child cascade stays at N=1 in ERP** —
  the quinzenal → mensal → trimestral nested period auto-generation
  has no equivalent in PF / daily-life today. Re-evaluate when N=2.
- **Status string vocabulary stays as-is in ERP** — `metas` rows
  persist `status` ∈ {`no_prazo`, `atrasada`, `vencida`, `concluida`}.
  We do NOT migrate ERP to seed `GoalStatus` strings in this batch
  (would be a schema-touching project; out of scope).
- **AST-first** — `libcst` for any structural Python edit. Regex/sed
  forbidden.
- **No monkey-patching of our own code in tests** — refactor tests
  to import seed helpers directly when the local helper goes away.
- **PYTHON prefix** — `/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python`
  for pytest in this worktree (parallel-worktree venv shadowing —
  defensive `seed/lib/backend/tests/conftest.py` shadow-purge fix
  already on main from Batch 1B).
- **Branch + commit only** — never push to main; orchestrator merges.
- **No seed extensions in this batch** — if ERP-specific math is found
  that the seed doesn't cover, surface as a follow-up project. Carrying
  product-only logic into the seed is forbidden.

---

## 3. Design principles

1. **Boundary-mapping at the service layer.** Service functions read
   ERP-shaped rows (column names + types intact), transform to seed
   value objects, call seed functions, persist back to ERP-shaped
   rows. The seed never sees ERP column names; ERP never re-implements
   seed math.
2. **Behavior preservation on the wire.** Every existing test contract
   (count, status string, return shape) must pass unchanged.
   Refactoring is the goal, not feature work.
3. **Delete-on-replace.** When a local helper is replaced by a seed
   call, the local helper's body is deleted. Tests that exercised the
   local helper either redirect to the seed module or are deleted as
   redundant (the seed's `tests/domain/metas/` already covers them).
4. **Keep ERP-shape glue minimal.** A 1-line wrapper around a seed
   function only when the call site needs the wrapper for
   readability — otherwise inline `from noctusai_lib.domain.metas
   import ...` at the call site.

---

## 3a. Seed-first analysis (REQUIRED)

This project IS the seed-first execution — by design, the seed is
already in place and the wiring is the consumer cycle.

1. **Is the contract identical for every product?** YES — the math
   (proportional target, period bounds, business-day count) is
   identical across PF, ERP, and daily-life. The seed module is the
   normalized form.
2. **Is the data source product-specific?** YES — ERP's `metas` /
   `meta_periodos` / `metas_config` tables. Schema-mapping at the
   boundary keeps the seed pure.
3. **Is the placement product-specific?** YES — ERP routers + ERP
   services. Seed has no router opinion (correct — pure domain).
4. **Is the visibility / permission rule the same?** YES — uniform
   "compute the math, then let the product persist". RLS / org_id /
   per-user filters are 100% product-side.
5. **Does the seam already exist in seed?** YES — every helper this
   project removes from ERP has a 1:1 match on the seed surface
   (`__init__.py` of `noctusai_lib.domain.metas`).
6. **Default-on or opt-in?** N/A — this is a code-shape refactor, not
   a feature flag.

**Litmus — per-product code count this design requires:**

- [x] **A small section** — the boundary-mapping glue at the service
      layer (read ERP row → call seed → write ERP row). The math itself
      is now zero-product-lines (lives in seed).

**Phase plan implications:** §6 walks through ERP services one by one
because that's the *consumer scope* of this project (one product), not
because the design is wrong. The seed-side work is already done; this
project is structured around ERP's service files.

---

## 4. Scope

**In scope:**

- **Refactor `products/erp-imobiliario/backend/app/services/metas_service.py`**
  to consume `noctusai_lib.domain.metas`:
  - Delete `_period_end_date` → use `period_bounds(PeriodKind.X, ref)[1]`.
  - Delete `_count_weekdays` → use `count_business_days`.
  - Delete `_dias_uteis_totais_mes`, `_dias_uteis_restantes_semana`,
    `_dias_uteis_restantes_mes`, `_dias_uteis_totais_ano`,
    `_dias_uteis_restantes_ano` → use `working_days_*` family.
  - Delete `_calcular_meta_proporcional` → use `proportional_target`.
  - Map ERP's `tipo` strings (`diaria`, `semanal`, `mensal`, `anual`) ↔
    `PeriodKind` enum via a small in-file mapping (no public seam — ERP
    keeps its tipo vocabulary).
- **Refactor `products/erp-imobiliario/backend/app/services/meta_periodos_service.py`**
  to consume the seed `period_bounds`:
  - Replace `quinzena_bounds(ref)` body with seed
    `period_bounds(PeriodKind.FORTNIGHTLY, ref)`.
  - Replace `mes_bounds(ref)` body with seed
    `period_bounds(PeriodKind.MONTHLY, ref)`.
  - Replace `trimestre_bounds(year, quarter)` body with seed
    `period_bounds(PeriodKind.QUARTERLY, date(year, quarter*3-2, 1))`
    (translation: pick a date inside the quarter, ask seed for its
    quarterly bounds).
  - The `gerar_trimestre` cascade + the in-house `_get_or_create_periodo`
    + `_months_in_trimestre` + `_month_name_pt` stay ERP-side (N=1).
- **Update tests** to import from the seed when the local helper is
  removed; preserve every existing assertion.
- **Run ERP backend pytest + full `seed/lib/backend/` tests**, confirm
  green count is preserved or improved (some local-helper tests get
  deleted as redundant; the seed's 111 tests cover the same math).
- **End-of-project bundled proposal** in `projects/erp-metas-seed-wiring/proposals/`
  with absorbed-duplications list, follow-ups surfaced, phase learnings.
- **`findings.md`** at project root maintained throughout.

**Out of scope (deferred — with reason):**

- **`metas_empresa_service.py`, `metas_equipe_service.py`,
  `metas_configuracao_service.py`, `meta_fechamentos_service.py`,
  `meta_rankings_service.py`, `metas_digest_service.py`** — audited;
  none of these duplicate seed math. They're domain-shape services
  (CRUD + cascade-invariant + score formulas + email digest).
  *(Engineer 3's §2.4 audit-pass requirement satisfied below in §5.)*
- **`meta_api_service.py`** — false-positive in the dispatch brief's
  "9 metas-related files" count. This is the **Facebook/Meta company
  API service** for Lead Ads + Campaign sync (`MetaApiConfig`,
  `sync_leads`, `sync_campaigns`). Unrelated to "metas" (goals).
  *(Audit confirms zero metas-domain code.)*
- **ERP `status` vocabulary migration** to seed `GoalStatus` strings
  — would be a schema-touching project; ERP keeps its current strings.
- **`gerar_trimestre` cascade lift** — N=1; reopen when N=2.
- **Frontend (TS) `useMetas` lift** — separate cycle; different layer,
  different recurrence trigger.
- **`metas_digest_service` milestone counts** — currently reads from
  `meta_milestones` table directly (ERP-specific). The seed's
  `accumulate_contribution.crossed_threshold_pct` is wired to a future
  ERP cycle that writes the milestone rows; out of scope here.

---

## 5. Architecture / Data Model

### Files touched

| File | Action |
|---|---|
| `products/erp-imobiliario/backend/app/services/metas_service.py` | refactor — drop 7 local helpers, consume seed |
| `products/erp-imobiliario/backend/app/services/meta_periodos_service.py` | refactor — 3 bound helpers consume seed; cascade unchanged |
| `products/erp-imobiliario/backend/tests/services/test_metas_service.py` | update — redirect helper-import tests to seed (or delete redundant) |
| `products/erp-imobiliario/backend/tests/routers/test_meta_periodos_router.py` | update — `quinzena_bounds`/`mes_bounds`/`trimestre_bounds` tests pass unchanged via service-level alias |
| `projects/erp-metas-seed-wiring/findings.md` | create + maintain |
| `projects/erp-metas-seed-wiring/proposals/<bundle>.md` | file at close |

### 9-service audit table (Engineer 3 §2.4 deliverable)

| Service | Math/state-machine duplication of seed? | Action |
|---|---|---|
| `metas_service.py` | YES — `_period_end_date`, `_count_weekdays`, `_dias_uteis_*` (5 helpers), `_calcular_meta_proporcional` | Refactor (Phase 1) |
| `meta_periodos_service.py` | PARTIAL — `quinzena_bounds`, `mes_bounds`, `trimestre_bounds` overlap with seed `period_bounds`. The `gerar_trimestre` + `_get_or_create_periodo` cascade is ERP-only (N=1). | Refactor bounds (Phase 1); cascade stays |
| `meta_fechamentos_service.py` | NO — period-closing aggregation + per-corretor snapshot writer + score-unified formula. ERP-specific (depends on `meta_eventos`, `meta_fechamentos`, score weights). | Keep as-is |
| `metas_empresa_service.py` | NO — company-meta CRUD + cascade-invariant check (sum(equipe) ≤ empresa). 3-tier VGV cascade is ERP-only (N=1). | Keep as-is |
| `metas_equipe_service.py` | NO — team-meta CRUD + cascade enforcement against `metas_empresa`. Same N=1 ERP-only shape. | Keep as-is |
| `metas_configuracao_service.py` | NO — per-org scoring config CRUD (`vgv_por_ponto`, `peso_pontos`, `peso_vgv`, `metrica_ranking_padrao`). ERP-specific. | Keep as-is |
| `meta_rankings_service.py` | NO — leaderboard aggregation from `meta_eventos` + score computation using `metas_configuracao`. ERP-specific. | Keep as-is |
| `metas_digest_service.py` | NO — biweekly digest builder using shared `noctusai_lib.email.digest` (P3 pattern). ERP-specific milestone reads. | Keep as-is |
| `meta_api_service.py` | NO — **Facebook/Meta (the company) Lead Ads API**. Misnomer — unrelated to metas-domain. | Keep as-is |

**Net:** 2 of 9 service files refactor (`metas_service.py`,
`meta_periodos_service.py`); 7 stay untouched.

### Tipo-string ↔ PeriodKind mapping (ERP-internal)

ERP's `metas_service.py` uses tipo strings `diaria` / `semanal` /
`mensal` / `anual` (the four `TIPOS` it ships). These map to seed
`PeriodKind`:

| ERP tipo | Seed `PeriodKind` |
|---|---|
| `diaria` | `DAILY` |
| `semanal` | `WEEKLY` |
| `mensal` | `MONTHLY` |
| `anual` | `YEARLY` |

The mapping lives in the ERP service file (a small `dict[str,
PeriodKind]`) — no need to expose as a public seam.

For unknown tipo (the existing `_period_end_date("unknown", ref)`
fallback returns `ref`; `_calcular_meta_proporcional("bimestral", …)`
returns `meta_mensal` unchanged), we preserve the legacy fallback
behavior in the boundary mapping — the seed itself raises `ValueError`
for unknown `PeriodKind`, so the fallback lives at the boundary.

ERP's `meta_periodos_service.py` uses a different vocabulary
(`quinzenal` / `mensal` / `trimestral` / `anual`); those map to
`FORTNIGHTLY` / `MONTHLY` / `QUARTERLY` / `YEARLY`. Same pattern.

---

## 6. Implementation phases

### Phase 0 — Audit + project file ✅
- [x] Read seed module (`__init__.py`, `periods.py`, `progress.py`,
      `status.py`, `value_objects.py`).
- [x] Read Engineer 3's bundled proposal.
- [x] Audit all 9 ERP "meta*" service files (table in §5 above).
- [x] Confirm `meta_api_service.py` is a false positive (Facebook).
- [x] Run baseline pytest (53 passing) before any change.
- [x] File this PROJECT.md.

**Improvements:** none identified — pure audit + scaffold. (Block added retroactively 2026-05-04 by `seed-shadow-purge-helper-lift` engineer to satisfy hook self-check; original engineer omitted the block.)

### Phase 1 — Refactor `metas_service.py` + `meta_periodos_service.py` ✅
- [x] Add `from noctusai_lib.domain.metas import (PeriodKind,
      period_bounds, count_business_days,
      working_days_total_in_month,
      working_days_remaining_in_week,
      working_days_remaining_in_month,
      working_days_total_in_year,
      working_days_remaining_in_year, proportional_target)` to
      `metas_service.py`.
- [x] Add ERP `tipo` ↔ `PeriodKind` mapping (`_TIPO_TO_PERIOD_KIND`).
- [x] Replace `_period_end_date` body with `period_bounds(...)[1]` +
      legacy-tipo fallback.
- [x] Replace `_count_weekdays`, `_dias_uteis_totais_mes`,
      `_dias_uteis_restantes_semana`, `_dias_uteis_restantes_mes`,
      `_dias_uteis_totais_ano`, `_dias_uteis_restantes_ano` bodies
      with 1-line seed delegations (names preserved for test/caller
      compat per §7 Open Question 1 resolution).
- [x] Replace `_calcular_meta_proporcional` body with
      `proportional_target(...)` + legacy-tipo fallback (returns
      `meta_mensal` for unknown tipos).
- [x] Drop unused `import math` and `import timedelta` from
      `metas_service.py`.
- [x] Refactor `meta_periodos_service.py` `quinzena_bounds` /
      `mes_bounds` / `trimestre_bounds` to delegate to seed
      `period_bounds`. Drop unused `import calendar` + `timedelta`.
- [x] Apply defensive shadow-purge to
      `products/erp-imobiliario/backend/tests/conftest.py` (mirrors the
      seed/lib/backend conftest fix; ERP-side product tests were
      not previously protected — surfaced cross-product follow-up
      to mirror in PF + daily-life conftests).
- [x] Tests preserved as-is — every existing assertion passes
      because the public function names + signatures + return shapes
      are unchanged. No test refactor needed (Open Question 1
      resolution: keep ERP-side names as thin shims).
- [x] Run focused tests: 53 passed (`tests/services/test_metas_service.py`
      + `tests/routers/test_meta_periodos_router.py`).
- [x] Run full ERP backend pytest: **1819 passed** (excludes
      `tests/realdb/` — those need a live Supabase). No regression.
- [x] Run full `seed/lib/backend/` pytest: **660 passed**. No regression.
- [x] AST-first: refactor used `libcst` transformers (`/tmp/refactor_metas_service.py`
      + `/tmp/refactor_meta_periodos_service.py`); Edit only used for
      whitespace formatting after libcst output (PEP 8 blank lines).

**Improvements:**
- The shadow-purge belongs in `noctusai_lib.testing` as a public
  helper — every product conftest can call
  `from noctusai_lib.testing import purge_shadowing_finders;
  purge_shadowing_finders()` instead of duplicating the logic.
  Cross-product follow-up: file `seed-shadow-purge-helper-lift`
  project to absorb this into `noctusai_lib.testing`.
- The `quinzena_bounds`/`mes_bounds`/`trimestre_bounds` shims could
  become `__all__`-exported aliases pointing at seed names if/when
  ERP-side callers migrate to `period_bounds(PeriodKind.X, ref)`
  directly. Low-priority: 5 internal callers + one test file.
- `metas_service.py` module docstring still says "All date math is
  computed in Python to avoid N+1 RPC round-trips" — the ERP-keeper
  shape is preserved (`criar_metas_hoje` still uses 2-3 DB queries +
  pure-Python loop), but the math itself now lives in seed. Cosmetic;
  next pass could clarify.
- Sister engineers (PF + daily-life) likely need the same product
  conftest shadow-purge fix this session for their `noctusai_lib.domain.metas`
  imports to resolve. The architect should mirror the fix when merging
  their branches.

### Phase 2 — Close + bundled proposal ✅
- [x] Synthesize the in-step `**Improvements:**` notes into ONE
      bundled proposal in `projects/erp-metas-seed-wiring/proposals/`.
- [x] Maintain `findings.md` (5 categories: errors / mistakes-slips /
      lessons / interesting-findings / knowledge-pieces) — see
      project-folder for the durable artifact OR the engineer's
      response (the Write-tool restriction on findings.md surfaced
      mid-execution; content captured in the engineer's report).
- [x] Flip Phase 1 + Phase 2 headers to ✅ in this PROJECT.md.
- [x] Phase commit on branch.
- [x] Report back to architect.

---

## 7. Open questions

1. **Should the `_count_weekdays` and `_dias_uteis_*` helpers stay as
   1-line aliases for backward-compat with their direct test imports?**
   *Recommendation:* delete the helpers; redirect the helper-direct
   tests to the seed (those tests duplicate seed coverage anyway).
   The seed's `count_business_days` + `working_days_*` family is the
   canonical home. Deciding on the way down — log in §11.

2. **Does the legacy `_period_end_date("unknown", ref) → ref` fallback
   matter?** *Recommendation:* preserve it — one test case
   (`test_unknown_tipo_returns_same_day`) and one
   (`test_unknown_tipo_returns_meta_mensal`) cover it. Cheap to keep at
   the boundary; future cleanup project might tighten it.

---

## 8. Dependencies & blockers

- **Seed module shipped + green** — confirmed (`commit 09fa759`,
  111-test suite passing on main).
- **Branch tracking origin/main** — confirmed at session start.
- **Sister engineers (PF + daily-life)** working in their own worktrees;
  no shared files in this project's scope (PF + daily-life don't touch
  ERP code paths). No collision risk in this batch.

---

## 9. Success criteria

- ERP backend pytest passes with the same 53+ count (or higher if new
  boundary-mapping tests added; never lower for the same scope).
- `seed/lib/backend/` pytest still 111+ green; no regression.
- Zero remaining occurrences of `_calcular_meta_proporcional`,
  `_period_end_date`, `_count_weekdays`, `_dias_uteis_*` *bodies* in
  `metas_service.py` (greppable as a closure check).
- `meta_periodos_service.py` `quinzena_bounds` / `mes_bounds` /
  `trimestre_bounds` bodies delegate to seed (greppable).
- One bundled proposal filed; `findings.md` synthesized.

---

## 10. How to use this plan

- This project is dispatched as a parallel engineer brief — execution
  collapses Phase 1 + Phase 2 into one effective working pass per
  Engineer 3 §2.5 (single coupled change, not two phases).
- Branch + commit per phase; orchestrator merges to main.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-04 | Initial PROJECT.md drafted from `templates/PROJECT-TEMPLATE.md` after audit of all 9 ERP meta* service files. | Engineer B (claude-opus-4-7) |
| 2026-05-04 | Phase 1 + Phase 2 collapse shipped: refactored `metas_service.py` (7 helper bodies → seed delegations) + `meta_periodos_service.py` (3 bound helpers → seed delegations); dropped unused `math` / `timedelta` / `calendar` imports; added defensive shadow-purge to ERP `tests/conftest.py`. AST-first via libcst. Tests: 53 focused passed → 1819 full ERP (excl. realdb) passed → 660 seed/lib passed. Bundled proposal filed. | Engineer B (claude-opus-4-7) |
