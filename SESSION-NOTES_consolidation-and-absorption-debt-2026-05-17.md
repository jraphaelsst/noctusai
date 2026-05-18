# Session notes — consolidation + fix-on-contact of absorption-surfaced debt (2026-05-17)

> **Status:** working notes, root-staged at user request. Durable lessons folded
> into `KB § GUIDES/absorb-seed-workspace.md` + `KB § 01-PHILOSOPHY.md` +
> `feedback_dangling_deleted_product_path` (this file is the *narrative*; the KB
> entries are the durable, self-contained form per durable-docs-self-contained).

## 1 · What this session did

- **Consolidation pass** — landed the converged deliverables of 9 closed projects
  (oauth-integrations-seed-lift, seed-standalone-dev-ergonomics,
  fleet-build-product-deps, promotion-manifest-parser-blocklist,
  seed-singleton-guard, symbol-first-stage-4-codification, llm-tool-audit-rollout,
  conftest-workaround-cleanup, seed-adapter-convergence) + the doc-sync layer.
  Verified green: `seed/lib` 1503 ✅ · `seed/framework` 86 ✅ · `social-wiring` ⏳.
- **2 new methodology rules** authored + three-way-synced (KB ∧ CLAUDE.md ∧ memory):
  1. **Codebase is source of truth; docs/summaries/memory are derived** — verify
     any claim against the tree (`git status`/`Read`/`pytest`/ledger) before
     acting; doc⊥code → code wins. Strict generalization of verify-the-seed-ships-it
     ∧ estimate-off-evidence ∧ no-silent-errors.
  2. **Fix-on-contact for pre-existing debt** — bumping a pre-existing
     failure/drift while doing other work does NOT license leaving it: (1) verify
     pre-existing vs baseline, (2) **fix in-flight**, (3) surface problem +
     root-cause + *solution applied*. Surface-only = silent-error one level up.
     Exceptions (never silent): out-of-safe-scope → surface w/ recommendation +
     named destination; balloons-to-project → file it.
- **engineer-default.md** — KB-autostage-hook hazard documented in §2 (CRITICAL
  stage-only contract) + §9 — the always-referenced standing surface, so the
  guarantee reaches every future dispatch by construction.

## 2 · The fix-on-contact event (the substance)

Verifying the consolidation tree surfaced **14 `mcp/noctusai` test failures**.
Per *codebase-is-source-of-truth*: baseline-checked each against `origin/main` in
throwaway worktrees rather than assuming → **100% pre-existing**, zero regressions
from this session's work. Per *fix-on-contact*: fixed, did not surface-only.

| Cluster | N | Root cause | Fix applied |
|---|---|---|---|
| A — stale `mailing` probes | 7 | `mailing` deleted in social-wiring-absorption Wave-4; mcp test matrix is a *derived surface* the teardown grep missed | New `tests/conftest.py` `domain_product` fixture — registry-derived, never re-staleable. Repointed test_products / test_diff / test_analyzers |
| B — `test_seed_is_minimal` | 1 | seed backend 500→509 from legitimately-shipped dev-auth seam | Bound 500→600 *with positive content anchor* (`routers<=2`) + dated rationale |
| C — `test_no_python_mismatches` | 1 | root `/requirements.txt` consistent outlier vs product consensus | Reconciled fastapi/PyJWT/google-api/google-auth/openai pins across root+therapy+social-wiring |
| D — stale team-tool expectations | 3 | `noctus.team.dashboard` (scan_fusions rollup) joined; dashboard envelope became stable-skeleton not empty-dict | Updated frozen `six`→`seven` set; rewrote `TestTeamDashboard` to the current resilient contract |
| E — `score==100` compliance gate | 2 | **637 issues** platform-wide (332 test-patch-target + ~280 silent-except + 15 therapy monkeypatch-high + 2 seed-version-drift ENV); chronically aspirational gate, red since long before this session | Bounded subset fixed in-flight (social-wiring RLS + standard_routers + the `⊥` glyph I introduced); platform-scale remainder = **filed project** (fix-on-contact balloon exception); gate re-calibration = **user-decision, surfaced with recommendation** |

## 3 · The root insight (why all this existed)

**The `social-wiring` source repo predated the current seeding-system maturity.**
It was developed externally, then absorbed. The system it grew under did not yet
have: registry-derived test probes, the RLS `service_role_bypass` keeper, strict
dep-pin reconciliation, the single-container house model, the codification
pipeline that since *added* keeper detectors which retroactively surface
pre-existing violations. So the absorption did not *create* the debt — it
**imported a product from an earlier methodology epoch and exposed the delta**.
The 14 mcp failures + 637 compliance issues are the measurable size of *"how
much the platform's methodology advanced while this product grew elsewhere."*

This is the durable lesson for the **seeding-absorbing system**: an absorption is
a *methodology-epoch merge*, not just a code move. The absorb procedure must
explicitly reconcile the **derived/generated surfaces** (mcp product-introspection
tests, compliance baseline, dependency pins, version-static) the same way it
reconciles functional code — because those surfaces encode assumptions about the
*old* fleet shape and silently rot when the fleet changes underneath them.

## 4 · Surfaced for user decision (not silently left)

- **`score==100` compliance gate calibration.** It penalizes every warning ×3,
  averaged across 14 products → `100` requires near-zero issues fleet-wide. It has
  been red since before this session because the codification pipeline keeps
  *adding* detectors that surface pre-existing debt (the pipeline working as
  designed). **Recommendation:** re-spec the gate to "no NEW high/critical vs a
  committed baseline" (regression-detector semantics) instead of "absolute 100"
  (aspirational), OR accept-with-rationale + a filed platform-compliance-remediation
  project for the 637. Not fixed this session because the gate's contract is a
  methodology decision, not a code defect (fix-on-contact "needs-a-decision"
  exception — surfaced with recommendation + named destination, explicitly).
