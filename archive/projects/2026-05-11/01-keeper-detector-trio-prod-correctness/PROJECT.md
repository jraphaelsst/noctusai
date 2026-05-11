# keeper-detector-trio-prod-correctness — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** ✅ **CLOSED — 2026-05-11.** All 3 phases ✅ shipped in single engineer dispatch. 3 keeper detectors live + 16 regression tests green + KB updated. Therapy-platform smoke confirms 12-of-12 GG drift cases + `gcal_authorization_is_fresh` search_path + 5 admin-bypass gaps surface as warnings. Platform-wide additional latent gaps surfaced (core 149 admin-bypass, erp 34, mailing 18, pf 1). Archive on close.
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

### Phase 0 — Audit + design lock ✅

- [x] Confirm Engineer GG's three categories — re-read his Phase 4 report.
- [x] Read existing keeper detector shapes at `mcp/noctusai/tools/noctus/dev/compliance.py` for naming + return shape conventions.

**Improvements:**
- Mirrored `check_test_status_assertion` shape (per-product detector, AST-walking the backend tree, returning `list[dict]` with `product/file/line/issue/severity` keys). No new shape needed — the trio fits cleanly into the existing detector contract.
- Confirmed `_walk_python_files` helper was MCP-scoped (whole-repo silent-error sweep); needed a per-product variant. Added `_walk_product_backend_python` next to the trio — kept the exclusion set in sync.

### Phase 1 — Ship 3 detectors + tests ✅

- [x] Author each detector function (3 functions).
- [x] Register in keeper's detector registry — wired into `check_all_products()` + `tools/noctus/dev/review.py::_detect()` (both required per the comment block at the top of `compliance.py`).
- [x] 3 regression tests at `mcp/noctusai/tests/test_compliance_prod.py` (sibling file — total 16 tests, ≥1 true-positive + ≥1 false-positive per detector + edge cases for chained admin calls + dollar-quoted function bodies + non-Constant table args).
- [x] Each detector fires correctly on a known-broken fixture; clean on known-good — 16/16 green.

**Improvements:**
- Test fixtures use `_mk_product()` helper that mirrors the real `<root>/backend/{app,migrations}/` tree shape — same pattern as `TestMockSchemaValidation._mk_product` already in `test_compliance.py`. No new patterns introduced.
- `_function_block_text` helper handles three Postgres function shapes: `$$ ... $$`, `$tag$ ... $tag$`, and `AS 'literal'` fallback (regex-locates the matching closer). Documented in detector docstring; tested via the multi-function fixture.
- AST shape `_admin_client_bindings` walks both `Assign` and `AnnAssign` nodes; tested via the bound-variable false-positive case.

### Phase 2 — Verify + close ✅

- [x] Run keeper detectors across all products via `run_review(product_slug=...)` — surfaces 43 issues in therapy-platform alone:
  - 37 unknown-table refs (12 distinct tables — EXACT match to Engineer GG's N=12 drift: anamneses, sessions, therapist_reviews, goals, reminder_configs, clinic_therapist_configs, settings_history, therapeutic_journal, financial_transactions, ai_prompt_settings, ai_prompt_history + notifications).
  - 1 missing-search_path function (EXACT match: `therapy.gcal_authorization_is_fresh`).
  - 5 admin-bypass gaps (3 distinct tables: ai_prompt_history, ai_prompt_settings, settings_history).
- [x] Platform-wide trio output (proof of additional latent gaps):
  - core: 2 unknown + 149 admin-bypass
  - erp-imobiliario: 2 unknown + 9 search_path + 34 admin-bypass
  - mailing: 18 admin-bypass
  - personal-finance: 1 admin-bypass
- [x] `pytest tests/test_compliance_prod.py -q` → 16 passed in 0.12s.
- [x] KB doc updated — `KNOWLEDGE-BASE/CONTEXT/PATTERNS/testing.md § Production-correctness keeper detectors` with detector shapes, false-positive design, worked example, platform-wide table.
- [x] Tick + Improvements + §11 + archive.

**Improvements:**
- Pre-existing `test_all_products_compliant` + `test_real_products_pass_validate` in `test_compliance.py` were already failing on main due to unrelated seed-version stamp drift (worktree → main hash mismatch). Did NOT modify them — the failures are not caused by this work.
- `TestCheckDetectorHasRegressionTest.test_real_repo_passes` will fail until merge to main: the meta-detector reads `REPO_ROOT` which resolves to main noc (via the `.noctusai-workspace` marker pointing back) NOT the worktree. The new test file is in the worktree only. This is the standard branch-vs-main gap documented in `feedback_worktree_base_verification.md` + `feedback_mcp_write_tools_resolve_caller_root.md`. Resolves automatically post-merge.

## 7. Open questions

- None — detector shapes are well-defined.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [x] 3 detectors ship + pass regression tests — 16 regression tests in `mcp/noctusai/tests/test_compliance_prod.py` all green.
- [x] Running keeper review surfaces the N=12 drift + search_path + RLS gaps (proving detector value) — 12-of-12 drift cases match GG's audit case-for-case; `gcal_authorization_is_fresh` is the lone search_path miss as GG flagged; admin-bypass gaps surface platform-wide (core 149, erp 34, mailing 18, therapy 5, pf 1).
- [x] KB doc updated — `KB § PATTERNS/testing.md § Production-correctness keeper detectors`.

## 10. How to use this plan

Single-engineer dispatch via worktree.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer GG's therapy P4 close (commit `a56a39e`) surfaced 3 keeper-detector candidates. Each detector-shape (deterministic, observation-only). Pure detector authoring + regression tests. | claude-opus-4-7 |
| 2026-05-11 | **Phase 0+1+2 ✅ shipped together.** 3 detectors authored in `mcp/noctusai/tools/noctus/dev/compliance.py` (`check_unknown_table_references`, `check_function_search_path_pinned`, `check_admin_endpoint_service_role_bypass`). Wired into `check_all_products()` + `review._detect()`. 16 regression tests in `tests/test_compliance_prod.py` — all green. KB doc updated. Therapy-platform smoke-test surfaces all 12 of GG's drift cases + the `gcal_authorization_is_fresh` search_path gap + 5 admin-bypass gaps. Platform-wide surface (`core` 149 admin-bypass, `erp` 34, `mailing` 18, `pf` 1) demonstrates trio caught latent drift across products. | engineer (worktree-agent-a4415cefe090ff457) |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
