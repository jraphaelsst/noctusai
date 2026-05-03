-- 025_handle_new_user_org_id.sql
--
-- Extends the `public.handle_new_user()` trigger that fires on
-- `auth.users` INSERT so newly-created profiles carry `org_id` from the
-- user's metadata. Closes the post-024 gap where the column existed +
-- backfilled but new signups would land null again.
--
-- The trigger ran from migration 001 onward; this is a SECURITY DEFINER
-- replacement that adds the org_id column population in the INSERT
-- payload. Behavior is otherwise identical.
--
-- Filed by `projects/erp-schema-drift-deep-audit/` Phase 1 (security-fix
-- slice) on 2026-05-03.

CREATE OR REPLACE FUNCTION public.handle_new_user()
  RETURNS trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'public'
AS $function$
BEGIN
  INSERT INTO erp.profiles (id, nome, email, telefone, org_id)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'nome', NEW.email),
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'telefone', ''),
    NULLIF(NEW.raw_user_meta_data->>'org_id', '')::uuid
  );
  RETURN NEW;
END;
$function$;
