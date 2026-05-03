# Digest Helpers Absorption — Project Document

> **Why this project exists.** The recurrence rule fires on two helper names
> across the digest-shaped services in 4-5 products: `_render_bodies` (core,
> daily-life, erp-imobiliario, mailing, personal-finance — N=5) and
> `_generate_narrative` (core, daily-life, mailing, personal-finance — N=4).
> Each implementation differs only in domain references (table names, field
> keys, period vocabulary). The shared shell is the absorption target;
> per-product wrappers pass domain-specific args.
>
> **Filed by `projects/side-projects-batch/` Phase 3.b** as the Phase 5
> calibration follow-up. The recurrence count exceeds `MUST formalize` (N≥3)
> and has been at this level since the absorption-search trio shipped.
> Phase 0 interrogation pending.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** 📋 **FILED** — Phase 0 interrogation pending. No phases designed yet.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Project slug:** `digest-helpers-absorption`
- **Project location:** `projects/digest-helpers-absorption/` (cross-product / platform-infra — lands seed-side digest primitives + migrates 5 products)
- **Related docs:**
  - `KB § 04-SHARED-LIBRARY.md` — current digest module conventions in `noctusai_lib.domain.digest`.
  - `KB § PATTERNS/seed-lib-layout.md` — for layer placement.
  - `KB § PATTERNS/project-execution.md § 2.7 The recurrence rule`.
  - Parent batch: `projects/side-projects-batch/PROJECT.md` Phase 3.b.

---

## 1. Context & Purpose

The five digest-shaped services that implement weekly/monthly/per-period summary generation share a near-identical scaffolding shape:

- `products/core/backend/app/services/audit_digest_service.py`
- `products/daily-life/backend/app/services/weekly_review_service.py`
- `products/erp-imobiliario/backend/app/services/metas_digest_service.py`
- `products/mailing/backend/app/services/campaign_debrief_service.py`
- `products/personal-finance/backend/app/services/monthly_narrative_service.py`

Common helpers per product:

- `_render_bodies(...)` (5/5 products) — assembles email/notification bodies from a context dict + Jinja templates, dispatches to recipients.
- `_generate_narrative(...)` (4/5 products — ERP's metas digest carries an accept-with-rationale entry that excludes it from this absorption per `KB § PATTERNS/accept-with-rationale.md`) — calls the LLM with a per-product prompt + period context, returns prose for the digest body.

Both helpers also share the `_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "email_templates"` line (5 products) — that's a third absorption candidate.

The bodies differ only in:
- Domain dict keys (`metas_realizadas` vs `revisões_da_semana` vs `campanhas_disparadas`)
- Template paths (`audit_digest.html` vs `weekly_review.html` vs `metas_digest.html`)
- Recipient resolution (org members vs solo user vs clinic team)
- Period vocabulary (semana / mês / período)

Win: ship `noctusai_lib.domain.digest` (already exists per related-doc reference) with `render_digest_body(context, template_name, recipient_list, ...)` + `generate_narrative_for_period(context, prompt_template, period, ...)` primitives. Per-product wrappers shrink to ~10-15 lines; the shared shell stops drifting.

---

## 2. Confirmed constraints

_(filled at Phase 0 interrogation)_

Candidate questions:

- **ERP metas digest accept-with-rationale carve-out** — already documented (`KB § PATTERNS/accept-with-rationale.md` § ERP metas digest). Does it ALSO carve out `_render_bodies`, or only `_generate_narrative`? Phase 0 reads the catalog entry + the actual divergence to decide.
- **Per-product wrapper shape** — Class-based `XxxDigestService(SeedDigestService)` inheritance OR module-level wrapper with `render_xxx_digest(...)` calling primitives directly? *Recommendation:* module-level wrappers; OO inheritance creates seed-product coupling that's hard to evolve.
- **Migration cadence** — one commit per product migration so each is bisectable. Order: smallest diff first (likely mailing or PF), then digest-by-digest.

---

## 3. Design principles

_(filled at Phase 0 interrogation; provisional)_

1. **Primitive-and-wrapper, not inheritance.** Cleaner evolution path; products stay independent.
2. **Templates stay per-product.** Each digest's HTML/Jinja template is product-specific (different prose); only the rendering shell moves.
3. **Accept-with-rationale ERP metas carve-out preserved.** Don't try to absorb past a documented divergence.

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** YES — the helpers' shape is identical; only the domain args differ.
2. **Is the data source product-specific?** YES — per-product hooks resolve the digest's content; the *container* is seedable.
3. **Is the placement product-specific?** NO — digest-rendering is universal infrastructure.
4. **Is the visibility / permission rule the same?** YES — admin-client access for the recipient resolution + email send.
5. **Does the seam already exist in seed?** PARTIALLY — `noctusai_lib.domain.digest` has primitives; this project wires the shell helpers consistently.
6. **Default-on or opt-in?** OPT-IN. Products that don't ship a digest don't import the primitives.

**Per-product code count after migration:** ~10-15 lines per product (wrapper). 0 framework code.

---

## 4. Scope

**In scope:**
- New / extended `noctusai_lib.domain.digest` — `render_digest_body` + `generate_narrative_for_period` primitives.
- Tests at `seed/backend/lib/tests/domain/test_digest.py`.
- Migration of 4 products' `_render_bodies` (excluding ERP per accept-with-rationale): mailing, personal-finance, daily-life, core.
- Migration of 3 products' `_generate_narrative` (mailing, personal-finance, daily-life, core; ERP excluded).
- KB doc update at `KB § 04-SHARED-LIBRARY.md § domain/digest`.
- Final scan rerun: confirm `_render_bodies` count drops from 5 → 1 (ERP only), `_generate_narrative` from 4 → 0.

**Out of scope:**
- `_TEMPLATE_DIR` Path expression (also recurring at N=5) — separate, smaller absorption project.
- Frontend changes — none of these helpers touch frontend.

---

## 6. Implementation phases

### Phase 0 — Audit + design

- [ ] Read each of the 5 `*_digest_service.py` files end-to-end; capture the divergence inventory in §11.
- [ ] Read `noctusai_lib.domain.digest` current state — what primitives already exist?
- [ ] Decide primitive shape (signatures, dependency injection seams).
- [ ] Confirm or revise §2 / §3 with user.

### Phase 1+ — Migrate (designed at Phase 0)

_(per-product migration phases land here once design is locked)_

---

## 7. Open questions

1. **Accept-with-rationale scope** — does ERP carve out apply to both helpers or just `_generate_narrative`?
2. **Primitive shape** — class-based vs module-level. Recommendation: module-level.
3. **Migration ordering** — smallest-diff first or domain-priority order?

---

## 8. Dependencies & blockers

- None at filing time. Pure DRY work.

---

## 9. Success criteria

- `noctusai_lib.domain.digest` lands with primitives + tests + KB doc.
- 4 products migrated for `_render_bodies` (5 → 1 ERP only).
- 3 products migrated for `_generate_narrative` (4 → 0).
- Platform test baseline preserved.
- `noctusai_scan_cross_product_helpers` rerun shows the recurrence rule no longer fires on these names.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | **Project filed** as the Phase 5 calibration follow-up surfaced by `projects/side-projects-batch/` Phase 3.b. Scans confirmed `_render_bodies` (N=5) + `_generate_narrative` (N=4) standing recurrences. Phase 0 interrogation pending. | Claude Opus 4.7 |
