# social-wiring-settings-di-rewrite — Project Document

> **Filed 2026-05-20** as the named follow-up from `social-wiring-monkeypatch-test-refactor` (engineer SW-P5 close). Self-contained (durable-docs rule).
>
> **Symbol-first authoring** per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** 📋 **FILED** — awaits dispatch when picked up.
- **Owner / stakeholders:** joaoraphaelsst@gmail.com · architect
- **Related docs:**
  - `projects/social-wiring-monkeypatch-test-refactor/` (parent — closed P1-P4 with `settings_override` fixture + 9 sanctioned residual)
  - `KB § PATTERNS/di-test-seam.md` (the canonical DI seam recipe)
  - `KB § PATTERNS/testing.md` § DI-test-seam-conventions (depth)
- **Project slug:** `social-wiring-settings-di-rewrite` (root `projects/`)

---

## 1. Context & Purpose

The parent project `social-wiring-monkeypatch-test-refactor` resolved 50 `check_no_self_monkeypatch` warnings in social-wiring tests by:
- **41 sites (config-value class)**: introducing a `settings_override` conftest fixture that mutates the Pydantic `app.config.settings` singleton via raw `setattr` + automatic restore. AST keeper unflags because the call is no longer `monkeypatch.setattr` of our module.
- **9 sites (logic/seam-substitute class)**: sanctioned with `# self-patch-ok: <reason>` comments (5 sub-classes: di-seam-substitute, external-boundary, router-exception-mapping-test).

The `settings_override` fixture is **structurally equivalent** to direct `monkeypatch.setattr` on the singleton — it dodges the keeper's AST match but the underlying production-code shape is unchanged. The HONEST fix is a production DI seam: routers/services take settings via `Depends(get_settings)` or kwarg, and tests use `app.dependency_overrides[get_settings] = lambda: stub_settings`. Same for the 6 logic-mock sites (UploadService method, EmailService class) — they need DI seams on the consuming service/router rather than method-level patching.

This project ships that real production DI rewrite.

---

## 2. Confirmed constraints

- **Production code IS in scope here** (parent project explicitly forbade prod changes; this project is the destination for that work).
- **Same green-test baseline**: `cd products/social-wiring/backend && pytest` stays at 384 passing.
- **Per-class triage**:
  - **Class A — Settings DI (41 sites)**: Routers + services that read `settings.X` directly migrate to `Depends(get_settings)` (FastAPI) or `settings: Settings = settings` kwarg (services). Tests replace `settings_override(...)` calls with `app.dependency_overrides[get_settings] = lambda: SocialWiringSettings(**overrides)`.
  - **Class B — UploadService DI (2 sites)**: Wire `_build_upload_service` as a FastAPI dependency; tests override with a fake-service factory that yields configured `UploadServiceError`s.
  - **Class C — EmailService DI (2 sites)**: Add `email_service_factory: Callable[..., EmailService] = EmailService` kwarg to `NotificationService.__init__`; tests inject `MagicMock`.
  - **Class D — Redis client (1 site)**: Convert `_redis_client()` factory in `intake_monitor_router.py` to a `Depends(get_redis_client)` dependency; tests use `app.dependency_overrides`.
  - **Class E — Email marketing audit/digest seams (3 sites)**: Already DI-seam-shaped (`get_audit_writer` factory); convert from module-attribute patching to a real `audit_writer_factory` parameter on `_record_audit` / `_generate_narrative`.

---

## 3a. Seed-first analysis

The DI patterns above are general: Pydantic-settings-via-`Depends` is the canonical FastAPI shape. The seed already exposes `make_get_current_user_org` (auth dep factory); a sibling **`make_get_settings(settings_class)` factory** in `noctusai_seed.config` (or `noctusai_lib.api`) belongs here for cross-product reuse.

**N≥2 check**: erp-imobiliario, core, daily-life, and seed all carry `monkeypatch.setattr(settings, "X", ...)` patterns (see `KB § PATTERNS/testing.md` § Severity ratchet table). Lifting this DI seam to the seed unlocks the same migration across the fleet. **Recurrence rule N≥3 → MUST formalize**.

---

## 4. Scope

**In scope:**
- Production code changes in `products/social-wiring/backend/app/` for the 5 classes above.
- Per-class test migration: from `settings_override(...)` to `app.dependency_overrides`.
- Conftest cleanup: remove `settings_override` once all 41 sites migrate.
- Same-session three-way sync: extend `KB § PATTERNS/di-test-seam.md` with Class-A (Pydantic-settings-via-`Depends`) recipe + reference implementation in social-wiring.

**Out of scope:**
- Other products' settings DI rewrites (per pilot-products-first cadence; social-wiring IS a pilot; non-pilots extend in a later wave).
- Seed-level `make_get_settings` factory lift (file as `seed-config-di-factory` follow-up if the recurrence count justifies it at this project's close).

---

## 6. Phases

- **P0 ⏳ — Audit.** Map each of the 50 production-code sites that consume `settings.X` / `EmailService` / `UploadService` / `_redis_client` / `get_audit_writer`. Identify which are router-level (use `Depends`) vs service-internal (use kwarg).
- **P1 ⏳ — Class-A pilot (settings DI).** Add `get_settings` dep to `app.dependencies`. Migrate `dashboard_router` (2 test sites, simplest). Verify pytest green. Three-way sync.
- **P2 ⏳ — Class-A fleet.** Migrate `settings_router`, `videos_router`, `upload_router` (the bulk). Remove `_YT_COMPLETE` helpers as their roles collapse into `app.dependency_overrides`.
- **P3 ⏳ — Class-B/C/D/E.** UploadService factory, EmailService factory, `_redis_client` Depends, audit_writer factory. Each migrates its 1-2 test sites alongside.
- **P4 ⏳ — Cleanup.** Remove `settings_override` from conftest.py. Remove all 9 `# self-patch-ok:` sanctioned markers. `check_no_self_monkeypatch` social-wiring count → 0. Ratchet severity to `high` for social-wiring (extend `_NO_SELF_MONKEYPATCH_HIGH_SEVERITY_PRODUCTS`).

---

## 9. Success criteria

- `cd products/social-wiring/backend && pytest` green at 384+ (no test count regression).
- `check_no_self_monkeypatch` social-wiring count: **9 → 0**.
- `settings_override` fixture removed from conftest.py.
- All 9 `# self-patch-ok:` markers removed.
- KB § PATTERNS/di-test-seam.md augmented with the Pydantic-settings-via-`Depends` Class-A recipe + social-wiring reference.
- `_NO_SELF_MONKEYPATCH_HIGH_SEVERITY_PRODUCTS` includes `social-wiring`.

---

## 10. How to use this plan

Fresh worktree off `origin/main`. Engineer obeys `.claude/agents/engineer-default.md`. P0 audit + P1 pilot first (read-only audit; small-scope pilot to validate the recipe). Then P2-P4 in sequence.

---

## 11. Change log

| Date | Entry | By |
|---|---|---|
| 2026-05-20 | Filed by Engineer SW-P5 as the named follow-up from `social-wiring-monkeypatch-test-refactor` P3 (9 sites sanctioned with `# self-patch-ok:` that require production DI to truly resolve). | Engineer SW-P5 |
