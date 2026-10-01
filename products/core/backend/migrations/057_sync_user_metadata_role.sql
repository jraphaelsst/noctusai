-- Migration 057_sync_user_metadata_role.sql (2026-10-01)
-- Forward-only + idempotent.
--
-- WHY: every product frontend reads the caller's role from the JWT's
-- `user_metadata` (`resolveSSOContext` → `org_role` / `noctus_role`) to decide
-- which create/edit/delete controls to show. That metadata is a CACHE of
-- `public.noctus_users`, but only ONE path wrote the role into it — Core's
-- `/api/sso/session` (the product launcher). Signup (`auth.py`) and OAuth
-- signup (`oauth.py`) wrote `org_id` only, so an org OWNER who signed in to a
-- product directly was shown as "Membro" with every admin-gated button
-- hidden, while the backend (which reads the trusted row) would have
-- accepted every write. Live 2026-10-01: Igig Agency's owner saw IgIg with no
-- CRUD on any page.
--
-- FIX AT THE SOURCE: the row is the truth, so the row keeps its cache in
-- sync. Any INSERT, or UPDATE of org_id / org_role / role, merges the same
-- three keys `/api/sso/session` writes into `auth.users.raw_user_meta_data`
-- (shallow `||` merge — the SSO enrichment keys like plan/license stay).
-- Covers every writer (signup, OAuth, invites, team role changes, operator
-- scripts) without each one having to remember.
--
-- UX only: `user_metadata` is user-writable and NEVER authorizes — the
-- backend keeps resolving roles from `public.noctus_users`
-- (`make_resolve_platform_role`, SEC-2). A session sees the new value on its
-- next login / token refresh.

CREATE OR REPLACE FUNCTION public.sync_noctus_user_metadata()
  RETURNS trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'public'
AS $f$
BEGIN
  UPDATE auth.users
     SET raw_user_meta_data = COALESCE(raw_user_meta_data, '{}'::jsonb)
                              || jsonb_build_object(
                                   'org_id', NEW.org_id,
                                   'org_role', NEW.org_role,
                                   'noctus_role', NEW.role)
   WHERE id = NEW.id;
  RETURN NEW;
END;
$f$;

REVOKE ALL ON FUNCTION public.sync_noctus_user_metadata() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS noctus_users_sync_metadata ON public.noctus_users;
CREATE TRIGGER noctus_users_sync_metadata
  AFTER INSERT OR UPDATE OF org_id, org_role, role ON public.noctus_users
  FOR EACH ROW EXECUTE FUNCTION public.sync_noctus_user_metadata();

-- Backfill: bring every existing cache in line with its row (only rows that
-- actually differ are touched).
UPDATE auth.users u
   SET raw_user_meta_data = COALESCE(u.raw_user_meta_data, '{}'::jsonb)
                            || jsonb_build_object(
                                 'org_id', nu.org_id,
                                 'org_role', nu.org_role,
                                 'noctus_role', nu.role)
  FROM public.noctus_users nu
 WHERE nu.id = u.id
   AND (u.raw_user_meta_data->>'org_id'      IS DISTINCT FROM nu.org_id::text
     OR u.raw_user_meta_data->>'org_role'    IS DISTINCT FROM nu.org_role
     OR u.raw_user_meta_data->>'noctus_role' IS DISTINCT FROM nu.role);
