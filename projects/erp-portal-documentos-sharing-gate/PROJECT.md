# erp-portal-documentos-sharing-gate — Project Document

> **Filed 2026-05-20** as the P0 LGPD follow-up surfaced by ERP-P6 (erp-wiring Phase 6). Self-contained (durable-docs rule).
>
> **Symbol-first authoring** per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** 📋 **FILED** — design needs interrogation; NOT a 1-line hotfix as initially scoped.
- **Owner / stakeholders:** joaoraphaelsst@gmail.com · architect
- **Related docs:**
  - `LGPD-WARNINGS.md` entry: "Public bearer-token endpoint surfaces full documentos rows without filter on document sensitivity / sharing-status flag"
  - `KB § PATTERNS/lgpd.md` (the five questions)
  - `archive/projects/2026-05-20/...erp-wiring/PROJECT.md` (parent that surfaced this)
- **Project slug:** `erp-portal-documentos-sharing-gate` (root `projects/`)

---

## 1. Context & Purpose

`products/erp-imobiliario/backend/app/routers/portal_externo.py:portal_documentos` (line ~290) returns ALL `erp.documentos` rows for a portal-cliente bearer token, filtered only by `org_id + cliente_id`. Documents may carry CPF, contract scans, ID copies, sensitive financial annexes — LGPD Art. 5 + Art. 11 surface.

ERP-P6's audit surfaced this as P0: "production code is more permissive than the test contract — the fixture sets `compartilhado_portal: True` but the production query has no filter on that field." Engineer recommended a 1-line `.eq("compartilhado_portal", True)` fix.

**Re-audit at filing (2026-05-20):** `erp.documentos` does NOT ship a `compartilhado_portal` column at all (migrations `001_erp_imobiliario.sql:1656` + `004_mvp_expansion.sql:282` both define the table without this column). The test fixture asserts a column that doesn't exist in the production schema — the mock predicate passes by coincidence; in production, every row would lack the field. **The P0 is a multi-phase project, not a hotfix.**

---

## 2. Confirmed constraints

- **Schema change required.** Cannot add the filter without adding the column first.
- **Backfill policy decision required.** Existing rows: default `FALSE` (no docs visible until explicitly shared — safer) OR default `TRUE` (preserve current behavior, opt-out via FE) — user/architect decision.
- **FE UX surface required.** Admin needs a way to mark documents as compartilhado-with-portal (or the inverse: mark them as private).
- **LGPD Art. 7 §3 + Art. 18 alignment.** Cliente has data-subject rights to know what's exposed; the gate is the platform's compliance-anchor for portal-shared-documents.

---

## 3a. Seed-first analysis

This is product-specific (ERP-imobiliário's portal-cliente flow). NO seed concern — the per-document sharing flag is a domain-specific contract. Per-product code count: this is the only product with portal-cliente documentos exposure currently. If a 2nd product surfaces a similar shape, file an absorption candidate.

Litmus: per-product code in seed = 0 LoC. This is properly product-local.

---

## 4. Scope

**In scope:**
- Migration adding `erp.documentos.compartilhado_portal boolean NOT NULL DEFAULT <decided>`
- Backend: filter at `portal_externo.py:portal_documentos` query + audit-log read access
- Backend: admin endpoint to toggle the flag (PATCH `/api/documentos/{id}/compartilhamento` or similar)
- Frontend: admin UI to mark documents compartilhado (per-document toggle in admin documents view)
- Frontend: portal-cliente view shows only shared documents
- Tests: align fixture to actual schema; production-path tests pin the filter

**Out of scope:**
- Per-document sensitivity-class (sensitive/normal/public) — surfaced as a v2 destination if needed.
- Retroactive PII redaction on existing document text — separate project.
- Other portal_* endpoints (3 select-star surfaces deferred to `erp-imobiliario-dto-contract`).

---

## 6. Phases

- **P0 ⏳** — Design interrogation. Confirm: backfill policy default (FALSE-safer-by-default ∨ TRUE-preserve-behavior); FE UX (per-document toggle ∨ bulk-share-on-portal-issue ∨ inherit-from-contract); audit-log scope.
- **P1 ⏳** — Migration (add column + default + backfill SQL). Mirror in Supabase MCP.
- **P2 ⏳** — Backend filter + admin toggle endpoint + audit-log.
- **P3 ⏳** — Frontend: admin UI + portal-cliente view sync.
- **P4 ⏳** — Tests aligned to real schema; production-path pins.
- **P5 ⏳** — Verify: pytest green, vite build green, keeper review, LGPD-WARNINGS.md entry resolved.

---

## 7. Open questions

1. **Backfill default for existing rows?** *Recommendation:* `FALSE` — safer-by-default; cliente explicitly authorizes sharing per-document. Risk: portal users lose immediate access until admin marks docs. Mitigation: surface a one-time admin alert post-deploy.
2. **FE UX shape?** *Recommendation:* per-document toggle in admin documents table (simplest); future: bulk-mark on portal-token-issue.
3. **Audit-log granularity?** *Recommendation:* log every portal-side READ + every admin-side toggle; the cliente has Art. 18 right to know exposure history.

---

## 9. Success criteria

- `erp.documentos` has `compartilhado_portal` column with documented default.
- `portal_documentos` query filters by `compartilhado_portal=True`.
- Admin can toggle the flag per document; portal-cliente sees only shared docs.
- LGPD-WARNINGS.md entry for `/documentos` resolved.
- pytest green; vite build green; keeper 0 issues.

---

## 11. Change log

| Date | Entry | By |
|---|---|---|
| 2026-05-20 | Filed as the P0 LGPD follow-up from erp-wiring Phase 6. Re-audit revealed it's a multi-phase project (column doesn't exist yet), not a 1-line hotfix. Architect. | Architect |
