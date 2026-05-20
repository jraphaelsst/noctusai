# erp-portal-documentos-sharing-gate — Project Document

> **Filed 2026-05-20** as the P0 LGPD follow-up surfaced by ERP-P6 (erp-wiring Phase 6). Self-contained (durable-docs rule).
>
> **Symbol-first authoring** per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** ⏳ **IN PROGRESS** — P0+P1+P2 ✅ landed by Engineer D 2026-05-20; P3/P4/P5 deferred to next-wave dispatch.
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

- **P0 ✅** — Design interrogation. Architect-locked (2026-05-20): backfill = FALSE (safer-by-default, LGPD-aligned Art. 7 §3 + Art. 18); FE UX = per-document toggle in admin documents table (bulk-mark deferred to v2); audit-log = every portal-side READ + every admin-side toggle via `log_action()`.

  **Improvements:**
  - Applied inline: schema gap re-confirmed via grep — column genuinely absent at `001_erp_imobiliario.sql:1656` ∧ `004_mvp_expansion.sql:282`; partial index `idx_documentos_compartilhado_portal WHERE compartilhado_portal=true` added to support the hot portal read path without indexing dead rows.
  - Bystander: `portal_cliente.py` follow-up (`erp-imobiliario-dto-contract`) carries the parallel DTO-whitelist work; no scope creep here.

- **P1 ✅** — Migration `031_documentos_compartilhado_portal.sql` at `products/erp-imobiliario/backend/migrations/`. Adds `compartilhado_portal boolean NOT NULL DEFAULT false` + partial index. Mirror to Supabase MCP deferred to architect at landing time (engineer has no project_id binding in this dispatch).

  **Improvements:**
  - Applied inline: prelude shape mirrors `030_tool_call_audits.sql` (file-header `--` block + `SET search_path = erp, public;` + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`). `IF NOT EXISTS` makes the migration idempotent against partial rollouts.
  - Deferred to architect: Supabase MCP mirror (`mcp__claude_ai_Supabase__apply_migration`) — destination = architect's commit-time landing step; engineer surfaces the migration filename in return.

- **P2 ✅** — Backend filter + admin toggle endpoint + audit-log.
  - `portal_externo.py:portal_documentos` adds `.eq("compartilhado_portal", True)` + `log_action(..., 'documento_portal_acesso')` capturing cliente_id, doc_id list, portal_token_id.
  - `documentos.py:toggle_compartilhamento` ships `PATCH /api/documentos/{documento_id}/compartilhamento` with `DocumentoCompartilhamentoBody { shared: bool }`; role-gated `Depends(require_role("platform_admin", "owner", "admin", "manager"))`; logs `log_action(..., 'documento_compartilhamento')`.

  **Improvements:**
  - Applied inline: portal-side audit uses `pessoa_id` as the actor (the cliente, not the agent that issued the token) — this is what the Art. 18 right-to-know subject-access path needs to surface "who saw what about me." `detalhes` carries `documento_ids` + `org_id` + `portal_token_id` for cross-join reconstruction.
  - Applied inline: `DocumentoCompartilhamentoBody` extends `StrictHttpModel` → unknown fields → 422 (pinned in `test_toggle_unknown_field_rejected`).
  - Bystander: tests cover 7 status pins (admin-200 × 3 roles, corretor-403, default-user-403, missing-field-422, unknown-field-422, not-found-404) + filter-pin (shared+private both seeded → only shared returned). Status-code-assertion rule satisfied for every body assertion.

- **P3 ⏳** — Frontend: admin UI per-document toggle in admin documents table + portal-cliente view sync + one-time admin alert post-deploy ("N documents currently private; review and opt-in for portal sharing"). **Destination = next-wave dispatch** (engineer-default §6 — out of this dispatch's brief; FE was explicitly out-of-scope).
- **P4 ⏳** — Tests aligned to real schema; production-path pins. **Partially complete** in P2 (the filter + toggle paths pinned with 10 new tests). **Destination = next-wave dispatch** for the full sweep: align ALL test fixtures that seed `documentos` rows to the new schema column, add Supabase-MCP integration test that runs the migration against a clean DB and re-runs the suite.
- **P5 ⏳** — Verify: pytest green (this dispatch ⏳ — engineer runs locally), vite build green (FE wave), keeper review (cross-product), LGPD-WARNINGS.md entry resolved ✅ (this dispatch). **Destination = next-wave dispatch** for the keeper + vite gates after FE lands.

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
| 2026-05-20 | P0+P1+P2 landed by Engineer D: migration `031_documentos_compartilhado_portal.sql` + `portal_externo.py:portal_documentos` filter + audit-log + `documentos.py:toggle_compartilhamento` admin endpoint + 10 backend tests pinning filter/role-gate/422/404 paths. LGPD-WARNINGS.md entry resolved. P3/P4/P5 deferred to next-wave dispatch (destination = follow-up architect dispatch). | Engineer D |
