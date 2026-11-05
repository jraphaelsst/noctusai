# Testing Standards

> **Policy here, harness there (split 2026-11-05).** This doc is the testing POLICY (compliance-reviewer):
> the layers, the rules, the gates and their contracts. The HOW-TO — running suites, the seed test kit,
> mock schema/CHECK mechanics, real-DB tiers, conftest patterns, framework suites, the vitest factory,
> pollution bisecting — moved losslessly to `KB § PATTERNS/compliance/test-harness-playbook.md` (test-engineer). The craft (strategy per layer,
> doubles, property/mutation, flaky policy, smells) is `KB § PATTERNS/compliance/test-engineering-canon.md`.

Every product must have all five test layers. No product ships without them.

| Layer | What it tests | Where | When to write |
|-------|---------------|-------|---------------|
| **Unit (routers)** | Individual endpoints — CRUD, auth, validation, error handling | `tests/routers/test_*.py` | One per domain router |
| **Unit (services)** | Business logic in isolation — calculations, transformations, state machines | `tests/services/test_*.py` | One per service with non-trivial logic |
| **Integration** | Cross-service flows — campaign references template + list, automation enrolls contacts | `tests/integration/test_*.py` | When entities reference each other |
| **E2E** | Full user journeys — create contact → template → campaign → send → verify stats | `tests/integration/test_e2e_flows.py` | One per product, covers the golden path |
| **Regression** | Bug-shaped tests pinning behavior that broke in production / detector false-positives / security incidents / known-edge-cases. Names the incident. | `tests/regression/test_<short_case>.py` (or inline `# Regression: ...` docstring inside the closest unit/integration test) | Every time a bug is fixed, a detector misbehaves on a real case, or an incident discovered behavior the unit tests didn't cover |

## Rules

- **Unit tests:** mock the database (`MockSupabaseClient`). Test one endpoint at a time.
- **Integration tests:** mock the database but test multi-step flows where step N depends on step N-1.
- **E2E tests:** simulate a real user journey through multiple endpoints. Each test is a story.
  - **Selector stability (Playwright):** the seed FE ships **zero `data-testid`**, so the live E2E specs target **Portuguese text/role/label** selectors (`getByRole('button', {name:'Entrar'})`, `getByText('Esqueceu a senha?')`). Fast-green but **copy-fragile** — a copy / i18n change silently breaks the suite (a coupling to user-visible strings, not a stable contract). The stable fix is to seed `data-testid` on the shared design-system components the suites target (LoginForm, nav, key tables) and migrate assertions to them — a **seed FE change ⇒ the seed→propagate cadence, pilots-first** (core + erp have E2E today). Tradeoff documented; the testid seeding is tracked as a follow-up.
- **Regression tests:** name the case. Every regression test must reference the incident in its docstring or filename — date, project that surfaced it, or original ticket. Without that reference, it's just a unit test that may decay into noise. See `§ Regression tests in practice` below.
- **Deterministic:** no hardcoded dates (use `date.today()` / `date.today() - timedelta(days=N)`), no external API calls, no network.
- **Auth boundary:** every product must verify that unauthenticated requests return 401 for all protected endpoints.
- **An owner decision reversed ⇒ grep the tests that pin the old policy, in the same commit.** A test written to an earlier decision (e.g. RG required for contract parties) stays green on its own branch and only reds on the merged tip, after the reversal lands from another branch. That cost a full fleet integrate on 2026-11-04. When you implement a reversal, search the tests for the old policy's identifiers and rewrite each one to the new decision, naming the decision and its date in the docstring.
- **No self-monkeypatching:** never `monkeypatch.setattr(<our_module>, "<our_fn>", _noop)` or `patch.object(<our_module>, "<our_fn>", ...)`. If you find yourself reaching for it, the test is asking you to wire a seam differently. See `§ No self-monkeypatching — refactor playbook` for the three legitimate patterns.

## Harness how-to — moved to the playbook (2026-11-05)

These sections moved verbatim to `KB § PATTERNS/compliance/test-harness-playbook.md`; the heading text is unchanged there, so an existing
`testing.md § <heading>` reference resolves by searching the playbook for the same heading.

| Former `testing.md` heading | Now |
|---|---|
| `## Running` (incl. the stale-bytecode gotcha) | playbook §1 |
| `## Mock helpers` · `### Re-binding the auth user — bind_user_metadata` · `### Canonical test identity — TEST_USER_ID / TEST_ORG_ID` · `### Parallel-worktree shadow purge` · `### Seed-singleton isolation guard` | playbook §2 |
| `### Schema validation` — the MECHANICS (error shape, construction knobs, strict mode, bypass list, source files) · `### CHECK constraints` | playbook §3 (the opt-out POLICY stays below) |
| `## Seed-layer test harnesses` · `### Frontend harness notes` · `### Consent-guard product conftest pattern` (incl. **Side-effect verification via `inserted_payloads`**) · `### Framework-test inheritance suites` · `### Per-product frontend hook tests` | playbook §5 |
| `## Test-isolation pollution detection` | playbook §6 |
| `## TS outline-corpus baseline — a safety net, not a wall` | playbook §7 |

### Schema validation (default-on since 2026-04-24)

`MockSupabaseClient` validates column references, unknown tables (strict mode) and every migration-declared CHECK constraint by default. **How it works, its knobs and error shapes →** `KB § PATTERNS/compliance/test-harness-playbook.md` §3. The opt-out policy:

**A `validate_schema=False` mock is a test double that hides the contract it doubles — the same false-green family as the auth-boundary `assert status in (401, 404)` rule (`KB § PATTERNS/compliance/auth-boundary-false-green.md`).** There, the non-401 branch masks a route that doesn't exist or fails before auth runs; here, an un-validated mock masks a column/table the code writes that the *live* database doesn't have. Three real bugs shipped invisibly through exactly this hole (`erp.assinaturas.external_id` / `erp.tool_call_audits` / `erp.llm_preferences`, 2026-09-17 — see `KB § PATTERNS/backend/database-rls.md § Migrations mirror the code`): the product's tests ran `validate_schema=False`, so a missing column/table was invisible to them right up until a real request hit it.

**Opt-out guardrail.** The keeper `check_mock_schema_validation` detector flags any `validate_schema=False` site that has no rationale keyword (`schema-drift`, `reconciliation`, `follow-up`, `TODO`) IN THE SAME FILE. Put the rationale inside the module docstring or in a `#` comment above the line. Widened 2026-09-18 to scan the FULL `backend/tests/` tree (was `conftest.py`-only) — see `KB § PATTERNS/compliance/compliance-regression-baseline.md` § Baselined debt must carry a reason for the codified rule + the per-product remediation shape.

**The authoritative SET of opt-outs is derived, not hand-kept here** — whatever `check_mock_schema_validation` reports live, mirrored as fingerprints in `mcp/noctusai/tests/compliance_baseline.json` (a NEW undocumented opt-out fails `test_all_products_compliant` as a regression). This section records the WHY, which a baseline fingerprint cannot carry — per `CLAUDE.md` §1 "derive, don't sync by hand".

**Known opt-outs** (expected to flip back once their reconciliation project ships; each empirically re-confirmed 2026-09-18 by flipping `validate_schema=True` and observing the real `MockSchemaError`s below — never re-verify by reading a comment, verify by running the suite):
- `therapy-platform` — ~20 drifts tracked by `products/therapy-platform/projects/therapy-audio-lifecycle-schema-reconciliation/` (`conftest.py` + `test_bulk.py` + `test_scheduling_service.py` + `test_admin_service.py`; e.g. `therapy.therapist_settings has no column 'session_duration_minutes'`).
- `erp-imobiliario` — 8 drifts tracked by `products/erp-imobiliario/projects/erp-schema-drift-reconciliation/` (`conftest.py`; e.g. `erp.whatsapp_config has no column 'webhook_secret'`).
- `adconnect` — `relatorios_sellout` (and other org_id-bearing tables) carry an `org_id` column at runtime the migration doesn't declare (`conftest.py` + `test_admin_router.py` + `test_rewards_engine.py` + `test_admin_service.py`; e.g. `adconnect.relatorios_sellout has no column 'org_id'`). No dedicated reconciliation project filed yet — the rationale lives in `conftest.py`, referenced by the other 3 files.

**Remediated 2026-09-18** (were opt-outs with NO local reason; flipping caused zero failures, so the flag was removed rather than baselined): `agents` (`test_approvals_store.py`, `test_transcripts_store.py` — needed `schema="agents"` added), `social-wiring` (6 files across `scheduling`/`edicao_fotos`/`services` — needed `schema="social_wiring"` added; the mock had been silently NOT validating at all, since an unqualified schema is an unknown-table WARN+skip, not a real absence of drift), `personal-finance` (`test_onboarding_service.py` — needed `schema="personal-finance"` added).

---

## Regression tests in practice

Regression tests pin behavior that **broke once and might break again**. Without one, every fix is a one-shot — the next refactor can silently undo it. With one, the test fails the moment the same shape returns.

**When to write one (the trigger list).** ANY of these mandates a regression test:

1. **A production bug got fixed.** The fix landed; before merging, write a test that fails on the pre-fix code and passes on the fix. Reference the date / incident / project that caught it.
2. **A detector / linter / type-check missed a real case.** The keeper detectors, vitest config checks, schema-validation guards, etc. — when one of them lets a real-world case through (false negative) or fires on a legitimate one (false positive), the case becomes a fixture.
3. **A security issue was patched.** Even if the fix is one line, lock the behavior in. Reference the LGPD / OWASP / CVE class so future readers know why the assertion is shaped that way.
4. **A subtle edge case surfaced during code review or incident postmortem.** "We didn't think of this" is the cheapest signal — capture it before it leaves your head.
5. **A migration / schema change broke a query.** Add the regression test in `tests/regression/test_<table>_schema.py` so future migrations catch the same shape.

**Where to put it (two valid shapes):**

- **Dedicated file in `tests/regression/`** — when the regression spans multiple endpoints/services or doesn't fit naturally in any single existing test file. Filename names the case: `tests/regression/test_postgrest_404_on_single.py`, `tests/regression/test_phase_state_consistency_paused_phase_checkmark.py`. Each file's docstring opens with `"""Regression: <one-line description>. Caught <date> by <project|incident>."""`.
- **Inline `# Regression: ...` docstring** inside the closest existing test class — when the regression cleanly belongs with the surrounding behavior tests. Example from `products/core/backend/tests/routers/test_settings_router.py:173`:
  ```python
  def test_falls_back_to_platform_settings(self, client):
      """Regression: when org_settings has no match, must fall back to platform_settings."""
      ...
  ```
  The `Regression:` keyword is grep-able and tells the next reader "don't delete this even if it looks redundant — there was a reason."

**How to name it:**

- Test function: `test_<short_case>_<expected_behavior>` (e.g. `test_paused_project_with_phase_checkmark_does_not_flag_clean_folder`).
- Comment includes the **date caught** + the **project / incident** + the **wrong behavior that USED to ship** (so future readers understand the assertion's intent).

**Worked examples already in the repo:**

| Test | File | Case |
|---|---|---|
| `test_does_not_flag_paused_with_phase_checkmark_in_narrative` | `mcp/noctusai/tests/test_compliance.py:670` | Detector false-positive caught against `repo-state-consolidation` PROJECT.md (Phase 0 ✅ in narrative ≠ project closed) |
| `test_silent_ok_comment_does_NOT_suppress` | `mcp/noctusai/tests/test_compliance.py:601` | Pins removal of `# silent-ok` escape hatch (user directive 2026-04-28). |
| `test_legacy_logger_warn_alias_recognized` | `mcp/noctusai/tests/test_compliance.py:638` | Detector must recognise `_log.warn(...)` (deprecated stdlib alias) as legitimate logging. Caught in code review. |
| `test_postgrest_handler.py` (entire file) | `products/core/backend/tests/test_postgrest_handler.py` + ERP mirror | Lock `.single() on 0 rows → 404 not 500` after the framework handler was added. |

**Anti-patterns (what kills regression tests):**

- Test name like `test_bug_fix_1` — useless to a future reader.
- No reference to the original incident — the test rots; someone deletes it as dead.
- Asserting the implementation, not the symptom — fragile to refactor; passes by coincidence.

### Regression-test-the-detector — platform-wide methodology

**Every keeper detector ships colocated with a regression test.** A `check_*` function in `mcp/noctusai/tools/compliance.py` that has no matching `Test<CamelCase>` class somewhere under `mcp/noctusai/tests/` is itself a violation, flagged by the detector `check_detector_has_regression_test` (severity `high`).

**Why platform-wide.** Detectors fail silently when they regress — they keep returning the same `score: 100` while missing the case they were supposed to catch. The regression test is the only thing that locks the contract: a future refactor that breaks the detector's true-positive shape (or introduces a false-positive) fails CI immediately. Without it, a real-world miss can ship undetected. This applies to every detector for every product the keeper watches over: existing ones, future ones, and any new product's detectors.

**The contract.** A regression test for a detector must:

1. **Pin at least one true positive** — feed the detector a known-bad shape; assert it flags. The shape should mirror a real-world case the detector exists to catch.
2. **Pin at least one false positive that's NOT flagged** — feed the detector a known-good shape that *looks* similar; assert it returns `[]`. This protects against the detector becoming over-aggressive after a refinement.
3. **Pin the severity** — assert `i["severity"]` matches the documented severity from `KB § 06-AGENTS.md § Detectors`. A silently-downgraded severity is the same as a regression.

**Naming.** The test class name is `Test<CamelCase-of-detector>` (e.g. `check_silent_errors` → `TestCheckSilentErrors`). The detector's case-insensitive matcher accepts both the prefixed (`TestCheckSilentErrors`) and unprefixed (`TestSilentErrors`) shapes, plus acronym-preserving forms (`TestAIFeatureCompleteness`). Any other shape requires an entry in `_DETECTOR_TEST_OVERRIDES` mapping the detector to its test target.

**Pre-commit.** The same keeper also runs in `scripts/hooks/pre-commit` (§ 7b, `--check-detector-has-regression-test`) when `compliance.py` or a `mcp/noctusai/tests/test_check_*.py` is staged, so a new detector without its `Test<DetectorCamel>` bounces at commit, not at integrate (`keeper_meta`, 2026-10-24); engineer briefs carry the reminder in `BEFORE_RETURNING_BLOCK`.

**CI integration.** `check_detector_has_regression_test` runs as part of `check_all_products` (i.e. `mcp/noctusai/cli.py --review` / `--validate`), which the test workflow invokes on every PR via `.github/workflows/test.yml`. A new detector merged without its regression test fails the workflow.

**Worked examples** (each detector → its test class):

| Detector | Test class | Test file |
|---|---|---|
| `check_seed_compliance` | `TestSeedCompliance` | `mcp/noctusai/tests/test_compliance.py` |
| `check_silent_errors` | `TestCheckSilentErrors` | `mcp/noctusai/tests/test_compliance.py` |
| `check_no_self_monkeypatch` | `TestCheckNoSelfMonkeypatch` | `mcp/noctusai/tests/test_compliance.py` |
| `check_phase_state_consistency` | `TestPhaseStateConsistency` | `mcp/noctusai/tests/test_compliance.py` |
| `check_clean_folder_violations` | `TestCheckCleanFolderViolations` | `mcp/noctusai/tests/test_compliance.py` |
| `check_ai_feature_completeness` | `TestAIFeatureCompleteness` | `mcp/noctusai/tests/test_compliance.py` |
| `check_mock_schema_validation` | `TestMockSchemaValidation` | `mcp/noctusai/tests/test_compliance.py` |
| `check_path_references` | (override → `TestFindRefs`) | `mcp/noctusai/tests/test_refs.py` |
| `check_standard_routers_audit` | `TestStandardRoutersAudit` | `mcp/noctusai/tests/test_standard_routers_audit.py` |
| `check_frontend_entrypoint`, `check_out_of_contract_trees` | (overrides) | `mcp/noctusai/tests/test_phase5_detectors.py` |
| `check_config_extends_product_settings` | (override) | `mcp/noctusai/tests/test_config_inheritance.py` |
| `check_frontend_config_paths` | `TestRegexMatching` etc. | `mcp/noctusai/tests/test_frontend_config_paths.py` |
| `check_seed_version_propagation` | (functions, override) | `mcp/noctusai/tests/test_seed_version_propagation.py` |
| `check_detector_has_regression_test` | `TestCheckDetectorHasRegressionTest` | `mcp/noctusai/tests/test_compliance.py` |
| `check_test_status_assertion` | `TestCheckTestStatusAssertion` | `mcp/noctusai/tests/test_test_status_assertion_detector.py` |
| `check_seed_export_membership` | `TestCheckSeedExportMembership` | `mcp/noctusai/tests/test_seed_export_and_slug_set_detectors.py` |
| `check_hardcoded_product_slug_set` | `TestCheckHardcodedProductSlugSet` | `mcp/noctusai/tests/test_seed_export_and_slug_set_detectors.py` |

**Adding a new detector?** The recipe (and the order matters):

1. Write the test class **first**, with a true-positive case and a false-positive case (this is the spec).
2. Implement the `check_*` function in `mcp/noctusai/tools/compliance.py` (or a sibling module) until the test passes.
3. Register the detector in `check_all_products()`.
4. Document it in `KB § 06-AGENTS.md § Detectors` with severity + rationale.
5. Run `mcp/noctusai/cli.py --validate` and confirm the detector contributes `[]` to a clean tree.

If you need to land the detector before the test (rare — usually because the detector emerged from a real-world incident), still write the test in the same commit. The CI gate fails otherwise.

---

## Production-correctness keeper detectors — the three-detector trio

**The trio.** Three keeper detectors flag latent production bugs that pass against `MockSupabase` mocks but fail at runtime against real Supabase. Surfaced 2026-05-10 by Engineer GG's `therapy-platform-wiring` Phase 4 audit (commit `a56a39e`) which discovered an N=12 migration drift case that had been silently green for 7+ days.

| Detector | What it catches | Severity |
|---|---|---|
| `check_unknown_table_references` | `<X>.table("name")` where `name` is not declared by any `CREATE TABLE` in `products/<p>/backend/migrations/*.sql`. MockSupabase WARN+skip returns empty results, production fails. | `warning` |
| `check_function_search_path_pinned` | `CREATE [OR REPLACE] FUNCTION ...` blocks without `SET search_path = ...`. Supabase advisor 0011 flags it; per-function risk analysis is cheaper to skip if a detector enforces. | `warning` |
| `check_admin_endpoint_service_role_bypass` | `get_admin_client().table("T")` (chained or bound-var) where `T` has no `CREATE POLICY "service_role_bypass" ... ON <schema>.T` in migrations. Bypass silently fails. | `warning` |

**The slip pattern.** Tests against `MockSupabase` are HAPPY-PATH biased — the mock answers a query against any table name with an empty result-set (WARN+skip mode, default since 2026-04-24). When code drifts (rename, table never landed, schema typo), the test stays green; production fails the moment a real Supabase responds. The three-detector trio uses migrations + AST as the static oracle to close this gap.

**AST shape — `check_unknown_table_references`.**

- Walks every `.py` under `products/<p>/backend/app/` (excludes tests + migrations + caches).
- Matches any `<expr>.table("X")` call where `"X"` is a `Constant[str]` (skips f-strings + name references — false-positive avoidance).
- Diffs against the unqualified table-name set extracted from `CREATE TABLE [IF NOT EXISTS] [<schema>.]<name>` in every `products/<p>/backend/migrations/*.sql`.
- Allowlists Supabase-managed `auth.users` + core-bootstrap `products` / `organizations` / `user_org_roles` to suppress cross-cutting false positives.
- Short-circuits when the product has no migrations directory.

**Regex shape — `check_function_search_path_pinned`.**

- For each `products/<p>/backend/migrations/*.sql`, finds every `CREATE [OR REPLACE] FUNCTION [<schema>.]<name>(` start.
- Walks forward through the dollar-quoted body (`$tag$ ... $tag$` with any tag, including empty) to find the block's end terminator.
- Asserts `\bSET\s+search_path\b` appears somewhere in the block. Missing → warning.
- Anywhere-in-block placement is accepted (the clause may sit in the function header BEFORE `AS`, or in `WITH (SET ...)` style — match is permissive).

**AST + regex hybrid — `check_admin_endpoint_service_role_bypass`.**

- AST-finds local-variable bindings of `get_admin_client()` return values: `admin_db = get_admin_client()` and `db: SomeType = get_admin_client()`.
- AST-walks every `.table("X")` call; flags those where the receiver is either a bound admin-client variable OR the chained shape `get_admin_client().table("X")`.
- Diffs against the table set extracted by regex from `CREATE POLICY "service_role_bypass" ... ON [<schema>.]<table>` across all migration files.
- Same external-tables allowlist as the unknown-table detector.

**False-positive design.** All three detectors are configured for FALSE NEGATIVES over false positives:

1. Non-`Constant[str]` table arguments are skipped (the detector can't resolve runtime-built strings statically; a dataflow pass would be a much larger lift for marginal gain).
2. Cross-product schema references that legitimately live in another product's migrations would false-flag — accept-with-rationale + comment is the escape.
3. Tables accessed via admin client for cross-tenant reads where RLS is intentionally not bypassed (foreign-key tenant-id enforcement) would false-flag — same accept-with-rationale path.

**Worked example — therapy-platform N=12 drift.** Running the trio against `products/therapy-platform/` on 2026-05-11 surfaces:

```
check_unknown_table_references: 37 issues
  distinct tables flagged: ai_prompt_history, ai_prompt_settings, anamneses,
    clinic_therapist_configs, financial_transactions, goals, notifications,
    reminder_configs, sessions, settings_history, therapeutic_journal,
    therapist_reviews                                    # ← exact GG N=12 + 1
check_function_search_path_pinned: 1 issue
  functions flagged: therapy.gcal_authorization_is_fresh # ← exact GG case
check_admin_endpoint_service_role_bypass: 5 issues
  distinct tables flagged: ai_prompt_history, ai_prompt_settings,
    settings_history
```

The detector catch matches GG's manual audit case-for-case. The detectors close the silent-fail vector that allowed the drift to ship for 7+ days.

**Adopters.** Run on every product; current platform-wide counts (2026-05-11):

| Product | unknown_table | search_path | admin_bypass |
|---|---|---|---|
| adconnect | 0 | 0 | 0 |
| core | 2 | 0 | 149 |
| daily-life | 0 | 0 | 0 |
| dev-team | 0 | 0 | 0 |
| erp-imobiliario | 2 | 9 | 34 |
| imobi-scheduling | 0 | 0 | 0 |
| mailing | 0 | 0 | 18 |
| personal-finance | 0 | 0 | 1 |
| seed | 0 | 0 | 0 |
| therapy-platform | 37 | 1 | 5 |
| youtube-crawler | 0 | 0 | 0 |

The numbers are the to-be-triaged backlog — `cli.py --review` authors proposals per finding for explicit accept/refactor decisions.

**Why warning, not high.** All three findings reflect real production gaps but the false-positive risk is non-zero (cross-product schema references, intentionally-not-bypassed admin reads, functions deliberately relying on caller search_path). `warning` lets the trio surface every candidate without blocking validation gates; the accept-with-rationale path handles the legitimate carve-outs.

---

## Status-code-assertion rule — pin the code, not just the body

**The rule.** Every pytest test method that asserts on response BODY (`<resp>.text`, `<resp>.json()`, `<resp>.content`) MUST also assert on response STATUS CODE (`<resp>.status_code <op> <val>`) **in the same method body**. Body-only assertions can go green for the wrong reason.

**Why — the YouTube Crawler Phase 1 case study.** A router test shipped with this shape:

```python
def test_recipient_without_channel_rejected(self, client):
    resp = client.post("/api/settings/recipients", json={"name": "x"})
    assert "at least one of" in resp.text.lower()
```

The test went green. The endpoint was unusable. What actually happened: the request hit a broken `Depends(get_org_id)` chain demanding `?user=` and `?token=` query params; the response was 422 with TWO error entries — (a) the seed's broken auth dep, and (b) the schema-validation `"at least one of"` error. The substring assertion matched (b). The test passed. The endpoint was structurally broken for any authed traffic.

The substring matched. The status code was `422` (not the expected `422` for the right reason — for the WRONG reason). Without `assert resp.status_code == 422` next to the body assertion, the test author had no signal that the endpoint was answering for the wrong reason. The status-code pin would have caught it (the dep-chain failure changes which path the request takes; the right-reason path returns 422-with-one-error-entry, not 422-with-two).

**The structural fix.** A keeper detector — `check_test_status_assertion` (`mcp/noctusai/tools/noctus/dev/compliance.py`) — flags any test method asserting on response body without a sibling status-code check. Severity `warning`. Surfaces via `noctus.dev.review` and `noctus.dev.validate`.

**What the detector catches:**

```python
# FLAGGED — body-only assertion, no status_code pin
def test_x(client):
    resp = client.get("/api/x")
    assert "ok" in resp.text  # ← could be 500, 403, 422 — we don't know

# FLAGGED — JSON body assertion alone
def test_y(client):
    resp = client.get("/api/y")
    assert resp.json()["name"] == "x"  # ← 200? 201? schema-error 422?

# FLAGGED — content (binary body) assertion alone
def test_z(client):
    resp = client.get("/api/img/1")
    assert b"PNG" in resp.content  # ← could be a 500 HTML error page
```

**What the detector accepts:**

```python
# OK — body + status code, both load-bearing
def test_x(client):
    resp = client.get("/api/x")
    assert resp.status_code == 200
    assert "ok" in resp.text

# OK — any comparison op against status_code satisfies
def test_y(client):
    resp = client.get("/api/y")
    assert resp.status_code in (401, 403)
    assert "unauthorized" in resp.text.lower()

# OK — inequality also counts
def test_z(client):
    resp = client.get("/api/z")
    assert resp.status_code != 500
    assert "data" in resp.json()
```

**Conservative gating — false negatives over false positives.** The detector binds a "response variable" set at method scope: only names assigned from `client.<verb>(...)` (or `await client.<verb>(...)`) on the right side of an assignment count as response vars. Body-attr matches against names NOT in that set are silently skipped. Drops false positives on domain-object attributes that happen to share the name (`digest.text`, `result.content` on a tool-result object, etc.) at the cost of missing tests that use helper-returned responses (`resp = _do_request(client, "/x")`). The latter is an intentional miss — extending the helper to assert status_code internally is a valid pattern, and we'd rather skip than noise.

**Method-scope only.** Helper functions (any name not starting with `test_`) are NOT scanned. A `def _assert_payload(resp)` helper that's missing a status_code check internally won't fire the detector — the tests that CALL it will, but only if they don't pin status code at the call site.

**Cross-product cleanup is per-product.** Pre-existing slips at detector-introduction time were catalogued in `KB § PATTERNS/common/accept-with-rationale.md` (each entry: file / line / why-accept / revisit-trigger) so the platform-wide scan runs clean. Cleanup belongs to per-product test-maintenance follow-ups.

**Frontend (Vitest) coverage:** OOS today — a follow-up `keeper-test-status-assertion-frontend` project will ship a ts-morph-based variant once the Python detector beds in.

---

## No self-monkeypatching — refactor playbook

`monkeypatch.setattr(<our_module>, "<our_fn>", _noop)` and `patch.object(<our_module>, "<our_fn>", ...)` neuter the very logic the test claims to verify. The keeper detector `check_no_self_monkeypatch` flags these; severity is `warning` while a per-product cleanup is in flight, ratcheting to `high` when each product's count reaches zero.

**The three legitimate patterns** — pick by test shape, not by ease.

### Pattern 1: Dependency Injection (DI) — the default

**When.** The unit under test calls a helper or service that does I/O (DB write, external API, audit-log dispatch). Production callers default to a real client; tests pass a mock.

**Shape.**

```python
# Production code — kwarg defaults to None and resolves at call time
async def process_session_end(
    appointment_id: str,
    db: Any,
    *,
    core_db: Any | None = None,
    transcribe: Callable[..., Awaitable[str]] | None = None,
):
    core_db = core_db or get_core_client()                           # production path
    transcribe_fn = transcribe or transcription_service.assemble_transcript
    transcript = await transcribe_fn(appointment_id, db)
    ...
```

```python
# Test — inject the mock, no patching
async def test_process_session_end_happy_path():
    db = _db_with_grants()
    db.set_table_data("appointments", [SAMPLE_APPOINTMENT])

    async def fake_transcribe(*_a, **_kw):
        return "Transcrição completa."

    result = await ai_pipeline.process_session_end(
        appointment_id="appt-001",
        db=db,
        core_db=db,
        transcribe=fake_transcribe,
    )
    assert "summaries" in result
```

**Why it works.** The production call site never holds onto the mock — the kwarg defaults to None, runtime resolves the real client. Tests inject. Zero patching. Reference adopters: `_resolve_core_db(core_db)` in `products/therapy-platform/backend/app/services/ai_pipeline.py`; `consent-guard-rollout` (DI for `bind_consent_module_to_mock`).

**When NOT to use DI.** If the dependency is reached from 8+ call sites scattered across the codebase, threading a kwarg through all of them is more churn than it's worth. Use Pattern 2 instead.

### Pattern 2: Boundary mock at the import site

**When.** The unit under test calls our service helper which calls an external boundary (LLM API, email provider, payment gateway). Patch the **external** symbol at the import site, not our service helper.

**Shape.**

```python
# Wrong — patches our helper, neuters the test
with patch.object(longitudinal_service, "generate_clinical_longitudinal", ...):
    await ai_pipeline.process_session_end(...)
```

```python
# Right — patches the LLM call inside our helper at the boundary
with patch.object(noctusai_lib.llm, "chat_completion", AsyncMock(return_value=FAKE_LLM_RESPONSE)):
    await ai_pipeline.process_session_end(...)
# Real `generate_clinical_longitudinal` runs; only the LLM round-trip is faked.
```

**Why it works.** The boundary belongs to an external library — patching it is the standard mock pattern, allowed by the rule. Our orchestration logic, our error handling, our consent guards — all execute. The test now actually verifies the chain, not just the call order.

**Patch at the consumer-side import binding, never at the producer-side definition.** The mock target is the consumer module's local symbol — `patch("app.services.X.schedule_coro")` (consumer's `from noctusai_lib.primitives.tasks import schedule_coro` binding), NOT `patch("noctusai_lib.primitives.tasks.schedule_coro")` (producer-side definition). The consumer-side path tracks refactors automatically: rename the seed helper or move it to a different layer, the consumer's import re-binds, and the patch path stays accurate. The producer-side path silently no-ops the moment the consumer's import shape changes — a recurring slip class. *Formalized 2026-05-10 from `projects/schedule-coro-fire-and-forget/` Phase 3 proposal item #3.*

**When NOT to use boundary mocks.** When the inner helper does enough work that running it would require seeding more data than the test scope allows. Then Pattern 3.

### Pattern 3: Seed real data via `MockSupabaseClient`

**When.** The function under test reads from the DB and dispatches based on the data. Don't patch the read — seed the table and let the real read run.

**Shape.**

```python
# Wrong — patches the read function, the test no longer exercises the query logic
with patch.object(consent, "require", return_value=None):
    await ai_pipeline.process_session_end(...)
```

```python
# Right — seed `ai_consent` rows; real `require()` reads the mock and returns silently
db = MockSupabaseClient()
db.set_table_data("ai_consent", [
    {"user_id": "patient-001", "feature_key": "therapy.session_summary",
     "granted": True, "granted_at": "2026-04-27T00:00:00Z", "revoked_at": None},
])
await ai_pipeline.process_session_end(db=db, core_db=db, ...)
# Revocation path: same shape, set granted=False or revoked_at=now()
```

**Why it works.** The mock IS the dependency. Seeding rows is identical in cost to a `patch.object` plus correct setup, and now the test exercises the real consent guard. Reference adopter: `_db_with_grants(...)` helper in `products/therapy-platform/backend/tests/services/test_ai_pipeline_service.py`.

**Side-effect verification:** when the production code writes a notification or audit row, read `mock_sb._tables["notifications"].inserted_payloads` after the call. Public list maintained by every `insert(payload)`. Production code stays untouched. Same product reference.

### Picking the pattern

| Test shape | Pattern |
|---|---|
| Orchestrator unit test (verifies "calls A then B then C") | DI — pass each helper as a kwarg with its real default |
| Service unit test (verifies internal logic of the service) | Boundary mock — patch the external lib at the boundary |
| Router unit test (verifies HTTP-shape behavior, including auth/consent) | Seed real data — let routes hit the real guards |
| Integration test (multi-service flow) | Seed real data + boundary mock for the external calls |
| Edge case / error path | Seed the bad data; let the real validator raise |

### Refactor procedure (per site)

1. Find the `monkeypatch.setattr` or `patch.object` line.
2. Identify the symbol's package: ours (`app.*`, `noctusai_lib.*`, `noctusai_seed.*`) → must refactor; external (`openai.*`, `httpx.*`, `stripe.*`) → already correct, the detector allowlists these.
3. Pick the pattern (table above).
4. Apply: add kwarg / change patch target / seed table.
5. Run the test — confirm green AND that the test still exercises a meaningful failure path (try seeding bad data; the test should fail).
6. Re-run keeper: `mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --validate` — confirm the count dropped.

### Severity ratchet

Detector severity is `warning` by default because the first run flagged 420 sites and tanking score from 100 → 0 was unhelpful. The ratchet flips a product to `high` once it reaches zero, blocking regression.

| When | Action |
|---|---|
| A product reaches 0 self-monkeypatch warnings | Detector severity flips to `high` for that product. New violations block CI. |
| All products at 0 | Detector severity flips to `high` repo-wide; the `warning` carve-out is removed. |

**Implementation** (2026-05-01): the per-product override lives in `mcp/noctusai/tools/compliance.py` as `_NO_SELF_MONKEYPATCH_HIGH_SEVERITY_PRODUCTS: frozenset[str]`. To ratchet a product, add its folder name to that set + extend the keeper test (`test_severity_high_for_ratcheted_product`). Regression tests in `mcp/noctusai/tests/test_compliance.py::TestCheckNoSelfMonkeypatch` cover both branches.

**Currently ratcheted (`high`):**
- `therapy-platform` — 115 → 0 (closed 2026-05-01 via `projects/keeper-warning-triage` Phase 1: pilot pattern-1 DI in `test_ai_pipeline_service.py`, pattern-3 seed-real-data sweep in `test_messaging_router.py`, and Wave C digest absorption side-effect on the remaining service tails).
- `social-wiring` — 43 → 0 (2026-05-24, `social-wiring-settings-di-rewrite`).

**Still draining (`warning`):** `erp-imobiliario` (96), `core` (44), `mailing` (18), `personal-finance` (16), `daily-life` (11), `<seed-lib>` (139 in 16 files — `seed/…` only; until 2026-10-29 these were mislabelled `<mcp>` and the seed PRODUCT's were mislabelled `<seed-lib>`; the label now keys on the `seed/` path prefix), `seed` (5, the seed product). Per-product follow-up project slugs: `<product>-tests-no-self-patch` (filed when picked up). Pilot proof + cleanup status lives in `projects/keeper-warning-triage/PROJECT.md` §6.

**Pilot result (2026-04-28).** `products/therapy-platform/backend/app/services/ai_pipeline.py` introduced a `_PipelineHooks` dataclass with the 5 helper functions as fields; production callers omit `hooks=` and resolve to `_DEFAULT_HOOKS` (real services). `tests/services/test_ai_pipeline_service.py` migrated `TestProcessSessionEnd` (8 tests) + `TestPatientConsentGuards.{test_session_summary_consent_revoked, test_longitudinal_consent_revoked}` (2 tests) from `patch.object(<our_module>, ...)` to a `_hooks(...)` factory that returns `_PipelineHooks(transcribe=AsyncMock(...), summarize=AsyncMock(...), ...)`. 33 sites cleared (43 → 10 in that file; 315 → 282 platform-wide). All 17 tests in the file pass; real consent guards execute end-to-end; revoked-feature paths verified via `hooks.<helper>.assert_not_awaited()`.

---

## Coverage gaps + ratchet plan

The "five layers" table at the top is the **target shape** every product should reach. Today, coverage is uneven. This section is the inventory + ratchet plan — open it before adding new tests so you know the highest-leverage gap to fill.

> ⚠️ **Stale inventory (flagged 2026-11-05, fix-on-contact).** The counts below were taken 2026-04-28 against **7 products** (Playwright row updated 2026-06-10). On 2026-11-05 `products/` holds **19 entries** (incl. `seed` and `dev-team`), so every "N/7" denominator is out of date and the per-product adopter lists are incomplete. The numbers were NOT re-measured here (no fleet-wide coverage run in that slice) — treat the rows as a lower bound on the gap, not as current state. Re-inventory destination: the Wave-2 `test-engineer` split of this doc (agent-refinement PROJECT.md §4a). **Re-inventoried 2026-11-05 (file counts per product, not coverage %; no coverage tool is configured anywhere) → `KB § PATTERNS/compliance/test-engineering-canon.md §10`** — the tables below are kept as the historical baseline the ratchet rows refer to. Judging test adequacy (mutation, flaky, coverage-as-signal) → `KB § PATTERNS/compliance/code-review-craft.md §6–§8`.

### Backend coverage

| Tier | Status | Gap |
|---|---|---|
| Unit (routers + services) | ✅ Universal | Self-monkeypatch debt being cleaned per `§ No self-monkeypatching — refactor playbook` (315 → 282 as of 2026-04-28 pilot). |
| Integration | ✅ Universal | Healthy — only 7 self-monkeypatch hits across all integration tests platform-wide. |
| E2E (`tests/integration/test_e2e_flows.py`) | ⚠️ Partial | ERP only. Other products: TBD. |
| Regression | ⚠️ Partial — see `§ Regression tests in practice` | No `tests/regression/` dir anywhere yet; informal regressions live in `test_postgrest_handler.py` (core + ERP) + inline `# Regression: ...` docstrings (`test_settings_router.py`, `test_dimob_router.py`, `test_dimob_service.py`). Convention: prefer the dedicated dir for new ones. |
| `tests/realdb/` (real-DB integration) | ⚠️ 3/7 products | Adopters: `core`, `erp-imobiliario`, `personal-finance` — each has a `realdb/` dir with `pytest.mark.realdb` marker, auto-skipped when `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` are unset. Missing: `therapy-platform`, `mailing`, `daily-life`, `adconnect`. RLS regressions in those 4 products are caught only at deploy time. |
| Mutation / property-based | ❌ 0/7 | No `hypothesis`, no `pytest-property`, no mutation-test harness anywhere. |

### Frontend coverage

| Tier | Status | Gap |
|---|---|---|
| Hook tests (`*.test.ts` via vitest) | ⚠️ 4/7 products with **just useAI** | Each adopter has exactly one test file (`useAI.test.ts`) with 4-8 `it()` cases. Adopters: erp-imobiliario, mailing, personal-finance, daily-life. **Zero tests in therapy-platform, core, adconnect** — vitest harness is wired but no specs. `npx vitest run` exits 1 ("No test files found") which is the honest signal. |
| Component tests | ❌ 0/7 | No component-level vitest specs anywhere — only the AI hook is tested. |
| Page tests | ❌ 0/7 | Pages are exercised only via Playwright (where it exists) — see next row. |
| Playwright E2E | ⚠️ 3/11 wired, **specs LIVE** (updated 2026-06-10) | core (6 specs) + erp-imobiliario (8 specs) + social-wiring (35 specs, Mailchimp integration Slice C, wired 2026-06-10) under `e2e/tests/*.spec.ts` — config pattern: `webServer` boots vite dev, backend mocked via `page.route` fixtures, chromium-only, `data-testid` selectors (social-wiring: testid-first) + role/label selectors (core+ERP: copy-fragile, see selector-stability note). Remaining products: not wired. |
| **Boundary-contract tests** (added 2026-05-20) | ⚠️ 2/5 boundaries covered | Named class for "tests-green-dashboard-red" bugs — full spec at `KB § PATTERNS/backend/boundary-contract-tests.md`. **B1** build-injection (vite `define` → bundle literals) — ✅ covered at source by `check_seed_canonical_default`; bundle-side assertion still open. **B2** HTTP schema (FE↔BE cap drift e.g. `le=20`-vs-top-50) — ❌ accept-w/-destination, file `<product>-fe-be-schema-contract` on N=2. **B3** third-party library contract (TanStack v5 `queryFn` return-type) — ✅ Stage-4 `check_query_fn_returns_undefined`. **B4** container env propagation (`.env`→stage→runtime) — ❌ accept-w/-destination, file `smoke-fleet-env-propagation` on N=2 (manual `KB § PATTERNS/devops/containerization.md § 12b` today). **B5** library-default propagation (seed default → N consumers) — ✅ same detector as B1. Authoring-time discipline: every PR adds a "if this contract drifts, what existing test fails?" line per touched seam. |

### Ratchet plan (filling each gap)

Each row below names a follow-up project slug + its trigger to start. **No project here is in flight today** (2026-04-28); they're in the queue.

| Gap | Trigger | Follow-up project |
|---|---|---|
| Frontend hook tests in therapy / core / adconnect | When a product first ships a hook that does I/O (mutation / query) | `<product>-frontend-hook-coverage` |
| Frontend component tests | When N=2 products have a duplicated component bug | `frontend-component-test-pattern` (seed-level — define the pattern, then per-product adoption) |
| Frontend Playwright specs in core + ERP | When a flow goes user-facing (signup, billing, cross-product navigation) | `<product>-playwright-golden-paths` |
| `tests/realdb/` in the 4 missing products | When a product's first RLS-shaped bug ships to prod | `<product>-realdb-rls` |
| Mutation / property-based testing | When a product's bug class is "happy-path tests pass but edge values break it" — typically math-heavy services (PF, ERP metas) | `mutation-test-pilot` (one product, one service, prove the pattern) |
| Self-monkeypatch debt | Per-product cleanup; ratchet detector severity to `high` when count = 0 | `<product>-tests-no-self-patch` |
| B4 row-seeding (only therapy uses it) | When a product's autouse-fixture pattern misses a consent-revocation path | per-product, no umbrella project — small refactor |
| Boundary-contract tests — open boundaries (B2 HTTP schema, B4 container env) | N=2 surfacing of the same shape (per `KB § PATTERNS/backend/boundary-contract-tests.md` recurrence rule) | `<product>-fe-be-schema-contract` (B2) / `smoke-fleet-env-propagation` (B4) |

**Anti-pattern to avoid:** filing a "frontend test coverage" umbrella project that tries to fix every gap at once. Each gap above has a different trigger and a different shape; bundling them produces a project no one finishes. Pick by trigger, not by aspiration.

**Where to track real status:** filename `mcp/noctusai/cli.py --status` will list active projects + flags; this section names what *should* exist, not what does. The section gets updated when a follow-up project ships.

---

---

See also:
- `../06-AGENTS.md` — the MCP heal loop runs tests automatically
- `../../INSTRUCTIONS/05-TESTING-EVALS.md` — eval strategy (beyond unit/integration)

## No self-monkeypatching — gated at BOTH ends

The rule ("patch external boundaries; never our own code") is old and the
keeper `check_no_self_monkeypatch` has enforced it at commit/CI time for a
long time. It worked, and it still cost us a rewrite every time, because of
*when* it fired:

    engineer writes the suite with self-patches
      -> N green tests
        -> commit or CI red
          -> rewrite the suite onto real seams

2026-09-02: 16 patched symbols across two certidões test files, 197 green
tests, full rework after the slice looked finished. The owner's framing —
"we always monkeypatch, then fix the monkeypatching afterwards" — is the
accurate description of a backstop with no construction half.

**The fix is the shape CLAUDE.md §1 already prescribes for self-branching:**
gate at both ends. `test_seam_guard.decide` runs as a **PreToolUse hook** and
DENIES a `Write`/`Edit`/`MultiEdit`/`Bash` call that would introduce a
self-patch into a test file, with a refusal naming the offending symbols
*and* the remedy. `check_no_self_monkeypatch` stays exactly as it was — the
backstop.

### A gate is a safety net behind a mechanism, not a wall

Two holes shipped with the first version, both from the guard judging more
than the call in front of it:

* **Whole-file scan.** It re-parsed the entire resulting file, so a
  PRE-EXISTING self-patch anywhere in a test file blocked EVERY later edit to
  that file — an unrelated change, or even the fix itself (2026-09-14, a
  legacy `unittest.mock.patch` in a seed-lib fixture file made it un-editable
  from the write-time end). `decide` now judges only the lines a `Write` adds
  relative to the current on-disk content (or, for a brand-new file, the
  whole thing), and only the lines an `Edit`/`MultiEdit` adds relative to
  `old_string` — via a `difflib.SequenceMatcher` line diff, checked against
  each violating statement's full `lineno..end_lineno` span so a multi-line
  `monkeypatch.setattr(...)` call is judged as one unit. An edit that
  *removes* the only violation is allowed, same as it always was; an edit
  that never touches the violating lines no longer sees them at all.
* **Bash bypass.** It only fired on `Write`/`Edit`/`MultiEdit`, so a test file
  authored via `cat > tests/test_x.py <<'EOF' ... EOF` skipped it entirely —
  three self-monkeypatch violations reached CI that way on 2026-09-07 and
  were only caught by the commit-time keeper. `decide` now also matches on
  `Bash`: it resolves any heredoc/redirect in the command whose write target
  `is_test_file()` recognises (reusing `primary_write_guard`'s own
  `_HEREDOC_RE` / `_redirect_targets` parser rather than a second one) and
  runs the SAME `find_self_patches` predicate over the heredoc body. One
  heredoc per opening line; a test file produced by some other shell
  construct (`printf`, `python3 -c "open(...).write(...)"`) is still only
  caught by the commit-time keeper — stated as a deliberate limit, not
  hidden.

### One predicate, two enforcement points

The guard owns no detection logic. Both ends import
`_extract_patch_target` / `_resolve_target_via_imports` /
`_classify_patch_target` / `_build_import_map` / `_SELF_PATCH_OK_COMMENT_RE`
from `tools/noctus/dev/self_patch_predicate.py`. Two hand-rolled predicates
would drift, and *disagreeing* gates are worse than one gate: an agent denied
for something the keeper permits learns to distrust both.

🔴 **`self_patch_predicate.py` must stay stdlib-only.** The hook runs under
whatever `python3` is on PATH, not the repo venv. The first version imported
`compliance.py`, which imports pydantic at module scope; under the system
interpreter that raised, the hook failed OPEN by design, and the guard
silently never fired — while every unit test passed, because those run under
the venv. `TestTheHookActuallyFiresInProduction` pins this with an isolated
(`python -I`) import and an end-to-end hook invocation. Adding a third-party
import to that module re-breaks the guard invisibly.

### Escape hatch and overrides

`# self-patch-ok: <reason>` on the patching line is honoured identically by
both ends — write it once, accepted at both. `NOCTUS_ALLOW_SELF_PATCH=1`
disables only the write-time half, for a deliberate bulk operation; the
keeper is unaffected, which is the point.

### Fast feedback

`python mcp/noctusai/cli.py --check-no-self-monkeypatch` — ~4 seconds, with
the SAME regression semantics as CI (exit 1 only on findings absent from
`compliance_baseline.json`). Before it existed, the only way to run this
detector was the ~15-minute compliance suite; that is how 56 findings
accumulated unnoticed inside one slice.

### What it bought

Rewriting the certidões suite onto real seams did not just satisfy a gate —
it raised coverage in three places, because the patches had been hiding the
code under test: the real `_fetch_certidao` retry ladder, the CENPROT
root-level receipt fallback, and the storage key-vs-URL branch had never
executed. Test count went 197 → 199 and the assertions became behavioural
("a 2-minute-old row must survive the sweep") rather than call-routing
("was this function name invoked").

## Reference a migration by NAME, never by number (2026-10-10)

`task_branch integrate` renumbers a colliding `NNN_x.sql` to `MMM_x.sql`. With ~5 sessions writing
social-wiring migrations concurrently (N>=3 on 2026-10-09) a test that hardcodes `"217_x.sql"` or
`migrations/217_x.sql` breaks on a rebase that changed nothing else.

- **By construction:** `from noctusai_lib.testing.migrations import migration_path, migration_sql` —
  `migration_path(<migrations dir | backend dir | product root>, "x")` resolves the ONE
  `<digits>_x.sql` (zero or several matches raise `MigrationLookupError` naming candidates; never a guess).
  Order assertions compare resolved names, not literals.
- **Backstop (ratchet):** keeper `check_migration_number_refs_in_tests` (`--check-migration-number-refs-in-tests`,
  pre-commit on staged `products/*/backend/tests/**`, awake products only). Pre-existing offenders are in
  `mcp/noctusai/tests/migration_number_refs_baseline.json` (`{files: {path: count}}`); only a new file or a grown
  count blocks. `--refresh-migration-number-refs-baseline` is shrink-only — touching a legacy test? migrate it to
  the helper (docstrings too: the keeper counts raw text) and refresh.

## "Not configured" exceptions carry `IntegrationNotConfigured` (2026-10-10)

An integration that refuses to run because its config is absent (`*NotConfigured` / `*NaoConfigurado`) mixes in `noctusai_lib.primitives.not_configured.IntegrationNotConfigured`:

```python
class VistaConfigError(VistaError, IntegrationNotConfigured): ...
```

The mixin is plain, so it does not change MRO or `except` behaviour. `check_stand_in_conformance` leg A resolves DI graphs in a config-less subprocess and skips these BY TYPE, across a `raise … from exc` wrapper, via `is_integration_not_configured`. An unmarked one reads as a stand-in violation, which was the red since 9363832c4.

Keeper `check_not_configured_carries_marker` blocks a new unmarked class at pre-commit, scoped to the staged products. Scope: the seed packages and active products' `backend/app/`; tests are out of scope.
