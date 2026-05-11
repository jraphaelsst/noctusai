# projects/adco-response-model-sellout-fix · 2026-05-11

> Scope: R2 of 4 REAL_BUG drifts from RESPONSE-MODEL-AUDIT (de045c3). File-disjoint from R1/R3/R4 (handled by ADCO-REWARDS-FIX).
> Branch: `adco-response-model-sellout-fix-2026-05-11`. Base: `de045c3`.

---

## 1 · Context (zero-context reader)

`SelloutOut`, `SubmissionMode`, `SelloutStatus`, the three `Sellout*In` request schemas, and the four `sellout_service.*` write paths drifted from the `relatorios_sellout` migration. The drift was invisible at runtime because `MockSupabaseClient` doesn't enforce column existence or CHECK constraints, so the entire pre-fix code path passed 230 tests despite being unable to survive a single real-Supabase insert.

The audit at `projects/response-model-silent-drop-audit/PROJECT.md` § 4.3 listed four concrete misalignments. R2 covers them all (they're all in the same product slice — sellout.py schema + sellout_service.py + sellout.py router).

## 2 · Living Q→A

| # | Q | Decision |
|---|---|---|
| 1 | `periodo` collapse — Option α (split) vs Option β (compute + ignore on write)? | **α**: split into `periodo_inicio` / `periodo_fim`. Frontend already passes both fields (`useSellout.ts:41-42`), so back-end was the lagging side. Simpler than β; no derived-field magic. |
| 2 | `SubmissionMode` Literal — add `'attachment'` to DB CHECK, or remove from the Literal? | **Remove from Literal**, rename to `'freeform'`. DB CHECK is the source of truth; frontend already uses `'freeform'`; the `/upload-attachment` route persists `'freeform'` to align. |
| 3 | `org_id` on `relatorios_sellout` — add the column, or drop the schema field + service writes? | **Drop**. The DB design uses RLS via `distributor_id → distributors.org_id`; adding a redundant column would denormalize the contract. Service still accepts `org_id` as a kwarg for the admin-notification email — just no longer writes it. |
| 4 | `SelloutStatus` Literal — scope-creep to also align `'rejeitado'` → `'recusado'`? | **Yes, in scope.** It's the same bug class (Literal mismatch with DB CHECK); fixing the other three drifts in the same file but leaving this one would leave a known production failure for a future engineer. |
| 5 | Frontend hook update? | **Out of scope.** Frontend already uses `periodo_inicio`/`periodo_fim` and `'freeform'`. The only frontend impact is `'rejeitado'` → `'recusado'` on the review form, which has no current consumer (the review UI isn't wired yet). Deferred — file a follow-up if/when the review UI lands. |

## 3 · Scope

- `products/adconnect/backend/app/schemas/sellout.py` — schema rewrite.
- `products/adconnect/backend/app/services/sellout_service.py` — payload writes + review validation + helper.
- `products/adconnect/backend/app/routers/sellout.py` — Form params + service kwargs + admin list filter.
- `products/adconnect/backend/tests/routers/test_sellout_router.py` — adjust existing tests + 6 new regression tests.

No migration. No frontend change. No seed-lib change.

## 3a · Seed-first analysis

This is product-specific schema-vs-DB drift in adconnect. The DRY-recurrence rule does NOT fire on the per-product fix (every product carries its own schemas). The *meta-pattern* — schema fields silently dropped against DB columns — already has a planned seed surface: the `seed-keeper-check-response-model-vs-migration` follow-up project at the audit's §8 (a keeper detector that AST-walks `response_model=X` routes + diffs against the migration's CREATE TABLE).

This engineer does NOT extend the seed; the keeper detector is a separate engineer dispatch after the four schema fixes land.

## 4 · Files touched

- `products/adconnect/backend/app/schemas/sellout.py` — rewrite. Split `periodo` → `periodo_inicio` + `periodo_fim`; rename Literal `'attachment'` → `'freeform'`; remove `SelloutOut.org_id`; align `SelloutStatus` to DB CHECK (`pendente|em_analise|aprovado|recusado`); add `created_at`/`updated_at`; align `SelloutReviewIn.status` Literal.
- `products/adconnect/backend/app/services/sellout_service.py` — added `_iso_date()` helper; updated `submit_estruturado` / `submit_nfe` / `submit_attachment` signatures + payload (drop `org_id`, drop `periodo`, add `periodo_inicio` + `periodo_fim`); `submit_attachment` now writes `submission_mode='freeform'`; `review()` validation set `{aprovado, recusado}`.
- `products/adconnect/backend/app/routers/sellout.py` — `Form()` params now `periodo_inicio` + `periodo_fim`; service calls pass the new kwargs; admin `list_reports` filter drops the broken `.eq("org_id", ...)` (RLS handles scoping).
- `products/adconnect/backend/tests/routers/test_sellout_router.py` — updated 4 existing tests; added 6 regression tests.

## 5 · Verification

- Baseline: `pytest products/adconnect/backend/ -q` → 230 passed / 18 skipped (pre-fix).
- After fix: 236 passed / 18 skipped (+6 regression tests; 0 regressions).
- `noctus.dev.review --product adconnect` → 0 issues.

## 6 · Coordination notes

- **ADCO-REWARDS-FIX** parallel: disjoint files (rewards.py + admin.py + rewards_service.py + financial_service.py). No collision risk.
- **org_id resolution in `accrue_for_sellout_approval`**: `rewards_service.py:250` reads `relatorio_row.get("org_id")`. Post-fix, that key is `None` because the DB row no longer carries it. `_fetch_active_rules(db, None)` already handles `None` (line 89-96), so no immediate breakage. However, in production, every reward rule will match the relatorio regardless of org. That's a real bug — but its location is `rewards_service.py`, owned by ADCO-REWARDS-FIX. Surfaced to the orchestrator below.

## 7 · Open follow-ups (for the orchestrator)

- **`accrue_for_sellout_approval` org-id resolution** — the rewards service needs to look up `org_id` via the distributor (`SELECT org_id FROM distributors WHERE id=?`) instead of reading it off the sellout row. Belongs in ADCO-REWARDS-FIX scope or a fresh follow-up. Flagged here because R2 surfaced it but the fix lives in REWARDS-territory.
- **Frontend review form `'rejeitado'` → `'recusado'`** — no current consumer; defer until the review UI lands.
- **Keeper detector for response_model vs migration** — already filed at audit §8 as `seed-keeper-check-response-model-vs-migration`. Independent dispatch.

## 8 · Change log

- 2026-05-11 — R2 schema/service/router/test fix; 4 drifts closed; 6 regression tests added.
