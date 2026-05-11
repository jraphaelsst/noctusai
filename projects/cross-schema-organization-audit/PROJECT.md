# cross-schema-organization-audit — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** 📋 **READY FOR EXECUTION.** Filed under user signal "create projects for deferrals/parks that happen along the way." Engineer W's `personal-finance-wiring` Phase 4 close (commit `15bea72`) caught a runtime bug — `monthly_narrative_service` reached `public.organizations` via product-schema client, would raise PGRST205. Bug masked by fixture-fallback. Likely repeats in ERP / therapy / daily-life sister services.
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

### Phase 0 — Audit

- [ ] Grep across all products for the suspect shape (recipe in §5).
- [ ] Catalog each hit: file:line, current client, target table, fallback shape if any.
- [ ] Classify: REAL_BUG (would raise PGRST205) / WORKS_BY_LUCK (search_path includes public) / OK (already uses get_core_client).

### Phase 1 — Fix REAL_BUGs

- [ ] For each REAL_BUG: switch to `get_core_client()`. Add test that exercises the non-fallback path (seed the org row, assert the service consumes it).
- [ ] AST-first (libcst). NEVER sed/regex.

### Phase 2 — Document WORKS_BY_LUCK + close

- [ ] For each WORKS_BY_LUCK: add a code comment explaining the search_path dependency OR switch to `get_core_client()` for safety.
- [ ] KB pattern doc: `KB § PATTERNS/cross-schema-reach.md` (or expand `KB § PATTERNS/database-rls.md` with a "cross-schema reach via `get_core_client()`" section).
- [ ] Methodology amendment: when authoring code, `or {fallback}` after a DB read requires at least one test exercising the non-fallback path.

## 7. Open questions

- None — Engineer W's diagnosis is unambiguous.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [ ] Zero REAL_BUG instances remaining across all products.
- [ ] KB pattern doc shipped.
- [ ] Methodology guard documented.
- [ ] All affected products' pytest green.

## 10. How to use this plan

Single-engineer dispatch. Audit + grep heavy; mechanical fixes once shape is locked.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer W's PF Phase 4 close (commit `15bea72`) caught real runtime bug in `monthly_narrative_service._fetch_window` (PGRST205 masked by fixture-fallback). Likely repeats in sister products. Mechanical audit + fix. | claude-opus-4-7 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
