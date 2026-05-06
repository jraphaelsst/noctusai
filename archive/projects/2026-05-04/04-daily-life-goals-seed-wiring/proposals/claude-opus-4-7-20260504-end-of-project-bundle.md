# Proposal: daily-life-goals-seed-wiring end-of-project bundle

**Agent:** claude-opus-4-7 (engineer; dispatched by architect — Batch 1C of `in-flight-execution-rollout`, sister to PF + ERP wiring)
**Origin:** project:daily-life-goals-seed-wiring:phase-close
**Generated:** 2026-05-04
**Severity:** medium
**Effort:** small (single-product wiring; collapsed Phase 0+1 per metas-domain-seed-absorption proposal § 2.5 calibration)
**Affected products:** daily-life (direct); future PF + ERP / cross-product follow-up (indirect)
**Status:** pending

---

## 1. Context

`projects/metas-domain-seed-absorption/` shipped `noctusai_lib.domain.metas` (commit `09fa759`). This sister project wired Daily Life's `goals_service.register_checkin` to consume `accumulate_contribution` from the seed. Math layer is now seed-shared; persistence + RLS + check-in schema stay in Daily Life. Test count: 233 → 235 (added two seed-wiring assertions). Seed/lib unchanged at 660. Three secondary improvements surfaced — bundled below.

---

## 2. Bundled improvements

### 2.1 Replicate parallel-worktree shadow-purge to PF + ERP product test conftests (cross-product DRY)

**Linkage.** Engineer 3 of `metas-domain-seed-absorption` shipped the shadow-purge in `seed/lib/backend/tests/conftest.py`. That fix only fires when running seed-lib-backend tests; product test suites have a separate conftest tree that doesn't inherit it. Daily Life hit the shadow on this wiring (Engineer C had to add the purge to `products/daily-life/backend/tests/conftest.py` to make `from noctusai_lib.domain.metas import accumulate_contribution` resolve correctly under the parallel-worktree venv setup).

PF wiring (Batch 1A) and ERP wiring (Batch 1B) almost certainly need the same fix. PF's existing conftest at `products/personal-finance/backend/tests/conftest.py` lines 1-19 mirrors Daily Life's pre-fix shape. ERP same.

**Application steps.** Apply the 30-line shadow-purge prelude to `products/personal-finance/backend/tests/conftest.py` and `products/erp-imobiliario/backend/tests/conftest.py`. Identical implementation to the Daily Life version filed in this commit. Verify with PF + ERP backend pytest.

**Risks.** Low — the helper is pure-import-side-effect, and the seed-lib version has been on main since Batch 1B without regressions.

**Recurrence:** N=3 across PF + ERP + daily-life — **MUST formalize**. Right destination is `seed/lib/backend/noctusai_lib/testing/conftest_helpers.py` (export `purge_shadowing_editable_finders()`); product conftests reduce to a 3-line import + call. Filing as cross-product follow-up project: `seed-conftest-shadow-purge-helper`.

### 2.2 Auto-flip `status` to `concluida` on completion

**Linkage.** The seed `accumulate_contribution` returns `transition.completed` — true when the contribution crossed `current → target`. Today Daily Life's `register_checkin` does NOT flip `metas.status` to `"concluida"` on completion; the user manually flips via `PATCH /api/goals/{id}`. PF auto-flips (per the seed wiring recipe in `KB § PATTERNS/metas-seed.md § 4`). Engineer C kept this out of scope to keep the wiring scope-minimal, but the asymmetry between PF and Daily Life is a slip that will eventually need the same fix.

**Application steps.** In `goals_service.register_checkin`, after the `accumulate_contribution` call, check `transition.completed` and append `"status": "concluida"` to the metas update payload. Add a test asserting the auto-flip path. Decision needed: does the user want the auto-flip behavior in Daily Life, or should it stay manual?

**Risks.** Behavior change — could surprise users who deliberately keep a goal "ativa" past hitting the target (rare but possible). Mitigated by the seed enum's sticky-COMPLETED design.

**Triage:** **defer** as a follow-up project (`daily-life-goals-auto-completion`) so the user can opt-in explicitly. Catalog as accept-with-rationale meanwhile.

### 2.3 Tighten `GoalUpdate.status` enum-validation via seed `from_pt_string`

**Linkage.** Today's `GoalUpdate` schema in `products/daily-life/backend/app/routers/goals.py` line 47 hardcodes the regex `^(ativa|concluida|pausada|cancelada)$`. The seed ships `from_pt_string` which does the PT-BR ↔ enum mapping. Migrating to `from_pt_string` would (a) centralize the vocabulary list, (b) get free synonym support (`ativa` ↔ `em_andamento`), (c) catch typos via raised `ValueError`.

**Application steps.** In `GoalUpdate`, replace the regex `pattern="^(ativa|concluida|pausada|cancelada)$"` with a `field_validator` that calls `from_pt_string(...)`. Round-trip through `to_pt_string` for the persisted value. Add test for the typo-rejection path.

**Risks.** Low — pure validation surface change; no schema migration.

**Triage:** **defer** as a small in-scope follow-up; not urgent. Catalog as accept-with-rationale: "PT-BR status string validation lives in product regex; should consume seed `from_pt_string`".

### 2.4 Re-sum-all drift-defense pattern dropped — accept-with-rationale

**Linkage.** Pre-wiring `register_checkin` re-summed all checkins (`total_valor = sum(c.valor)`) and wrote the result to `valor_atual`. Drift-resistant — if a checkin row gets manually deleted in Supabase, the next check-in re-syncs. Seed's canonical `accumulate_contribution` is incremental (`new_current = current + increment`); drift defense is gone.

**Application steps.** None unless drift is observed in production. If observed: file `daily-life-goals-drift-audit` to either (a) add a drift-detection cron, (b) restore the re-sum on a periodic basis, or (c) surface the gap as a seed-level concern (would affect PF + ERP too).

**Risks.** Low pre-production; non-zero in production with manual DB edits or partial failures.

**Triage:** **accept-with-rationale** — canonical seed wiring trumps drift-defense for this consumer; product can re-introduce defense at the boundary if needed without re-opening the seed.

### 2.5 Phase 0+1 collapse — methodology calibration confirmed

**Linkage.** This project ran Phase 0 (audit) + Phase 1 (wiring + test calibration) as a single commit, per the calibration noted in metas-domain-seed-absorption proposal § 2.5: "Single commit was the right shape." For seed-wiring follow-ups (lift consumer to seed seam), the audit + the implementation are tightly coupled — writing the test calibration revealed the mock-sequence change, which revealed the boundary fields needed (meta_valor + valor_atual), which finalized the audit.

**Application steps.** None — methodology learning. Future seed-wiring projects of the same shape (single product wiring to a seed seam) should plan for **1 collapsed phase**.

**Triage:** Update `KB § PATTERNS/proposals-and-improvements.md` or `KB § PATTERNS/seed-lib-layout.md` "Adding a new domain feature" with this calibration. **Recommendation:** lightweight — log as a phase-pattern note.

---

## 3. Acceptance Criteria

- [ ] Cross-product follow-up project `seed-conftest-shadow-purge-helper` filed (or the architect chooses to apply the per-conftest fix in PF + ERP wiring sister projects).
- [ ] `daily-life-goals-auto-completion` filed if user wants auto-flip.
- [ ] Accept-with-rationale catalog entries created for §2.3 + §2.4.
- [ ] Methodology learning §2.5 logged.

---

## 4. Standalone vs scheduled

All five improvements are independently executable.

- §2.1 is the highest-leverage (cross-product DRY; will block sister wirings if not fixed).
- §2.2 + §2.3 + §2.4 are scope-minimal Daily-Life-only follow-ups.
- §2.5 is methodology-only.

---

## 5. Related files

- `products/daily-life/backend/app/services/goals_service.py` — wired this commit.
- `products/daily-life/backend/tests/routers/test_goals_router.py` — added 2 seed-wiring tests.
- `products/daily-life/backend/tests/conftest.py` — shadow-purge prelude (mirror of seed/lib conftest).
- `seed/lib/backend/tests/conftest.py` — original purge helper (Batch 1B).
- `seed/lib/backend/noctusai_lib/domain/metas/progress.py` — seed math.
- `KB § PATTERNS/metas-seed.md § 4` — wiring recipe.
- `projects/metas-domain-seed-absorption/proposals/claude-opus-4-7-20260503-end-of-project-bundle.md § 2.1 + 2.3` — parent guidance.
