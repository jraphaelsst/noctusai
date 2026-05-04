# pf-metas-seed-wiring — Project Document

> **Living document.** Phase plan and audit conclusions evolve as work progresses; the §11 Change Log is the canonical history.

- **Created:** 2026-05-04
- **Last updated:** 2026-05-04
- **Status:** Phase 0 ready
- **Owner / stakeholders:** rapha (architect) · engineer-A (this agent — Batch 1C of `in-flight-execution-rollout`)
- **Related docs:**
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/metas-seed.md` — wiring recipe + status mapping table.
  - `projects/metas-domain-seed-absorption/PROJECT.md` — predecessor (seed lift project).
  - `projects/metas-domain-seed-absorption/proposals/claude-opus-4-7-20260503-end-of-project-bundle.md` — bundled proposal §2.1 + §2.6 named this project.
  - `projects/in-flight-execution-rollout/` — master orchestration this batch belongs to.
- **Project slug:** `pf-metas-seed-wiring` (root `projects/` location — sister to `erp-metas-seed-wiring` + `daily-life-goals-seed-wiring`; the three are Batch 1C of the in-flight-execution-rollout master tree).

---

## 1. Context & Purpose

The `noctusai_lib.domain.metas` seed module shipped on 2026-05-03 (commit `09fa759`) by absorbing the cross-cutting math + state machine + value objects + period date-math from PF, ERP, and Daily Life per N=3 MUST-FORMALIZE. The seed module is in place but no product consumes it yet — by design.

This project wires Personal Finance's two metas-touching services to consume the seed:

- `products/personal-finance/backend/app/services/metas_service.py` — financial goal tracking + contributions + progress projection (the original donor of `obter_progresso` math).
- `products/personal-finance/backend/app/services/orcamentos_service.py` — per-category monthly budgets (planned vs spent percentage math). Note: orcamentos is `orçamentos / budgets`, NOT `metas` — but the percent-complete shape is the same and the absorption proposal grouped it.

The win: PF stops carrying the lifted math locally; future bug-fix-once-ships-everywhere; PF drops `dateutil.relativedelta` from `metas_service.py` (still used by `recorrentes_service.py` — out of scope, different concern).

---

## 2. Confirmed constraints

The architect's brief (Batch 1C engineer-A dispatch) sets the constraints:

- **Worktree scope** — operate ONLY in `noctusai-worktrees/pf-metas-seed-wiring/`. ERP + daily-life are sister engineers' territory; touching them = collision. *(Drives "no ERP / no daily-life code edits".)*
- **AST-first for code edits** — libcst for Python; no sed/regex on source. *(Standing universal rule; reinforced.)*
- **PF schema + persistence stay product-side** — math + period bounds + status state machine flow through seed; column names (`valor_alvo` / `valor_atual` / `meta_contribuicoes`), Supabase queries, RLS, status string `"ativa"` / `"concluida"` stay in PF. *(Per `KB § PATTERNS/metas-seed.md § 3 What stays consumer-side`.)*
- **No incomplete commits** — backend tests must stay green at every phase commit. *(Universal.)*
- **Branch-push only; never push to main** — orchestrator merges. *(Per branching methodology.)*
- **Drop `dateutil.relativedelta` from `metas_service.py`** — seed has stdlib-only `_add_months`. Proposal §2.6 explicitly bundled this. *(Recurrent: same `dateutil` is used by `recorrentes_service.py` for a different concern (transaction recurrence) — out of scope; do NOT touch.)*
- **`crossed_threshold_pct` is the seed's optional milestone field** — no consumer in PF today. *(Per absorption proposal §2.3 — accept-with-rationale; future gamification consumer can opt in. Don't wire prematurely.)*

---

## 3. Design principles

1. **Boundary mapping is consumer-side.** PF's service methods accept/return PF-shaped dicts (PT-BR keys, status strings); inside the method body the boundary maps to seed value objects, calls seed functions, and maps results back. No PF caller sees `Goal` / `Target` / `Progress`.
2. **Status vocabulary stays PT-BR.** PF persists `"ativa"` / `"concluida"` / `"pausada"` strings. We call `accumulate_contribution(...)` for the math but keep the literal `"concluida"` string write — `to_pt_string(GoalStatus.COMPLETED)` is equivalent but PF's column constraint (regex `^(ativa|concluida|pausada|cancelada)$`) makes the literal more honest about the persisted vocabulary.
3. **Test surface preserved.** Existing per-method tests (`test_metas_service.py` + `test_orcamentos_service.py`) must continue to pass without changes to their assertions — boundary behavior is identical, math is identical.
4. **No `Period` / `period_bounds` consumption in PF.** PF's metas have no period-bounded recurrence (financial goals are open-ended toward a `data_alvo`); orcamentos use `periodo_mes` strings (e.g. `"2026-02"`) directly with no need for `period_bounds()`. We consume only `compute_progress` / `accumulate_contribution` / `project_completion_date`. *(Drives a smaller diff than ERP's wiring will need.)*
5. **`obter_progresso` returns PF's dict shape verbatim** — `{"meta", "percentual", "faltam", "data_previsao", "contribuicoes"}` — only the math behind it changes.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

This is a **single-product** project (PF only) by design. The cross-product concern (the math + state machine + period date-math) is already lifted to seed in the predecessor project. This wiring project is the consumer-side fan-out — explicitly in `KB § PATTERNS/metas-seed.md § 8 Out-of-scope` as the named follow-up.

Six-question checklist:

1. **Is the contract identical for every product?** YES for the math (`compute_progress`, `accumulate_contribution`, `project_completion_date`). Already lifted. PF wiring is the consumer.
2. **Is the data source product-specific?** YES — PF's `metas` + `meta_contribuicoes` + `orcamento_itens` Supabase tables. Persistence stays PF-side.
3. **Is the placement product-specific?** YES — PF's service classes (`MetasService`, `OrcamentosService`) own the boundary mapping.
4. **Is the visibility / permission rule the same?** N/A (service-layer; PF's existing RLS via `org_id` filter stays).
5. **Does the seam already exist in seed?** YES — `noctusai_lib.domain.metas` exports `compute_progress`, `accumulate_contribution`, `project_completion_date`, `Target`, `Contribution`, `to_pt_string`, `GoalStatus`. `__init__.py` lines 36-70 confirm the public surface ships.
6. **Default-on or opt-in?** OPT-IN per consumer — each product writes its own boundary mapping at the service layer.

**Litmus — per-product code count this design requires:**

- [ ] **0 lines** — N/A (boundary mapping is per-product by design; the cross-product part is already at zero in seed).
- [ ] **1 line** — N/A.
- [x] **A small section** — the boundary mapping inside each PF service method. Acceptable: data source is PF-specific (PF schema columns, Supabase client, PT-BR status string).
- [ ] **Multiple files / pages / mounts per product** — NO; only `metas_service.py` + `orcamentos_service.py` change in PF.

**Phase plan implications:** §6 phases work in **PF service layer** (not "walk through products"). The replication-to-seed symmetry rule does not fire — the cross-product math is already at zero per-product LOC; this is the consumer-side wiring of an already-zero seed.

---

## 4. Scope

**In scope:**

- Refactor `app/services/metas_service.py`:
  - `listar` percent calculation → `compute_progress(...).percent_complete` (or inline since it has no contributions context). **Resolution:** keep the inline `min(... / ... * 100, 100)` as it's a list-iteration display calc with no contributions data; replace with seed `compute_progress` if cleaner. *(Decided during Phase 1.)*
  - `adicionar_contribuicao` → seed `accumulate_contribution(target, current, increment)`; map `transition.completed → "concluida"` write.
  - `obter_progresso` → seed `compute_progress(...)` + `project_completion_date(...)`. Drop the local `dateutil.relativedelta` import.
- Refactor `app/services/orcamentos_service.py`:
  - `obter_progresso` percent_usado calculation → consider seed `compute_progress(target=Target(total_planejado), current=total_gasto)`; the seed semantic is "current vs target" so it cleanly maps. (Note: budget *spending* vs goal *accumulation* are inverse framings but the math is identical.)
- Refactor `app/services/dashboard_service.py § resumo()` lines 62-65: same `valor_alvo` / `valor_atual` percentual math as `metas_service.listar`. Use seed.
- Drop `dateutil.relativedelta` from `metas_service.py` (only — `recorrentes_service.py` keeps its dateutil dep).
- Run + green: PF backend pytest + full seed-lib pytest.

**Out of scope (for now — with reason):**

- ERP wiring (sister engineer's territory in Batch 1C — `erp-metas-seed-wiring`).
- Daily-life wiring (sister engineer's territory in Batch 1C — `daily-life-goals-seed-wiring`).
- Removing `python-dateutil` from PF's requirements — `recorrentes_service.py` still uses it for transaction recurrence (different concern). *(Could be cleaned up if/when recurrence math also lifts to seed; out of scope for this project.)*
- Frontend changes (`useMetas` / `useGoals` hook lift) — explicitly deferred per `KB § PATTERNS/metas-seed.md § 8`.
- `crossed_threshold_pct` consumer wiring (no PF use case yet — gamification deferred).
- Migrations — no schema changes; seed maps to/from existing PF schema verbatim.

---

## 5. Architecture / Data Model

**No data-model changes.** PF tables (`metas`, `meta_contribuicoes`, `orcamentos`, `orcamento_itens`) keep their existing shape. The boundary mapping happens inside the service method body.

**Mapping table (PF column ↔ seed value object):**

| PF column / variable                     | Seed counterpart                                  |
|------------------------------------------|---------------------------------------------------|
| `metas.valor_alvo`                       | `Target.amount` / `target` arg                    |
| `metas.valor_atual`                      | `current` arg                                     |
| `metas.status` (`"ativa"`)               | `GoalStatus.IN_PROGRESS` ↔ `from_pt_string(...)` |
| `metas.status` (`"concluida"`)           | `GoalStatus.COMPLETED`                            |
| `meta_contribuicoes.valor` + `.data`     | `Contribution(amount, at)` value object           |
| `data_previsao` (in `obter_progresso`)   | `project_completion_date(...)` return            |
| `percentual`                             | `compute_progress(...).percent_complete`         |
| `faltam`                                 | `compute_progress(...).remaining`                |
| `orcamento_itens.valor_planejado` (sum)  | `Target.amount` — viewed as "spending budget"    |
| `orcamento_itens.valor_gasto` (sum)      | `current` — current spending                     |
| `percentual_usado`                       | `compute_progress(...).percent_complete`         |

**Files touched:**

- `products/personal-finance/backend/app/services/metas_service.py` — refactor.
- `products/personal-finance/backend/app/services/orcamentos_service.py` — refactor.
- `products/personal-finance/backend/app/services/dashboard_service.py` — refactor `resumo()`'s metas percentual loop.
- `projects/pf-metas-seed-wiring/findings.md` — durable findings file (5 categories).
- `projects/pf-metas-seed-wiring/proposals/<bundled-proposal>.md` — phase-close bundled proposal.

---

## 6. Implementation phases

### Phase 0 — Audit + 1:1 mapping ✅ (this commit)

- [x] Read seed module surface (`noctusai_lib.domain.metas` `__init__.py` + 5 implementation files) — confirmed `compute_progress` + `accumulate_contribution` + `project_completion_date` ship and are runtime-ready (not just Protocol/Fake).
- [x] Read PF `metas_service.py` + `orcamentos_service.py` + `dashboard_service.py` — every duplication mapped (table in §5).
- [x] Read PF tests `test_metas_service.py` + `test_orcamentos_service.py` — confirmed test assertions are compatible with the seed math (same numbers come out).
- [x] File this PROJECT.md + skeleton findings.md.

**Improvements:**
- The seed's `compute_progress` returns a `Progress` value object — PF's existing `obter_progresso` returns a dict. Mapping the value object back to dict at the boundary is a 4-line operation; clean.
- `compute_progress` accepts `today: date | None = None`, only computes ETA when supplied. PF's current code `from datetime import date; date.today()` is the natural call-site; keep `date.today()` at the boundary (testable via dependency injection if ever needed; not needed now).
- `obter_progresso` for orcamentos has different semantics than for metas (spending vs accumulation) but the **math** (current/target × 100) is identical; reusing `compute_progress` is honest because the math IS the same — the framing (`percentual` vs `percentual_usado`) stays in the response dict naming.
- Dashboard `resumo()` duplicates `metas_service.listar`'s percent loop verbatim — single helper call would close N=2 within PF. Inline `compute_progress` call works.

### Phase 1 — Refactor MetasService + DashboardService + drop dateutil

- [ ] AST-edit `metas_service.py`:
  - Add `from noctusai_lib.domain.metas import (...)` import.
  - Refactor `listar(...)` percent loop → seed `compute_progress` (no contributions context; just `target` + `current`).
  - Refactor `adicionar_contribuicao(...)` → use `accumulate_contribution(target, current, valor)`.
  - Refactor `obter_progresso(...)` → use `compute_progress(...)` + `project_completion_date(...)`. Replace `dateutil.relativedelta` with the seed's `project_completion_date` (which uses stdlib `_add_months` internally).
  - Remove the now-unused `from datetime import date, datetime` if any imports become orphaned.
- [ ] AST-edit `dashboard_service.py § resumo()`:
  - Use seed `compute_progress(...)` for the metas percentual loop (same shape as `MetasService.listar`).
- [ ] Run PF backend pytest — confirm green.
- [ ] Verify `dateutil` no longer imported in `metas_service.py` (`grep "dateutil" products/personal-finance/backend/app/services/metas_service.py` → 0 hits).

### Phase 2 — Refactor OrcamentosService

- [ ] AST-edit `orcamentos_service.py`:
  - Add `from noctusai_lib.domain.metas import compute_progress, Target` import.
  - Refactor `obter_progresso(...)` `percentual_usado` calculation → seed `compute_progress`.
- [ ] Run PF backend pytest — confirm green.
- [ ] Run full seed-lib pytest — confirm no regression (sanity, since we don't touch seed code).

### Phase 3 — Close + bundled proposal

- [ ] Verify all checkboxes ticked + phase headers ✅.
- [ ] File `projects/pf-metas-seed-wiring/proposals/claude-opus-4-7-20260504-end-of-project-bundle.md`:
  - Duplications absorbed (before/after counts).
  - Anything noticed as a follow-up.
  - Phase learnings.
- [ ] Synthesize `findings.md` (5 categories).
- [ ] Phase commit; push branch.

---

## 7. Open questions

1. **Should `metas_service.listar` use seed `compute_progress` or stay inline?** — Decided in Phase 0: use seed for consistency / single source of truth. The seed call is one line, no perf cost in a list iteration.
2. **Does `compute_progress` work for budget-spending math?** — Yes. The math is identical (current ÷ target × 100). The seed has no opinion on whether it's accumulation vs spending; consumer decides what `current` and `target` mean. *(Confirmed via reading seed `progress.py` lines 27-32 + 96.)*

---

## 8. Dependencies & blockers

- **Seed `noctusai_lib.domain.metas` shipped + green** — confirmed (commit `09fa759`; 111 tests passing).
- **PF backend test baseline green** — established in Phase 1 before edits.
- **No collision with sister engineers** — they edit ERP / daily-life only; this project edits PF only. No file overlap.

---

## 9. Success criteria

- PF backend pytest green (`pytest products/personal-finance/backend/tests/`).
- Full seed-lib pytest green (`pytest seed/lib/backend/tests/`).
- `metas_service.py` has zero `dateutil` imports.
- All `valor_atual / valor_alvo * 100` shapes in PF replaced with `compute_progress(...)` calls.
- Bundled proposal filed at `projects/pf-metas-seed-wiring/proposals/`.
- `findings.md` synthesized (5 categories).
- Branch `pf-metas-seed-wiring` pushed to origin (architect FF-merges to main).

---

## 10. How to use this plan

Standard living-document protocol per `KB § PATTERNS/project-execution.md`. Engineer-A executes top-to-bottom; phase commits on the branch; orchestrator (architect) handles cross-product merge.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-04 | Phase 0 filed: PROJECT.md + audit + 1:1 mapping table; seed surface verified (runtime-ready, not just Protocol/Fake) | claude-opus-4-7 (engineer-A, Batch 1C of in-flight-execution-rollout) |
