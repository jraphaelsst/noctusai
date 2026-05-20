# erp-financial-surfaces-role-gate — Project Document

> **Filed 2026-05-20** as the N=4 DRY follow-up surfaced by ERP-P7 (erp-wiring Phase 7). Self-contained (durable-docs rule).
>
> **Symbol-first authoring** per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** 📋 **FILED** — N=4 DRY recurrence; formalize-pass scope.
- **Owner / stakeholders:** joaoraphaelsst@gmail.com · architect
- **Related docs:**
  - `LGPD-WARNINGS.md` entries (4): financeiro / dimob / impostos / banco router role-gate gaps
  - `KB § PATTERNS/backend.md § Auth — canonical pattern` (the `make_require_role` factory + `app/dependencies.py:121` binding)
  - `KB § PATTERNS/lgpd.md`
- **Project slug:** `erp-financial-surfaces-role-gate` (root `projects/`)

---

## 1. Context & Purpose

ERP-P7 (erp-wiring Phase 7 LGPD audit) surfaced that 4 ERP financial/fiscal routers — `financeiro`, `dimob`, `impostos`, `banco` — share the **exact same shape**: **write endpoints are audit-logged via `log_action()`** but **read endpoints are NOT audit-logged AND NOT role-gated**. Every authenticated team member can list/export the org's full financial/fiscal/banking ledger.

This is the N=4 instance of the role-gate-gap pattern → recurrence rule fires hard ⇒ MUST formalize.

---

## 2. Confirmed constraints

- **All 4 routers share the same fix shape**: `Depends(require_role(...))` on read endpoints + `log_action()` on aggregate reads (`/resumo`, `/fluxo-caixa`, `/preview`, etc.).
- **The `require_role` factory already ships** at `app/dependencies.py:121` (bound via `make_require_role(get_current_user, get_erp_user_role)`).
- **Per-router role tuple differs slightly**:
  - financeiro/banco → `("platform_admin", "owner", "admin", "manager")` (general financial)
  - dimob/impostos → `("platform_admin", "owner", "admin", "contador")` (accounting-tier)
  - Final tuple TBD in P0 design.

---

## 3a. Seed-first analysis

The `make_require_role` factory IS the seed-shaped solution (already in `noctusai_seed`). Per-product role-tuple decision stays product-local. **NO new seed code** — this is consumption-side adoption of an existing seed seam.

Litmus: per-product code in seed = 0 LoC.

---

## 4. Scope

**In scope:**
- `financeiro.py`, `dimob.py`, `impostos.py`, `banco.py` — add `Depends(require_role(...))` to read endpoints + `log_action()` to aggregate reads.
- LGPD-WARNINGS.md: resolve the 4 entries.
- Tests: per-router gate tests (admin allowed, non-admin 403).

**Out of scope:**
- New read-audit-log table — uses existing `log_action()` infrastructure.
- Retention/purge policy for read events — separate concern; default to existing `log_action` retention.

---

## 6. Phases

- **P0 ⏳** — Design interrogation: confirm role-tuple per router (financeiro/banco general vs dimob/impostos accountant-tier); confirm read-event audit-log scope (aggregate-only ∨ all reads).
- **P1 ⏳** — Apply role-gates + read-audit-logs to the 4 routers (file-disjoint; can parallel-dispatch).
- **P2 ⏳** — Tests: per-router gate (admin allowed, contador allowed where applicable, non-admin 403). 4-5 tests per router.
- **P3 ⏳** — Verify: pytest green, keeper 0 issues, LGPD-WARNINGS.md entries resolved.

---

## 7. Open questions

1. **Final role-tuple per router?** Recommendation: financeiro/banco → `(platform_admin, owner, admin, manager)`; dimob/impostos → `(platform_admin, owner, admin, contador)`. Confirm.
2. **Aggregate-only read-audit ∨ all reads?** Recommendation: aggregate-only (`/resumo`, `/fluxo-caixa`, `/preview`) — the high-exfiltration shapes; per-id reads stay un-logged.

---

## 9. Success criteria

- 4 routers gate read access via `Depends(require_role(...))`.
- Aggregate-shape reads log via `log_action()`.
- 4 LGPD-WARNINGS.md entries resolved.
- pytest green (new gate tests pass; existing tests unaffected if they use admin tokens).
- Keeper 0 issues.

---

## 11. Change log

| Date | Entry | By |
|---|---|---|
| 2026-05-20 | Filed as the N=4 DRY follow-up from erp-wiring Phase 7 audit. Surface candidate for absorption review — N=4 within one product (4 routers same shape); cross-product N=2+ would trigger seed-formalization. | Architect |
