# metas-domain-seed-absorption — Project Document

> Living document. Phase status icons per `templates/PROJECT-TEMPLATE.md`. Proposals filed live in `./proposals/`.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** Phase 0 ✅ · Phase 1 ✅ · Phase 2 ✅ → Phase 3 in progress
- **Owner / stakeholders:** joaoraphaelsst · architect (parent orchestrator)
- **Related docs:**
  - `KB § PATTERNS/seed-lib-layout.md` (target layer = `domain/`)
  - `KB § PATTERNS/scheduling-seed.md` (canonical reference for the seed-domain shape)
  - `KB § PATTERNS/project-execution.md § 2.7 Recurrence rule` (the trigger)
  - `KB § GUIDES/seed-first-design.md`
  - `products/personal-finance/projects/personal-finance-wiring/proposals/phase-1-seed-absorption-followups.md` (predecessor; § 7 named this slug as a follow-up dispatch)
- **Project slug:** `metas-domain-seed-absorption` (cross-product / platform — lives at `projects/<slug>/` per `KB § PATTERNS/project-execution.md § 1`).

---

## 1. Context & Purpose

The metas/goals/targets/budget domain — *value-and-target tracking* — recurs across **at least three products** with structurally identical primitives:

- **Personal Finance** — `services/metas_service.py` (financial goals + contributions accumulating into `valor_atual` toward `valor_alvo`) and `services/orcamentos_service.py` (per-category budgets — `valor_planejado` / `valor_gasto` per `periodo_mes`).
- **ERP Imobiliário** — `services/metas_service.py` (sales targets — `meta_pretendida` / `meta_realizada` over period `tipo` ∈ {diaria, semanal, mensal, anual}, with proportional cascade), plus `meta_periodos_service.py` (parent-child period tree — quinzenal → mensal → trimestral → anual), `metas_empresa_service.py`, `metas_equipe_service.py`, etc.
- **Daily Life** — `services/goals_service.py` (habit check-ins accumulating into `valor_atual`).

Per the **DRY recurrence rule** (`KB § PATTERNS/project-execution.md § 2.7`): N=3 → MUST formalize. The replication-to-seed slip detector (`feedback_replication_to_seed_slip.md`) also fires on the predecessor's "across PF + ERP + daily-life" framing. The right per-product code count for the cross-cutting bits is **zero**.

The win: a shared, pure-domain `noctusai_lib.domain.metas` module lifting the cross-cutting math + value-objects (Goal, Target, Progress, Period, Contribution, Status), so each product's service file becomes a thin persistence-layer wrapper that calls into the seed for arithmetic and state transitions. **Consumers wiring is OUT OF SCOPE this dispatch** — that's a follow-up cycle.

---

## 2. Confirmed constraints

Captured from the dispatch brief (architect → engineer, 2026-05-03). No live user interrogation in this dispatch — engineer scope is fixed.

- **Scope** — file PROJECT.md + implement seed module + tests. **Do NOT touch any product code** (`products/*/backend/app/services/metas*.py` is read-only this dispatch). *(Concerns the absorption itself; product-wiring is a follow-up cycle.)*
- **Layer** — `seed/lib/backend/noctusai_lib/domain/metas/` per `KB § PATTERNS/seed-lib-layout.md`. *(Pure domain — no DB, no FastAPI, no SDK calls. Persistence stays product-side via Protocol seam.)*
- **Worktree isolation** — `noctusai-worktrees/metas-domain-seed-absorption/`, branch `metas-domain-seed-absorption`. Parallel sibling engineers operate on `noctusai_lib/api/auth.py` and `noctusai_lib/domain/ai/` — zero file overlap. *(Branching-first orchestration.)*
- **Pre-commit hook venv** — `PYTHON=/Users/rapha/.../venv/bin/python` if module-not-found.
- **No push to main** — branch-to-branch only, project commit gates only.
- **Tests stay green** in seed-lib scope (`seed/lib/backend/`).
- **No `--no-verify`** on commits.

---

## 3. Design principles

1. **Pure domain — no IO.** The seed module never touches the DB, FastAPI, or any SDK. All persistence is product-side; the seed exposes a `Protocol` seam for the product to plug its own repository in. Matches `noctusai_lib.domain.scheduling` — value objects + Protocols + defaults + engine; product wires its own DB-backed implementations.
2. **Vocabulary-neutral.** No "meta_pretendida" / "valor_alvo" / "categoria" — those are PF/ERP/Portuguese product surface. Seed uses platform-neutral names: `Goal`, `Target`, `Progress`, `Period`, `Contribution`, `GoalStatus`. Product services map their schema names ↔ seed value objects at the boundary.
3. **Period-shape pluralism.** Products use different period vocabularies (PF: open-ended dates; ERP: diaria / semanal / quinzenal / mensal / trimestral / anual; daily-life: per-day check-ins). The seed exposes a `Period` value object + a `PeriodKind` enum covering all three, plus pure date-math helpers (`period_bounds`, `count_business_days`, `proportional_target`) that ERP-style products consume verbatim and PF/daily-life ignore.
4. **Progress is computed, never stored.** `Progress` is a derived value object — given `target` + `current` + optional contribution history, the seed returns `Progress(percent_complete, remaining, projected_completion_date | None, status)`. Product services persist `valor_atual` / `meta_realizada` for query speed; the seed never assumes either is canonical. Product service calls `compute_progress(...)` to refresh.
5. **Contribution-accumulator is shared.** PF (financial deposits) + Daily Life (habit check-ins) both accumulate floating values into `valor_atual` and flip status to "concluida" on threshold cross. Lift this to `accumulate_contribution(target, current, increment) -> ProgressTransition` which returns the new value + whether the goal completed in this transition.
6. **Status is a state machine, not a string.** `GoalStatus` enum: `pending | in_progress | on_track | at_risk | overdue | completed | abandoned`. Pure transitions encoded as a function — `next_status(progress, period_remaining_pct, current_status) -> GoalStatus`. Products map their status strings (PF "ativa"/"concluida"; ERP "no_prazo"/"atrasada") to/from the seed enum at the boundary.
7. **Persistence-Protocol — Protocol-over-Callable.** When a downstream consumer (a product, or a seed-level integration test) needs to inject a repository, expose a `GoalRepository` Protocol with typed methods (`fetch_goal`, `list_goals`, `record_contribution`, `update_goal`). Per `KB § PATTERNS/seed-lib-layout.md § Consumer-injection seams — Protocol over Callable`. Default implementation provided as `InMemoryGoalRepository` (testing convenience), no real adapter shipped in this project (products keep their own).

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** **YES** for the *math + state-machine + value-object shape*. NO for *schema names + persistence target + status vocabulary* — products map their schema at the boundary. Seed surface is contract-identical; product surface is mapping code.
2. **Is the data source product-specific?** **YES** — each product owns its `metas` / `orcamentos` / `goals` / `checkins` table. Seed accepts pre-fetched value objects + returns derived value objects. Per § 3.7, an optional `GoalRepository` Protocol seam lets a consumer wire the seed deeper, but products are not required to.
3. **Is the placement product-specific?** **NO** — the seed module is pure-Python and product-agnostic. Each product's `services/metas*.py` becomes a thin shell that calls seed primitives.
4. **Is the visibility / permission rule the same?** **NO** — RLS / org-scoping / user-scoping is product-specific. Seed has no opinion on access control; products keep their existing `org_id` / `user_id` filters at the persistence layer.
5. **Does the seam already exist in seed?** **NO** — `noctusai_lib.domain.scheduling` is the canonical reference shape (engine + Protocols + value objects + defaults), but no `metas` / `goals` namespace exists today. Verified by reading `seed/lib/backend/noctusai_lib/domain/__init__.py` (none of the listed sub-packages match).
6. **Default-on or opt-in?** **OPT-IN** — products that already ship goal-tracking adopt the seed via service-layer refactor (a future cycle). The seed module is just sitting there; no factory mounts it; no auto-registration.

**Litmus — per-product code count this design requires:**

- [x] **A small section** — each product keeps its persistence + RLS + schema-naming, but the math + state-machine + period helpers move to seed. Per-product LOC for the cross-cutting bits = 0; per-product LOC for the mapping shell = small (~30-50 lines per service).

**Phase plan implications:** §6 phases work IN SEED (correct). No phase walks through products one by one. The cross-product wiring (the "use the seed module" part) is a follow-up cycle, OUT OF SCOPE this dispatch — same shape as `make-get-current-user-org-factory` (file the seed gift; product migrations follow).

---

## 4. Scope

**In scope (this dispatch):**
- File this PROJECT.md + Phase 0 audit findings.
- Design the `noctusai_lib.domain.metas` module shape (value objects, enums, pure functions, Protocol seam).
- Implement the module under `seed/lib/backend/noctusai_lib/domain/metas/`.
- Tests under `seed/lib/backend/tests/domain/metas/`.
- KB cross-reference: pointer in `KB § INDEX.md` + new `KB § PATTERNS/metas-seed.md` summary doc (lives in seed-domain catalog row of `KB § 04-SHARED-LIBRARY.md`). *(Three-way sync rule fires; minimal because no CLAUDE.md §1 rule changes — only a KB depth doc + INDEX entry.)*

**Out of scope (deferred to follow-up cycles):**
- **Wiring PF / ERP / daily-life to consume the seed module.** Three follow-up projects (one per product) will refactor each product's `services/metas*.py` to call the seed. *Reason:* this is a structural lift; cross-product code touches are out of dispatch scope per the brief.
- **`meta_periodos_service.py` parent-child period tree (ERP-only today).** ERP's `quinzenal → mensal → trimestral → anual` cascade is interesting but only N=1 today (PF + daily-life don't have it). Seed ships `period_bounds(kind, ref) → (start, end)` for the simple cases; the *cascade* (parent-child auto-generation) stays in ERP until N=2+.
- **Frontend metas types / hooks.** A separate seed-frontend cycle absorbs `useMetas` / `useGoals` patterns. The dispatch named "metas-domain" deliberately scopes to backend domain logic.
- **Migrations.** No schema changes in this project. Each product's existing tables keep their existing shape; the seed maps to/from them at the service boundary.

---

## 5. Architecture / Data Model

### 5.1 Phase 0 audit — what recurs vs what's product-specific

Read 2026-05-03 from worktree:

#### Cross-cutting (lifts to seed)

| Concept | PF (`metas_service.py`) | PF (`orcamentos_service.py`) | ERP (`metas_service.py`) | Daily Life (`goals_service.py`) | Lift to seed as |
|---|---|---|---|---|---|
| Target value | `valor_alvo` | `valor_planejado` (per item) | `meta_pretendida` | `valor_alvo` (via meta) | `Target.amount: float` |
| Current value | `valor_atual` | `valor_gasto` (per item) | `meta_realizada` | `valor_atual` | `Progress.current: float` |
| Percent complete | `min(atual/alvo*100, 100)` | `gasto/planejado*100` | (computed at query) | (not stored) | `Progress.percent_complete -> float` |
| Remaining | `max(alvo-atual, 0)` | `planejado-gasto` (saldo) | (computed at query) | (not stored) | `Progress.remaining -> float` |
| Completion threshold | `atual >= alvo → "concluida"` | n/a (budgets don't "complete") | n/a | `total_valor` accumulator | `accumulate_contribution(...)` |
| Contribution accumulation | `meta.valor_atual += contrib.valor` | n/a (sync from txns) | n/a | `valor_atual = sum(checkins.valor)` | `accumulate_contribution(target, current, inc)` returns `(new_current, completed: bool)` |
| Projected completion | `data + relativedelta(months=meses_restantes)` from monthly avg | n/a | n/a | n/a | `project_completion_date(history, target, current, today) -> date \| None` |
| Period business-days math | n/a | per-month bounds | `_count_weekdays`, `_dias_uteis_*`, `_calcular_meta_proporcional` | n/a | `period_bounds(kind, ref)`, `count_business_days(start, end)`, `proportional_target(monthly, kind, ref)` |
| Period kinds | (open-ended dates) | per-month | diaria/semanal/mensal/anual | per-day | `PeriodKind` enum: `DAILY / WEEKLY / FORTNIGHTLY / MONTHLY / QUARTERLY / YEARLY / OPEN_ENDED` |
| Status string | "ativa" / "concluida" | n/a | "no_prazo" / "atrasada" | implicit | `GoalStatus` enum + `next_status()` |

#### Product-specific (stays in product)

- **Schema names** — `metas` vs `orcamentos` vs `checkins`; `valor_atual` vs `meta_realizada` vs `valor_gasto`; `usuario_id` vs `user_id` vs `org_id`.
- **Persistence** — Supabase queries with RLS / `org_id` / `user_id` filters.
- **Auth** — each service receives a scoped `db` client; seed has no opinion.
- **Domain-specific batch creators** — `criar_metas_hoje()` (ERP-specific: cron-like daily target seeding from active configs) stays in ERP; the *`_calcular_meta_proporcional`* it calls lifts to seed.
- **Cross-table sync** — `OrcamentosService.sincronizar_gastos()` (PF-specific: pulls actuals from `transacoes` table) stays in PF; the *percent / saldo math* lifts.
- **Period parent-child cascade** — `meta_periodos_service.gerar_trimestre()` (ERP-only at N=1) stays in ERP.
- **Status vocabulary** — `"ativa"`/`"no_prazo"`/etc. mapped product-side to/from `GoalStatus`.

### 5.2 Module shape (seed/lib/backend/noctusai_lib/domain/metas/)

```
noctusai_lib/domain/metas/
├── __init__.py              # Public surface; re-exports
├── value_objects.py         # Goal, Target, Progress, Period, Contribution, GoalStatus, PeriodKind
├── progress.py              # compute_progress, accumulate_contribution, project_completion_date
├── periods.py               # period_bounds, count_business_days, proportional_target,
│                            # business_days_remaining_in_*, working_days_total_in_*
├── status.py                # GoalStatus state machine, next_status(...)
└── repository.py            # GoalRepository Protocol + InMemoryGoalRepository
```

Tests:
```
seed/lib/backend/tests/domain/metas/
├── __init__.py
├── test_value_objects.py
├── test_progress.py
├── test_periods.py
├── test_status.py
└── test_repository.py
```

### 5.3 Public API (sketch)

```python
from noctusai_lib.domain.metas import (
    Goal, Target, Progress, Period, Contribution,
    GoalStatus, PeriodKind,
    compute_progress, accumulate_contribution, project_completion_date,
    period_bounds, count_business_days, proportional_target,
    next_status,
    GoalRepository, InMemoryGoalRepository,
)

# PF financial goal:
prog = compute_progress(target=Target(50_000), current=12_500, contributions=[...], today=date.today())
# → Progress(percent_complete=25.0, remaining=37_500, projected_completion_date=date(2027, 3, 1), status=GoalStatus.IN_PROGRESS)

# ERP daily target from monthly:
target_today = proportional_target(monthly_target=300, kind=PeriodKind.DAILY, ref=date.today())

# Habit accumulation:
new_current, completed = accumulate_contribution(target=30, current=12, increment=1)
# → (13, False)
```

---

## 6. Implementation phases

### Phase 0 — Audit & file PROJECT.md ✅ (this phase)
- [x] Read predecessor proposal (PF wiring §7 named the slug + scope).
- [x] Read all three product service files: PF metas + PF orcamentos + ERP metas + ERP meta_periodos + Daily Life goals.
- [x] Identify cross-cutting vs product-specific shapes (table in §5.1).
- [x] Verify destination layer per `KB § PATTERNS/seed-lib-layout.md` — confirmed `domain/metas/`.
- [x] Read canonical reference (`noctusai_lib.domain.scheduling`) for shape + tests style.
- [x] File this PROJECT.md.

**Improvements:**
- ERP's `_period_end_date` and `meta_periodos.mes_bounds` / `quinzena_bounds` / `trimestre_bounds` overlap — same date math, two different signatures, two different files in the same product. After the seed module ships, ERP's cleanup cycle should call seed `period_bounds()` from both. *(In ERP scope, not this project.)*
- PF's `obter_progresso` projected-completion uses `dateutil.relativedelta` — seed module SHOULD use stdlib `calendar.monthrange` math to keep `primitives/` discipline (seed-lib avoids 3rd-party deps where stdlib suffices).
- Daily Life's `goals_service` uses `noctusai_lib.api.auth.first_or_none` — interesting cross-layer use; that helper is already in seed, no action needed but confirms the pattern.

### Phase 1 — Design value objects + module skeleton ✅
- [x] Create `seed/lib/backend/noctusai_lib/domain/metas/__init__.py` with planned-occupants docstring + `__all__` placeholder.
- [x] Create `value_objects.py` — `Goal`, `Target`, `Progress`, `Period`, `Contribution`, `GoalStatus`, `PeriodKind` (frozen dataclasses + enums).
- [x] Create `repository.py` — `GoalRepository` Protocol + `InMemoryGoalRepository` default.
- [x] Wire `__init__.py` re-exports.
- [x] Create `seed/lib/backend/tests/domain/metas/__init__.py` + skeleton test files importable.
- [x] Phase 1 + Phase 2 collapsed into one commit (tightly coupled, see Change Log).

**Improvements:**
- Phase 1 + 2 collapsed into a single working pass (write module + write tests in one breath); the project plan kept them as separate phases per the template, but in practice the tests exercise the public surface so writing them apart wastes a context round-trip. Future similar projects: budget for 1 collapsed phase, not 2.
- `GoalStatus.value` doubles as the canonical persisted string (string-valued enum). Predicted in §3.6; confirmed correct on Phase 2 — products can `db.update({"status": GoalStatus.COMPLETED.value})` directly without going through `to_pt_string`. The PT mapping is for legacy strings (`ativa`/`concluida`) that products already persist; new products should use the enum value.
- `_add_months` was promoted from "use `dateutil.relativedelta`" (PF's choice) to "stdlib `calendar.monthrange` math" inside Phase 2 to keep the seed-lib stdlib-only discipline. Cited in `KB § PATTERNS/seed-lib-layout.md` table — `primitives/` "stdlib-only" — but applies upward through `domain/` for the same reason (no surprise transitive deps).

### Phase 2 — Implement pure-function modules + tests ✅
- [x] `periods.py`: `PeriodKind` enum methods + `period_bounds`, `count_business_days`, `business_days_remaining_in_week/month/year`, `working_days_total_in_month/year`, `proportional_target`. Tests cover ERP's `_calcular_meta_proporcional` cases verbatim.
- [x] `progress.py`: `compute_progress`, `accumulate_contribution`, `project_completion_date`. Tests cover PF's `obter_progresso` cases + daily-life accumulation.
- [x] `status.py`: `GoalStatus` enum + `next_status` state machine. Tests cover PF "concluida" threshold + ERP "no_prazo"/"atrasada" by period-remaining-pct.
- [x] Update `__init__.py` to re-export final surface.
- [x] Run `pytest seed/lib/backend/tests/domain/metas/` — **111 passed**.
- [x] Run full seed-lib pytest — **638 passed** (baseline 527 + 111 new = no regression).
- [x] Phase 1 + Phase 2 commit (no push).

**Improvements:**
- One test caught my arithmetic at first try (test_project_completion_date_calculates_eta) — wrote expected ETA based on confused mental model of monthly_avg vs total. Fix was in the test, not the production code, but it's a reminder that: tests for "X months from now" need the full chain spelled out in the comment, not just the answer.
- ERP's `_calcular_meta_proporcional` had no QUARTERLY case; I added one as a natural extension (monthly * 3 * remaining_in_quarter / total_in_quarter). Rationale: ERP's project has `quinzenal/mensal/trimestral/anual` periods but proportional target only handled `diaria/semanal/mensal/anual`. The QUARTERLY extension is consistent with the ERP shape and harmless (no consumer today).
- `accumulate_contribution`'s "crossed_threshold_pct" milestone detection is bonus value that wasn't in any product today — it's a small extension (~10 LOC) that downstream gamification / notification consumers will appreciate. Catalog as accept-with-rationale: SHIPPED-AHEAD-OF-CONSUMER, well-tested, no maintenance burden.

### Phase 3 — KB integration + project close
- [ ] Add `KB § PATTERNS/metas-seed.md` (concise: shape + wiring recipe, modeled on `scheduling-seed.md`).
- [ ] Add INDEX.md row for the new pattern doc.
- [ ] Add `KB § 04-SHARED-LIBRARY.md` row for `domain/metas/`.
- [ ] Add CLAUDE.md `§ The Map → Patterns` pointer (one-liner).
- [ ] File ONE end-of-project proposal at `./proposals/` bundling all phase-1 + phase-2 + phase-3 improvements (per project-execution.md § proposals-and-improvements).
- [ ] Run `python scripts/verify-kb-sync.sh` (or `python mcp/noctusai/cli.py --verify-kb-sync`).
- [ ] Final commit + push branch (branch-to-branch, NOT to main).

---

## 7. Open questions

1. **Should `Period` carry a parent-period reference for ERP's quinzena→mes→trimestre cascade?** — *Recommendation: NO for this project.* ERP is N=1; per recurrence rule, lift only the bounds-math, leave the cascade in ERP. Reopen if PF or daily-life ever introduces nested periods.
2. **Should `accumulate_contribution` return a `ProgressTransition` named tuple or a plain `(new_value, completed_bool)` tuple?** — *Recommendation: named tuple.* More extensible (we may later add `crossed_threshold_pct` for milestone notifications) without breaking callers.
3. **Should `project_completion_date` accept a custom `cadence` (monthly avg vs weekly avg)?** — *Recommendation: monthly default, `cadence: PeriodKind = MONTHLY` parameter.* PF uses monthly today; daily-life may want weekly cadence later.
4. **Naming: `metas` (Portuguese) or `goals` (English)?** — *Recommendation: `metas`.* Matches the dispatch slug, matches the recurrence pattern (PF + ERP both use `metas` in code; daily-life is the outlier with `goals_service.py`). Brand-neutral within the platform; seed-lib already has Portuguese-influenced names elsewhere (`first_or_none` is English; mixed already). Confirmed by predecessor brief naming the project "metas-domain".

---

## 8. Dependencies & blockers

- None. Pure-domain module; no DB, no SDK, no migration. Existing `noctusai_lib.domain.scheduling` shape is the implementation template.
- Sibling parallel projects (`make-get-current-user-org-factory`, `ai-plumbing-seed-absorption`) have **zero file overlap** with this project (`api/auth.py` and `domain/ai/` vs new `domain/metas/`). Architect verified pre-dispatch.

---

## 9. Success criteria

- `noctusai_lib.domain.metas` module exists at the documented path with the documented public surface.
- ≥ 30 unit tests (value objects + progress + periods + status + repository).
- `pytest seed/lib/backend/tests/` 100% green; no flakes.
- `noctus.dev.scan_recurrence` after this lands shows `metas/goals/orcamentos` services as N=3 *consumers* of `noctusai_lib.domain.metas` (target state — measured in the follow-up wiring cycle, not here).
- KB pointer in INDEX.md + `04-SHARED-LIBRARY.md` row + CLAUDE.md map row land same session as the code (three-way sync).
- ONE end-of-project proposal filed in `./proposals/` bundling phase improvements.
- Branch `metas-domain-seed-absorption` pushed to its remote (NOT main).

---

## 10. How to use this plan

- Phase-by-phase. Architect may dispatch fresh sub-engineers per phase OR carry through.
- Live-tick sub-tasks as they complete (don't batch).
- Improvements captured during steps; one bundled proposal at project close (per `KB § PATTERNS/proposals-and-improvements.md`).
- Per-phase local commit; final commit + branch push at PROJECT CLOSE.
- All changes inside `seed/lib/backend/` + `KNOWLEDGE-BASE/` + `CLAUDE.md` + `projects/metas-domain-seed-absorption/`.
- No product code touched (read-only).

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | Initial PROJECT.md drafted from `templates/PROJECT-TEMPLATE.md` after Phase 0 audit of PF / ERP / daily-life metas services. Recurrence-rule trigger: N=3 MUST FORMALIZE per `KB § PATTERNS/project-execution.md § 2.7`. Predecessor: `products/personal-finance/projects/personal-finance-wiring/proposals/phase-1-seed-absorption-followups.md § 7.3`. | claude-opus-4-7 (engineer; dispatched by architect) |
| 2026-05-03 | Phase 1 + Phase 2 shipped in a single commit (tightly coupled — module + tests written in one pass). New `seed/lib/backend/noctusai_lib/domain/metas/` ships 5 source modules (value_objects, periods, progress, status, repository) + 1 `__init__.py` re-export barrel. New `seed/lib/backend/tests/domain/metas/` ships 5 test files = 111 tests total. Full seed-lib pytest: 638 passed (was 527 baseline). Domain `__init__.py` doc-block updated to list `metas/` as active occupant. | claude-opus-4-7 |
