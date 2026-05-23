# Boundary-contract tests — exercising the seam, not adjacent to it

> Companion to `KB § PATTERNS/testing.md`. Authored 2026-05-20 after a
> recurrence of "tests green, dashboard red" — every recent dashboard bug
> on social-wiring fit the same shape: unit tests covered the *side* of
> the seam, nothing covered the **contract crossing it**.

---

## 1 · The named class

A **boundary-contract test** exercises the contract that crosses a seam
between two layers — where each layer is independently testable but the
*translation* between them is where bugs live. Unit tests mock the seam
(by design). Integration tests assemble multiple components but often
keep the boundary itself mocked. A boundary-contract test asserts the
artifact, format, or shape that actually traverses the seam.

Bugs caught by this class always have the same retro: "unit tests
passed, FE built clean, BE tests green — and the dashboard still
toasted." The reason is structural — every unit test on either side
agreed with itself; nothing exercised the translation.

---

## 2 · Recurring shapes — seven named boundaries

| # | Boundary | Recent bit | Why unit tests miss it |
|---|---|---|---|
| **B1** | **Build-injection** — env var → vite `define` → bundle literal | `infra.tsx` defaulted to `localhost:8000` (core's port) → every non-core product's bundle baked core's URL. `vite.config.factory.ts` `\|\| 8000` for unmapped ports — same shape. | Unit tests read the seed source via Node, not the built bundle. The `define`-injected literal is invisible until vite builds. |
| **B2** | **HTTP schema** — FastAPI `Query(le=N)` ↔ FE chart fetch param | `top-videos` capped at `le=20` while FE chart labelled "top 50 do cache" → 422 on every dashboard load. | BE tests use `le=20`, FE tests use mocked responses with N items. Nothing asserts the two caps agree. |
| **B3** | **Third-party library contract** — TanStack Query v5 `queryFn` may not return `undefined` | `useLLMSpend` swallowed 404 by `return undefined` → v5 surfaced `data is undefined` as a toast on every dashboard render. | Component tests mock `useQuery({ data, isLoading })`. The real queryFn + real React Query Provider + 404 response is the only path that exercises the v5 contract. |
| **B4** | **Container env propagation** — `.env` ↔ compose `env_file` ↔ stage chain ↔ running container | `ENCRYPTION_KEY` empty in container despite being in `.env` — stage `frontend-build` had it, `runtime-watch` (which `FROM runtime`, not `FROM frontend-build`) didn't. | BE tests inject a Fake CredentialStore. The full env chain only resolves in `docker compose up`. |
| **B5** | **Library-default propagation** — seed fallback literal ↔ N consumer products | `infra.tsx` fallback was a literal that worked for consumer #1, silently misrouted #2..N. | Each consumer's unit tests pass (the consumer either overrides or matches by coincidence). The default itself is unit-tested in isolation — no consumer-sweep test exists. |
| **B6** | **E2E-harness env injection** — `.env` `VITE_SUPABASE_*` ↔ playwright `webServer.env` | core + erp playwright configs didn't inject `VITE_SUPABASE_*` → the seed supabase client threw at module load → React never mounted → 43/44 specs failed "element(s) not found". | A dev's local `.env` feeds the webServer so E2E is green **locally**; CI has no `.env` → the whole suite collapses. The local↔CI parity gap. Unit/component tests mock the supabase client, never boot the real webServer. |
| **B7** | **Fixture ↔ real-schema** — a test fixture asserts a column/shape the production schema lacks | erp-portal `documentos` fixture set `compartilhado_portal: True`, but the column didn't exist → the mock honored the predicate (test green) while the production query had no such filter (LGPD over-exposure). | Both sides agree with the **fixture**: the fixture invents the column, the query is tested against the fixture. Nothing asserts the **real** schema has it. Surfaces on a data-source migration / schema change. |

Each shape has the same anatomy:
1. A contract crosses a process / build / wire / runtime boundary.
2. Each *side* of the contract has tests.
3. **The contract itself has no test.**
4. The bug surfaces only in production-shaped execution.

---

## 3 · Authoring-time discipline

When you write a feature, **identify the boundaries before the code**:

1. **List the seams.** A typical product PR touches: env var → FE bundle
   (B1) · FE → BE HTTP (B2) · BE → library / SDK (B3) · `.env` →
   container (B4) · seed default → product consumer (B5).
2. **For each seam, name the contract.** "FE chart expects N items"
   ↔ "BE endpoint caps at N." "Hook swallows 404 → null." "Build-time
   var injected as same-origin string." "Fernet key must be set or
   adapter raises."
3. **Pick the test layer**: each contract gets a test at the *boundary*,
   not on either side. The detector below catches B3 deterministically;
   the others have either keepers (B1, B5), integration drills (B4), or
   the recurrence-rule trigger waiting for N=2 (B2 — schema↔FE today).

The authoring question to ask: "**If this contract drifts, what
existing test fails?**" If the honest answer is *"none of them"*, the
contract has no boundary-contract test. File one now or accept-with-
rationale-and-destination.

---

## 4 · What ships today

| Boundary | Shipped detector / test | Status |
|---|---|---|
| **B1** Build-injection | `check_seed_canonical_default` (Stage-4 keeper, 2026-05-20) — flags consumer-#1 port literals in seed source. Source-side, not bundle-side. | ✅ Class covered at source; bundle-side assertion is a follow-up. |
| **B2** HTTP schema | None today. **Triggers `[A]` accept-with-rationale** — destination: `<product>-fe-be-schema-contract` follow-up when N=2 (next instance of FE/BE-cap drift fires the recurrence rule). | ⏳ Accepted; destination filed. |
| **B3** Third-party library contract | `check_query_fn_returns_undefined` (Stage-4 keeper, 2026-05-20 — this doc's primary deliverable). | ✅ Class covered. |
| **B4** Container env propagation | **Partial:** `prod_config_parity` (`noctus.dev.predeploy_check`, 2026-05-23) — pre-deploy audit of the prod env snapshot: every product resolves a non-localhost prod URL, no `PRODUCT_URL_*`/`CORS_ORIGINS` loopback value (the deploy-config-contract 3rd leg, `KB § PATTERNS/deploy-config-contract.md § 5b`). Container-freshness still manual (`KB § PATTERNS/containerization.md § 12b`); full `.env`↔compose↔stage-chain smoke is the remaining gap. | ⏳ Env-value subclass detected; full-chain `smoke-fleet-env-propagation` still destination when N=2. |
| **B5** Library-default propagation | `check_seed_canonical_default` (same keeper as B1 — the source-side rule is identical). | ✅ Class covered. |
| **B6** E2E-harness env injection | `check_playwright_supabase_env` (Stage-4 keeper, 2026-05-23) — every `products/*/frontend/playwright.config.ts` whose `webServer` boots the SPA MUST inject `VITE_SUPABASE_*` into `webServer.env`. The E2E-harness sibling of B1's `check_dockerfile_vite_supabase_args`. `error` severity; live baseline 0 (core + erp). | ✅ Class covered. |
| **B7** Fixture ↔ real-schema | None today. **Triggers `[A]` accept-with-rationale** — destination: a `check_fixture_asserts_real_column` migration-aware detector when N=2 (next instance of a fixture asserting an absent schema column fires the recurrence rule). The authoring-discipline rule (§3) holds until then. | ⏳ Accepted; destination filed. |

---

## 5 · Shipped detector — `check_query_fn_returns_undefined`

**Class flagged.** Any TanStack-Query `queryFn` whose function body
returns `undefined` (literal `return undefined;` OR bare `return;`).

**Scope.** Every `.ts` / `.tsx` file under `seed/lib/frontend/`,
`seed/framework/frontend/`, and `products/*/frontend/`. Comments,
strings, and template literals are stripped before the brace walk so
`return undefined` inside a doc comment or a string explaining the bug
does not false-flag (mirrors `check_seed_canonical_default`'s
`_strip_for_scan` reuse).

**Predicate.**
1. Find each `queryFn:` arrow-function-with-body opener
   (`queryFn: (async)? (...) => {` — bare expression bodies like
   `queryFn: () => api.get(...)` are out of scope; they can't `return
   undefined` literally).
2. Walk forward counting braces in the comment/string-stripped text to
   find the matching `}`.
3. Within the body line range, flag any line matching either
   `\breturn\s+undefined\b` or `^\s*return\s*;\s*$`.

**Escape hatch.** `query-fn-undefined-ok` token in a comment on the
same line or any of the 5 preceding lines. Use only when the v5
contract has been read and a defensible reason exists (rare — usually
the right shape is `return null`).

**Severity.** `warning` until baseline confirms 0 — then promote to
`high`. Live baseline at ship time (2026-05-20): 0 across all 297
`queryFn:` sites in seed+products.

**Test.** `mcp/noctusai/tests/test_compliance.py ::
TestCheckQueryFnReturnsUndefined`. Mirrors the
`TestCheckSeedCanonicalDefault` shape — `_mk` helper drops a fake FE
file, asserts flagged / not-flagged per case (literal, bare,
inside-comment, inside-string, arrow-expression, escape hatch).

---

## 6 · Pattern: how to think about adding a future boundary detector

The 5 classes above are **not exhaustive**. New boundaries emerge as
the platform grows. When a new dashboard / wire-level bug surfaces:

1. **Triage the bug** — is it really at a boundary, or at one side of
   it? (Side bugs go to that side's unit tests; boundary bugs land
   here.)
2. **Name the boundary** — extend the table in §2 with the same
   anatomy (boundary / recent bit / why unit tests miss it).
3. **Pick a detection style** — *static* (regex / AST scan, like B1 and
   B3) is cheapest; *contract-extraction* (parse both sides of the
   wire, assert agreement, like proposed B2) is medium; *runtime
   smoke* (boot real containers, exercise endpoint, like proposed B4)
   is most expensive.
4. **Recurrence rule applies**: N=1 → fix in-flight + memory entry;
   N=2 → triage time (file the formalization project or accept-with-
   rationale-and-destination); N=3+ → MUST formalize. The §2 table
   tracks the count.

---

## 7 · Anti-pattern — "more unit tests will fix this"

When a boundary bug ships, the wrong reaction is to add unit tests on
the side that broke. The structural fix is:
- For B1, B3, B5: a static detector (cheapest, runs every commit).
- For B2, B4: contract-extraction or runtime smoke (heavier, accepted
  with destination until N=2).

A unit test that mocks the seam reproduces the original bug class — it
asserts each side agrees with itself, not that the boundary holds. The
keeper detectors are deliberately deterministic predicates over the
codebase: they survive refactors, they don't need a maintainer to keep
remembering "the queryFn rule", they bind the methodology to the tree.

---

## 8 · Doc anchors

- `KB § PATTERNS/testing.md § Coverage gaps + ratchet plan` — boundary-
  contract tests now appear as a named row.
- `KB § PATTERNS/seed-canonical-defaults.md` — the B1+B5 detector lives
  here in full detail.
- `KB § PATTERNS/methodology-codification-pipeline.md` — the s1→s4 path
  every boundary class flows through.
- Memory: `feedback_boundary_contract_tests.md` (this doc's index entry)
  + `feedback_query_fn_never_returns_undefined.md` (the B3 instance).
