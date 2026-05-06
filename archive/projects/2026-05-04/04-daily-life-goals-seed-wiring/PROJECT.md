# Daily Life Goals — Seed Wiring

> **Living document.** Phases evolve; capture in §11 / `findings.md`.

- **Created:** 2026-05-04
- **Last updated:** 2026-05-04
- **Status:** Phase 0+1+2 ✅ — closed (collapsed per metas-domain-seed-absorption § 2.5)
- **Owner / stakeholders:** jraphaelsst · architect (orchestrator) · Engineer C (Batch 1C of `in-flight-execution-rollout`)
- **Related docs:** `KNOWLEDGE-BASE/CONTEXT/PATTERNS/metas-seed.md`, `projects/metas-domain-seed-absorption/proposals/claude-opus-4-7-20260503-end-of-project-bundle.md`, sister wiring projects `pf-metas-seed-wiring` + `erp-metas-seed-wiring`
- **Project slug:** `daily-life-goals-seed-wiring` — single-product wiring; lives at root `projects/` because it's part of the cross-product `in-flight-execution-rollout` master tree (Batch 1C).

---

## 1. Context & Purpose

Commit `09fa759` shipped `noctusai_lib.domain.metas` — pure-domain math + value objects + state machine extracted from PF, ERP, and Daily Life under the N=3 MUST-FORMALIZE rule. The seed module is in place; **no product consumes it yet** — by design, per the `metas-domain-seed-absorption` end-of-project bundle (§2.1).

This project wires Daily Life's `goals_service.register_checkin` to consume the seed's `accumulate_contribution`. Daily Life's terminology is bilingual: column names + status strings are PT-BR (`metas`, `valor_atual`, `ativa`/`concluida`) but the code identifiers + service-layer vocabulary are English (`goals`, `checkins`, `register_checkin`). The seed is language-neutral at the math layer (`accumulate_contribution`), explicit at the PT-BR adapter layer (`from_pt_string` / `to_pt_string` — Daily Life skips these).

**Win condition.** `goals_service.py` imports + calls `accumulate_contribution`; the math layer is the seed's; product keeps Supabase persistence + RLS + check-in schema; product tests stay green; seed-lib tests stay green; milestone-crossing detection (`crossed_threshold_pct`) is captured for future gamification consumers (logged today).

---

## 2. Confirmed constraints

- **Daily Life is org-less in standalone mode** — `user_id` is the keeper, not `org_id`. *(Seed treats `Goal.id` as opaque; nothing changes.)*
- **Schema is PT-BR (`metas` / `checkins` / `valor_atual`); code identifiers are English (`register_checkin`, `goals_service`).** *(Mapping happens at the boundary inside `goals_service.py`. No migration; no schema change.)*
- **`crossed_threshold_pct` first-consumer territory.** Engineer 3 shipped milestone detection ahead of consumer (proposal §2.3). Daily Life captures the value via logging today (gamification-ready surface, no UI change yet); a follow-up project will wire push notifications. *(Prevents seed re-open on second cycle.)*
- **No PT-BR status adapters.** Daily Life's status flip from `"ativa"` → `"concluida"` happens at the boundary; the seed's `to_pt_string` exists for PF / ERP and remains optional for Daily Life. *(Daily Life today doesn't auto-flip status on completion in `register_checkin` — the user manually flips via PATCH /api/goals/{id}. Adding auto-flip is a behavior change → in-scope OR out-of-scope decision below.)*
- **No PATCH-side auto-status-flip in this project.** Today the router accepts a manual status update; the seed's `transition.completed` flag will surface the auto-flip opportunity but we'll catalog it as an accept-with-rationale follow-up to keep the change scope-minimal. *(Reduces risk; matches PF/ERP cycle scope.)*

---

## 3. Design principles

1. **Boundary mapping at the service layer.** `goals_service.py` is the boundary. Inside the function, reads pull `valor_atual` (PT-BR column), call seed math, write back `valor_atual` (PT-BR column). The seed never sees PT-BR.
2. **Re-sum-all replaced by single-shot accumulation.** Today's flow does insert → select-all-checkins → sum → update. The seed's pattern is single-shot (`new_current = current + increment`). This is the canonical wiring per `KB § PATTERNS/metas-seed.md §4`. Drift-defense via re-sum is out of scope; if drift occurs in production, that's a separate audit task (catalog as accept-with-rationale follow-up).
3. **Milestone capture via logging.** `crossed_threshold_pct` is captured at INFO level — gamification + notifications are first-consumer territory; logging today is the audit-trail surface.

---

## 3a. Seed-first analysis (REQUIRED)

Six-question checklist (`KB § GUIDES/seed-first-design.md`):

1. **Is the contract identical for every product?** YES — `accumulate_contribution(target, current, increment) → ProgressTransition` is product-neutral. PF, ERP, and Daily Life all need it.
2. **Is the data source product-specific?** YES — Daily Life persists in Supabase `metas`/`checkins` with `user_id` filter; PF uses `metas` + `meta_contribuicoes` + `org_id`; ERP uses `metas` + actuals from deals. Seed provides the math; persistence stays product-side.
3. **Is the placement product-specific?** YES — `goals_service.register_checkin` is the daily-life service endpoint; the wiring lives there.
4. **Is the visibility / permission rule the same?** NO — Daily Life RLS is `user_id`; PF is `user_id + org_id`; ERP is `org_id` + role-based. Each product handles RLS at its own boundary.
5. **Does the seam already exist in seed?** YES — `noctusai_lib.domain.metas.accumulate_contribution` (commit `09fa759`).
6. **Default-on or opt-in?** DEFAULT-ON — every check-in flows through the seed math.

**Litmus — per-product code count this design requires:**

- [x] **A small section** — product-specific data wiring around a seed-shaped function. `register_checkin` keeps its Supabase-shape; the math line that today computes `total_valor` becomes a `accumulate_contribution(...)` call. ~8 lines change inside the existing function.

**Phase plan implications:** §6 phases work in the *daily-life* product (correct — this is a single-product wiring inside a master-tree of three sister wirings). The seed math itself ships uniformly; only the boundary code lives in daily-life. No replication framing.

---

## 4. Scope

**In scope:**
- Refactor `products/daily-life/backend/app/services/goals_service.py::register_checkin` to import + call `accumulate_contribution` from `noctusai_lib.domain.metas`.
- Capture `crossed_threshold_pct` via `logger.info` for future gamification consumers.
- Verify all daily-life backend tests stay green; verify seed-lib tests stay green.
- Update test mocks in `test_goals_router.py::TestCheckin::test_checkin` if the call sequence changes (re-sum-all → single-shot accumulation = different Supabase calls).

**Out of scope (for now — with reason):**
- **Auto-flip status to `concluida` on completion** — today the router accepts a manual status update; auto-flip is a behavior change deserving its own project. Catalog as accept-with-rationale.
- **Push notification on milestone crossing** — first-consumer territory; explicit in proposal §2.3 of `metas-domain-seed-absorption`. Filed as follow-up.
- **Drift-defense via re-sum-all** — today's redundant select-all+sum is a defensive pattern. Removing it is the canonical seed wiring; if drift becomes observable in production, audit task.
- **Goal/Progress object adoption in `obter_meta`** — daily life today returns the raw `metas` row; mapping to `Goal` / `Progress` value objects is unnecessary for current consumers. Future-when-needed.
- **`compute_progress` adoption** — Daily Life today doesn't expose progress percentages (no `obter_progresso`-equivalent endpoint). Future-when-needed.
- **PATCH /api/goals/{id} status enum-validation.** Today accepts `ativa|concluida|pausada|cancelada` — could be tightened with `from_pt_string`. Catalog as accept-with-rationale.

---

## 5. Architecture / Data Model

**File path:** `products/daily-life/backend/app/services/goals_service.py` (single file change).

**Today's flow (lines 30-65):**
```
1. SELECT meta WHERE id=? AND user_id=?  → verify
2. INSERT INTO checkins (...)             → record
3. SELECT valor FROM checkins WHERE meta_id=?  → re-sum
4. UPDATE metas SET valor_atual=SUM(valors) WHERE id=?  → persist
```

**Wired flow (post-refactor):**
```
1. SELECT meta_valor, valor_atual FROM metas WHERE id=? AND user_id=?  → verify + read state
2. INSERT INTO checkins (...)                                          → record
3. seed.accumulate_contribution(target, current, increment)            → seed math
4. UPDATE metas SET valor_atual=transition.new_current WHERE id=?      → persist
5. logger.info on crossed_threshold_pct                                → audit trail
```

**Field mapping:**
- `metas.meta_valor` (PT-BR) ↔ `Target.amount` (seed via the bare float `target` parameter — `accumulate_contribution` doesn't require constructing a `Target` value object)
- `metas.valor_atual` (PT-BR) ↔ `current` parameter / `transition.new_current` (seed)
- `checkins.valor` (PT-BR) ↔ `increment` parameter (seed)

---

## 6. Implementation phases

### Phase 0 — Audit + design lock ✅

- [x] Read seed module surface + KB pattern + Engineer 3's bundled proposal.
- [x] Read daily-life `goals_service.py` + router + tests + conftest.
- [x] Run baseline tests: daily-life backend = 233 passing; seed/lib backend = 660 passing.
- [x] Confirm decision: **single-shot accumulation** (not re-sum-all). Confirm: **milestone via logger.info** (no new endpoint or notification surface). Confirm: **no auto-status-flip** (out of scope).
- [x] Map out test mock changes: `TestCheckin::test_checkin` expects 2 sequential `metas` responses (verify, update) + 2 `checkins` responses (insert, select-for-sum). New flow: 2 `metas` responses (verify-with-meta_valor+valor_atual, update) + 1 `checkins` response (insert only). Drop the re-sum select.

**Improvements:** none captured this phase — design audit only.

### Phase 1 — Wiring + test calibration ✅

- [x] AST-edit `goals_service.py`: change SELECT to include `meta_valor, valor_atual`; replace re-sum-all + sum-loop with `accumulate_contribution(target, current, increment)`; persist `transition.new_current`; log `transition.crossed_threshold_pct`.
- [x] Update `test_checkin` mock sequence: drop the second `checkins` response; first `metas` response includes `meta_valor` + `valor_atual` so the seed math has inputs.
- [x] Run daily-life backend tests; verify 233 pass.
- [x] Run seed/lib backend tests; verify 660 pass.

**Improvements:** to be captured during execution.

### Phase 2 — Phase close + bundled proposal ✅

- [x] File `projects/daily-life-goals-seed-wiring/proposals/claude-opus-4-7-20260504-end-of-project-bundle.md` with absorbed-duplications + follow-ups + phase learnings.
- [x] Findings captured in this engineer's report (5 categories).
- [x] Commit Phase 0+1+2 (collapsed per metas-domain-seed-absorption § 2.5 calibration — single commit for the whole single-product wiring).

**Improvements:** none identified — phase-close mechanics only. (Block added retroactively 2026-05-04 by `seed-shadow-purge-helper-lift` engineer to satisfy hook self-check; original engineer omitted the block.)

---

## 7. Open questions

None — design locked from Engineer 3's proposal §2.1 + KB pattern §4.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Test mock sequence drift breaks `test_checkin` | Run daily-life backend tests; explicit assertion on the new sequence. |
| `meta_valor` is None for habits (vs goals) | Habit type allows null target; `accumulate_contribution` requires non-negative target; treat None target as 0 (sentinel) — a habit with no numeric target accumulates without a "completed" trigger. |
| Removing re-sum-all introduces drift | Out of scope per §4; if drift observed, audit task. |

---

## 9. Test plan

- Daily-life backend pytest: 233 passing → 233 passing (or +N if new assertions added).
- Seed/lib backend pytest: 660 passing → 660 passing (no seed change).

---

## 10. Copy-paste commands

```sh
# Run daily-life backend tests (use venv from main worktree per Engineer brief)
/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest \
  /Users/rapha/Documents/repository/NoctusAI/noctusai-worktrees/daily-life-goals-seed-wiring/products/daily-life/backend/tests/ -q

# Run seed/lib backend tests
/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest \
  /Users/rapha/Documents/repository/NoctusAI/noctusai-worktrees/daily-life-goals-seed-wiring/seed/lib/backend/tests/ -q
```

---

## 11. Change Log

- 2026-05-04 (Phase 0) — Project filed; baseline measured (233 + 660); design locked. Engineer C (Batch 1C of `in-flight-execution-rollout`).
- 2026-05-04 (Phase 1) — `goals_service.register_checkin` AST-rewritten via libcst to consume `noctusai_lib.domain.metas.accumulate_contribution`. Single-shot accumulation replaces re-sum-all. Milestone crossings (`crossed_threshold_pct`) logged at INFO. Two new tests added (`test_checkin_with_null_target_habit`, `test_checkin_milestone_crossing_logged`). Daily-life backend: 233 → 235 passing. Seed/lib backend: 660 passing (unchanged).
- 2026-05-04 (Phase 1 — environment fix) — Added shadow-purge prelude to `products/daily-life/backend/tests/conftest.py` mirroring the seed-side helper from Batch 1B. Required because the parallel-worktree venv carried an editable `noctusai_lib` install pointing at a sibling worktree that lacks the `domain.metas` module. Cross-product DRY recurrence (PF + ERP have identical conftest shape) flagged in proposal § 2.1.
- 2026-05-04 (Phase 2) — Bundled proposal filed: `proposals/claude-opus-4-7-20260504-end-of-project-bundle.md`. 5 improvements captured.
