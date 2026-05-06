# Proposal: metas-domain-seed-absorption end-of-project bundle

**Agent:** claude-opus-4-7 (engineer; dispatched by architect — parallel-batch B3 of N=3 same-shape seed-absorption sister projects)
**Origin:** project:metas-domain-seed-absorption:phase-3
**Generated:** 2026-05-03
**Severity:** medium
**Effort:** medium
**Affected products:** none directly (seed-only); future consumers — personal-finance, erp-imobiliario, daily-life
**Status:** pending

---

## 1. Context

`projects/metas-domain-seed-absorption/` shipped `noctusai_lib.domain.metas` — the cross-cutting goals/targets math + state machine + value objects + period date-math, lifted from PF, ERP, and Daily Life per N=3 MUST-FORMALIZE (`KB § PATTERNS/project-execution.md § 2.7`). Pure-domain; persistence stays product-side. 111 tests pass; no regression in the 638-test full seed-lib suite. KB pointer + 04-SHARED-LIBRARY catalog row + INDEX.md row + CLAUDE.md map row all in three-way sync. This bundle captures the live improvements observed during Phase 0+1+2 execution.

---

## 2. Bundled improvements

### 2.1 Filing follow-up cycles for the three product wirings (independently executable)

**Linkage.** The seed module is in place but no product consumes it yet — by design, per the dispatch brief. Three sister projects need to file:

- **`pf-metas-seed-wiring`** — refactor `products/personal-finance/backend/app/services/metas_service.py` + `orcamentos_service.py` to call `compute_progress`, `accumulate_contribution`, `project_completion_date` from the seed. Map PF schema columns (`valor_alvo`, `valor_atual`, "ativa"/"concluida") at the boundary. Drop `dateutil.relativedelta` from PF's `metas_service` (seed uses stdlib).
- **`erp-metas-seed-wiring`** — refactor `products/erp-imobiliario/backend/app/services/metas_service.py` to call `proportional_target`, `period_bounds`, `count_business_days` from the seed. Drop `_period_end_date`, `_count_weekdays`, `_dias_uteis_*`, `_calcular_meta_proporcional` local helpers. Also: refactor `meta_periodos_service.py` to use seed `period_bounds` for the simple bounds calls (the parent-child cascade `gerar_trimestre` stays — N=1).
- **`daily-life-goals-seed-wiring`** — refactor `products/daily-life/backend/app/services/goals_service.py` to call `accumulate_contribution`. Map `valor_atual` ↔ `Progress.current`.

**Application steps.** Each project: read its product's service file → identify call sites → refactor to seed import + boundary mapping → add tests covering the boundary mapping → ensure existing product test count holds.

**Risks.** Boundary-mapping bugs (column names mistyped). Mitigated by existing per-product test counts catching regressions.

### 2.2 ERP `meta_periodos_service.py` overlap with new seed `period_bounds`

**Linkage.** ERP has TWO different period-bounds implementations today: `_period_end_date` in `metas_service.py` and `quinzena_bounds` / `mes_bounds` / `trimestre_bounds` in `meta_periodos_service.py`. Both implement the same fortnight + month + quarter math; the seed lift unifies them. Bundled in the `erp-metas-seed-wiring` project (§2.1) but worth surfacing as its own line item so the cleanup doesn't get forgotten under "wire metas service to seed".

**Application steps.** In the ERP wiring project, after the `metas_service.py` refactor, sweep `meta_periodos_service.py` callers of the bounds helpers and migrate them to seed `period_bounds(PeriodKind.X, ref)`. The ERP-specific `gerar_trimestre` cascade stays.

**Risks.** Low — pure-function math swap.

### 2.3 `crossed_threshold_pct` ahead of consumer (accept-with-rationale candidate)

**Linkage.** `accumulate_contribution` returns `ProgressTransition(new_current, completed, crossed_threshold_pct)`. The third field is a small extension over the PF / Daily Life shape (which only need `new_current` + `completed`); it detects 25/50/75/100% milestone crossings. No consumer today.

**Why it shipped now.** Cheap to add (~10 LOC + 3 tests); zero risk because optional / `None`-defaulted; unblocks future gamification + notification consumers without a follow-up seed change. Otherwise the second-cycle agent re-opens the seed module to add it, which is the slip-shape we're explicitly trying to avoid.

**Application steps.** None now. When a consumer (notifications-on-milestone, gamification celebration confetti, etc.) emerges, surface this as the existing seed seam → file the consumer cycle → done.

**Triage.** Cataloging in `KB § PATTERNS/accept-with-rationale.md § Seed extension shipped ahead of consumer — accumulate_contribution.crossed_threshold_pct` is a follow-up improvement (deferred — small, optional), or just keep this proposal as the audit trail. **Recommendation:** keep this proposal as audit trail; the seed-extension is well-tested and self-documenting.

### 2.4 ERP `meta_*_service.py` family seed adoption — measure absorption depth

**Linkage.** ERP has 9 metas-related services (`metas_service`, `metas_empresa_service`, `metas_equipe_service`, `meta_rankings_service`, `meta_fechamentos_service`, `meta_periodos_service`, `metas_configuracao_service`, `metas_digest_service`, `meta_api_service`). The audit (Phase 0) only mapped the math layer recurrence; some of these may have additional pattern slips that the seed module surfaces as the wiring cycle progresses.

**Application steps.** During the `erp-metas-seed-wiring` project, schedule a Phase 0 audit pass over all 9 service files calling the new seed module. Anything that re-implements `compute_progress` / `accumulate_contribution` / `period_bounds` math should be migrated. Run `noctus.dev.scan_recurrence` against the directory after the migration.

**Risks.** Low — discovery work, not a blocker.

### 2.5 Phase 1+2 collapse — methodology calibration

**Linkage.** The PROJECT template suggests Phase 1 (skeleton) + Phase 2 (implementation) as separate phases, but in practice for this lift the two phases were tightly coupled — writing tests revealed the public surface, and writing the public surface needed test calibration. Single commit was the right shape.

**Application steps.** None — this is a methodology learning. Future seed-absorption projects of the same shape (lift pure-domain math from N≥2 products) should plan for **1 collapsed implementation phase** instead of 2. Phase 0 (audit) + Phase 1 (implement+tests) + Phase 2 (KB sync + close) is more honest than 4 phases.

**Triage.** Update `KB § PATTERNS/proposals-and-improvements.md` or `KB § PATTERNS/seed-lib-layout.md`'s "Adding a new domain feature" section with this calibration. **Recommendation:** lightweight — log as a phase-pattern note; not a behavior change.

### 2.6 PF `dateutil.relativedelta` → stdlib calendar.monthrange

**Linkage.** PF's `obter_progresso` uses `dateutil.relativedelta(months=int(meses_restantes))` for ETA projection. The seed `project_completion_date` rewrites this in stdlib (`_add_months` clamps to last-day-of-month). When PF wires to the seed (§ 2.1), `dateutil` becomes an unused PF dep. Sweep + remove.

**Application steps.** Bundled into `pf-metas-seed-wiring`: after seed wiring, `grep -rn "dateutil" products/personal-finance/backend/app/` — if zero hits, drop `python-dateutil` from PF's `pyproject.toml`. Otherwise, document the remaining use.

**Risks.** Low.

---

## 3. Acceptance Criteria

- [ ] Three follow-up wiring projects filed (or, if architect prefers a master-tree, one master + 3 children per `KB § PATTERNS/master-tree-parallel-batches.md`).
- [ ] `crossed_threshold_pct` audit trail preserved (this proposal stays in the project folder).
- [ ] ERP wiring project Phase 0 includes the 9-service audit pass.
- [ ] Methodology learning §2.5 logged.
- [ ] PF wiring project includes the `dateutil` sweep.

---

## 4. Standalone vs scheduled

All six improvements are **independently executable**. The seed module is already in place; nothing in this bundle blocks anything else.

- §2.1 is the highest-leverage (3 follow-up dispatches).
- §2.2, §2.4, §2.6 fold into §2.1 sub-tasks.
- §2.3 is documentation-only (audit trail).
- §2.5 is methodology-only (KB calibration; no code).

---

## 5. Related files

- `seed/lib/backend/noctusai_lib/domain/metas/**` — the lifted module.
- `seed/lib/backend/tests/domain/metas/**` — 111 tests.
- `KB § PATTERNS/metas-seed.md` — wiring recipe (downstream wiring projects read this first).
- `KB § PATTERNS/seed-lib-layout.md` — layer model the module obeys.
- `products/personal-finance/backend/app/services/metas_service.py` — PF wiring target.
- `products/personal-finance/backend/app/services/orcamentos_service.py` — PF wiring target.
- `products/erp-imobiliario/backend/app/services/metas_service.py` — ERP wiring target.
- `products/erp-imobiliario/backend/app/services/meta_periodos_service.py` — ERP secondary wiring target.
- `products/daily-life/backend/app/services/goals_service.py` — Daily Life wiring target.
