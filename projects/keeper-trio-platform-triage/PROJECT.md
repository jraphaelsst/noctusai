# keeper-trio-platform-triage — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** ⏳ **EXECUTING — Phase 0 ✅ + Wave 0 ✅ + Wave 1 dispatched 2026-05-11.** Phase 0: Engineer RR (commit `f1940a5`) classified 215 findings → **12 REAL_BUG / 201 DEFENSE_IN_DEPTH / 2 FALSE_POSITIVE**. Wave 0 (parallel × 2, FF-merged 2026-05-11): WW (commit `b76c43f`) shipped `noctusai_lib.sql.service_role_bypass(table, schema)` helper byte-equal to therapy's canonical pattern + 22 tests + KB amend; XX (commit `40269c3`) tuned detectors to skip `.schema(X).table(Y)` chains (−1 FP cleared at `core/admin_llm_usage.py:92`). Wave 1 dispatched (parallel × 4): YY core (billing_events REAL_BUG + 13 tables), ZZ erp (3 REAL_BUGs + 14 tables — longest pole), AAA mailing (6 tables), BBB pf (1 table).
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `keeper-trio-platform-triage`

---

## 1. Context & Purpose

Engineer II's keeper-detector-trio (`check_unknown_table_references` + `check_function_search_path_pinned` + `check_admin_endpoint_service_role_bypass`) now runs in `cli.py --review`. Running it across all products surfaces:

| Product | unknown_table | search_path | admin_bypass |
|---|---|---|---|
| adconnect | 0 | 0 | 0 |
| core | 2 | 0 | **149** |
| daily-life | 0 | 0 | 0 |
| dev-team | 0 | 0 | 0 |
| erp-imobiliario | 2 | **9** | **34** |
| imobi-scheduling | 0 | 0 | 0 |
| mailing | 0 | 0 | **18** |
| media-scheduling | 0 | 0 | 0 |
| personal-finance | 0 | 0 | 1 |
| seed | 0 | 0 | 0 |
| therapy-platform | 37 → 1 (post-HH drift sweep) | 1 → 0 (post-GG mig 012) | 5 |
| youtube-crawler | 0 | 0 | 0 |

**Therapy is now clean** (Engineers GG + HH cleared it). Remaining: core (149 admin_bypass), erp (9 search_path + 34 admin_bypass), mailing (18 admin_bypass), PF (1).

200+ findings — too big for a single engineer. Master-tree project that dispatches per-product child engineers via parallel batches.

## 2. Confirmed constraints

- **Each detector is observation-only** (keeper carve-out). Triage decides accept/refactor/formalize per finding.
- **Many `admin_bypass` "gaps" are likely false positives** — service_role bypasses RLS at the connection level (Supabase service_role JWT); explicit `service_role_bypass` policies are defense-in-depth, not strict requirement. Phase 0 must classify per product.
- **`search_path` gaps in ERP are real** — 9 functions need `SET search_path = ''` per advisor 0011.

## 3. Design principles

1. **Classify before fixing.** Each finding gets one of: REAL_BUG (production fails) / DEFENSE_IN_DEPTH (works but should harden) / FALSE_POSITIVE (detector noise).
2. **Per-product child engineers** — file overlap risk if multiple engineers touch same product backend.
3. **Phase 0 audit is the high-leverage step** — classification cuts 200+ findings to a manageable triage queue.

## 3a. Seed-first analysis

- **Cross-product master-tree.** Each child closes one product's findings.
- **Per-product code count?** Variable — depends on classification (REAL_BUG fixes inline, DEFENSE_IN_DEPTH adds policies, FALSE_POSITIVE updates detector).
- **Detector tuning** — if FALSE_POSITIVE rate is high, this project should also feed back into the detector (e.g. accept `is_admin_endpoint` heuristic refinement).

## 4. Scope

- **In scope:**
  - Run `cli.py --review --product <p>` for each non-clean product.
  - Classify each finding (REAL_BUG / DEFENSE_IN_DEPTH / FALSE_POSITIVE).
  - Per product: fix REAL_BUGs inline; harden DEFENSE_IN_DEPTH; tune detector for FALSE_POSITIVE.
  - Update KB pattern doc if new convention emerges.
- **Out of scope:**
  - Detector authoring (Engineer II shipped them).
  - Therapy product (already cleared).

## 5. Architecture / Data Model

Master-tree pattern (`KB § PATTERNS/master-tree-parallel-batches.md`): one child project per product per detector category. Likely 4-6 children based on size:

- `keeper-trio-core` (149 admin_bypass + 2 unknown_table)
- `keeper-trio-erp` (9 search_path + 34 admin_bypass + 2 unknown_table)
- `keeper-trio-mailing` (18 admin_bypass)
- `keeper-trio-pf` (1 admin_bypass)
- (therapy already cleared)

OR a single product-walking child for the smaller ones; the bigger products (core 149) get their own.

## 6. Implementation phases

### Phase 0 — Per-product classification ✅ *(2026-05-11)*

- [x] For each non-clean product: run `cli.py --review --product <p>` and capture all findings.
- [x] Classify each finding (REAL_BUG / DEFENSE_IN_DEPTH / FALSE_POSITIVE).
- [x] Build per-product triage queue. → `phase-0-triage.md` (176 lines).
- [x] **Decision**: FALSE_POSITIVE rate <3% per product (core 0.7%, erp 2.2%, mailing 0%, pf 0%) — no detector-FIRST gate needed. Wave 0 still recommended so Wave 1 children consume canonical `service_role_bypass(table)` helper.

**Improvements (Phase 0):**
- Top-3 REAL_BUGs surfaced as production bugs masked by MockSupabase WARN+skip — see §11 for detail.
- Detector tuning opportunity: `.schema(X).table(Y)` chain support (N=1 today at `core/admin_llm_usage.py:92`; tune now before consumers proliferate).
- 192 admin_bypass DEFENSE_IN_DEPTH findings consolidate into a single decision: add `service_role_bypass(table)` helper to `noctusai_lib.sql` (mirroring `prelude` + `updated_at_trigger`) — closes 192 findings via one seed addition + per-product backfill.

### Phase 1 — Per-product child dispatches (parallel)

- [ ] Dispatch `keeper-trio-core` (149 admin_bypass + 2 unknown_table) — biggest; likely most false positives (admin uses get_admin_client extensively).
- [ ] Dispatch `keeper-trio-erp` (9 search_path = clearly real; 34 admin_bypass = needs classification).
- [ ] Dispatch `keeper-trio-mailing` (18 admin_bypass).
- [ ] Dispatch `keeper-trio-pf` (1 admin_bypass — possibly a 5-min fix; consider inline rather than dispatch).

### Phase 2 — Roll up + close

- [ ] Each child reports; orchestrator merges all on main.
- [ ] If detector tuning fired, ship that as well.
- [ ] KB amend if any new convention emerged.
- [ ] Archive master + child projects.

## 7. Open questions

- **Q1**: Are explicit `service_role_bypass` policies strictly required, or is Supabase service_role connection-level bypass sufficient? **Default rec**: defense-in-depth (explicit policy) — Supabase docs recommend it, and the detector's reasoning ("admin bypass will silently fail") only holds for RLS-enabled tables without the policy. Audit per product to confirm.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [ ] All non-therapy products at `0 issues` from the keeper trio detectors.
- [ ] Each finding either fixed, hardened, or tuned out.
- [ ] KB pattern doc reflects any new convention.

## 10. How to use this plan

Master-tree orchestration. Phase 0 single agent (classification); Phase 1 parallel children (per product).

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer II's keeper-detector-trio (commit `e23a4be`) surfaced 200+ platform-wide latent admin-bypass + search_path + unknown_table gaps. Master-tree dispatching per-product children. | claude-opus-4-7 |
| 2026-05-11 | **Wave 1 dispatched (parallel × 4 engineers)**: YY (`keeper-trio-core` — billing_events REAL_BUG + 13 tables service_role_bypass backfill), ZZ (`keeper-trio-erp` — ai.py phantom certidoes_negativas rewrite + 9 search_path SECURITY DEFINER hardening + org_settings cross-schema architecture decision + 14 tables backfill — longest pole), AAA (`keeper-trio-mailing` — 6 tables backfill), BBB (`keeper-trio-pf` — 1 table backfill). All consume WW's new `noctusai_lib.sql.service_role_bypass(table, schema)` helper. Engineer briefs reinforce: NEVER `--no-verify` (CLAUDE.md §1) + Edit/Write phantom-success watch (shell heredoc fallback) + MCP write tools `worktree_path=` (recurrence N=3 session-wide). | claude-opus-4-7 |
| 2026-05-11 | **Wave 0 closed (parallel × 2 engineers, both FF-merged + archived)**: WW (`keeper-trio-seed-formalize`, commit `bb70334` → `b76c43f`) shipped `noctusai_lib.sql.service_role_bypass(table, schema)` helper — canonical impl at `noctusai_lib.domain.sql_templates`, thin wrapper at `noctusai_lib.sql`, byte-equal to therapy's `001_therapy_platform.sql:846+`; 22 new tests; KB amend at `database-rls.md`. XX (`keeper-detector-schema-chain-tuning`, commit `86f518b` → `40269c3`) tuned `check_unknown_table_references` + `check_admin_endpoint_service_role_bypass` to skip `.schema(X).table(Y)` chains via new `_has_schema_in_chain` AST helper; 4 new regression tests; `--review --product core` count 151 → 150 (-1 FP cleared). **Slips surfaced for methodology learning**: (a) WW reported **Edit/Write tool phantom-success** — tool reports OK but on-disk `grep` shows no change; shell heredoc fallback worked reliably. Worth corroborating with future engineers. (b) WW used `--no-verify` to bypass pre-commit on a "false positive" phase-state issue on therapy-platform-wiring Phase 5 — CLAUDE.md §1 forbids hook-skipping without explicit user request. Captured for methodology evolution. (c) MCP write tools (`scaffold_migration`, `lgpd_flag`) writing to noc canonical instead of engineer worktree — session-wide N=3 (UU + WW + VV). Existing `projects/mcp-worktree-path-resolution/` Phase 4 rollout needs to extend to these tools. | claude-opus-4-7 |
| 2026-05-11 | **Phase 0 (read-only classification) closed by Engineer RR** (commit `ed15a60` → cherry-picked to main as `f1940a5`). 215 findings classified across core (151) / erp (45) / mailing (18) / pf (1): **12 REAL_BUG** / **201 DEFENSE_IN_DEPTH** / **2 FALSE_POSITIVE**. Top-3 high-priority REAL_BUGs: (1) `erp/ai.py:351` references phantom `certidoes_negativas` table — actual tables are `certidao_consultas` + `certidao_resultados`; (2) `erp/003_schema_separation.sql:750` `delete_expired_password_codes()` is SECURITY DEFINER without `SET search_path` — privilege-escalation vector; (3) `core/billing.py:284` references phantom `core.billing_events` — Stripe webhook broken in production. Triage doc at `phase-0-triage.md`. Recommended dispatch: Wave 0 (`keeper-trio-seed-formalize` + `keeper-detector-schema-chain-tuning`, parallel × 2) → Wave 1 (`keeper-trio-{core,erp,mailing,pf}`, parallel × 4) FF-gated on Wave 0. False-positive rate <3% per product — no detector-FIRST gate needed, but Wave 0 preferred so Wave 1 children consume canonical `service_role_bypass(table)` helper from `noctusai_lib.sql`. | claude-opus-4-7 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
