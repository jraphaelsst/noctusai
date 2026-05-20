# erp-imobiliario-test-baseline-recovery — Project Document

> **Filed 2026-05-20** as the test-baseline-recovery sweep surfaced by ERP-D (erp-portal-documentos-sharing-gate dispatch). Self-contained (durable-docs rule).
>
> **Symbol-first authoring** per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** 📋 **FILED** — baseline-red sweep; classify-then-fix; size unknown until P0.
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

- **P0 ⏳** — Classify: read each of the 31 failing tests, group by root-cause cluster. Output: `findings.md` cluster table.
- **P1 ⏳** — Drain cluster A (largest first; likely whatsapp_webhook ∨ certidoes).
- **P2 ⏳** — Drain cluster B.
- **P3 ⏳** — Drain cluster C (and beyond, as needed).
- **P4 ⏳** — Verify: `pytest` from `products/erp-imobiliario/backend/` ALL green; document any genuinely-orphaned tests deleted with rationale.

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
