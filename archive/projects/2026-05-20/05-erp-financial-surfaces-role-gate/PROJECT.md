# erp-financial-surfaces-role-gate — Project Document

> **Filed 2026-05-20** as the N=4 DRY follow-up surfaced by ERP-P7 (erp-wiring Phase 7). Self-contained (durable-docs rule).
>
> **Symbol-first authoring** per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** ✅ **EXECUTED** — N=4 DRY recurrence; formalize-pass scope. Phases P0/P1/P2/P3 ✅; LGPD entries resolved; 95 new gate tests + 47 existing router tests green.
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

- **P0 ✅** — Design interrogation: role-tuples locked by architect — financeiro/banco → `("platform_admin", "owner", "admin", "manager")`; dimob/impostos → `("platform_admin", "owner", "admin", "contador")`. Audit-log scope: AGGREGATE-only (`/resumo`, `/fluxo-caixa`, `/preview`, `/validate`, `/extratos`, `/conciliacao`); per-id GETs un-logged.
  **Improvements:**
  - Applied inline: ø (decisions inherited from brief; no Phase-0 audit triggered).
  - Bystander: ø.
- **P1 ✅** — Applied role-gates + read-audit-logs to all 4 routers (file-disjoint single engineer-C dispatch — no need to parallel-fan).
  **Improvements:**
  - Applied inline: 4 router edits via `Edit` (AST-safe Python literal swaps — replacing `Depends(get_current_user)` → `Depends(require_role(*ROLES))` + tuple-unpack of `(user, token, role)`); local module-scope role-tuple constants `_FINANCEIRO_READ_ROLES`/`_DIMOB_ROLES`/`_IMPOSTOS_ROLES`/`_BANCO_ROLES` keep the gate values visible at the import block (caveman-readable).
  - Deferred (with destination): **write-side role-gating** (POST/PATCH/DELETE on the 4 routers stay on `Depends(get_current_user)`) — the brief locked "read endpoints" only; writes still audit-log every mutation via `log_action`, so attribution is preserved. Destination: file follow-up `erp-financial-surfaces-write-role-gate` if the per-router LGPD audit fires N=4 again on the write surface OR if pen-test surfaces a write-without-role exploit. Reasoning recorded in the LGPD-WARNINGS.md `financeiro` resolution line.
  - Bystander: ø (no MCP-first / AST-first opportunity surfaced this phase; routers are already AST-edit-friendly).
- **P2 ✅** — 4 new role-gate test files (`tests/routers/test_{financeiro,dimob,impostos,banco}_role_gate.py`) + per-file autouse role-promotion fixture in the 4 existing router tests so they stay green under the new gate. 95 role-gate tests, all `.status_code`-asserted per status-code-assertion rule. Coverage shape: allowed-role-parametrized × {list,resumo,fluxo,preview,validate,extratos,conciliacao,retorno,…} + forbidden-role-parametrized + per-aggregate audit-log call assertion.
  **Improvements:**
  - Applied inline: chose per-router-module `patch("app.routers.<x>.log_action", mock)` for audit-log assertions instead of relying on the conftest's `app.dependencies.log_action` patch — the latter doesn't intercept the router-module re-export (Python binds local names at `from ... import` time). This matches the convention already established in `test_matriculas_router.py`. Documented in each `TestReadAuditLog` docstring.
  - Bystander finding (proactive): the noctusai testing kit could ship a `patch_log_action_on_router(router_module)` context-manager helper to make this convention discoverable. N≥4 same-shape — silently absorbed into engineer findings (see §11 + findings.md). Destination: `noctusai_lib.testing` enhancement, recorded as a P5-tier opportunity.
- **P3 ✅** — Verification:
  - 4 new gate test files: `pytest tests/routers/test_*_role_gate.py` → **95 passed**.
  - 4 existing router test files: `pytest tests/routers/test_{financeiro,dimob,impostos,banco}_router.py` → **47 passed** (autouse fixture preserves prior contracts).
  - Full ERP backend suite: `pytest` → **2035 passed, 31 failed, 34 skipped**. The 31 failures are pre-existing baseline (`git stash -u` → re-run → diff failure-sets = 0). Untouched by this project.
  - 4 LGPD-WARNINGS.md entries marked `[x]` with strike-through + resolution line per brief.
  **Improvements:**
  - Applied inline: the pre-edit baseline diff was paired (stash-untracked-included + re-run + sorted-grep-diff) — sanctioned methodology for "is my change neutral on pre-existing failures?". Used twice this session.
  - Deferred (with destination): the 31 pre-existing failures span `certidoes`, `emails`, `configuracoes`, `whatsapp_webhook`, `gamificacao`, `bi_dashboard`, `site_imoveis`. They are pre-existing as of fork-base SHA 3695b87e and were not part of the engineer-C brief scope. Destination: surface to architect for triage routing (separate follow-up). Not silently swallowed — explicit in §11 below.
  - Bystander: ø.

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
| 2026-05-20 | P0/P1/P2/P3 executed by engineer-C (single-engineer dispatch, file-disjoint scope). All 4 LGPD-WARNINGS entries resolved with strike-through + resolution line. 95 role-gate tests + 47 existing router tests green. Full backend suite shows 31 pre-existing failures, NEUTRAL Δ (verified via `git stash -u` baseline diff). Write-side role-gating deferred to follow-up; recorded in LGPD financeiro entry. The replication-to-seed test: per-router code count = 4 lines (one role-tuple constant per file) — within-product N=4 not cross-product, seed factory `make_require_role` already exists, so no new seed code (litmus per §3a satisfied: seed code 0 LoC). | Engineer C |
