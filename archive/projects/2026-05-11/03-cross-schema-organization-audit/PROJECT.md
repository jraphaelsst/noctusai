# cross-schema-organization-audit — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-11
- **Status:** ✅ **CLOSED — Phase 0/1/2 complete.** Audit across all 11 non-core products surfaced 0 REAL_BUG and 0 WORKS_BY_LUCK. The PF Engineer W fix (`monthly_narrative_service` → `get_core_client()`) was 1-of-1 — no sister-service repeats. Therapy `ai_pipeline.py` already uses explicit-DI `core_db`. Sister digest services (daily-life `weekly_review`, mailing `campaign_debrief`, ERP `metas_digest`, core `audit_digest`) don't reach `public.organizations` from a product-schema client. KB pattern + methodology amendment shipped.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `cross-schema-organization-audit`
- **Related docs:**
  - `archive/projects/...//personal-finance-wiring/proposals/phase-4-tier-c-followups.md §3.1` — Engineer W's detailed proposal
  - `seed/framework/backend/noctusai_seed/database.py::DatabaseModule.get_core_client` — the canonical seam

---

## 1. Context & Purpose

PF's `monthly_narrative_service._fetch_window` had this shape (pre Engineer W fix):

```python
org_res = db.table("organizations").select(...).eq("id", org_id).execute()
org_record = org_res.data or {"id": org_id, "nome": "Você"}  # fallback masks the bug
```

`db` is the product-schema Supabase client, which has `search_path = "personal-finance", public`. PostgREST resolves `db.table("organizations")` against the FIRST schema in search_path — `"personal-finance"` — where the `organizations` view/table doesn't exist. Result: PGRST205 at runtime.

The fallback (`or {fallback}`) hides this — tests don't seed organizations rows, fallback always wins, false-green. **Real bug only manifests in production.**

Engineer W fixed it by switching to `get_core_client()` which gives a Supabase client rooted in `public` schema. Same bug shape likely exists across products — every product that needs to read `public.organizations` from a service.

## 2. Confirmed constraints

- **`get_core_client()` is the canonical seam** — already used in 6 seed `routers.py` call sites + post-fix in PF `monthly_narrative_service.py`.
- **Fixture-fallback masking is the slip shape** — services with `or {fallback}` after a DB read can hide PGRST205 from tests.
- **The audit grep is mechanical**: find all `db.table("organizations")` (or `noctus_users`, `core.*`) calls in product services where `db` is a product-schema client.

## 3. Design principles

1. **Audit by shape, not by name.** Grep for product-schema clients touching `public.*` tables.
2. **Fix-or-document each hit.** Either switch to `get_core_client()` or document why the cross-schema reach works (e.g. PostgREST `search_path` happens to include `public`).
3. **Add a methodology guard**: when a service has `or {fallback}` after a DB read of a known-shape row, write at least one test that exercises the non-fallback path.

## 3a. Seed-first analysis

- **Cross-product?** YES — likely 4+ products affected.
- **Seed home?** Pattern doc at `KB § PATTERNS/cross-schema-reach.md` (or expand `database-rls.md`).
- **Per-product code count for cross-cutting concern?** Each product that needs `public.organizations` calls `get_core_client()`; zero per-product seam needed.

## 4. Scope

- **In scope:**
  - Grep audit across `products/*/backend/app/services/` + `app/routers/` for product-schema-client touching `public.*` tables.
  - Fix each hit (switch to `get_core_client()`) OR document why it works.
  - KB pattern doc: when to use `get_core_client()`.
  - Methodology: write one non-fallback-path test per `or {fallback}` line discovered.

- **Out of scope:**
  - Refactoring seam ownership (the seam exists and is canonical).
  - Adding new cross-schema seams.

## 5. Architecture / Data Model

Grep recipe:

```bash
# Suspect calls: product-schema client reaching public.*-shaped tables
grep -rnE 'db\.table\("(organizations|noctus_users|product_licenses|user_org_memberships)"\)' products/*/backend/app/
# Also catch: indirect via local helper that uses the wrong client
grep -rnE 'def.*get.*organization|fetch_org' products/*/backend/app/services/
```

Fix recipe (per hit):

```python
# BEFORE
result = self._db.table("organizations").select(...).execute()

# AFTER
core_db = get_core_client()  # imported from app.dependencies or similar
result = core_db.table("organizations").select(...).execute()
```

## 6. Implementation phases

### Phase 0 — Audit ✅

- [x] Grep across all products for the suspect shape (recipe in §5).
- [x] Catalog each hit: file:line, current client, target table, fallback shape if any.
- [x] Classify: REAL_BUG / WORKS_BY_LUCK / OK.

**Catalog (non-core products only — core OWNS the public schema, its calls are correctly rooted):**

| File:line | Table | Client | Classification | Notes |
|---|---|---|---|---|
| `products/personal-finance/backend/app/services/monthly_narrative_service.py:154` | `organizations` | `core` (from `get_core_client()`) | OK | Engineer W's post-fix shape — already canonical |
| `products/therapy-platform/backend/app/services/ai_pipeline.py:138` | `notifications` | `core_db` (DI default `get_core_client()`) | OK | Explicit DI shape with optional override |
| `products/imobi-scheduling/backend/app/services/authorization.py:259,273,300` | `users` | `self._scoped` (imobi_scheduling-rooted) | OK | `imobi_scheduling.users` — same-schema |
| `products/imobi-scheduling/backend/app/routers/whatsapp_router.py:207` | `users` | `admin.schema(AuthorizationService.SCHEMA).table(...)` | OK | Explicit `.schema("imobi_scheduling")` |
| `products/therapy-platform/backend/app/services/messaging_service.py:509,519,539,549,563` | `user_blocks` | `db` (therapy-rooted) | OK | `therapy.user_blocks` — same-schema |
| `products/therapy-platform/backend/app/services/admin_service.py:1161` | `user_blocks` | `db` (therapy-rooted) | OK | Same |
| `products/erp-imobiliario/backend/**/*.py` (multiple `profiles` hits) | `profiles` | product-schema | OK | `erp.profiles` lives in ERP schema (migration `003_schema_separation.sql` moved it) |

Sister digest services audited and **do not reach `public.organizations` from a product-schema client**:
- `products/daily-life/backend/app/services/weekly_review_service.py` — only daily-life tables in `_fetch_window`.
- `products/erp-imobiliario/backend/app/services/metas_digest_service.py` — only erp tables in `_fetch_context`.
- `products/mailing/backend/app/services/campaign_debrief_service.py` — only mailing tables in `_fetch_window`.
- `products/core/backend/app/services/audit_digest_service.py` — lives in core; its `db.table("organizations")` is correctly rooted in public.

**Classification totals: 0 REAL_BUG · 0 WORKS_BY_LUCK · all hits OK.**

### Phase 1 — Fix REAL_BUGs ✅

- [x] No REAL_BUGs found; nothing to switch.
- [x] AST-first guard upheld — no code edits made; would have used libcst.

### Phase 2 — Document WORKS_BY_LUCK + close ✅

- [x] No WORKS_BY_LUCK hits to document.
- [x] KB pattern doc — added "Cross-schema reach via `get_core_client()` — 2026-05-11" section to `KNOWLEDGE-BASE/CONTEXT/PATTERNS/database-rls.md`.
- [x] Methodology amendment — added rule to `CLAUDE/backend.md`: "Cross-schema reach goes through `get_core_client()`; `or {fallback}` after a DB read requires a non-fallback-path test."

**Improvements (in-scope, applied):**
- KB pattern doc captures the slip shape (PGRST205 + fallback masker) for future readers.
- `CLAUDE/backend.md` gets the authoring-rule pointer (three-way sync — KB depth + topical rule).

**Deferred / accept-with-rationale:**
- None. The audit closed clean.

## 7. Open questions

- None — Engineer W's diagnosis is unambiguous.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [x] Zero REAL_BUG instances remaining across all products — **audit confirmed clean before any code changes were needed**.
- [x] KB pattern doc shipped — `KB § PATTERNS/database-rls.md § Cross-schema reach via get_core_client()`.
- [x] Methodology guard documented — `CLAUDE/backend.md` + KB section above.
- [x] All affected products' pytest green — no products were modified (audit was code-read-only); methodology + doc layer only.

## 10. How to use this plan

Single-engineer dispatch. Audit + grep heavy; mechanical fixes once shape is locked.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer W's PF Phase 4 close (commit `15bea72`) caught real runtime bug in `monthly_narrative_service._fetch_window` (PGRST205 masked by fixture-fallback). Likely repeats in sister products. Mechanical audit + fix. | claude-opus-4-7 |
| 2026-05-11 | **Phase 0/1/2 executed in single engineer dispatch.** Audit grep + extended grep (admin client, `.schema(...)` indirections, all 138 unique tables in non-core services) surfaced 0 REAL_BUG / 0 WORKS_BY_LUCK across 11 non-core products. PF was the lone occurrence; Engineer W's fix was sufficient. Phase 1 had no work (nothing to fix). Phase 2 shipped: (a) `KB § PATTERNS/database-rls.md § Cross-schema reach via get_core_client()` documenting the slip shape + canonical fix + audit result; (b) `CLAUDE/backend.md` rule "Cross-schema reach goes through `get_core_client()`; `or {fallback}` after a DB read requires a non-fallback-path test." | engineer-cross-schema |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
