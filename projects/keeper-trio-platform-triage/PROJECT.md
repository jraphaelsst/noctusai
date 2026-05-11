# keeper-trio-platform-triage — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** 🚨 **READY FOR EXECUTION — PLATFORM-WIDE PRODUCTION-CORRECTNESS GAPS.** Filed under user signal "create projects for deferrals/parks that happen along the way." Engineer II's keeper-detector-trio close (commit `e23a4be`) surfaced **200+ latent admin-bypass gaps + 9 erp search_path + ~50 unknown-table cases** across the platform. Each gap is a real production-correctness risk masked by MockSupabase WARN+skip.
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

### Phase 0 — Per-product classification

- [ ] For each non-clean product: run `cli.py --review --product <p>` and capture all findings.
- [ ] Classify each finding (REAL_BUG / DEFENSE_IN_DEPTH / FALSE_POSITIVE).
- [ ] Build per-product triage queue.
- [ ] **Decision**: if detector FALSE_POSITIVE rate is >50%, file detector-tuning follow-up at higher priority.

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

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
