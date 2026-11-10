# Code-review craft — the reviewer's canon behind the keepers

> **Owner:** agent `compliance-reviewer` (advisor, read-only). **Consumers:** every review of a branch/diff, the merged-tip review before bless, the phase proposal the reviewer files.
> **Status:** craft canon, 2026-11-05 (agent-refinement W1-S6). Sources verified 2026-11-05 unless marked otherwise in §12.

**What this is.** The profession's code-review and test-adequacy canon (Google's review standard, Conventional Comments, review-size research, ISO/IEC 25010, cognitive complexity, the test pyramid and trophy, mutation testing, flaky-test management, coverage as a signal), mapped onto how noc already reviews.

**Why it exists.** The 2026-11-05 audit found the reviewer was a *methodology-compliance gate*: every workflow step was a keeper or tool run (`noctus.dev.validate`, `scan_wiring`, the `scan_*` sextet). Keepers catch the shapes we have already seen. They do not judge design, complexity, naming, or whether a test suite would actually catch a fault. This doc is the human-judgement layer that runs after them.

**How to use it.** Run the house mechanisms first (they are the floor and they are cheap). Then walk §2 lenses on the diff, label every finding (§3), check size (§4), and judge tests by fault detection (§6–§8). **Where a house mechanism and the general canon disagree, the house mechanism wins** (e.g. the house requires strict `== 401` even where general advice would accept "any 4xx"). Copy §9 into the review.

## Contents
0. Standard term ↔ house term
1. Standard of review
2. What to look for: the 12 lenses
3. Comment taxonomy and severity
4. Review size and pacing
5. Maintainability lens: ISO/IEC 25010, cognitive complexity, named refactorings
6. Test-strategy assessment: pyramid vs trophy, mutation, property tests
7. Flaky tests
8. Coverage as a signal
9. Review checklist (copyable)
10. Worked examples
11. Anti-patterns
12. Sources

## 0 · Standard term ↔ house term

| Standard term | House term / mechanism |
|---|---|
| Code health (Google) | "clearly improves the platform"; regression semantics: no NEW high/critical vs `compliance_baseline.json` (`KB § PATTERNS/compliance/compliance-regression-baseline.md`) |
| CL / change list | a worker branch `feat/<slug>` or a merged-tip range `origin/dev..HEAD` |
| Reviewer approval | a `pass` recommendation; the tech-lead enforces the merge gate |
| Blocking comment | `issue (blocking)` with file:line ⇒ `block` recommendation |
| Static analysis floor | the keepers (`noctus.dev.validate`, pre-commit hook) |
| Follow-up ticket | a `noctus.dev.file_proposal` row, or an in-code `NOC-REMEDIATE[<class>]` marker (`KB § PATTERNS/common/remediation-markers.md`) |
| Test pyramid layers | the five layers of `KB § PATTERNS/compliance/testing.md` (unit · integration · realdb · E2E · regression) |
| Quarantine | `NOC-REMEDIATE[flaky]` + a named destination; never a silent retry |

## 1 · Standard of review

**Principle.** Google's senior principle: reviewers "should favor approving a CL once it is in a state where it definitely improves the overall code health of the system being worked on, even if the CL isn't perfect." There is no perfect code, only better code. Minor optional points are marked as nits so the author knows they can ignore them.

**How it applies here.** The regression-baseline gate already encodes "better, not perfect" for the keeper layer: the absolute score is informational, only a NEW high/critical regresses (`compliance-regression-baseline.md`). The human layer uses the same bar: a `pass` does not mean "nothing left to improve"; it means "the platform is healthier after this lands, and nothing blocking remains".

**Who decides and how disagreement resolves.** The reviewer recommends; the tech-lead decides the merge. A disagreement between reviewer and author is settled on technical facts and data (a failing probe, a cited rule), not preference. A methodology question that the KB does not answer goes to `architect`; it is not settled inside the review.

**Checklist**
- [ ] Is the platform clearly healthier with this change than without it?
- [ ] Is every blocking finding tied to a fact (file:line, failing probe, cited rule), not a preference?
- [ ] Have nits been labelled `nitpick` so they cannot block?

**Anti-patterns.** Holding a change hostage for unrelated cleanup (file it as a proposal instead). Approving because "the keepers are green".

## 2 · What to look for: the 12 lenses

Google's "what to look for" walks design, functionality, complexity, tests, naming, comments, style, consistency, documentation, every line, context and good things. Its closing checklist: well-designed; functionality good for users; UI sensible; parallel code safe; not more complex than it needs to be; no speculative generality; appropriate unit tests; well-designed tests; clear names; comments explain *why*; documented; conforms to the style guides.

Each lens below has the noc-specific probe the general canon does not know about.

| # | Lens | noc probe (where to look) |
|---|---|---|
| 1 | **Design** | Does it belong in the seed? Is a customization going through a named seam? (`KB § 03-SEED-ARCHITECTURE.md`; architect-owned `KB § PATTERNS/architect/seed-absorption.md`). Organ-shaped FE code imports `@noctusai/lib` (`KB § PATTERNS/architect/products-consume-canonical-organs.md`). |
| 2 | **Functionality** | Route-exists ≠ wired: page shows real data ∧ owns its CRUD (`KB § PATTERNS/frontend/product-internal-wiring.md`). Edge cases on money and dates (month boundaries, 2027 tax boundary, cents rounding). Concurrency: races on first-write (see `test_dre_api.py:327` first-put race test for the house shape). |
| 3 | **Complexity** | §5: cognitive complexity of touched functions; speculative generality ("might need later"). |
| 4 | **Tests** | §6–§8: would the tests fail if the code were wrong? Auth tests strict `== 401` (`KB § PATTERNS/compliance/auth-boundary-false-green.md`); no self-monkeypatching (`testing.md` §No self-monkeypatching). |
| 5 | **Naming** | Domain names match the KB vocabulary (pt-BR domain terms are deliberate — `simples_base`, `livro_caixa`); concepts are the same only by definition AND data. |
| 6 | **Comments** | Explain *why*; a deferral carries `NOC-REMEDIATE[<class>]` with a destination, never a bare TODO. |
| 7 | **Style** | Leave to linters; style is never `blocking` unless a keeper says so. |
| 8 | **Consistency** | Same problem, same mechanism: grep for the existing mechanism before accepting a new one (§1 "codebase is source of truth for solutions"). |
| 9 | **Documentation** | Docs follow code in the same commit (commit-msg hook / `Docs-Reviewed:` trailer, `KB § PATTERNS/common/doc-staleness-gate.md`); eight-way sync for rule changes (`KB § PATTERNS/common/eight-way-sync.md`). |
| 10 | **Every line** | Read every human-written line; generated files and lockfiles are scanned for scope, not read line by line. Say which files you did not read. |
| 11 | **Context** | Read the whole function/file around the hunk; a 3-line diff can break an invariant 40 lines up. Check the merged tip, not only the branch (per-branch green ≠ integration green). |
| 12 | **Good things** | Say what was done well (`praise:`). It reinforces the practice and keeps reviews credible. |
| + | **Accessibility** (house addition) | UI diffs: keyboard reachability, labels, contrast, focus order, loading/empty/error states announced. Depth: the frontend craft canon `PATTERNS/frontend/frontend-craft-canon.md` (frontend-engineer, W1-S4). Accessibility defects that block a user from completing a task are `issue (blocking)`. |

**Anti-patterns.** Keeper output pasted as the review. Reviewing only the hunks without the surrounding function. Skipping lens 12.

## 3 · Comment taxonomy and severity

**Principle.** Conventional Comments format: `<label> [decorations]: <subject>` then an optional discussion. Labels: `praise`, `nitpick`, `suggestion`, `issue`, `todo`, `question`, `thought`, `chore`, `note` (plus optional `typo`, `polish`, `quibble`). Decorations: `(blocking)`, `(non-blocking)`, `(if-minor)`. `note` is always non-blocking; `nitpick` is a trivial preference.

**House mapping (label → keeper severity → verdict).**

| Label (+ decoration) | Typical content | Maps to keeper severity | Verdict effect |
|---|---|---|---|
| `issue (blocking)` | correctness bug, security hole, false-green test, data loss, a NEW high/critical, seed fork | critical / high | **block** (≥1 required for a block; must cite file:line) |
| `issue (non-blocking)` | real defect with low blast radius, safe to land + fix next | medium | pass + proposal row with destination |
| `todo` / `chore` (blocking) | a required, mechanical step (docs not staged, INDEX row missing, `Docs-Reviewed:` trailer) | — | block until done (usually trivial) |
| `suggestion (non-blocking)` | better design/test; mutation pilot; refactoring by catalog name | low | pass + proposal |
| `question` | possible concern, unsure | — | neither; author answers |
| `nitpick` / `polish` / `typo` | preference, wording | low / none | **never blocks** |
| `thought` / `note` | ideas, awareness | — | never blocks |
| `praise` | good practice | — | — |

**Rule.** A `block` recommendation needs at least one `issue (blocking)` with file:line and a one-line reason a reader can verify. "Feels wrong" is a `question`, not a block.

**Example (house shape).**
```
issue (blocking): products/x/backend/tests/routers/test_orders.py:41 — `assert r.status_code in (401, 422)`
passes when validation runs before auth; the test never proves auth. Assert `== 401` with a valid body.
```

## 4 · Review size and pacing

**Principle.** Google: "100 lines is usually a reasonable size for a CL, and 1000 lines is usually too large", at the reviewer's judgement. SmartBear's peer-review study: review no more than 200–400 LOC at a time; defect density drops significantly at rates faster than 500 LOC/hour; don't review for more than 60 minutes at a time (60–90 for 200–400 LOC).

**How it applies here.** The house runs large merged-tip reviews (a wave of N slices). The reviewer's job is to keep each *read* within the evidence-backed window, not to refuse merged tips:
- Count **human-authored changed lines**, excluding lockfiles, generated barrels, snapshots, baselines (`compliance_baseline.json`), and pure moves (`git diff --stat -M`).
- Over ~400 human LOC or ~20 human-authored files ⇒ review in **per-slice passes** (one per `feat/<slug>` in the range, `git log --first-parent`), each ≤ ~400 LOC, then one integration pass on the merged tip for cross-slice effects (derived artifacts, barrels, parity files).
- A single branch over ~1000 human LOC with no internal seams ⇒ `suggestion (blocking)`: split it (Google's splitting recipes: stacked changes, split by files, horizontal by layer, vertical by feature).
- Say in the output which files were scanned rather than read.

**Anti-patterns.** Approving a 3k-line diff in one pass. Counting lockfile churn as review load (inflates) or skipping a hand-written migration because it "looks generated" (hides).

## 5 · Maintainability lens

**ISO/IEC 25010.** The product-quality model names nine characteristics: functional suitability, performance efficiency, compatibility, interaction capability, reliability, security, maintainability, flexibility, safety (current edition as listed by iso25000.com). **Maintainability** splits into modularity, reusability, analysability, modifiability and testability. Use these words to justify a non-keeper finding: "this lowers *testability* because the 5 helpers are module-level and only patchable" is a reviewable claim; "I don't like it" is not.

**Cognitive complexity (SonarSource, G. Ann Campbell).** Three basic rules: (1) ignore structures that are shorthand for multiple statements; (2) add +1 for each break in linear flow (loops, conditionals, catches, switches, sequences of mixed logical operators, recursion; jumps); (3) add for nesting, because nested breaks are harder to hold in mind. Method calls are free. Use it as a *delta* signal on touched functions, not an absolute gate.
- **House application.** When a touched function's nesting deepens by two or more levels, or its branch count roughly doubles, ask for the refactoring by its Fowler catalog name: *Extract Function*, *Decompose Conditional*, *Replace Nested Conditional with Guard Clauses*, *Replace Conditional with Polymorphism*, *Split Phase*, *Introduce Parameter Object*.
- **Testability bridge.** The house DI seam (`testing.md` Pattern 1, `_PipelineHooks` in therapy `ai_pipeline.py`) is *Introduce Parameter Object* applied to collaborators. A finding that needs self-monkeypatching to test is a testability finding first.

**Checklist**
- [ ] Touched functions: did nesting or branch count jump? Name the refactoring.
- [ ] Is a new abstraction used by ≥2 callers today? If not, speculative generality (`suggestion`).
- [ ] Can the new code be tested without patching our own symbols?

## 6 · Test-strategy assessment

**Pyramid (Cohn, restated by Vocke on martinfowler.com).** Two rules: write tests with different granularity; the more high-level, the fewer tests. Avoid duplication across layers: "if a higher-level test spots an error and there's no lower-level test failing, you need to write a lower-level test"; "push your tests as far down the test pyramid as you can".

**Trophy (Kent C. Dodds).** Static → unit → integration → E2E, with most weight on integration: "The more your tests resemble the way your software is used, the more confidence they can give you."

**Which fits noc.** Both, by side:
- **Backend (FastAPI + Supabase).** Router-level integration tests through the app client (`MockSupabaseClient`, CHECK-constraint validation, schema validation) are the confidence layer and are already universal (`testing.md` §Coverage gaps). Pure domain math (`noctusai_lib.domain.finance.*`) is pushed down to unit + property tests, per the pyramid.
- **Frontend (React + TanStack).** Trophy shape: static (TypeScript, lint) + hook/component integration via vitest + a few Playwright golden paths. Component and page tests are 0 today (`testing.md` frontend table), so the trophy's main layer is the gap.

**Mutation testing.** A mutant is the code with one small fault injected. Stryker's states: killed (a test failed), survived (all tests passed — a test is likely missing), no coverage, timeout (counts as detected); compile/runtime errors are excluded. **Mutation score = detected / valid × 100**, with detected = killed + timeout and valid = detected + survived + no-coverage.
- **Python: mutmut.** `mutmut run "module*"` runs a subset by wildcard; runs are resumable and incremental ("only re-tests mutants in functions whose source changed"); `mutmut browse` shows survivors; config lives under `[tool.mutmut]` in `pyproject.toml` (`source_paths`, `pytest_add_cli_args_test_selection`); `# pragma: no mutate` skips lines. By default only called functions are mutated.
- **TypeScript: Stryker** (`stryker-mutator.io`).
- **House rule.** Mutation runs are heavy: they go through the hardware gate (`python mcp/noctusai/tools/noctus/dev/hw_admission.py run --job pytest:<target> -- …`, `KB § PATTERNS/devops/hardware-admission-budget.md`). The reviewer *recommends* a pilot; an executor runs it. Today: 0/7 mutation or property harnesses (`testing.md` §Coverage gaps, Backend table); the ratchet row `mutation-test-pilot` triggers on "math-heavy services".
- **Without running anything,** the reviewer can still do a *mutation probe by reading*: pick the 2–3 most dangerous one-token mutations (`>=`→`>`, `+`→`-`, delete a `Depends(...)`, drop a `.neq(...)` filter) and find the test assertion that would fail. No assertion ⇒ a surviving-mutant class, named in the finding.

**Property-based tests.** For math services, assert invariants over generated inputs (e.g. "sum of monthly rows == period total"; "basis flips exactly at the boundary"). Python: Hypothesis. Adding a test dependency is a declared-dep decision (`KB § PATTERNS/common/silent-test-failure-from-missing-dep.md`), so it is proposed, not slipped in.

## 7 · Flaky tests

**Principle.** A flaky test passes and fails on the same code. Google (Micco, 2016): about 1.5% of all test runs reported a flaky result, and about 84% of observed pass→fail transitions involved a flaky test. Their mitigations included re-running failing tests and marking tests flaky so they fail only after consecutive failures.

**House rule.** Flaky ≠ green. A test seen to pass and fail on the same commit is:
1. **Quarantined with a named destination** — `NOC-REMEDIATE[flaky]` at the test + a proposal row naming the suspected cause class (order dependence, shared singleton, time, network, the shared-checkout worktree sensitivity).
2. **Bisected for pollution first** — the house playbook for test-isolation pollution lives in `test-harness-playbook.md` §6 (seed-singleton guard §2, shadow purge §2); most noc "flakes" so far were pollution, not randomness.
3. **Never retried into silence.** A CI retry that turns red into green hides the 84%-class signal; the verdict channel must belong to what is judged (§1 verdict-channel integrity).

## 8 · Coverage as a signal

**Principle.** Google's "Code Coverage Best Practices" (Arguelles, Ivanković, Bender, 2020): there is no ideal coverage number; as general guidelines 60% is acceptable, 75% commendable, 90% exemplary; human judgement over the uncovered lines and behaviours matters more than the percentage; a team target is a business decision of the product owners. (Body not rendered at fetch time; these points are confirmed by search excerpts — re-read before quoting verbatim.)

**House application.**
- Look at **changed-line and branch** coverage of the diff, not the repo total.
- Uncovered *error branches* in money, auth and consent code are findings; uncovered logging is not.
- A test that executes a line without asserting its effect adds coverage and zero fault detection; §6's mutation probe is the check.
- Never ask for "coverage to X%" as a block reason. Ask for the specific missing assertion.

## 9 · Review checklist (copyable)

```
Review — <branch or range> — <date>
Floor (house mechanisms)
- [ ] noctus.dev.validate (regression vs baseline): no NEW high/critical
- [ ] seed-compliance · scan_wiring · scan_* sextet (DRY) · eight-way sync
- [ ] verified on a clean origin/dev worktree / merged tip
Size
- [ ] human LOC = __ ; files = __ ; passes = __ (≤ ~400 LOC each) ; scanned-not-read: __
Lenses
- [ ] design (seed seam / organ consumed)   - [ ] functionality (edges, money, dates, races)
- [ ] complexity (nesting/branch delta)     - [ ] tests (fault detection, strict 401, no self-patch)
- [ ] naming   - [ ] comments (why; NOC-REMEDIATE)   - [ ] consistency (existing mechanism)
- [ ] docs (same commit; INDEX; sync)       - [ ] accessibility (UI diffs)   - [ ] context (whole fn, merged tip)
Tests
- [ ] mutation probe by reading: 2–3 mutants → the assertion that kills each
- [ ] flaky seen? → NOC-REMEDIATE[flaky] + destination
Decisions and acceptance (product-engineer slices)
- [ ] noctus.dev.decision_log action=audit: no §7 blocker (engineer-decision-rights.md §7); surprise test re-run on 1 in 5 autonomous rows + every class=other
- [ ] every acceptance criterion has ≥1 test citing its id
Findings (Conventional Comments, file:line)
- praise: …
- issue (blocking): …
Verdict: pass | block   Proposal: <file_proposal id>
```

## 10 · Worked examples

### A · Auth false-green at review time

**Setup.** A diff adds `assert r.status_code in (401, 422)` to a router test in `products/<x>/backend/tests/routers/test_*.py`.

**Floor.** The keeper `check_auth_boundary_false_green` (`mcp/noctusai/tools/noctus/dev/compliance.py:22974`, AST walk over `ast.Compare` + `ast.In`) flags it; the PreToolUse write-time half may already have refused it (`auth-boundary-false-green.md` §Write-time half).

**Craft layer.** The keeper says *that* the shape is wrong; the review says *why* and *what the right test is*. The house's own fixed version is the model: `products/dev-team/backend/tests/integration/test_e2e_flows.py:55-60` posts a **valid** `RunRequest` body (`{"task": "x"}`) so the body parses and the auth dependency fires, then asserts strict `== 401`. The comment there records the trap: an unknown field would 422 on the `StrictHttpModel` before auth.

**Mutation probe by reading.** Mutant: delete `Depends(get_current_user)` (or the product's auth dependency) from the route. With `in (401, 422)` and an invalid body, the request still returns 422 ⇒ the test passes ⇒ **surviving mutant**. With `== 401` and a valid body, the mutant returns 200/201 ⇒ killed.

**Finding.**
```
issue (blocking): <file>:<line> — `in (401, 422)` passes when validation runs before auth;
deleting the auth dependency would survive this test. Send a valid body and assert `== 401`
(model: products/dev-team/backend/tests/integration/test_e2e_flows.py:55-60).
```
Verdict: **block**, file:line cited.

### B · A math service: the Simples base across the 2027 boundary

**Setup.** A change touches `seed/lib/backend/noctusai_lib/domain/finance/simples_base.py` — the month split across the cash→invoice boundary (`INVOICE_BASIS_FROM = date(2027, 1, 1)` at :26; `basis_of` at :40-42; row totals at :113-114).

**What the existing tests already kill (read before asking for more).** `seed/lib/backend/tests/domain/finance/test_dre_api.py:162` checks the four-month split and per-month bases; `:180-185` checks the pure periods and asserts `basis_of("2026-12") == "cash"` and `basis_of("2027-01") == "invoice"`. So the `>=` → `>` mutant at `simples_base.py:42` is **killed** by `:184`. Say so: a reviewer who demands a test that already exists loses credibility.

**What is not pinned.** The invariant "sum of the monthly rows == the period totals" is asserted only for one seeded dataset (`:170-171`). A property test would generate receivables/settlements on both sides of the boundary and assert: (a) `totals.base_cents == Σ months.base_cents`; (b) every month `< 2027-01` is `cash`, every month `≥ 2027-01` is `invoice`; (c) installment interest counts in the base regardless of the DRE line setting (`:189` covers one case).

**Recommendation.**
```
suggestion (non-blocking): simples_base.py — pilot mutation testing here (the `mutation-test-pilot`
trigger "math-heavy services", testing.md §Ratchet plan):
  hw_admission.py run --job pytest:seed-finance -- mutmut run "noctusai_lib.domain.finance.simples_base*"
and add a Hypothesis property test for the Σ-rows == totals invariant (declare the dep first).
```
Not a block: the boundary itself is pinned. Filed as a proposal row with the destination `mutation-test-pilot`.

## 11 · Anti-patterns

- **Keeper output as the review.** Green keepers are the floor; a review that only lists tool results did not happen.
- **Style bikeshedding as blocking.** Style is a linter's job; a `nitpick` never blocks.
- **Approving an unreviewable diff.** Over the §4 window in one pass ⇒ the review is a rubber stamp.
- **Coverage chasing.** Tests that execute without asserting; "raise coverage to 80%" as a block reason.
- **Retry-to-green.** Turning a flaky red into a green with retries; it hides most real failures (§7).
- **Asking for tests that already exist.** Read the suite (Example B) before asking.
- **Unlabelled findings.** The author cannot tell a must-fix from a musing.

## 12 · Sources

| Title | URL | Supports | Accessed |
|---|---|---|---|
| Google eng-practices — The Standard of Code Review | https://google.github.io/eng-practices/review/reviewer/standard.html | §1 senior principle; "Nit:" | 2026-11-05 |
| Google eng-practices — What to look for in a code review | https://google.github.io/eng-practices/review/reviewer/looking-for.html | §2 lenses + summary checklist | 2026-11-05 |
| Google eng-practices — Small CLs | https://google.github.io/eng-practices/review/developer/small-cls.html | §4 100/1000 lines; splitting recipes | 2026-11-05 |
| SmartBear — Best Practices for Peer Code Review | https://smartbear.com/learn/code-review/best-practices-for-peer-code-review/ | §4 200–400 LOC, <500 LOC/h, ≤60 min | 2026-11-05 |
| Conventional Comments | https://conventionalcomments.org/ | §3 labels + decorations | 2026-11-05 |
| ISO/IEC 25010 overview (iso25000.com) | https://iso25000.com/en/iso-25000-standards/iso-25010 | §5 nine characteristics; maintainability sub-characteristics | 2026-11-05 |
| SonarSource — Cognitive Complexity (white paper, G. Ann Campbell) | https://www.sonarsource.com/docs/CognitiveComplexity.pdf | §5 three rules (structure confirmed via search; PDF text not extracted — re-verify exact wording before quoting) | 2026-11-05 |
| Fowler — Refactoring catalog | https://refactoring.com/catalog/ | §5 refactoring names | 2026-11-05 (audit-verified) |
| Ham Vocke — The Practical Test Pyramid | https://martinfowler.com/articles/practical-test-pyramid.html | §6 two rules; push tests down | 2026-11-05 |
| Kent C. Dodds — The Testing Trophy and Testing Classifications | https://kentcdodds.com/blog/the-testing-trophy-and-testing-classifications | §6 trophy layers; "resemble the way your software is used" | 2026-11-05 |
| Stryker — Mutant states and metrics | https://stryker-mutator.io/docs/mutation-testing-elements/mutant-states-and-metrics/ | §6 states + score formula | 2026-11-05 |
| mutmut documentation | https://mutmut.readthedocs.io/en/latest/ | §6 commands, incremental runs, config | 2026-11-05 |
| Google Testing Blog — Flaky Tests at Google and How We Mitigate Them (Micco, 2016-05-27) | https://testing.googleblog.com/2016/05/ | §7 1.5% / 84% (confirmed via search excerpt of the post) | 2026-11-05 |
| Google Testing Blog — Code Coverage Best Practices (2020-08) | https://testing.googleblog.com/2020/08/code-coverage-best-practices.html | §8 60/75/90 guidelines; judgement over % (body not rendered; search-confirmed) | 2026-11-05 |
