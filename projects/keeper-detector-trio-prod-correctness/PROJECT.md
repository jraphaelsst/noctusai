# keeper-detector-trio-prod-correctness — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** 📋 **READY FOR EXECUTION.** Filed under user signal "create projects for deferrals/parks that happen along the way." Engineer GG's therapy P4 (commit `a56a39e`) surfaced three keeper-detector candidates that would have caught the N=12 drift + RLS hole + search_path gaps at test/review time instead of production runtime.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `keeper-detector-trio-prod-correctness`

---

## 1. Context & Purpose

Engineer GG's Phase 4 audit caught three categories of latent production-correctness bugs that existed for days/weeks unnoticed because tests passed against mocks:

1. **N=12 migration drift** — code references tables that don't exist in live schema. MockSupabase WARN+skip masks; real Supabase fails.
2. **search_path missing** on `gcal_authorization_is_fresh` function — Supabase advisor 0011 flags it; per-function risk analysis is cheaper to skip if a detector enforces.
3. **service_role_bypass policy gaps** — every admin endpoint that uses `get_admin_client()` needs the target table to have `service_role_bypass FOR ALL TO service_role USING (true)` policy. Missing = silent permission failure.

Each is detector-shape (deterministic, observation-only — fits keeper's compliance contract).

## 2. Confirmed constraints

- **Keeper is observation-only** (per `feedback_keeper_observation_only.md` 2026-04-19). Detectors emit warnings; LLM authors fixes via `--review`.
- **Three detectors live alongside existing keeper checks** at `mcp/noctusai/tools/noctus/dev/compliance.py` (or sibling).
- **Each detector ships colocated regression test** per `feedback_regression_test_the_detector.md`.

## 3. Design principles

1. **One detector per check.** No bundling — each fires independently.
2. **Live-DB or migration-files as oracle.** Don't trust mocks; cross-check against `migrations/*.sql` (preferred — no DB connection needed for keeper).
3. **WARN, not ERROR.** Detector emits warning; agent decides fix.

## 3a. Seed-first analysis

- **Cross-product?** YES — applies to all products with admin endpoints + RLS + functions.
- **Seed home?** `mcp/noctusai/tools/noctus/dev/compliance.py` (sibling of existing keeper detectors).

## 4. Scope

- **In scope:**
  - `check_unknown_table_references` — WARN per `db.table("X")` where X is not in any `products/<product>/backend/migrations/**/*.sql`.
  - `check_function_search_path_pinned` — WARN per `CREATE FUNCTION` (or `CREATE OR REPLACE FUNCTION`) without `SET search_path`.
  - `check_admin_endpoint_service_role_bypass` — WARN per `get_admin_client().table("T")` where T lacks `service_role_bypass` policy in migrations.
  - 3 regression tests (one per detector).
  - KB doc entry: `KB § PATTERNS/testing.md § Production-correctness keeper detectors`.
- **Out of scope:**
  - Auto-fix (keeper is observation-only).
  - Fixing the existing drift / search_path / RLS gaps (separate projects).

## 5. Architecture / Data Model

```python
# mcp/noctusai/tools/noctus/dev/compliance.py (or compliance_prod.py sibling)

def check_unknown_table_references(repo_root: Path) -> list[Issue]:
    """WARN per db.table("X") where X is not in any migrations/*.sql for the product."""
    # 1. For each products/<p>/backend/app/**.py:
    # 2.   grep `db.table("X")` callsites
    # 3.   collect known tables from products/<p>/backend/migrations/*.sql (CREATE TABLE statements)
    # 4.   diff: any X in code not in migrations → WARN

def check_function_search_path_pinned(repo_root: Path) -> list[Issue]:
    """WARN per CREATE FUNCTION without SET search_path."""
    # Parse each migration's CREATE [OR REPLACE] FUNCTION block; require SET search_path = ... in body

def check_admin_endpoint_service_role_bypass(repo_root: Path) -> list[Issue]:
    """WARN per get_admin_client().table('T') where T lacks service_role_bypass policy."""
    # 1. grep get_admin_client().table("T") callsites
    # 2. collect policies from migrations: grep "service_role_bypass" + which table
    # 3. diff
```

## 6. Implementation phases

### Phase 0 — Audit + design lock

- [ ] Confirm Engineer GG's three categories — re-read his Phase 4 report.
- [ ] Read existing keeper detector shapes at `mcp/noctusai/tools/noctus/dev/compliance.py` for naming + return shape conventions.

### Phase 1 — Ship 3 detectors + tests

- [ ] Author each detector function (3 functions).
- [ ] Register in keeper's detector registry.
- [ ] 3 regression tests at `mcp/noctusai/tests/test_compliance.py` (or sibling).
- [ ] Each detector fires correctly on a known-broken fixture; clean on known-good.

### Phase 2 — Verify + close

- [ ] Run keeper `cli.py --review` across all products — should surface the 12 drift cases + search_path gaps + RLS gaps now flagged as issues (immediate value).
- [ ] Tick + Improvements + §11 + archive.

## 7. Open questions

- None — detector shapes are well-defined.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [ ] 3 detectors ship + pass regression tests.
- [ ] Running keeper review surfaces the N=12 drift + search_path + RLS gaps (proving detector value).
- [ ] KB doc updated.

## 10. How to use this plan

Single-engineer dispatch via worktree.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer GG's therapy P4 close (commit `a56a39e`) surfaced 3 keeper-detector candidates. Each detector-shape (deterministic, observation-only). Pure detector authoring + regression tests. | claude-opus-4-7 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
