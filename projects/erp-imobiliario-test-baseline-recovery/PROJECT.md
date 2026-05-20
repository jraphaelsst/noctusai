# erp-imobiliario-test-baseline-recovery — Project Document

> **Filed 2026-05-20** as the test-baseline-recovery sweep surfaced by ERP-D (erp-portal-documentos-sharing-gate dispatch). Self-contained (durable-docs rule).
>
> **Symbol-first authoring** per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** ✅ **READY-FOR-COMMIT** — Engineer-G (REDISPATCH) drained all 31 baseline-red failures inline; 2075 pass / 0 fail / 34 skip stable across 2 runs.
- **Owner / stakeholders:** joaoraphaelsst@gmail.com · architect
- **Related docs:**
  - `products/erp-imobiliario/backend/` test suite
  - `KB § PATTERNS/testing.md`
- **Project slug:** `erp-imobiliario-test-baseline-recovery` (root `projects/`)

---

## 1. Context & Purpose

Engineer D's full pytest run on the ERP backend produced **1949 pass / 31 fail / 34 skip**. D verified (via `git stash` + re-run against `origin/main`) that all 31 failures **pre-existed D's work** — they are baseline-red, not regressions. D was correctly out-of-safe-scope (the failing files were not in their brief's Files-to-modify) and surfaced the finding instead of silently expanding scope.

**Baseline-red is a silent-error shape one level up** — engineers see "31 failures" in `pytest` output and have to *manually verify* they're pre-existing every time. Cure: drain the failures so green-is-real.

---

## 2. Confirmed constraints (from D's surfacing)

The 31 failures cluster into ~8 named files:
- `whatsapp_webhook` × 8 tests
- `certidoes` × 8 tests
- `clientes` × 1 test
- `emails` × 2 tests
- `configuracoes` × 2 tests
- `bi_dashboard` × 1 test
- `gamificacao` × 1 test
- `site_imoveis` × 1 test
- `portais` × 1 test
- `matching` × 1 test
- `email_service` × 2 tests

Hypotheses (need P0 audit to confirm):
- **whatsapp_webhook** — likely the signature-validation shape changed at the seed level (5-pin contract); tests pinned the old shape.
- **certidoes / clientes / emails / configuracoes** — Pydantic strict-by-default (`StrictHttpModel`) absorption may have tightened schemas; fixtures still use loose shapes.
- **bi_dashboard / gamificacao / matching** — likely seam drift from refactor waves.

---

## 3a. Seed-first analysis

This is product-local (ERP-specific tests). Per-product code count in seed = 0 LoC. If any cluster turns out to be a seed contract drift (e.g., webhook signature) the cure ships in seed and the test consumes the updated contract. Audit at P0 routes the work.

---

## 4. Scope

**In scope:**
- P0 — classify 31 failures into root-cause clusters (likely 3-5 buckets).
- P1+ — drain bucket-by-bucket (one engineer per bucket if independent; sequential if cascading).
- Goal: `pytest` from ERP backend goes green; CI signal is real again.

**Out of scope:**
- New test coverage (this is recovery, not expansion).
- Refactoring the test infrastructure itself (a separate concern; surfaced as bystander if needed).

---

## 6. Phases

- **P0 ✅** — Classify: 31 failures across 11 files; cluster table in `findings.md`. Matches brief hypothesis (whatsapp_webhook count was 10 not 8 — the 2 HMAC tests folded into the same root cause).
  **Improvements:**
  - The 986-TypeError-storm Engineer E observed was orthogonal env noise (stale starlette in shared site-packages), NOT a regression class. Real baseline = 31 fails, env-refresh did not change the count.
- **P1 ✅** — Drain whatsapp_webhook (10 tests). Root cause: mock-skew (fixtures missing 3 predicate fields). Fix: libcst AST transform across 16 `set_table_data("whatsapp_config", ...)` call-sites.
  **Improvements:**
  - libcst transformer is reusable for any fixture-row-augmentation pattern; surfaced as candidate for `noctus.dev.scan_mock_predicate_skew` MCP keeper (see findings.md § Methodology improvement).
- **P2 ✅** — Drain certidoes (8 tests). Root cause: seed-boundary `_get_public_client` was constructing real Supabase clients in test paths that hit `resolve_credential`. Fix: conftest `client` fixture now patches `noctusai_lib.config.credentials._get_public_client` → mock_sb (precedent: `test_standard_llm_smoke.py`'s `llm_client` fixture). Same patch transparently drained `emails` cluster.
  **Improvements:**
  - The conftest-level patch is structurally correct; the previous per-fixture (`llm_client`) pattern was scoped to one test file but the seed-boundary applies product-wide. Three-way-sync candidate: KB § PATTERNS/testing.md could document "seed-boundary credential patches go in product conftest, not per-test."
- **P3 ✅** — Drain remaining clusters: configuracoes (code-drift to seed `chat_completion`), gamificacao/clientes/matching/portais/site_imoveis/bi_dashboard (mock-skew shape), email_service (same shape as P2 but tests don't use `client` fixture → per-test patch).
  **Improvements:**
  - The configuracoes cluster surfaces a pattern: when production code is refactored to consume a new seed surface, the tests that mock the OLD path silently start matching the WRONG outcome branch (here LLMNotConfigured returned "API Key inválida" instead of the expected "sucesso"). Test-side mock-skew is hard to spot via grep; the only oracle is the test failing.
- **P4 ✅** — Verify: `pytest` from `products/erp-imobiliario/backend/` returns **2075 passed, 34 skipped, 0 failed, 1 warning in 36.64s**. Stable across 2 consecutive full-suite runs. NO tests deleted as orphaned (all 31 were salvageable via fixture/mock updates).
  **Improvements:**
  - The 1 lingering warning (`'_delayed_tjsp_process' was never awaited` in `test_certidoes_service.py::TestScheduleTjspForOrg::test_idempotent_when_task_in_flight`) pre-exists this work. Not a regression. Candidate for a follow-up fix-on-contact if the architect green-lights touching that test file.

---

## 7. Open questions

1. **Per-cluster dispatch vs single engineer?** Recommendation: single engineer for P0 (classification is one mental model); decide per-cluster after P0 (file-disjoint clusters → parallel; cascading → sequential).
2. **Inline cutoff applies?** Per [[feedback_dispatch_cutoff_inline_threshold]] — if P0 reveals a cluster is <100 LoC ∧ <3 files ∧ single-phase, architect drains inline. If clusters average ≥100 LoC, dispatch.

---

## 9. Success criteria

- `pytest` from `products/erp-imobiliario/backend/` returns 0 failures.
- Any tests deleted (rather than fixed) carry a `findings.md` rationale.
- Keeper 0 issues; baseline-fingerprint cleaned.

---

## 11. Change log

| Date | Entry | By |
|---|---|---|
| 2026-05-20 | Filed from ERP-D dispatch finding. 31 pre-existing failures, ~8 files, ~5 clusters expected. Out-of-safe-scope for D; sweep recovery project. | Architect |
| 2026-05-20 | Engineer-E first dispatch returned BLOCKED on env-drift (shared site-packages had stale starlette pinned to dead worktree → 986 router-init TypeErrors masking the real 31) + missing PROJECT.md on `origin/main`. Both architect-resolved. | Engineer-E + Architect |
| 2026-05-20 | Engineer-G (REDISPATCH) ran the real baseline (`venv/bin/pytest`, 31 failures confirmed); classified 11 clusters across same-shape mock-skew (9) / code-drift (1) / seed-boundary-mock-missing (2 cascading via shared conftest patch). Drained all clusters inline within engineer-default scope (test files only). Final: **2075 passed / 0 failed / 34 skipped** stable. NO seed/app/migration touches. 10 staged files. | Engineer-G |
