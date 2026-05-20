# platform-compliance-baseline

> **Filed 2026-05-17** as the `fix-on-contact` balloon-to-project destination
> for the platform-wide pre-existing compliance debt surfaced during the
> consolidation pass (commit `ef35a62`). NOT surface-only. Self-contained
> (durable-docs rule). Pairs with `social-wiring-absorption-debt` (that one is
> the per-product slice; this is the fleet-wide classes + the gate contract).

## 1. Context & Purpose

`check_all_products()` reports **637 issues, score 93** (penalties
critical:25/high:10/warning:3, per-product `max(0,100-Σ)` averaged → `100`
needs ≈zero issues fleet-wide). Baseline-verified: identical on `origin/main`
— this is **chronic pre-existing debt**, not a regression. It exists because
the methodology-codification pipeline keeps *adding* keeper detectors that
retroactively surface old violations (the pipeline working as designed). Two
`mcp/noctusai` tests gate on `score==100`
(`test_compliance.py::{TestAIFeatureCompleteness::test_real_products_pass_validate,
TestSeedCompliance::test_all_products_compliant}`) and have therefore been red
since well before this session.

## 3a. Seed-first analysis

The two dominant classes are cross-cutting (N≫3 → MUST formalize, not
per-product patch):
- **`test_patch_target` (332, bulk erp-imobiliario):** tests
  `patch()`-ing our own symbols — the `no-monkeypatching-of-our-own-code`
  rule (`feedback_no_monkeypatching_in_tests`). Fix shape = dependency
  injection / seed `MockRequestBuilder.inserted_payloads` read-side, applied
  per test cluster; the *pattern* is one seed-testing convention, the
  instances are many.
- **silent-except "swallows errors" (~280, across mcp/seed/products):** the
  `no-silent-errors` / no-`# silent-ok` rule (`feedback_silent_ok_*`). Fix =
  `logger.debug/exception(...)` at each site; the convention is seed-level
  (`KB § PATTERNS/logging.md`), instances fleet-wide.
- **therapy monkeypatch-high (15):** same class as test_patch_target,
  high-severity (session_audio/scheduler/audit_hook tests).
- **seed-version-drift (2, ENV):** `_version_static.py` stamped to the
  pre-commit HEAD lags the post-commit SHA — a pre-commit-stamp artifact,
  NOT code debt; clears on next install/build. Exclude from the count or
  make the detector tolerate the 1-commit stamp lag.

## 4. Scope

**In:** drive `check_all_products()` 637 → near-0 across the fleet, by
*formalizing the conventions* (DI test pattern; logging-at-except) and
mechanically applying per cluster. Decide the **`score==100` gate contract**
(§7). **Out:** social-wiring's 174 (→ `social-wiring-absorption-debt`).

## 6. Implementation phases (wave-based, pilot-first)

- **P0 ✅ — categorize + gate decision.** `check_all_products()` ⇒ score
  100 but 18 high/critical (2 seed-drift `<platform>` + 1 archive-staleness
  `<root>` = non-deterministic env artifacts; 15 therapy-platform
  monkeypatch-high). §7 resolved WITH the user ⇒ **(A)**.
  - [x] Full high/critical dump by product
  - [x] §7 gate contract resolved with user = (A)
- **P5 ✅ — gate re-spec + verify (the only gating phase under (A)).**
  - [x] Both gate tests re-spec'd to regression semantics (libcst,
        AST-first); absolute score now informational (`print`, not assert)
  - [x] Committed deterministic baseline `compliance_baseline.json` (12
        fingerprints) + regenerable `refresh_compliance_baseline.py`
  - [x] 2 remediation conventions + the new gate pattern formalized in KB
        (3 docs) + CLAUDE.md §2 + INDEX.md additive pointers; verify-kb-sync ✅
  - [x] `pytest mcp/noctusai/tests/ -q` ⇒ **1349 passed** (gate tests green
        under regression semantics; llm-collection fix-on-contact applied)
- **P1-P4 — NON-gating under (A); deferred-with-destination (NOT executed
  here).** Mechanical fleet sweeps that *drain* the baseline (shrink it);
  not required for the gate to be green. Destinations:
  - **P1 silent-except sweep** → incremental per-pilot follow-up, drain via
    `KB § PATTERNS/logging-at-except.md`; baseline shrinks per resolved site.
  - **P2 test_patch_target refactor (erp bulk)** → incremental, drain via
    `KB § PATTERNS/di-test-seam.md`; parallelizable per test-file cluster.
  - **P3 therapy high-sev monkeypatch (the 12 baseline fingerprints)** →
    same DI-seam destination; highest-priority drain candidate.
  - **P4 seed-version-drift tolerance** → SUPERSEDED: env-artifact classes
    (seed-drift / archive- / dispatcher-staleness) are now excluded from
    BOTH the baseline and the live set (no detector change needed).

## 7. Open questions (USER DECISION — surfaced, not silently chosen)

**The `score==100` gate is aspirational, not a regression detector.** Every
new keeper detector lowers it by surfacing pre-existing debt. Options:
- **(A) Re-spec the gate** to "no NEW high/critical vs a committed baseline"
  (regression semantics) + track absolute score as an informational metric.
  *Recommended* — keeps the gate green-able and still catches regressions;
  the codification pipeline can keep adding detectors without breaking CI.
- **(B) Keep `score==100`** and treat this project as the hard push to get
  there (largest scope; CI stays red until P5 completes).
- **(C) accept-with-rationale** the 2 gate tests at the current baseline with
  a documented target, no contract change.

**DECISION (locked 2026-05-18 by the user): (A).** Gate re-spec'd to
regression semantics + absolute score informational. Recorded; scopes the
project ⇒ only P0/P5 are gating, P1-P4 = non-gating incremental drains.

## 9. Success criteria

`check_all_products()` at the agreed target; the 2 compliance gate tests
green or re-specified per §7; conventions formalized in KB (not just
instance-fixed); no new frozen literals.

## 10. How to use this plan

P0 first, and **resolve §7 with the user before P1** — the gate contract
scopes the entire project. Fresh worktree; pilot-products-first cadence
(`KB § PATTERNS/project-execution.md § 2.12`); engineers obey
`.claude/agents/engineer-default.md`.

---

## 11. Change log

| Date | Entry | By |
|---|---|---|
| 2026-05-18 | §7 resolved with user ⇒ **(A)** regression-semantics gate; recorded in §7. P0 ✅ + P5 ✅ (the only gating phases under A). | PC-A |
| 2026-05-18 | Both `score==100` gate tests re-spec'd via libcst → "no NEW high/critical vs committed `compliance_baseline.json`"; absolute score now informational (`print`, never asserted). New `compliance_baseline.json` (12 deterministic fingerprints) + regenerable `refresh_compliance_baseline.py`. Env-artifact classes (seed-drift/archive-/dispatcher-staleness) excluded both sides ⇒ P4 SUPERSEDED. | PC-A |
| 2026-05-18 | 3 KB pattern docs added (compliance-regression-baseline + di-test-seam + logging-at-except) + CLAUDE.md §2 + INDEX.md additive pointers; `verify-kb-sync` ✅. 2 remediation conventions formalized as first-class named docs (pointer-shaped, no duplication of the authoritative testing.md/logging.md depth — DRY). | PC-A |
| 2026-05-18 | fix-on-contact: regenerator's `sys.path.insert(tools/)` shadowed the real `google` SDK → 7 llm test-module collection errors; pre-existing-vs-introduced verified by stash-and-rerun; fixed (package-root path only + importlib-contained helper load). `pytest mcp/noctusai/tests/ -q` ⇒ **1349 passed**. | PC-A |
| 2026-05-18 | P1-P4 fleet sweeps are NON-gating under (A) — recorded deferred-with-destination (incremental per-pilot drains via the 2 remediation-convention KB docs); NOT executed this session. Gating scope (P0/P5) complete; drain backlog open. | PC-A |
