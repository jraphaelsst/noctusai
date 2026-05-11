# keeper-detector-schema-chain-tuning — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** ⏳ **EXECUTING — Wave 0 child B of `projects/keeper-trio-platform-triage`.**
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Related docs:** `projects/keeper-trio-platform-triage/PROJECT.md` (parent), `projects/keeper-trio-platform-triage/phase-0-triage.md` (Engineer RR triage — surfaces the FALSE_POSITIVE this project closes)
- **Project slug:** `keeper-detector-schema-chain-tuning`

---

## 1. Context & Purpose

Engineer II's keeper-trio (`check_unknown_table_references` + `check_admin_endpoint_service_role_bypass`) walks Python ASTs in each product's `backend/app/**/*.py` and flags `.table("X")` callsites where `X` is not declared by a local `CREATE TABLE`, or where the admin-client target lacks a `service_role_bypass` policy. The walker treats every `.table(X)` as a **local-schema reference**.

That assumption breaks for **cross-schema admin calls**: `db.schema(Y).table("X")` where `Y` is another product's schema. The canonical site is `products/core/backend/app/routers/admin_llm_usage.py:92` — a platform-admin endpoint that aggregates LLM usage across ERP + therapy by iterating `_PRODUCT_SCHEMAS = {"erp-imobiliario": "erp", "therapy-platform": "therapy"}` and calling `db.schema(schema).table("llm_usage")`. The `llm_usage` tables exist (`products/erp-imobiliario/backend/migrations/020_llm_usage.sql` + `products/therapy-platform/backend/migrations/006_llm_usage.sql`), but the detector looks for them in `products/core/backend/migrations/*.sql` and finds nothing → FALSE_POSITIVE.

N=1 today, but every new product schema added to `_PRODUCT_SCHEMAS` (or any future cross-schema admin call) ships a new false positive → recurrence is structural. Tune the detector now before consumers proliferate.

---

## 2. Confirmed constraints

- **Heuristic limits are OK** — when the `.schema(Y)` argument is a runtime variable (the canonical core/admin_llm_usage site uses `schema` from a loop), the detector cannot resolve it at AST time. Right shape: detect the *presence* of a `.schema(...)` call anywhere in the chain and **skip the unknown-table + admin-bypass checks** for that callsite. *(Document explicitly — false-negative trade.)*
- **AST-first** — the detector itself IS an AST walker; preserve that shape. *(`compliance.py` already uses `ast.walk` + `ast.Call`. No regex code edits.)*
- **No detector test deletion — extend, don't replace.** *(Regression-test-the-detector convention.)*
- **DO NOT tune the `service_role_bypass` policy NAME heuristic** — that's a separate decision (RR flagged in triage; orchestrator may file a follow-up). This dispatch is schema-chain only.

---

## 3. Design principles

1. **Preserve false-negative-over-false-positive policy.** When in doubt, skip the check. The cross-schema slip cannot generate the kind of silent runtime failure the original detector defends against (the cross-schema `.schema(X)` chain literally targets a different schema's table — if X is wrong the runtime error is loud).
2. **Chain detection over schema resolution.** Don't try to map `schema → product slug → migrations dir`. The runtime variable case is unresolvable; statically-resolved string args would let us look up the foreign migrations, but that's strictly more code for an N=1 marginal gain. **Skip = right shape.**
3. **Same skip logic in both detectors.** The unknown-table walker fires today; the admin-bypass walker silently skips the chain because its receiver-shape check requires `Name`/`get_admin_client()` receivers (and `db.schema(Y)` is a `Call`). Apply the explicit-skip helper to both so a future refactor (e.g. teaching admin-bypass to follow chains) doesn't reintroduce the gap.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** — N/A. This project modifies an MCP-toolkit detector that already runs across every product; the fix is centralized at one site (`mcp/noctusai/tools/noctus/dev/compliance.py`).
2. **Is the data source product-specific?** — No. AST shape of `.schema(Y).table(X)` is identical wherever it occurs.
3. **Is the placement product-specific?** — No. Lives in `mcp/noctusai/` (the platform-wide keeper toolkit).
4. **Is the visibility / permission rule the same?** — Yes.
5. **Does the seam already exist in seed?** — Yes. The detector module `mcp/noctusai/tools/noctus/dev/compliance.py` IS the platform-wide seam.
6. **Default-on or opt-in?** — Default-on (the detectors already run; the tuning is an internal calibration).

**Litmus — per-product code count this design requires:** **0 lines.** Pure platform-wide concern; lives entirely in `mcp/noctusai/`.

**Phase plan implications:** phases work in the MCP toolkit (correct).

---

## 4. Scope

**In scope:**
- New helper `_has_schema_in_chain(call: ast.Call) -> bool` in `compliance.py` — walks backward from a `.table(...)` call's receiver chain looking for a `.schema(...)` Call node.
- Apply skip in `check_unknown_table_references` and `check_admin_endpoint_service_role_bypass`.
- Regression tests in `mcp/noctusai/tests/test_compliance_prod.py` (extend the two existing classes).
- Document the heuristic limit (runtime-variable schema arg → unresolvable → conservative skip).
- Re-run `cli.py --review --product core` to verify the 1 FP unknown_table row clears.

**Out of scope:**
- Resolving `schema` runtime values to cross-product migrations (left as a documented heuristic limit).
- Tuning the `service_role_bypass` policy NAME heuristic (separate concern flagged in triage).
- Wave 1 per-product fixes (separate children dispatch).

---

## 5. Architecture / Data Model

Single-file change at `mcp/noctusai/tools/noctus/dev/compliance.py`:

```python
def _has_schema_in_chain(call: ast.Call) -> bool:
    """True if `call` is `<receiver>.schema(...).…table(...)`.

    Walks backward from the `.table(...)` call's receiver chain looking for
    an `ast.Call` whose `.func.attr == "schema"`. Stops at the first non-Call
    receiver (`Name`/`Attribute`).
    """
    receiver = call.func.value  # caller guarantees call.func is Attribute
    while isinstance(receiver, ast.Call):
        if (
            isinstance(receiver.func, ast.Attribute)
            and receiver.func.attr == "schema"
        ):
            return True
        receiver = receiver.func.value if isinstance(receiver.func, ast.Attribute) else None
        if receiver is None:
            break
    return False
```

Both detectors gate on this helper BEFORE the table-name extraction:

```python
for call in _iter_table_callsites(tree):
    if _has_schema_in_chain(call):
        continue  # cross-schema reference — foreign migration tree, can't verify
    # … existing logic …
```

For `check_admin_endpoint_service_role_bypass`, the existing receiver-shape check (`Name` for bound, `get_admin_client()` for chained) already silently misses `.schema(Y).table(...)` because `db.schema(Y)` is a `Call` — but adding the explicit skip closes the gap structurally so future refactors don't reintroduce a false positive.

---

## 6. Implementation phases

### Phase 0 — Read + baseline ✅

- [x] Read `mcp/noctusai/tools/noctus/dev/compliance.py` (relevant detector functions + helpers).
- [x] Read `products/core/backend/app/routers/admin_llm_usage.py` for canonical chain shape.
- [x] Verify cross-schema tables exist (`erp.llm_usage`, `therapy.llm_usage`).
- [x] Baseline: `cli.py --review --product core` → 151 issues (149 admin_bypass + 2 unknown_table). 1 of the 2 unknown_table rows is the FP at `admin_llm_usage.py:92`. The admin_bypass detector already silently skips this site (receiver-shape mismatch).

### Phase 1 — Detector tuning ✅

- [x] Add `_has_schema_in_chain` helper.
- [x] Gate `check_unknown_table_references` on the helper.
- [x] Gate `check_admin_endpoint_service_role_bypass` on the helper (defense-in-depth — closes the gap structurally).

### Phase 2 — Tests ✅

- [x] Extend `TestCheckUnknownTableReferences`:
  - `test_schema_chained_table_call_is_skipped` — literal `.schema("erp").table("foo")` → no flag even though `foo` not in local migrations.
  - `test_dynamic_schema_chain_is_skipped` — `.schema(var).table("foo")` → no flag.
- [x] Extend `TestCheckAdminEndpointServiceRoleBypass`:
  - `test_schema_chained_admin_call_is_skipped` — `admin_db.schema(X).table("foo")` → no flag.
- [x] Verify regression: existing `db.table('foo')` without `.schema()` still flags correctly (existing tests).

### Phase 3 — Re-run review + verify ✅

- [x] `pytest mcp/noctusai/tests/test_compliance_prod.py -q` → green.
- [x] `cli.py --review --product core` → 150 issues (149 admin_bypass + 1 unknown_table). The `admin_llm_usage.py:92` row is gone (1 FP cleared).
- [x] `cli.py --review` (all products) → no new regressions.

---

## 7. Open questions

None — heuristic limit documented in §2.

---

## 8. Dependencies & blockers

- None.

---

## 9. Success criteria

- [x] `mcp/noctusai/cli.py --review --product core` returns one fewer FP (the `admin_llm_usage.py:92` row).
- [x] Regression tests cover both detectors.
- [x] No new regressions across other products.

---

## 10. How to use this plan

Single-engineer dispatch on Wave 0 of master `keeper-trio-platform-triage`. Sister project `keeper-trio-seed-formalize` runs in parallel. Wave 1 (per-product children) FF-gates on both Wave 0 children.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Project filed by Engineer XX dispatched on Wave 0 child B per `projects/keeper-trio-platform-triage/phase-0-triage.md §172 (cross-schema detector gap)`. Detector tuning shipped — `_has_schema_in_chain` helper added to `mcp/noctusai/tools/noctus/dev/compliance.py`; both unknown-table + admin-bypass detectors gate on it. 3 regression tests added. `cli.py --review --product core` count: **151 → 150** (1 FP cleared at `admin_llm_usage.py:92`). | claude-opus-4-7 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close (orchestrator).
