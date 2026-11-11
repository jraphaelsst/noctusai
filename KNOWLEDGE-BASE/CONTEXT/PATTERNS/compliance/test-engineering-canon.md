# Test-engineering canon — the test engineer's textbook for this platform

> **What it is.** The profession's testing canon (test pyramid and trophy, test sizes, the
> test-double taxonomy, seams, contract tests, property-based and mutation testing, flaky-test
> management, test data builders, end-to-end practice, coverage, test smells) mapped onto
> NoctusAI's seed test kit, suites and gates, with in-tree file:line examples. Owned by
> `test-engineer` (`.claude/agents/test-engineer.md`).
>
> **Why it exists.** Testing at NoctusAI grew one incident at a time: every rule in
> `KB § PATTERNS/compliance/testing.md` came from a red, and most have a keeper. What had no home
> was the craft under them — how to choose a layer, a double, a size; when a property beats an
> example; how to run a mutation pilot; what to do with a flaky test besides retry it. The
> compliance-reviewer judges tests (`KB § PATTERNS/compliance/code-review-craft.md §6–§8`); this
> doc is the builder's side of the same standard.
>
> **How to use it.** Read §1 before any test slice; open the section your slice touches. The
> HOW-TO of the harness (fixtures, `MockSupabaseClient`, realdb, running suites, gotchas) is
> `KB § PATTERNS/compliance/test-harness-playbook.md`. The POLICY (layers every product must have,
> gates, strict 401, no self-patch) is `testing.md`. **The house mechanism wins over the general
> canon** — when this doc and a house pattern disagree, the house pattern is the contract and this
> doc is the bug (fix it on contact). House patterns are linked, never restated.

## Contents

0 · Standard term ↔ house term · 1 · The decision checklist · 2 · Strategy per layer ·
3 · Test sizes · 4 · Test doubles and seams · 5 · Contract tests · 6 · Property-based testing ·
7 · Mutation testing pilot · 8 · Flaky-test policy · 9 · Test data builders and fixture recurrence ·
10 · Coverage as a signal, and the re-inventory · 11 · E2E with Playwright · 12 · False-green
catalogue · 13 · Test smells with our examples · 14 · Author's test checklist · 15 · Anti-patterns ·
16 · Worked examples · 17 · Sources · Composes with

---

## 0 · Standard term ↔ house term

| Standard (Meszaros · Fowler · Google · Feathers) | House term / mechanism | Where |
|---|---|---|
| Test double — fake (working shortcut implementation) | the **Fake** half of every seed IO module (`Fake<X>` + `Real<X>` + `make_<x>`) | `KB § PATTERNS/backend/seed-fake-real-adapter.md` |
| Fake of a database client (PostgREST) | `MockSupabaseClient` — despite its name, a **validating fake**: it stores rows, applies filters, enforces columns, CHECKs and the 1 000-row cap | `seed/lib/backend/noctusai_lib/testing/mocks.py:1934`, `:114` |
| Spy (records how it was called) | `inserted_payloads` / `updated_payloads` on `MockRequestBuilder` | `mocks.py:1502-1545` |
| Stub (canned answers) | `set_table_data` · `set_sequential_responses` · `set_rpc_data` | `mocks.py:2109-2160` |
| Mock (pre-programmed expectations) | `unittest.mock` / `vi.fn` — **external boundaries only** | `testing.md § No self-monkeypatching — refactor playbook` |
| Seam + enabling point (Feathers) | the **DI seam**: a kwarg defaulting to `None`, resolved at call time; the call site is the enabling point | `KB § PATTERNS/backend/di-test-seam.md` |
| Test fixture / creation method | pytest fixtures + seed fixtures (`reset_rate_limiter`, `seed_singleton_guard`) + product creation methods (`mk_entry`, `_db_with_grants`) | test-harness-playbook §0 |
| Shared fixture leak / interacting tests | **pollution** (polluter → polluted) | playbook §6 |
| Small / medium / large test | hermetic pytest + vitest / PGlite + TestClient + webServer e2e / `realdb` on a live branch | §3 |
| Consumer-driven contract test | **FE↔BE contract-first** skeleton + boundary-contract tests B1–B7 | `KB § PATTERNS/architect/fe-be-contract-first-dispatch.md` · `KB § PATTERNS/backend/boundary-contract-tests.md` |
| Quarantine | `NOC-REMEDIATE[flaky]` in-code marker + a named destination | §8 · `KB § PATTERNS/common/remediation-markers.md` |
| Framework test inherited by every app | `framework_test_suites` (`HealthCheckSuite` … `AuthBoundarySuite`) | playbook §5 |
| Test that pins a past bug | regression test naming the incident | `testing.md § Regression tests in practice` |
| Static check on tests | keepers: `check_no_self_monkeypatch`, `check_auth_boundary_false_green`, `check_test_status_assertion`, `check_mock_schema_validation`, `check_conftest_env_setdefault`, `check_playwright_supabase_env`, `check_migration_number_refs_in_tests` | `mcp/noctusai/tools/noctus/dev/compliance.py` |

---

## 1 · The decision checklist for any test slice

Answer these before the first test is written; each points to its section.

- [ ] **Does every acceptance criterion have at least one test?** Each criterion in the spec
  (`KB § PATTERNS/product/product-management-canon.md` §4) is cited by id in a test name or comment,
  the traceability link (dev_team `qa_engineer.md`:11); the engineer still writes the red-first test.
- [ ] **What could break, and what would it cost?** Money, auth, consent, tenant isolation and data
  written to a third party rank first (Google's "Beyoncé Rule": if you liked it, you should have put a
  test on it — SWE at Google ch. 11).
- [ ] **Which layer owns the behaviour?** Pure rule ⇒ unit; seam (PostgREST, schema, auth dep,
  provider, env) ⇒ integration/contract at that seam; user journey ⇒ one e2e. §2.
- [ ] **What size can prove it?** Prefer the smallest size that can fail for the right reason. §3.
- [ ] **Which double, and is it faithful?** Real > fake > stub/spy > mock; never a double of our own
  code. §4.
- [ ] **Is there a property, not just examples?** Idempotence, round-trip, invariant sums,
  monotonic boundaries ⇒ §6.
- [ ] **Would a one-token mutation survive?** Name the mutant your assertion kills. §7.
- [ ] **Can it go green for the wrong reason?** Status pinned, strict 401, writes asserted, schema
  validated, no permissive disjunction. §12.
- [ ] **Is it deterministic and isolated?** No wall clock, no network, no order dependence, no
  ambient env. §8 · playbook §6, §8.
- [ ] **Does a builder/fixture for this data already exist?** Reuse before you write. §9.
- [ ] **Did I run it red first?** A test never seen failing has not been shown to test anything.

---

## 2 · Test strategy per layer

**Principle.** Two shapes compete. The **pyramid** (Cohn, restated by Vocke on martinfowler.com):
write tests at different granularity, fewer as they get higher, and "push your tests as far down the
test pyramid as you can". The **trophy** (Kent C. Dodds) adds a static base and puts most weight on
integration, because "the more your tests resemble the way your software is used, the more confidence
they can give you". Google's version is *fidelity vs. cost*: unit tests "are limited by the
imagination of the engineer writing them"; larger tests exist "to address fidelity" (SWE at Google
ch. 14).

**How it applies here.** Our production bugs cluster at **seams** — PostgREST row cap, schema drift,
auth deps, env propagation, FE↔BE shapes (`KB § PATTERNS/backend/boundary-contract-tests.md` §2 lists
seven named boundaries). So: a pyramid for domain math and primitives, a trophy for everything that
crosses a seam. The backend craft canon (`KB § PATTERNS/backend/backend-craft-canon.md §8`) and the
frontend craft canon (`KB § PATTERNS/frontend/frontend-craft-canon.md §10`) state the same split
from their side; this table is the whole-platform view.

| Layer | Shape | Confidence layer | Doubles | Run with |
|---|---|---|---|---|
| **Seed lib — domain/primitives** (`seed/lib/backend/noctusai_lib/domain/*`, `primitives/*`) | pyramid | unit + property tests on the rule; one HTTP test per router through a real `FastAPI` app | `MockSupabaseClient(validate_schema=True, schema=...)` (e.g. finance `RpcMockClient`, `seed/lib/backend/tests/domain/finance/conftest.py:74-75`); PGlite for SQL/RPC bodies | `seed/lib/backend` pytest via hardware gate |
| **Seed framework** (`seed/framework/{backend,frontend}`) | unit | factory shape, router registry, `createProductApp` auth branches | none / stubbed design system | playbook §5 Running |
| **Product backend** | trophy at seams | router tests through `TestClient` + validating mock; framework suites inherited; `realdb` for RLS | DI seams, seeded rows, `inserted_payloads`; `patch.object` on external SDKs only | product pytest |
| **Product frontend** | trophy | hook + page integration in vitest (render, assert what the user sees); a few Playwright golden paths | module mocks today, MSW proposed (frontend canon §10) | vitest via `createProductVitestConfig` |
| **MCP toolkit** (`mcp/noctusai/tests/`, ~395 files) | unit + golden fixtures | every keeper has a `Test<Detector>` with a true positive, a false positive and the severity (`testing.md § Regression-test-the-detector`) | tmp_path repos, frozen corpora (playbook §7) | sharded CI job; locally per file |
| **Migrations / SQL** | real engine | PGlite replay, applied twice (pre-commit); RPC/constraint tests on PGlite | none — the point is the real engine | `noctus.dev.migration_replay` · `KB § PATTERNS/backend/migration-chain-replay.md` |
| **LLM features / agents** | evals, not asserts | golden sets, judge calibration, cost caps | recorded/fake drivers (`FakeEvalTurnDriver`) | owned by the `ai-engineer` hire (Wave 2) — skill `noc-new-agent`; this doc only covers the deterministic harness around the evals |

**Checklist.**
- [ ] A rule with branches has a unit test per branch AND an integration test that the route wires it.
- [ ] A seam you touched has a test that would fail if the other side drifted (§5).
- [ ] Do not duplicate one fact at three layers; "if a higher-level test spots an error and there's
  no lower-level test failing, you need to write a lower-level test" (Vocke).

**Anti-patterns.** Unit-testing glue with mocks of our own functions (it tests the mock). An
e2e for every branch (slow, flaky, and the failure points nowhere). "More unit tests will fix this"
for a seam bug (`boundary-contract-tests.md` §7).

---

## 3 · Test sizes — small, medium, large

**Principle.** Google classifies tests by **size** (resources) separately from **scope** (how much
code): "small tests run in a single process, medium tests run on a single machine, and large tests
run wherever they want" (SWE at Google ch. 11). The 2010 "Test Sizes" post gives the constraints:
network — none / localhost only / yes; database — no / yes / yes; time limit — 60 / 300 / 900+ s.
Larger tests are more likely to be flaky — binary size and RAM correlate with flakiness at r² 0.82 and
0.76 (Listfield, 2017).

**How it maps here.**

| Size | Our suites | Constraint we enforce |
|---|---|---|
| **Small** | seed-lib unit tests, keeper tests, hook tests in vitest, pure domain math | no network, no real DB, no wall clock; hermetic env declared by the seed plugin (`pytest_plugin.py:40-70`) |
| **Medium** | router tests through `TestClient` + validating mock; PGlite SQL tests; Playwright with `webServer` on localhost and `page.route` mocks | localhost only; a live Supabase env aborts the session unless the test is `realdb` (`live_db_guard.py:66-89`) |
| **Large** | `realdb` suites on a disposable Supabase branch; post-deploy smokes (`noctus.dev.smoke_fleet`, `spa_smoke`); the owner's manual browser E2E | opt-in only (`NOCTUS_REALDB_TESTS=1`), prod ref refused (`realdb.py:75-108`) |

**Checklist.** Tag tests that must not run by default with a registered marker (`realdb`,
`slow` in `mcp/noctusai/pyproject.toml:64`); with `--strict-markers` an unknown mark is an error
(pytest docs). Keep the small tier fast enough to run before every commit of the slice.

**Anti-pattern.** A "unit" test that opens a socket, reads `.env`, or sleeps — it is a medium test
pretending to be small, and it will flake under load.

---

## 4 · Test doubles and seams

**Principle.** Meszaros' taxonomy (as summarized by Fowler, "Test Double"): a **dummy** fills a
parameter list; a **fake** has a working implementation with a shortcut; a **stub** gives canned
answers; a **spy** is a stub that records how it was called; a **mock** is pre-programmed with
expectations. Mocks verify **behaviour** (which calls were made); stubs and fakes support **state**
verification (Fowler, "Mocks Aren't Stubs"). Google's guidance (SWE at Google ch. 13): "our first
choice for tests is to use the real implementations"; a fake "is often the ideal technique when you
need to use a test double"; "interaction testing should be avoided when possible"; and "a fake must
have its own tests to ensure that it conforms to the API of its corresponding real implementation".
Feathers (Working Effectively with Legacy Code, ch. 4): "a seam is a place where you can alter
behavior in your program without editing in that place", and "every seam has an enabling point".

**How it applies here — the doubles ladder (prefer the highest rung that is fast enough).**

1. **Real implementation** — pure functions, Pydantic models, the seed's own helpers. Never double them.
2. **Real Postgres** — PGlite in-process for DDL, constraints, RPC bodies (playbook §4a); a disposable
   Supabase branch via `realdb` for RLS, grants, auth + RPC together (playbook §4b).
3. **Validating fake** — `MockSupabaseClient` with `validate_schema=True` (default) and the right
   `schema=`; it enforces columns, CHECKs and the row cap, so it is a *faithful* fake in the ways that
   have burnt us. Its known infidelities: `range()` replays the whole table (`mocks.py:1231`), no
   unique/FK/RLS. A test about those properties belongs on rung 2.
4. **Seed Fakes** — `Fake<X>` from each seed IO module (e.g. `FakeStorageBackend`, imported in
   `seed/lib/backend/tests/domain/finance/test_dre_api.py:15`). Google's rule applies: the Fake is
   tested against the same contract as the Real.
5. **Stubs/spies** — seeded rows; read `inserted_payloads` instead of patching a writer.
6. **Mocks** — `patch.object(<external SDK>, ...)` at the consumer-side import binding, only for
   third-party boundaries (LLM, email, payment, HTTP).

**The DI-seam rule (house, gated at both ends).** Never patch our own symbols. Add a seam instead: a
kwarg defaulting to `None` resolved at call time (`_resolve_core_db(core_db)`;
`products/therapy-platform/backend/app/services/ai_pipeline.py:49`) — the call site is Feathers'
enabling point; production never holds the double. The write-time hook `test_seam_guard` denies the
edit; the keeper `check_no_self_monkeypatch` is the backstop → `testing.md § No self-monkeypatching
— refactor playbook` and `§ gated at BOTH ends` · `KB § PATTERNS/backend/di-test-seam.md`.

**Container Postgres** (testcontainers: "throwaway, lightweight instances of databases") is *not*
adopted; it would duplicate PGlite + branches and add Docker to the test path on an 8 GB machine.
Propose it only for a suite that needs a real server (extensions, `LISTEN/NOTIFY`, concurrency) that
PGlite cannot give — PGlite "only has a single exclusive connection to the database" (PGlite docs).

**Checklist.**
- [ ] The double is no more permissive than the real thing (B7 — fixture ↔ real schema).
- [ ] A `validate_schema=False` carries a rationale and a destination (`testing.md § Schema validation`).
- [ ] Interaction assertions (`assert_called_with`) only where the call IS the contract (a message
  sent to a real phone, a payment captured).

**Anti-patterns.** `patch("app.services.x.our_fn")`; a hand-rolled per-product mock of the
Supabase client; asserting call order of our own helpers ("call-routing" tests — the certidões
rewrite replaced them with behavioural assertions, `testing.md § What it bought`).

---

## 5 · Contract tests

**Principle.** A contract test checks that two sides agree on the shape of what crosses between
them — not the business logic behind it: "A contract test does not check for side effects", and
scenarios "should not dig into the business logic of the Provider" (Pact docs, "Contract Tests vs
Functional Tests"). Consumer-driven contracts "let the consumers drive the implementation of a
contract" (Vocke). Pact adds a broker and `can-i-deploy` so a release knows "whether or not the
version you're about to deploy is compatible with the versions of the other apps".

**How it applies here.** We do not run Pact; FE and BE ship in one repo and one image per product,
so the contract is authored once, up front, by the tech-lead (skill `noc-contract-first`,
`KB § PATTERNS/architect/fe-be-contract-first-dispatch.md`): path + method, request fields, response
envelope vs bare + exact field names, status codes, auth posture. The test engineer's job is to make
that skeleton **executable** on both sides:
- **BE side:** a router test per endpoint asserting status + envelope + field names exactly as in the
  skeleton (not "contains") — the 2026-06-01 multi-account feature was 0% functional with both sides
  green because each tested its own imagined shape.
- **FE side:** the hook test's mocked response is copied from the skeleton, and a page test renders
  it; when MSW lands (frontend canon §10), the handler is the skeleton.
- **Boundaries B1–B7** (`KB § PATTERNS/backend/boundary-contract-tests.md` §2): for every seam a slice
  touches, write the line "if this contract drifts, what existing test fails?". No test ⇒ write it or
  record the gap with a destination.
- **Vendor contracts** (Meta, Google, WAHA, payment providers): record a real response once into a
  fixture, version it with the vendor API version, and test our adapter against it; webhook verifiers
  are tested against vendor-documented signatures (`seed/lib/backend/tests/test_webhook_signatures.py`).
  The live-vendor side belongs to `integrations-engineer` (`KB § PATTERNS/integrations/integration-craft-canon.md`).

**Anti-pattern.** Asserting `"providers" in body` (shape-agnostic) — passes on any envelope.

---

## 6 · Property-based testing

**Principle.** Instead of hand-picked examples, state a property — "an assertion of a relationship
between a code's input and output which should hold for all sets of inputs" (fast-check docs) — and
let the library generate inputs and **shrink** a failure to a minimal counterexample. Python:
Hypothesis ("you write tests which should pass for all inputs in whatever range you describe"; default
`deadline` 200 ms, `None` on CI; a failure database replays known counterexamples). TypeScript:
fast-check, with `@fast-check/vitest` for vitest.

**How it applies here.** Zero adopters today (no `hypothesis` or `fast-check` import in `seed/`,
`products/` or `mcp/`, 2026-11-05). Adding either is a dependency decision
(`KB § PATTERNS/common/silent-test-failure-from-missing-dep.md`) — a dedicated, owner-approved slice,
seed-lib first (pilots-first cadence). Candidate properties, highest value first:

| Target | Property |
|---|---|
| `domain/finance/simples_base.py:40-42` `basis_of` | monotone: `basis_of(m) == "invoice"` if and only if `m >= "2027-01"` for every month string |
| `simples_base` totals | `sum(month.base_cents) == totals.base_cents`; split period == concatenation of its sub-periods |
| money helpers (`to_cents` / `cents_to_decimal`) | round-trip `to_cents(cents_to_decimal(c)) == c` |
| phone / CPF / CNPJ normalizers | idempotent `normalize(normalize(x)) == normalize(x)`; valid check digits preserved |
| data-in-the-wrong-field relocation | never overwrites a filled field (`KB § PATTERNS/backend/data-in-the-wrong-field.md`) |
| `formatCurrency` (FE, `seed/lib/frontend/src/utils.ts:26-32`) | never renders `null` as a number — currently violated (PROJECT §6 defect 4); a property test would pin the fix |

**Checklist.** Bound the strategy to the domain (valid months, cents as ints, not floats); register a
`ci` settings profile; keep a found counterexample as an explicit `@example` regression.

**Anti-pattern.** A property that re-implements the function under test (it agrees with itself).

---

## 7 · Mutation testing pilot

**Principle.** Mutation testing "introduces changes to your code, then runs your unit tests against
the changed code" (Stryker). A mutant is **killed** when a test fails, **survives** when all pass, has
**no coverage** when no test runs it; score = detected / valid × 100. Google runs it diff-based and
probabilistic inside code review, reaching thousands of engineers (Petrović & Ivanković, ICSE-SEIP
2018) — the useful output is the *surviving mutant shown on the changed line*, not a repo-wide score.
Tools: **mutmut** (Python; resumable — "you can stop the mutation run at any time and mutmut will
restart where you left off"; `mutmut browse` to inspect and re-run survivors; config in
`[tool.mutmut]` of `pyproject.toml`) and **Stryker** (JS/TS; vitest runner; `thresholds` high/low/break
default 80/60/null — "set break to null (default) to never let your build fail"; `--incremental`).

**The pilot (proposed, not running — owner decision needed for the dependency).**
- **Owner:** `test-engineer` runs it; `compliance-reviewer` consumes survivors at review; the
  tech-lead approves adding `mutmut` (dev-only) to `seed/lib/backend`.
- **Targets (small, high-stakes, already well-tested — the pilot measures the tests, not the code):**
  1. `seed/lib/backend/noctusai_lib/domain/finance/simples_base.py` (156 lines) — tests
     `seed/lib/backend/tests/domain/finance/test_dre_api.py:162-200`. Expected mutant classes: `>=` →
     `>` at the 2027 boundary (`simples_base.py:42`, killed by `:186`), dropping the
     `CANCELLED` exclusion (`:47` — no cancelled receivable appears anywhere in `test_dre_api.py`, so this is a predicted survivor), the interest-suffix branch (`:49-50`, killed by `:189-193`).
  2. Auth deps — `seed/lib/backend/noctusai_lib/api/auth/__init__.py`: `is_authoritative_token_rejection`
     (`:161`), `make_require_role` (`:447`), `make_get_current_user_org` (`:735`); tests
     `seed/lib/backend/tests/test_auth.py` (89 tests). Any survivor here is a security finding.
  3. (FE, after 1–2) Stryker on `seed/lib/frontend/src/utils.ts` formatters.
- **Run:** through the hardware gate only —
  `python mcp/noctusai/tools/noctus/dev/hw_admission.py run --job mutmut:simples_base -- mutmut run "<module glob>"`
  from `seed/lib/backend`; never in a pre-commit hook; never fleet-wide.
- **Done =** every survivor is either killed by a new test or recorded as an **equivalent mutant**
  with a one-line reason; the report (mutants, killed, survived, runtime) goes in the delivery note.
  No score threshold gates anything during the pilot (Stryker's own default `break: null`).
- **Adopt if** the pilot finds ≥1 real missing assertion in code we believed covered; then the
  `mutation-test-pilot` ratchet row in `testing.md § Ratchet plan` closes and a diff-scoped run
  becomes a review aid. **Drop if** it finds only equivalent mutants at a cost > 30 min per module.

**Without running anything** — the mutation probe by reading (`code-review-craft.md §6`): name the
2–3 most dangerous one-token mutants and point at the assertion that kills each. Do this for every
money/auth/consent test you write.

---

## 8 · Flaky-test policy

**Principle.** A flaky test "exhibits intermittent or sporadic failure" (pytest docs). At Google,
about 1.5% of all test runs reported a flaky result, almost 16% of tests had some flakiness, and about
84% of pass→fail transitions involved a flaky test (Micco, 2016); SWE at Google ch. 11 notes tests
"begin to lose value" as flakiness approaches 1%. Fowler: non-deterministic tests "are useless as
regression tests"; quarantine them, "but fix quarantined tests quickly", with a limit (his examples:
8 tests, or no longer than a week). pytest warns that `xfail` as quarantine is "rather dangerous to use
permanently". Playwright calls a test that failed then passed on retry `flaky` — a label, not a pass.

**House policy — detect → classify → quarantine with expiry → fix → never retry-to-green silently.**
1. **Detect.** Pass and fail on the same commit = flaky. Local runs are randomized (`pytest-randomly`
   in the venv); CI product jobs are not (playbook §1 added notes) — so a local-only red is evidence,
   not noise.
2. **Classify before you call it flaky.** Most of ours were **pollution** (module-level dicts mutated
   by the mock, process-global gates, `sys.path` borrowed from a sibling file, import-time logging)
   → bisect with a pinned seed (playbook §6). Rule out chance (the 3-char Fernet needle,
   `testing.md`→playbook §6). Then time, network, ordering of async work, env (`own_test_env`).
3. **Quarantine with a ticket and an expiry.** Mark the test `NOC-REMEDIATE[flaky]: <cause class> —
   <YYYY-MM-DD>` at the test (the marker IS the named destination,
   `KB § PATTERNS/common/remediation-markers.md`), skip it with a `reason=` naming the marker, and give
   it a deadline of **14 days** or the next touch of that file, whichever is first. Never `xfail(strict=False)`.
4. **Fix at the source** — the polluter, the global, the clock — never a `setup_method` on the victim.
   A new process-global seam gets its reset in the seed pytest plugin, not per file.
5. **Never retry-to-green silently.** A retry may *diagnose*; it may not *decide*. Resolved 2026-11-05:
   the three Playwright configs (`products/{core,erp-imobiliario,social-wiring}/frontend/playwright.config.ts:7-11`)
   keep `retries: process.env.CI ? 2 : 0` (trace capture via `trace: 'on-first-retry'`) and now set
   `failOnFlakyTests: !!process.env.CI` (config option, Playwright 1.63 `test.d.ts:1274`): a spec that fails then
   passes fails the job. Trade-off vs `retries: 0`: keeps the trace of the first failure and does not hide
   which spec flaked, at the cost of up to 2 wasted reruns per real red. Quarantine = `test.fixme()` +
   `NOC-REMEDIATE[flaky]` at the spec, 14-day expiry (pending owner confirmation). `agents` has no Playwright config.

**Anti-pattern.** Rerun-until-green; `sleep` added to make it pass; deleting the test.

---

## 9 · Test data builders and fixture recurrence

**Principle.** Meszaros' **Creation Method**: "set up the test fixture by calling methods that hide
the mechanics of building ready-to-use objects behind Intent Revealing Names". A *test data builder*
(Freeman & Pryce, Growing Object-Oriented Software, Guided by Tests — cited by title) adds defaults +
overrides so each test states only what matters. Google prefers DAMP ("Descriptive And Meaningful
Phrases") over DRY inside a test body — repetition in a test is acceptable when it keeps the test
readable (SWE at Google ch. 12) — while helpers that hide *mechanics* are welcome.

**How it applies here.**
- Existing creation methods to reuse: finance `mk_entry`, `mk_account` (`seed/lib/backend/tests/domain/finance/conftest.py`),
  therapy `_db_with_grants` (playbook §5), the seed identity constants `TEST_USER_ID` / `TEST_ORG_ID`
  (playbook §2), `bind_user_metadata`.
- **Defaults come from the real schema**, never invented (B7); owner ids from the constants, never a
  literal (the `"test-user-id"` vs `"test-user-123"` typo).
- **Return fresh objects.** A module-level `SAMPLE_X = {...}` shared across tests is the dominant
  pollution shape (playbook §6); a builder function returning a new dict per call removes it by
  construction.
- **Recurrence rule applies to fixtures.** Run `noctus.dev.scan_test_fixture_recurrence` before adding
  a fixture: N=2 ⇒ triage, N≥3 ⇒ lift to `noctusai_lib.testing` (precedents: `reset_rate_limiter` N=5,
  `seed_singleton_guard` N=3, `bind_user_metadata` N=15+, `get_realdb_credentials` N=3). Content-diff
  before calling two fixtures duplicates (the N=4 byte-identical lesson, playbook §5).

**Anti-patterns.** A 40-line inline dict per test (Obscure Test); a builder that silently fills a
field the test is about (Mystery Guest); a shared mutable default.

---

## 10 · Coverage as a signal, and the re-inventory

**Principle.** "Test coverage is a useful tool for finding untested parts of a codebase"; it "is of
little use as a numeric statement of how good your tests are"; "if you make a certain level of coverage
a target, people will try to attain it" (Fowler). Google: no ideal number — 60% "acceptable", 75%
"commendable", 90% "exemplary"; per-commit goals of 99% reasonable with 90% a good lower threshold;
"what's not covered is more meaningful than what is covered" (Arguelles, Ivanković, Bender 2020).
Kent C. Dodds: returns diminish "as the coverage increases much beyond 70%".

**How it applies here.** No coverage tool is configured anywhere (no `pytest-cov`, no
`@vitest/coverage-*` in any `package.json`, no coverage step in `.github/workflows/test.yml`). The
**ratchet** we do have is structural: five layers per product (`testing.md` table), keeper ratchets
(self-patch severity per product, migration-number refs baseline), and "every test file is gated"
(`check_every_test_file_is_gated`, `check_ci_test_matrix_coverage`). A coverage ratchet, when added,
should be **changed-lines** coverage of a diff (vitest `thresholds` with `autoUpdate` moves the floor up
only — vitest docs), never a repo-wide target, and never a block reason by itself
(`code-review-craft.md §8`).

**Re-inventory (2026-11-05, file counts — not coverage).** Counts: backend `test_*.py` under
`backend/tests`, frontend `*.test.ts(x)` under `frontend/src`, Playwright `*.spec.ts`, `tests/realdb/`.
Awake products per `deploy/fleet/active-scope.txt` (agents, core, nosnolimiar, seed, social-wiring); the rest
are asleep — no gate checks them.

| Product | Awake | BE test files | FE test files | E2E specs | realdb |
|---|---|---:|---:|---:|---|
| agents | ✅ | 169 | 53 | 0 | — |
| core | ✅ | 108 | 40 | 7 | ✅ |
| nosnolimiar | ✅ | 8 | 2 | 0 | — |
| seed (product) | ✅ | 9 | 2 | 0 | — |
| social-wiring | ✅ | 662 | 329 | 5 | ✅ |
| erp-imobiliario | asleep | 136 | 27 | 9 | ✅ |
| therapy-platform | asleep | 85 | 5 | 0 | ✅ |
| community | asleep | 58 | 27 | 0 | — |
| orbity | asleep | 53 | 29 | 0 | ✅ |
| personal-finance | asleep | 48 | 19 | 0 | ✅ |
| igig | asleep | 44 | 47 | 0 | — |
| adconnect | asleep | 26 | 1 | 0 | ✅ |
| academia-de-reciclagem | asleep | 25 | 18 | 0 | — |
| p-studio | asleep | 20 | 5 | 0 | — |
| daily-life | asleep | 19 | 3 | 0 | — |
| knowledge-extractor | asleep | 17 | 0 | 0 | — |
| store | asleep | 13 | 5 | 0 | — |
| commerce | asleep | 8 | 8 | 0 | — |
| dev-team | asleep | 3 | 1 | 0 | — |

Fleet-wide: property-based 0, mutation 0, coverage tooling 0, Playwright configs 3 (core, erp,
social-wiring). **Highest-leverage gaps among awake products:** nosnolimiar and the seed product have thin
FE suites and no e2e; agents has no golden-path e2e; property tests for seed-lib money/date rules (§6).

---

## 11 · E2E with Playwright

**Principle (Playwright docs).** "Each test should be completely isolated from another test and should
run independently"; prefer "user-facing attributes and explicit contracts" — "we recommend prioritizing
role locators"; use web-first assertions, which wait "until the expected condition is met" (a manual
assertion "won't wait a single second"). Testing Library's priority is the same: `getByRole` is "your
top preference for just about everything"; `getByTestId` only when role or text cannot work.

**How it applies here.**
- **Harness:** `webServer` boots vite dev with the boot-critical `VITE_SUPABASE_*` placeholders
  (keeper `check_playwright_supabase_env`); the backend is mocked with `page.route` fixtures
  (`products/core/frontend/e2e/fixtures/`); chromium only; `workers: 1` and `retries: 2` in CI
  (`playwright.config.ts:7-11` — see §8 on retries).
- **Locators:** role + accessible name first (`getByRole('button', { name: 'Sair' })`,
  `products/core/frontend/e2e/tests/auth.spec.ts:124`). Core/erp specs lean on Portuguese copy
  (`getByText('Não tem conta? Criar agora')`, `auth.spec.ts:27`) — copy-fragile (`testing.md § Rules`,
  selector stability); social-wiring is testid-first. New specs: role first, testid when the role is
  ambiguous, raw text last. A spec that cannot find an element by role is often an accessibility bug.
- **No fixed sleeps.** Zero `waitForTimeout` in the three e2e trees today (2026-11-05) — keep it so.
  Wait on a web-first assertion or a response (`page.waitForResponse`).
- **Isolated data.** Each spec builds its own mocked state; nothing depends on an earlier spec.
  Live-backend e2e (the social-wiring contract run) uses its own fixtures pack and never hand-fills
  extractor output.
- **Harness validity first.** Before believing a red: browsers installed for the installed
  `@playwright/test`, tree current, server up, output untruncated; to compare versions the harness must
  have reproduced the failure at least once — reproduce in the CI image when local cannot
  (`KB § PATTERNS/common/methodology-execution-discipline.md` §10a).
- **The manual browser pass is a gate,** not a nicety: on 2026-07-22 it caught four defects that 1 227
  backend + 345 frontend green tests missed, each hidden by a double (row cap, `isLoading`, image deps).

---

## 12 · False-green catalogue

A false-green is a test that passes while the behaviour it names is broken. Each has a house fix and,
where possible, a static detector — a test runner cannot catch a green.

| Shape | Why it lies | Fix | Gate |
|---|---|---|---|
| `status_code in (401, 404\|422)` | the 404/422 branch passes with auth never run | strict `== 401` against a served path | `check_auth_boundary_false_green` · `KB § PATTERNS/compliance/auth-boundary-false-green.md` |
| body asserted, status not | 422-for-the-wrong-reason matches the substring | pin the status in the same test | `check_test_status_assertion` (`testing.md`) |
| `patch(our_fn)` | the guard under test is replaced | DI seam / seeded rows / external-only patch | `test_seam_guard` + `check_no_self_monkeypatch` |
| `validate_schema=False` | missing column/table invisible | validating mock, rationale + destination on opt-out | `check_mock_schema_validation` |
| fixture invents a column (B7) | mock honours the fixture, prod has no filter | defaults from migrations | discipline (detector at N=2) |
| unpaged select vs mock | `range()` replays the whole table | test the pager on rung 2, or assert page calls | `KB § PATTERNS/backend/postgrest-row-cap.md` |
| 200 with no writes | status pinned, side effect absent | assert the writes (`inserted_payloads`) | `KB § PATTERNS/backend/invitation-acceptance.md` |
| aggregate `failed == 0` | setup ERRORS uncounted | read `errors` + per-product `success` | playbook §1 |
| skipped real-DB tests | a skip reads as a pass | count skips; skip reason names the missing harness | playbook §4a |
| `setdefault` env | ambient `.env` wins; may reach prod | `own_test_env` | `check_conftest_env_setdefault` |
| retries turn red green | flaky becomes pass | §8 step 5 | closed by `failOnFlakyTests` (CI) |
| "absent from ciphertext" with a short needle | chance | long distinctive needle | discipline |
| a poll helper that returns on timeout | the test asserts on a stale state | fail loudly on deadline | §13 |

---

## 13 · Test smells with our examples

Meszaros' catalogue (xunitpatterns.com, "Test Smells"), each with a real instance and the fix.

| Smell (Meszaros) | Definition | Our instance | Fix |
|---|---|---|---|
| **Erratic Test** | "sometimes they pass and sometimes they fail" | auth tests failing at random after a latency test left an enforcing license gate (2026-10-22) | autouse snapshot/restore in the seed plugin (`pytest_plugin.py:121-136`) |
| **Interacting Tests** (cause of Erratic) | "Tests depend on each other in some way" | module-level `SAMPLE_X` mutated in place by the mock's write propagation (therapy 4F) | deep-copy at `MockRequestBuilder.__init__`; builders return fresh dicts (§9) |
| **Fragile Test** | fails when the SUT changes in ways that do not affect the part tested | Portuguese copy selectors in core e2e (`auth.spec.ts:27,35,58`) | role + name locators; testids on shared design-system parts |
| **Obscure Test / Mystery Guest** | cause and effect not visible in the test | rows from a module constant defined 300 lines up; hand-typed `"test-user-123"` | creation method with named overrides; identity constants |
| **Assertion Roulette** | hard to tell which assertion failed | compound `assert a == x and b is True` (`test_dre_api.py:165`) — pytest's assertion rewriting names the failing operand, so this is mild here; one fact per `assert` still reads better | split when a line holds unrelated facts |
| **Eager Test** (cause of Roulette) | "A single test verifies too much functionality" | `test_simples_base_switches_basis_at_2027_and_splits_a_period_crossing_it` (`test_dre_api.py:162-176`) checks basis, five totals and warnings | acceptable as a named scenario test *because* the edge cases also have focused tests (`:180-193`); otherwise split |
| **Conditional Test Logic** | "A test contains code that may or may not be executed" | `_poll` returns the body when its deadline passes instead of failing (`products/agents/backend/tests/studio/def/test_mecanismo_runs_endpoint.py:29-36`) | raise on deadline; reuse the conftest's `wait_until` (`products/agents/backend/tests/routers/conftest.py:230-246`) — also a duplicate helper (N=2) |
| **Slow Tests** | "The tests take too long to run" | `test_compliance.py` alone clocked 8+ minutes (`.github/workflows/test.yml:1575`) — got its own CI shard | the `--check-<keeper>` fast paths (~4 s) for the loop; keep slow corpora behind `-m slow` |
| **Test Logic in Production** | production code containing test-only logic | avoided by construction: DI kwargs default to the real dependency (`ai_pipeline.py:49`) instead of `if TESTING:` branches | keep seams as parameters, not flags |
| **Hard-coded test data / time** | literal dates rot | `date.today()` based fixtures (`testing.md § Rules`) | relative dates or an injected clock |

---

## 14 · Author's test checklist (before returning)

The reviewer's copy is `code-review-craft.md §9`; this is the builder's.

```
Tests — <slice> — <date>
- [ ] Each new test was seen RED first (against the bug or a reverted fix)
- [ ] Layer + size chosen on purpose (§2, §3); doubles from the highest rung affordable (§4)
- [ ] Status pinned; auth == 401; writes asserted; schema-validating mock with the right schema=
- [ ] No patch/monkeypatch of our own symbols; no setdefault env; no wall clock; no sleep
- [ ] Property or mutation probe named for money/auth/consent logic (§6, §7)
- [ ] Builders/fixtures reused; scan_test_fixture_recurrence run if a new fixture was added (§9)
- [ ] Regression tests name the incident + date (testing.md)
- [ ] Contract line written for every seam touched (§5)
- [ ] FULL suite of each touched product/package, through the hardware gate; errors + skips read
- [ ] Docs follow code (this canon / playbook / testing.md) in the same commit
```

---

## 15 · Anti-patterns

- Testing the mock: assertions that only restate what a double was told to return.
- Retry-to-green, `sleep`-to-green, `xfail`-to-green, delete-to-green.
- A coverage percentage as the goal (§10).
- One e2e per branch; zero e2e for the golden path.
- A per-product copy of a seed fixture or mock (the recurrence rule).
- Believing a red, or an A≡B, from a harness that could not exhibit the phenomenon (§11).
- Running a full suite or a mutation run outside the hardware gate.

---

## 16 · Worked examples

### A · A mutation probe on the Simples 2027 boundary (pilot target 1)

`basis_of` (`seed/lib/backend/noctusai_lib/domain/finance/simples_base.py:40-42`) returns
`"invoice" if date.fromisoformat(month + "-01") >= INVOICE_BASIS_FROM else "cash"`. Probe by reading:
- Mutant `>=` → `>`: `basis_of("2027-01")` becomes `"cash"`. Killed by
  `test_dre_api.py:186` (`basis_of("2027-01") == "invoice"`) and by `:184`.
- Mutant `INVOICE_BASIS_FROM = date(2027, 1, 1)` → `date(2027, 1, 2)`: same month string still maps to
  `-01` < `-02` ⇒ `"cash"` — killed by the same assertion.
- Mutant in `_counts_as_gross` (`:47`): drop `or entry["status"] == EntryStatus.CANCELLED.value`.
  `grep -n cancel test_dre_api.py` finds nothing — no test seeds a cancelled receivable — so this mutant
  is predicted to **survive**: the pilot's first expected finding, killed by a one-line addition to
  `seed_boundary` plus one assertion that the cancelled amount is not in `sales_cents`.
A property (§6) closes the class for good: for every month string, `basis_of(m) == "invoice"` if and only if
`m >= "2027-01"`. Review-side reading of the same module: `code-review-craft.md §10 B`.

### B · Flaky ≠ random: the license-gate pollution

Symptom (2026-10-22): org-auth tests failed differently on each run. A "thread race" was "proved" by
making `run_parallel` sequential — wrong, because the random order also changed between runs. Cause:
`test_shell_endpoint_latency.py` installed an enforcing process-global license gate and never reset it.
Fix at the source, once for every product: the autouse `_isolate_license_gate` fixture in the seed
plugin snapshots and restores the gate (`seed/lib/backend/noctusai_lib/testing/pytest_plugin.py:121-136`;
regression test `seed/lib/backend/tests/testing/test_license_gate_isolation.py`). Lessons that generalize:
pin the seed before any A/B (`--randomly-seed=<from the log>`); a new process-global seam gets its reset
in the plugin; quarantine would have been wrong here — the cause was findable in one bisect (§8 step 2).

### C · Choosing the rung: finance SQL on PGlite, not on the mock

The finance organ generates its own DDL (unique indexes, CHECKs, FKs, an RPC). The validating mock
covers columns and CHECKs but "cannot enforce unique indexes, CHECKs or FKs, and a parser cannot prove
DDL RUNS" (module docstring, `seed/lib/backend/tests/domain/finance/test_sql_on_real_postgres.py:1-6`).
So the router/report tests stay on rung 3 (`RpcMockClient(validate_schema=True, schema=SCHEMA)`,
`seed/lib/backend/tests/domain/finance/conftest.py:74-75`) and the DB-side rules go to rung 2: the
generator's DDL applied **twice** on PGlite, then each rule exercised in a `DO $$` block. The suite
skips visibly when `node` or the harness is absent (`:25-28`) — and a skip is read as "not tested",
never as a pass. Not chosen: a live `realdb` branch (needs credentials and network; RLS is not what
these tests are about) and testcontainers (a Docker dependency for no extra fidelity here).

---

## 17 · Sources

All accessed 2026-11-05. "Fetched" = page retrieved and the cited text checked against it.

| Source | URL | Supports | Status |
|---|---|---|---|
| Ham Vocke, "The Practical Test Pyramid" (martinfowler.com) | https://martinfowler.com/articles/practical-test-pyramid.html | pyramid layers, push tests down, CDC tests, test doubles | fetched |
| Martin Fowler, "Test Double" | https://martinfowler.com/bliki/TestDouble.html | dummy/fake/stub/spy/mock definitions | fetched |
| Martin Fowler, "Mocks Aren't Stubs" | https://martinfowler.com/articles/mocksArentStubs.html | state vs behaviour verification | fetched |
| Kent C. Dodds, "The Testing Trophy and Testing Classifications" | https://kentcdodds.com/blog/the-testing-trophy-and-testing-classifications | trophy, static layer, "resemble the way your software is used" | fetched |
| Kent C. Dodds, "Write tests. Not too many. Mostly integration." | https://kentcdodds.com/blog/write-tests | integration balance; diminishing returns past ~70% coverage | fetched |
| Software Engineering at Google, ch. 11 "Testing Overview" | https://abseil.io/resources/swe-book/html/ch11.html | sizes vs scope, Beyoncé Rule, flakiness ~1% loses value | fetched |
| — ch. 12 "Unit Testing" | https://abseil.io/resources/swe-book/html/ch12.html | unchanging tests, public APIs, behaviours, DAMP | fetched (some wording paraphrased) |
| — ch. 13 "Test Doubles" | https://abseil.io/resources/swe-book/html/ch13.html | prefer real; fakes; avoid interaction testing; fakes need tests | fetched |
| — ch. 14 "Larger Testing" | https://abseil.io/resources/swe-book/html/ch14.html | fidelity; unit tests limited by imagination | fetched |
| Simon Stewart, "Test Sizes" (Google Testing Blog, 2010) | https://testing.googleblog.com/2010/12/test-sizes.html | network/DB/time limits per size | fetched (raw HTML) |
| John Micco, "Flaky Tests at Google and How We Mitigate Them" (2016) | https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html | 1.5% of runs, 16% of tests, 84% of pass→fail | fetched (raw HTML) |
| Jeff Listfield, "Where do our flaky tests come from?" (2017) | https://testing.googleblog.com/2017/04/where-do-our-flaky-tests-come-from.html | size correlates with flakiness (r² 0.82 / 0.76) | fetched (raw HTML) |
| Gerard Meszaros, xUnit Test Patterns — Test Smells | http://xunitpatterns.com/Test%20Smells.html | smell definitions (§13) | fetched (http) |
| — Creation Method | http://xunitpatterns.com/Creation%20Method.html | creation method definition | fetched (http) |
| Freeman & Pryce, *Growing Object-Oriented Software, Guided by Tests* | — | test data builder (term only) | **cited by title; no page fetched** |
| Martin Fowler, "Eradicating Non-Determinism in Tests" | https://martinfowler.com/articles/nonDeterminism.html | quarantine, fix quickly, limits | fetched |
| Martin Fowler, "Test Coverage" | https://martinfowler.com/bliki/TestCoverage.html | coverage finds untested code; poor as a target | fetched |
| Arguelles, Ivanković, Bender, "Code Coverage Best Practices" (2020) | https://testing.googleblog.com/2020/08/code-coverage-best-practices.html | 60/75/90; per-commit 99/90; what's not covered | fetched (raw HTML) |
| Petrović & Ivanković, "State of Mutation Testing at Google" (ICSE-SEIP 2018) | https://research.google/pubs/state-of-mutation-testing-at-google/ | diff-based probabilistic mutation in code review | abstract fetched; full paper not read |
| Hypothesis documentation | https://hypothesis.readthedocs.io/en/latest/ · https://hypothesis.readthedocs.io/en/latest/reference/api.html | property-based testing in Python; deadline 200 ms / None on CI; database; shrinking | fetched (profiles wording paraphrased) |
| fast-check documentation | https://fast-check.dev/ · https://fast-check.dev/docs/introduction/what-is-property-based-testing/ · https://fast-check.dev/docs/ecosystem/ | property definition, shrinking, `@fast-check/vitest` | fetched |
| mutmut documentation | https://mutmut.readthedocs.io/en/latest/ | resumable runs, `[tool.mutmut]`, `mutmut browse` | fetched |
| Stryker Mutator — intro, mutant states, configuration | https://stryker-mutator.io/docs/ · https://stryker-mutator.io/docs/mutation-testing-elements/mutant-states-and-metrics/ · https://stryker-mutator.io/docs/stryker-js/configuration/ | states, score, thresholds 80/60/null, incremental | fetched (vitest-runner page not fetched) |
| Playwright — Best Practices, Locators, Retries | https://playwright.dev/docs/best-practices · https://playwright.dev/docs/locators · https://playwright.dev/docs/test-retries | isolation, role locators, web-first assertions, `flaky` label | fetched |
| Playwright — Command line (`--fail-on-flaky-tests`: "Fail if any test is flagged as flaky (default: false)") | https://playwright.dev/docs/test-cli | the CI flag for §8 step 5 | fetched |
| Testing Library — Guiding Principles; About Queries (priority) | https://testing-library.com/docs/guiding-principles · https://testing-library.com/docs/queries/about/#priority | query priority, user-centric tests | fetched |
| Pact — Introduction; Contract vs Functional tests; Can I Deploy | https://docs.pact.io/ · https://docs.pact.io/consumer/contract_tests_not_functional_tests · https://docs.pact.io/pact_broker/can_i_deploy | contract test scope, broker gating | fetched |
| Testcontainers; testcontainers-python Postgres module | https://testcontainers.com/ · https://testcontainers-python.readthedocs.io/en/latest/modules/postgres/README.html | throwaway real dependencies | fetched |
| pytest — fixtures, marks, flaky tests; pytest-xdist | https://docs.pytest.org/en/stable/explanation/fixtures.html · https://docs.pytest.org/en/stable/how-to/mark.html · https://docs.pytest.org/en/stable/explanation/flaky.html · https://pytest-xdist.readthedocs.io/en/stable/ | fixtures, strict markers, flaky causes, xfail-as-quarantine warning, `-n auto` | fetched |
| Michael Feathers, *Working Effectively with Legacy Code* (2004), ch. 4 "The Seam Model" (InformIT excerpt) | https://www.informit.com/articles/article.aspx?p=359417&seqNum=2 · https://www.informit.com/articles/article.aspx?p=359417&seqNum=3 | seam and enabling point definitions | fetched |
| PGlite | https://pglite.dev/ · https://pglite.dev/docs/ | Postgres in WASM; single exclusive connection | fetched ("single exclusive connection" is a fragment) |
| Vitest — Coverage guide and config | https://vitest.dev/guide/coverage · https://vitest.dev/config/coverage | v8 default, thresholds, autoUpdate | fetched |

House evidence is cited inline by file:line; every path was opened on 2026-11-05 on branch
`feat/agref-w2-test-engineer`.

---

## Composes with

`KB § PATTERNS/compliance/testing.md` (policy, compliance-owned) ·
`KB § PATTERNS/compliance/test-harness-playbook.md` (how-to, test-engineer) ·
`KB § PATTERNS/compliance/code-review-craft.md` (review judgement) ·
`KB § PATTERNS/compliance/auth-boundary-false-green.md` ·
`KB § PATTERNS/backend/di-test-seam.md` · `KB § PATTERNS/backend/boundary-contract-tests.md` ·
`KB § PATTERNS/backend/backend-craft-canon.md` §8 · `KB § PATTERNS/frontend/frontend-craft-canon.md` §10 ·
`KB § PATTERNS/backend/migration-chain-replay.md` · `KB § PATTERNS/devops/hardware-admission-budget.md` ·
`KB § PATTERNS/common/remediation-markers.md` · `KB § PATTERNS/common/methodology-execution-discipline.md`.
