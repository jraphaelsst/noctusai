# adco-rewards-cross-tenant-fix — Project Document

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 1+2+3 ✅ — ready for FF merge by orchestrator
- **Owner / stakeholders:** Architect (orchestrator) · Engineer ADCO-REWARDS-CT-2
- **Related docs:**
  - `products/adconnect/backend/app/services/rewards_service.py`
  - `products/adconnect/backend/tests/services/test_rewards_engine.py`
  - `products/adconnect/backend/migrations/001_adconnect.sql` (§ Rewards — `recompensas_acumuladas`, `regras_recompensa`, `distributors`)
- **Project slug:** `adco-rewards-cross-tenant-fix` at `projects/` (cross-cutting safety fix, not yet a recurring pattern)

---

## 1. Context & Purpose

The `accrue_for_pedido` and `accrue_for_sellout_approval` functions in
`rewards_service.py` derived the brand's `org_id` from the source row
(`pedido_row.get("org_id")` / `relatorio_row.get("org_id")`) — but
`adconnect.pedidos` and `adconnect.relatorios_sellout` **do not have an
`org_id` column** in the migration. In production this returned `None`,
and `_fetch_active_rules(db, None)` fell back to "select every active
rule across every brand" — a **cross-tenant data leak**: org A's reward
rules would write accruals against org B's distributor's sellout report.

In addition, the accrual payload built by `_build_accrual_row` wrote three
keys that don't exist on `recompensas_acumuladas`: `org_id`, `moeda`,
`descricao`. The mock accepts unknown keys; production Postgres rejects
with `column ... does not exist`.

This project fixes both bugs and locks in regression tests.

---

## 2. Confirmed constraints

- **Cross-tenant safety is non-negotiable.** *(Rewards routing must scope to a single brand at all times.)*
- **Schema is the source of truth.** `recompensas_acumuladas` has no `org_id`, `moeda`, or `descricao` columns — those writes were silent bugs hidden by the mock's permissive behavior.
- **`tipo` + `status` CHECK constraints are a separate concern.** Service currently writes `"cashback_percentual"` / `"pendente"` literals that violate the column CHECK constraints (`tipo IN ('cashback','pontos')`, `status IN ('acumulado','resgatado','expirado')`). Filed as follow-up `adco-rewards-status-check-alignment` (see §6 Surfaced findings).
- **Mock SELECT doesn't filter by predicates.** `MockSupabaseClient`'s `_do_execute` for SELECT returns all seeded rows regardless of accumulated `.eq()` predicates (UPDATE/DELETE paths DO filter). Cross-tenant tests must use `set_responses([...])` instead of relying on `.eq()` filtering.

---

## 3. Design principles

1. **Resolve `org_id` from the authoritative source.** A distributor's owning brand is `adconnect.distributors.org_id`; never trust per-row `org_id` columns on derived tables.
2. **Belt-and-suspenders defense.** Two independent guards: (a) `_resolve_org_id` returns None for missing/orphan distributors; (b) `_fetch_active_rules` refuses falsy `org_id` and returns `[]`. Either alone would fix the leak; both together fail closed on any future regression in the resolver.
3. **No silent column drops.** Remove the three nonexistent payload keys so production INSERTs match the schema; rely on real Supabase to reject any future drift loudly.

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** NO — `adconnect.distributors` is product-specific; the cross-tenant leak shape is product-local.
2. **Is the data source product-specific?** YES — `adconnect.distributors` lives in the product schema.
3. **Is the placement product-specific?** YES — within `products/adconnect/backend/app/services/rewards_service.py`.
4. **Is the visibility / permission rule the same?** YES — RLS already on `distributors`; this fix is service-layer, not policy-layer.
5. **Does the seam already exist in seed?** N/A — pattern is "resolve owning-org via JOIN through the entity table", which is product-bound enough that promoting now would be premature.
6. **Default-on or opt-in?** N/A — pure bug fix.

**Litmus:** product-specific bug fix. Per-product code count = small section (one helper + two call sites + payload-keys removal). Correct location. *Not seed material yet — if N≥2 products end up doing the same JOIN-to-resolve-org_id pattern, file a seed follow-up.*

---

## 4. Scope

**In scope:**
- Add `_resolve_org_id(db, distributor_id)` helper that JOINs through `adconnect.distributors`.
- Replace `org_id = X_row.get("org_id")` with `org_id = _resolve_org_id(...)` in both accrue functions.
- Insert early-return guards: in accrue functions on `org_id is None`; in `_fetch_active_rules` on falsy `org_id`.
- Remove `org_id`, `moeda`, `descricao` keys + `org_id` parameter from `_build_accrual_row`.
- Cross-tenant regression tests + payload-shape test.

**Out of scope (filed as follow-ups):**
- `tipo` / `status` CHECK constraint alignment (`cashback_percentual` literal + `pendente` literal violate Postgres CHECK). See §6.
- Mock SELECT predicate-filtering (would benefit many tests; out-of-scope safety guard for this fix).
- Promoting the resolver pattern to `noctusai_lib` if other products do the same (N=1 today).

---

## 5. Architecture / Data Model

**The bug** (BEFORE):

```
accrue_for_sellout_approval(relatorio_row):
    org_id = relatorio_row.get("org_id")   # None — column doesn't exist
    rules = _fetch_active_rules(db, org_id) # falls back to all rules
                                            # CROSS-TENANT LEAK
```

**The fix** (AFTER):

```
accrue_for_sellout_approval(relatorio_row):
    distributor_id = relatorio_row["distributor_id"]
    org_id = _resolve_org_id(db, distributor_id)   # JOIN distributors → org_id
    if org_id is None: return []                   # explicit refusal
    rules = _fetch_active_rules(db, org_id)        # filtered to one brand
                                                   # _fetch_active_rules ALSO
                                                   # refuses falsy org_id
                                                   # (defense-in-depth)
```

**Schema facts:**
- `adconnect.distributors(id, org_id, ...)` — authoritative org ownership.
- `adconnect.pedidos(distributor_id, ...)` — **no `org_id` column**.
- `adconnect.relatorios_sellout(distributor_id, ...)` — **no `org_id` column**.
- `adconnect.recompensas_acumuladas(distributor_id, regra_id, valor, tipo, status, ...)` — **no `org_id`, no `moeda`, no `descricao` column**.

---

## 6. Implementation phases

### Phase 1: Cross-tenant `org_id` JOIN fix ✅

**Improvements:** none identified — bug fix with full regression coverage; CHECK-constraint + mock-predicate findings filed as separate follow-up projects in §6a.


- [x] Add `_resolve_org_id(db, distributor_id)` helper — JOIN via `distributors` table; returns None on missing / orphan / falsy.
- [x] `accrue_for_sellout_approval`: replace `org_id = relatorio_row.get("org_id")` with resolver call + early-return on None.
- [x] `accrue_for_pedido`: same replacement + early-return.
- [x] Applied via libcst codemod at `/tmp/rewards_codemod.py`.

### Phase 2: Remove nonexistent column writes ✅

**Improvements:** none identified — bug fix with full regression coverage; CHECK-constraint + mock-predicate findings filed as separate follow-up projects in §6a.


- [x] Drop `org_id` parameter from `_build_accrual_row` signature.
- [x] Drop `org_id`, `moeda`, `descricao` keys from the payload dict.
- [x] Drop `org_id=org_id` kwarg from both call sites.
- [x] Applied via the same codemod.

### Phase 3: Regression tests ✅

**Improvements:** none identified — bug fix with full regression coverage; CHECK-constraint + mock-predicate findings filed as separate follow-up projects in §6a.


- [x] `test_resolve_org_id_via_distributors_table` — happy path.
- [x] `test_resolve_org_id_returns_none_when_distributor_missing` — orphan refusal.
- [x] `test_resolve_org_id_returns_none_when_distributor_id_falsy` — short-circuit on falsy.
- [x] `test_fetch_active_rules_refuses_falsy_org_id` — defense-in-depth guard.
- [x] `test_cross_tenant_accrual_refused_when_distributor_orphan` — end-to-end refusal via `accrue_for_sellout_approval`.
- [x] `test_accrual_refused_when_pedido_distributor_orphan` — same for `accrue_for_pedido`.
- [x] `test_payload_excludes_nonexistent_columns` — pins Phase 2 deletions (org_id, moeda, descricao MUST NOT appear in payload).
- [x] Updated `_build_db` helper to seed a default distributors row mapping `DIST → ORG` (without this every pre-existing test would fail closed under the new resolver).

### Phase 4: Defense-in-depth ✅

**Improvements:** none identified — bug fix with full regression coverage; CHECK-constraint + mock-predicate findings filed as separate follow-up projects in §6a.


- [x] `_fetch_active_rules`: refuse falsy `org_id` with explicit `[]` return + WARN log. Removes the "fallback to all rows" semantic.

---

## 6a. Surfaced findings (out of scope — for follow-up)

**`adco-rewards-status-check-alignment` (FILE THIS PROJECT)** — the `recompensas_acumuladas` table has CHECK constraints the service violates:
- `tipo IN ('cashback', 'pontos')` — service writes `rule.get("tipo")` which is `'cashback_percentual'` / `'cashback_fixo'` from `regras_recompensa.tipo` CHECK (`'cashback_percentual', 'cashback_fixo', 'pontos'`). The two enum spaces don't overlap.
- `status IN ('acumulado', 'resgatado', 'expirado')` — service writes `'pendente'`. Doesn't appear in the allowed set.

Mock accepts; **production Postgres will reject every accrual INSERT**. This is a separate bug — alignment work (either pick one enum space and migrate, or fold the discrepancy into the service translation layer) is out of scope for this PR. **Defer to a focused project.**

**`adco-mock-select-predicate-filter` (consider for seed-lib)** — `MockSupabaseClient._do_execute` for SELECT doesn't evaluate `.eq()` / `.in_()` / etc. predicates against seeded rows (only UPDATE/DELETE paths do). This forced the cross-tenant tests to use `set_responses(...)` instead of natural `set_table_data + .eq()`. Across the codebase, many tests have likely been written expecting SELECT to filter — they pass by accident because the test happens to seed only the relevant rows. A focused audit + fix would benefit many products. **Defer to a seed-lib project.**

---

## 7. Open questions

None — all design decisions either confirmed by the brief or settled by reading the schema.

---

## 10. Verification commands (copy-paste ready)

```bash
# From repo root:
export PYTHONPATH="$(pwd)/seed/lib/backend:$(pwd)/seed/framework/backend:$(pwd)/products/adconnect/backend"

# Targeted rewards engine tests:
cd products/adconnect/backend && python -m pytest tests/services/test_rewards_engine.py -v

# Full adconnect backend regression:
cd products/adconnect/backend && python -m pytest -q
# Expected: 247 passed, 18 skipped (was 240+18 pre-fix; +7 new regression tests)
```

---

## 11. Change log

- **2026-05-11 (Engineer ADCO-REWARDS-CT-2, continuation engineer):**
  - Previous engineer (ADCO-REWARDS-CT-1) applied Phase 1+2 via libcst codemod but couldn't complete Phase 3 / commit before ENOSPC.
  - Old worktree was swept by orchestrator cleanup; re-applied Phase 1+2 from scratch via fresh libcst codemod (same shape as documented).
  - Applied Phase 4 (defense-in-depth in `_fetch_active_rules`).
  - Wrote 7 new regression tests in Phase 3 (3 resolver-focused, 1 fetch-guard, 2 end-to-end orphan refusal, 1 payload-shape).
  - Updated `_build_db` helper to seed default distributors row.
  - Surfaced `adco-rewards-status-check-alignment` + `adco-mock-select-predicate-filter` as follow-up projects (§6a).
  - 247 passed + 18 skipped (baseline `233 + 18` per brief was stale; current run shows 247 — delta of 14 = 7 prior rewards-engine tests + 7 new).
