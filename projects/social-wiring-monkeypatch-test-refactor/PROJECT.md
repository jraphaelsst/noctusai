# social-wiring-monkeypatch-test-refactor — Project Document

> **Filed 2026-05-20** as the named P5 follow-up from `social-wiring-absorption-debt` (closed §11 2026-05-18). Self-contained (durable-docs rule).
>
> **Symbol-first authoring** per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** ⏳ **DISPATCHED** — Engineer SW-P5 (worktree off main).
- **Owner / stakeholders:** joaoraphaelsst@gmail.com · architect
- **Related docs:**
  - `archive/projects/2026-05-20/01-platform-compliance-baseline/` (sibling — same DI-seam class, fleet scope)
  - `KB § PATTERNS/di-test-seam.md` (the canonical remediation pattern)
  - `KB § PATTERNS/testing.md` (DI-test-seam-conventions canon)
  - `feedback_no_monkeypatching_in_tests` (the rule)
- **Project slug:** `social-wiring-monkeypatch-test-refactor` (root `projects/`)

---

## 1. Context & Purpose

The parent project `social-wiring-absorption-debt` closed P0-P4 ✅ but explicitly named P5 (50 `check_no_self_monkeypatch` sites in `products/social-wiring/backend/tests/**`) as a deferred-with-destination follow-up. The 50 sites are NOT mechanically blanket-fixable: 35 are config-value injections (easy DI-seam migration); 15 are logic / absence-path patches that require per-case judgment (a blanket autouse fixture re-introduces patching).

This project ships those 50 sites through the proper DI-seam destination, per-case.

---

## 2. Confirmed constraints

- **Tests-only scope.** Production code is OUT (the rule is `feedback_no_monkeypatching_in_tests` — tests patching OUR symbols; production has no analogous violations in social-wiring).
- **Per-case triage.** Each site lands on one of three outcomes (per `KB § PATTERNS/di-test-seam.md`):
  - **(a) DI-seam refactor** — replace `monkeypatch.setattr(our_module.X, ...)` with a fixture that injects a test-double via the seed's DI default (the right answer for the 35 config-value sites).
  - **(b) Sanctioned `# self-patch-ok:`** — only for absence-path tests where DI is genuinely the wrong shape (rare; needs `# self-patch-ok: <reason>` comment).
  - **(c) Real-DI rewrite** — refactor production code's DI seam first, then test through it (the harder option; should be rare).
- **Baseline preserved.** Full `cd products/social-wiring/backend && pytest` must remain green throughout.

---

## 3a. Seed-first analysis

The DI-seam pattern is seed-shaped (lives in `noctusai_lib.testing.di_seams` or similar) — NO per-product convention. Every "this is config-value injection" site goes through the same lifted fixture, so the recurrence rule says: lift to seed once, consume per-test. Already half-formalized in `KB § PATTERNS/di-test-seam.md`.

Litmus: per-product code in seed = **0 LoC**. Per-product code in tests = 50 sites refactored, no new seed-test code per product.

---

## 4. Scope

**In scope:**
- All 50 `check_no_self_monkeypatch` warnings in `products/social-wiring/backend/tests/**`
- 8 test files (catalog via `python mcp/noctusai/cli.py --review --product social-wiring` filtered to `check_no_self_monkeypatch`).
- Per-site triage recorded in §11.
- `KB § PATTERNS/di-test-seam.md` augmented with any new sub-pattern this work surfaces.

**Out of scope:**
- Other products' monkeypatch sites (those are platform-compliance-baseline P1/P2/P3 territory — separately scoped).
- Production code changes (unless option (c) Real-DI rewrite fires for a specific site — flag and surface, do not silent-rewrite).

---

## 6. Phases

- **P1 ⏳ — Catalog.** Run `--review --product social-wiring` filtered. Produce a table of all 50 sites: file:line · function · symbol patched · category-guess (config-value / absence-path / logic-mock).
- **P2 ⏳ — DI-seam refactor batch.** For each `config-value` site (≈35), apply the `KB § PATTERNS/di-test-seam.md` recipe. Re-run pytest after each batch of 10. Update §11.
- **P3 ⏳ — Per-case triage of the residual ≈15.** For each: decide (a)/(b)/(c) with one-sentence rationale. Apply (a) inline; emit `# self-patch-ok: <reason>` for (b); FILE FOLLOW-UP for any (c).
- **P4 ⏳ — Verify.** `pytest` green; `check_all_products()` for social-wiring shows `check_no_self_monkeypatch` count dropped from 50 to a residual = (b)+(c). Three-way sync: KB pattern doc updated if new sub-pattern emerged.

---

## 9. Success criteria

- `products/social-wiring/backend/tests/**` `check_no_self_monkeypatch` count drops 50 → ≤ count of (b) sanctioned + (c) deferred-with-followup.
- `cd products/social-wiring/backend && pytest` green (zero regression).
- Each site's per-case triage recorded.
- `KB § PATTERNS/di-test-seam.md` updated if new sub-pattern surfaced.

---

## 10. How to use this plan

Fresh worktree off `origin/main`. P1 catalog first (read-only); P2 batch-refactor with pytest after each 10. Engineers obey `.claude/agents/engineer-default.md`.

---

## 11. Change log

| Date | Entry | By |
|---|---|---|
| 2026-05-20 | Filed as the named P5 follow-up from `social-wiring-absorption-debt`. Architect. | Architect |
