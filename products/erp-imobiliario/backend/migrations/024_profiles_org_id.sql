-- 024_profiles_org_id.sql
--
-- Adds the missing `org_id` column on `erp.profiles` and backfills it from
-- `auth.users.raw_user_meta_data->>'org_id'` for every existing profile.
--
-- Why this migration exists. `app/routers/profiles.py:115` (the cross-org
-- access guard before `DELETE /api/profiles/<id>`) reads
-- `target_profile.data.get("org_id")` to compare against the caller's
-- `caller_org`. Because `profiles.org_id` did not exist in the live schema,
-- `target_org` was always None, the guard
--   `if target_org and caller_org != target_org`
-- was silently bypassed, and admins of one org could `auth.admin.delete_user(...)`
-- profiles owned by users of another org.
--
-- Phase 0 audit confirmed this in `projects/erp-schema-drift-deep-audit/`
-- (filed 2026-05-03 by `projects/side-projects-batch/` Phase 2.b). This
-- migration ships the narrow security-fix slice of that project: profiles
-- only, not the broader 11-table reconciliation. Wider work continues in
-- the project's deferred phases.
--
-- Backfill source: `auth.users.raw_user_meta_data->>'org_id'`. Every ERP
-- profile we sampled (5 random rows, 2026-05-03) had a non-null org_id in
-- user metadata, matching the JWT claim shape used by `get_org_id(user)`.
-- The backfill therefore mirrors the same source the cross-org guard
-- compares against.
--
-- The column is intentionally nullable for the brief window between
-- migration apply and code deploy: any profile that lands without a
-- backfilled org_id continues to fail-closed at the guard (`target_org and
-- ...` evaluates False, raises 403). After this migration ships and the
-- code deploy lands, future profile inserts must populate `org_id`.

SET search_path = erp, public;

ALTER TABLE erp.profiles
    ADD COLUMN IF NOT EXISTS org_id UUID;

COMMENT ON COLUMN erp.profiles.org_id
    IS 'Organization scope for cross-org access checks. Backfilled '
       '2026-05-03 from auth.users.raw_user_meta_data->>org_id. '
       'New profile rows MUST populate this; the cross-org guard at '
       'routers/profiles.py:115 fails closed when null.';

-- Backfill from auth.users metadata. Idempotent: only updates rows
-- where org_id is currently NULL.
UPDATE erp.profiles p
   SET org_id = (u.raw_user_meta_data->>'org_id')::uuid
  FROM auth.users u
 WHERE p.id = u.id
   AND p.org_id IS NULL
   AND u.raw_user_meta_data->>'org_id' IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_erp_profiles_org_id ON erp.profiles(org_id);
