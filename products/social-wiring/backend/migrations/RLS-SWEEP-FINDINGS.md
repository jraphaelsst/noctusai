# RLS Sweep Findings — current_org_id() rollout (2026-06-02)

## What this file is

A durable record of the fleet-wide RLS sweep performed as part of
`feat/rls-codify-org-fn`. The migration `011_rls_current_org_id.sql`
codifies the live fix applied to `social_wiring` on 2026-06-02.
This document records what else is broken and what proposed (NOT APPLIED)
migrations were written.

**Source of truth:** live `pg_policies` on Supabase project `nyplttplcoyiiqjrvtiw`,
queried 2026-06-02 via the Supabase Management API.

**Pointer:** `memory/feedback_rls_never_key_on_user_metadata.md`

---

## Root cause (summary)

Every org-scoped `authenticated` RLS policy that was authored before 2026-06-02
used:

```sql
org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
```

In Supabase, `auth.jwt() ->> 'org_id'` returns **NULL** because `org_id` lives
under `user_metadata`, not at the JWT top-level. This silently stripped all rows
on every authenticated user-scoped read while `service_role` writes succeeded.

The naive fix — reading `auth.jwt()->'user_metadata'->>'org_id'` — is a
**privilege escalation hole**: `user_metadata` is user-editable, and the
Supabase advisor flags it as `rls_references_user_metadata` (ERROR level).

The secure fix is:

```sql
CREATE OR REPLACE FUNCTION public.current_org_id()
  RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'public'
AS $f$ SELECT org_id FROM public.noctus_users WHERE id = (SELECT auth.uid()); $f$;
```

All policies call `current_org_id()` — a trusted-table read, not a JWT claim.

---

## social_wiring — FIXED LIVE + codified in 011

| Count | Status |
|-------|--------|
| 49 authenticated policies | Fixed live 2026-06-02, codified in migration 011 |
| 5 INSERT/ALL policies | NOT yet fixed live (still broken) — also codified in 011 |
| 49 service_role + public policies | Not affected (no org predicate or service_role bypass) |

**Migration file:** `011_rls_current_org_id.sql`
**Tech-lead action required:** Apply migration 011 to prod (Section 3 — the 5 unfixed INSERTs).

---

## Sweep results — other schemas

All policies in schemas outside `social_wiring` that still use the broken
`auth.jwt() ->> 'org_id'` (top-level) or `user_metadata` form.

| Schema | Product | Broken policies | Proposed migration |
|--------|---------|-----------------|-------------------|
| `erp` | erp-imobiliario | **170** | `proposed-rls-fixes/PROPOSED_erp_rls_current_org_id.sql` |
| `imobi_scheduling` | erp-imobiliario (orphan — no repo migration) | **56** | `proposed-rls-fixes/PROPOSED_imobi_scheduling_rls_current_org_id.sql` |
| `mailing` | social-wiring (orphan — absorbed) | **15** | `proposed-rls-fixes/PROPOSED_mailing_rls_current_org_id.sql` |
| `daily_life` | daily-life | **1** | `proposed-rls-fixes/PROPOSED_daily_life_rls_current_org_id.sql` |
| `media_scheduling` | unknown (orphan) | **1** | `proposed-rls-fixes/PROPOSED_media_scheduling_rls_current_org_id.sql` |
| `seed` | seed | **1** | `proposed-rls-fixes/PROPOSED_seed_rls_current_org_id.sql` |
| `storage` | erp (objects bucket) | **4** | `proposed-rls-fixes/PROPOSED_storage_rls_current_org_id.sql` |

**Total broken policies (excluding social_wiring):** 248

---

## Breakdown by schema

### erp (170 policies) — SURFACE: requires user auth to apply

The `erp.current_org_id()` function was already fixed live on 2026-06-02
(same session as social_wiring). However, **none of the 170 `erp` table
policies were updated** — they still call `auth.jwt()` directly inline (not
via the function). These are completely broken for all authenticated user reads.

The erp product's highest migration is `031_documentos_compartilhado_portal.sql`.
The proposed fix goes to `032_rls_current_org_id.sql` on the erp-imobiliario
product. But this is a **large cross-cutting change** requiring explicit
user authorization before applying.

**surface: BLOCKED — 170 erp RLS policies are broken (org reads return 0 rows).**
**Requires explicit user auth to apply proposed migration.**

### imobi_scheduling (56 policies) — orphan schema

Schema exists on the live DB but has no corresponding migration file in the
`products/erp-imobiliario/` directory. All 56 authenticated policies broken.
Need to determine product ownership before applying.

**surface: orphan schema imobi_scheduling — 56 broken policies, no repo migration.**

### mailing (15 policies) — orphan schema (absorbed by social-wiring)

The `mailing` schema was an older product absorbed into `social-wiring`.
The schema still exists on the live DB with 15 broken policies.
These are SELECT policies for the mailing tables (ai_feedback, ai_outputs,
automations, campaigns, etc.) — all reading from `auth.jwt()` inline.

**surface: orphan mailing schema — 15 broken policies. Confirm with tech-lead
whether these are still live or can be cleaned up.**

### daily_life (1 policy)

`daily_life.invitations.invitations_select_own_org` — SELECT policy, broken.
The `daily-life` product's highest migration is `006_ai_outputs.sql`.
Proposed fix goes to `007_rls_current_org_id.sql`.

### media_scheduling (1 policy) — orphan schema

Schema `media_scheduling.invitations` has 1 broken policy. No product owns
this schema in the repo. Tech-lead needs to identify ownership.

### seed (1 policy)

`seed.invitations.invitations_select_own_org` — SELECT policy, broken on the
live `seed` schema. The seed product's 001_seed.sql was updated in this commit
to use `current_org_id()` for future deploys, but the LIVE `seed` schema
policy is still broken. Proposed fix: `PROPOSED_seed_rls_current_org_id.sql`.

### storage (4 policies) — uses user_metadata (INSECURE)

The `storage.objects` ERP bucket policies use:
```sql
(storage.foldername(name))[1] = ((auth.jwt() -> 'user_metadata'::text) ->> 'org_id'::text)
```
This is the `user_metadata` form — user-editable, privilege-escalation risk.
Supabase advisor flags this as `rls_references_user_metadata` ERROR.

The fix requires adapting the folder-path check to use a subquery since
`storage.objects` has no direct `org_id` column:
```sql
(storage.foldername(name))[1] = (SELECT org_id::text FROM public.noctus_users WHERE id = (SELECT auth.uid()))
```
This is included in `PROPOSED_storage_rls_current_org_id.sql`.

**surface: storage.objects has user_metadata RLS (escalation risk) — 4 policies.**

---

## erp.current_org_id() — already fixed live (verified)

The `erp.current_org_id()` function was redefined on 2026-06-02:
```sql
CREATE OR REPLACE FUNCTION erp.current_org_id() RETURNS uuid
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'public', 'erp'
AS $f$ SELECT org_id FROM public.noctus_users WHERE id = (SELECT auth.uid()); $f$;
```
This is codified in `011_rls_current_org_id.sql` Section 1.
Note: the erp TABLE policies don't call this function — they still inline
the broken `auth.jwt()` form. See "erp" section above.

---

## Seed template fix (this commit)

The scaffold template at `templates/product-seed/backend/migrations/`
had the broken pattern in two files:
- `001_seed.sql` → `invitations_select_own_org` used `auth.jwt()` form
- `003_examples.sql` → all 4 CRUD policies used `auth.jwt()` form

Both files updated in this commit to use `current_org_id()`.
`current_org_id()` function declaration added to `001_seed.sql` and
`products/seed/backend/migrations/001_seed.sql` (the source of the template).

The `mcp/noctusai/tests/test_scaffold.py` regression test was updated to
assert `current_org_id()` and to assert `auth.jwt()` is absent from
scaffolded output.

---

## Actions required from tech-lead / user

1. **APPLY (requires prod auth):** Section 3 of `011_rls_current_org_id.sql`
   fixes the 5 remaining broken `social_wiring` INSERT/ALL policies.

2. **APPLY erp (requires prod auth + user authorization):**
   `PROPOSED_erp_rls_current_org_id.sql` — 170 broken policies.
   This is the highest-impact item: ALL erp authenticated user reads
   currently return 0 rows.

3. **RESOLVE orphan schemas:**
   - `imobi_scheduling` — 56 broken policies, no product owner in repo.
   - `mailing` — 15 broken policies, absorbed by social-wiring.
   - `media_scheduling` — 1 broken policy, unknown product.
   Determine ownership, then apply the proposed migrations.

4. **APPLY daily_life:** 1 broken invitation policy. Low impact but should
   be fixed for consistency.

5. **APPLY storage:** 4 user_metadata ERP policies. Escalation risk.
   Requires prod auth. Proposed migration included.

6. **APPLY seed:** 1 broken invitation policy on the live `seed` schema.
   Low impact (seed is a demo product).
