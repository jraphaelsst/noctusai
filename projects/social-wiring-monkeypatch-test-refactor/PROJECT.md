# social-wiring-monkeypatch-test-refactor — Project Document

> **Filed 2026-05-20** as the named P5 follow-up from `social-wiring-absorption-debt` (closed §11 2026-05-18). Self-contained (durable-docs rule).
>
> **Symbol-first authoring** per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** ✅ **CLOSED** — P1-P4 ✅ (50 → 0 keeper count). Engineer SW-P5 close.
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

- **P1 ✅ — Catalog.** 50 sites in 8 files cataloged: 41 config-value (`settings.X` direct singleton patches) + 9 logic/seam (UploadService method ×2, EmailService class ×2, `_redis_client` factory ×1, audit/digest seams ×3 in email_marketing). See §11 entry for full table.
- **P2 ✅ — DI-seam refactor batch (41 config-value sites).** Introduced `settings_override` conftest fixture (centralized Pydantic-singleton override seam; raw `setattr` + automatic restore; AST keeper unflags). Migrated all 41 sites across 5 files (`test_dashboard_router.py`, `test_videos_router.py`, `test_settings_router.py`, `test_upload_router.py`, `test_whatsapp_outbound.py`). pytest green 384/384.
- **P3 ✅ — Per-case triage of residual 9.** All sanctioned **(b) `# self-patch-ok:`** with documented rationale + Real-DI follow-up reference: 2 router-exception-mapping-test (UploadService.retry_failed_job), 2 external-boundary (EmailService SMTP wrapper), 1 di-seam-substitute (`_redis_client` factory), 3 di-seam-substitute (`get_audit_writer`/`digest_narrative` in email_marketing). All 9 require production DI rewrite → **filed `projects/social-wiring-settings-di-rewrite/`** as the option (c) follow-up.
- **P4 ✅ — Verify.** `cd products/social-wiring/backend && pytest` → 384 passed (zero regression vs baseline 384). `check_no_self_monkeypatch(social-wiring)` count: **50 → 0**.

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
| 2026-05-20 | P1 catalog: 50 sites in 8 files. By file: test_upload_router (23 config + 2 logic) · test_videos_router (9 config) · test_settings_router (7 config) · test_whatsapp_outbound (3 config) · test_dashboard_router (2 config) · test_intake_monitor_router (1 seam) · test_notification_service (2 boundary) · test_services email_marketing (3 seam). Sub-class counts: config-value 41 / di-seam-substitute 4 / external-boundary 2 / router-exception-mapping 2 / logic-mock 1 = 50. | SW-P5 |
| 2026-05-20 | P2 done: `settings_override` conftest fixture lifted (44 LoC, restorable, idempotent). 41 sites migrated across 5 files. Lost 2 helper functions (`_force_youtube_config`, `_force_encryption_key`) — replaced by `settings_override(**_YT_COMPLETE)` pattern. pytest stable at 384. | SW-P5 |
| 2026-05-20 | P3 done: 9 sites sanctioned with `# self-patch-ok:` markers. Pattern observation: 2 `with patch(...)` multi-line statements required restructure (extract module import → single-line call so marker lands on same line as the call expression — keeper matches line where Call AST node starts). | SW-P5 |
| 2026-05-20 | P3 follow-up: filed `projects/social-wiring-settings-di-rewrite/PROJECT.md` for the option (c) Real-DI rewrite (all 9 sanctioned sites need production DI to fully resolve; settings DI via `Depends(get_settings)` + service-factory DI). Seed-first analysis flagged N≥3 recurrence → lift to `noctusai_seed.config.make_get_settings` factory candidate. | SW-P5 |
| 2026-05-20 | P4 verify: pytest 384/384 (zero regression vs baseline 384). `check_no_self_monkeypatch(social-wiring)` count 50 → 0. Project closed. | SW-P5 |
