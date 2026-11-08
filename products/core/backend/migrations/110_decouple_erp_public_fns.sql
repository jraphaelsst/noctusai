-- Migration 110_decouple_erp_public_fns.sql (2026-11-08)
-- Forward-only + idempotent. ERP -> Social Wiring absorption, slice S6.
--
-- WHY: the owner is retiring erp-imobiliario. The `erp` schema cannot be dropped
-- while shared `public` functions still read or write it:
--   * public.handle_new_user()             -- AFTER INSERT ON auth.users: wrote erp.profiles
--   * public.assign_default_corretor_role()-- AFTER INSERT ON auth.users: wrote erp.user_roles
--   * public.on_license_change()           -- license trigger: PERFORMed public.provision_erp
--   * public.provision_erp(uuid)           -- seeded erp.site_config
--   * public.snapshot_product_usage()      -- nightly cron: counted erp.* rows
-- Every definition below starts from the LIVE prod definition read on 2026-11-08
-- (pg_get_functiondef), not from an older migration file; only the erp lines are
-- removed, everything else is byte-for-byte.
--
-- NOT TOUCHED (S8 contract step): public.has_role(uuid, erp.app_role) stays. It only
-- reads erp.user_roles and is used by ~50 erp RLS policies, erp.* trigger functions
-- and the storage.protect_bucket_control_columns() trigger function, all of which
-- keep running until the erp schema is dropped. Its signature names the type
-- erp.app_role, so it is dropped together with the erp schema in S8 (DROP SCHEMA
-- erp CASCADE), after the policies that call it are gone. Breaking it here would
-- break those policies. Behaviour for non-erp products is unchanged: has_role is
-- not called by any core / non-erp path.
--
-- Behaviour for every other product is unchanged: the functions below keep their
-- owner, SECURITY DEFINER, pinned search_path and the live ACL (service_role only);
-- CREATE OR REPLACE preserves grants, the REVOKEs are idempotent re-statements.

-- ---------------------------------------------------------------------------
-- 1. auth.users triggers
-- ---------------------------------------------------------------------------
-- assign_default_corretor_role existed only to give a new user the erp 'corretor'
-- role: nothing but erp reads it. Drop the trigger, then the function.
DROP TRIGGER IF EXISTS on_auth_user_created_assign_role ON auth.users;
DROP FUNCTION IF EXISTS public.assign_default_corretor_role();

-- handle_new_user: the only statement was the erp.profiles insert. The function and
-- its trigger (on_auth_user_created) are kept as a no-op so the trigger set on
-- auth.users does not change shape under a live signup path; S8 may drop both.
CREATE OR REPLACE FUNCTION public.handle_new_user()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
BEGIN
  RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 2. license provisioning: drop the erp-imobiliario branch, then provision_erp
-- ---------------------------------------------------------------------------
-- on_license_change was provision_erp's only caller (checked in pg_proc.prosrc over
-- every non-system schema; pg_depend has no recorded dependents). The erp branch is
-- removed (an erp licence now falls to ELSE NULL, still notifying), THEN the function
-- is dropped so no window exists in which the trigger calls a missing function.
CREATE OR REPLACE FUNCTION public.on_license_change()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  v_slug text;
  v_org_id uuid;
BEGIN
  SELECT slug INTO v_slug FROM public.products WHERE id = NEW.product_id;
  v_org_id := NEW.org_id;
  IF TG_OP = 'INSERT' AND NEW.status = 'active' THEN
    CASE v_slug
      WHEN 'personal-finance' THEN PERFORM public.provision_personal_finance(v_org_id);
      WHEN 'therapy-platform' THEN PERFORM public.provision_therapy(v_org_id);
      ELSE NULL;
    END CASE;
    INSERT INTO public.notifications (user_id, org_id, type, title, message, metadata)
    SELECT nu.id, v_org_id, 'system',
      'Novo produto disponível',
      'Sua organização agora tem acesso ao ' || COALESCE((SELECT nome FROM public.products WHERE id = NEW.product_id), v_slug) || '!',
      jsonb_build_object('product', v_slug, 'license_id', NEW.id, 'action', 'granted')
    FROM public.noctus_users nu WHERE nu.org_id = v_org_id;
  ELSIF TG_OP = 'UPDATE' AND OLD.status = 'active' AND NEW.status = 'revoked' THEN
    PERFORM public.deprovision_product(v_org_id, v_slug);
  END IF;
  RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION public.on_license_change() FROM PUBLIC, anon, authenticated;

DROP FUNCTION IF EXISTS public.provision_erp(uuid);

-- ---------------------------------------------------------------------------
-- 3. nightly usage snapshot: drop the erp-imobiliario branch
-- ---------------------------------------------------------------------------
-- An erp licence now hits ELSE CONTINUE (no metrics row), like any product without
-- a usage query. The cron job and the /api/usage RPC call are unchanged.
CREATE OR REPLACE FUNCTION public.snapshot_product_usage()
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  lic RECORD;
  v_slug text;
  v_active_users bigint;
  v_total_records bigint;
  v_now timestamptz := now();
BEGIN
  FOR lic IN
    SELECT l.org_id, l.product_id, p.slug
    FROM public.licenses l
    JOIN public.products p ON p.id = l.product_id
    WHERE l.status = 'active'
  LOOP
    v_slug := lic.slug;
    v_active_users := 0;
    v_total_records := 0;

    CASE v_slug
      WHEN 'personal-finance' THEN
        -- Active users: distinct users with transactions in last 30 days
        SELECT COUNT(DISTINCT user_id) INTO v_active_users
        FROM "personal-finance".transacoes
        WHERE created_at > v_now - interval '30 days';

        -- Total records: contas + transacoes + categorias
        SELECT (
          (SELECT COUNT(*) FROM "personal-finance".contas) +
          (SELECT COUNT(*) FROM "personal-finance".transacoes) +
          (SELECT COUNT(*) FROM "personal-finance".categorias WHERE user_id IS NOT NULL)
        ) INTO v_total_records;

      WHEN 'therapy-platform' THEN
        -- Active users: distinct therapists/patients with appointments in last 30 days
        SELECT COUNT(DISTINCT therapist_id) + COUNT(DISTINCT patient_id) INTO v_active_users
        FROM therapy.appointments
        WHERE created_at > v_now - interval '30 days';

        -- Total records: appointments + session_records + reviews
        SELECT (
          (SELECT COUNT(*) FROM therapy.appointments) +
          (SELECT COUNT(*) FROM therapy.session_records) +
          (SELECT COUNT(*) FROM therapy.reviews)
        ) INTO v_total_records;

      ELSE
        CONTINUE;
    END CASE;

    -- Insert metrics
    INSERT INTO public.product_usage (org_id, product_id, metric, value, recorded_at)
    VALUES
      (lic.org_id, lic.product_id, 'active_users_30d', v_active_users, v_now),
      (lic.org_id, lic.product_id, 'total_records', v_total_records, v_now)
    ON CONFLICT (org_id, product_id, metric, recorded_at) DO UPDATE SET value = EXCLUDED.value;
  END LOOP;
END;
$function$;

REVOKE ALL ON FUNCTION public.snapshot_product_usage() FROM PUBLIC, anon, authenticated;
