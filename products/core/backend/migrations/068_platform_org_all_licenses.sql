-- Migration: the platform org holds every product license, by construction
-- Schema: public (core)
--
-- WHY (owner decision 2026-10-07)
--   The NoctusAI platform org must reach EVERY product — including products
--   created in the future — always. The license gate's single source of truth
--   stays `public.licenses` (no `role == 'admin'` / org-id bypass in Python):
--   the platform org simply HOLDS an active, permanent license for every
--   product, and the database keeps it that way.
--
-- WHAT
--   1. organizations.is_platform — the platform operator's own org
--      (slug 'noctusai'). Exactly what the triggers below key on.
--   2. public.grant_platform_org_licenses() — inserts an active, permanent
--      (fim NULL) license for every (platform org x product) pair lacking an
--      active one, and clears any `fim` on an existing active one.
--      Idempotent. SECURITY DEFINER, search_path pinned, EXECUTE revoked.
--   3. Triggers that call it: AFTER INSERT ON products (a new product is
--      licensed to the platform org the moment it exists) and AFTER
--      INSERT/UPDATE OF is_platform ON organizations (an org becoming the
--      platform org gets everything).
--   4. public.licenses_platform_org_guard() — BEFORE UPDATE/DELETE on
--      licenses: refuses revoking, expiring, re-pointing or deleting a
--      platform org's ACTIVE license. A cascade from deleting the product or
--      the org itself is allowed (the parent row is already gone).
--   5. Backfill: run the grant once.
--
-- PROBES: verify_db_guards `licenses.platform_org.revoke_refused` +
--   `licenses.platform_org.holds_every_product` +
--   `licenses.platform_org.new_product_licensed`.
-- KB § PATTERNS/backend/tenancy-license-gate.md
SET search_path = public, public;

-- 1. organizations.is_platform -------------------------------------------------
ALTER TABLE public.organizations
    ADD COLUMN IF NOT EXISTS is_platform boolean NOT NULL DEFAULT false;
COMMENT ON COLUMN public.organizations.is_platform IS
    'The platform operator''s own org (NoctusAI). Holds an active, permanent '
    'license for every product by construction (core 068 triggers); its '
    'licenses cannot be revoked, expired or deleted.';

UPDATE public.organizations SET is_platform = true
 WHERE slug = 'noctusai' AND NOT is_platform;

-- 2. the grant ---------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.grant_platform_org_licenses()
  RETURNS void
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'public'
AS $$
BEGIN
  -- An active platform license is permanent: clear any expiry.
  UPDATE public.licenses l
     SET fim = NULL
    FROM public.organizations o
   WHERE o.id = l.org_id
     AND o.is_platform
     AND l.status = 'active'
     AND l.fim IS NOT NULL;

  INSERT INTO public.licenses (org_id, product_id, status, inicio, fim, source)
  SELECT o.id, p.id, 'active', now(), NULL, 'manual'
    FROM public.organizations o
   CROSS JOIN public.products p
   WHERE o.is_platform
     AND NOT EXISTS (
       SELECT 1 FROM public.licenses l
        WHERE l.org_id = o.id
          AND l.product_id = p.id
          AND l.status = 'active'
     );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.grant_platform_org_licenses() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.grant_platform_org_licenses() TO service_role;

-- 3. triggers that keep it true ------------------------------------------------
CREATE OR REPLACE FUNCTION public.platform_org_licenses_on_change()
  RETURNS trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'public'
AS $$
BEGIN
  PERFORM public.grant_platform_org_licenses();
  RETURN NULL;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.platform_org_licenses_on_change() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS products_grant_platform_org_license ON public.products;
CREATE TRIGGER products_grant_platform_org_license
    AFTER INSERT ON public.products
    FOR EACH STATEMENT EXECUTE FUNCTION public.platform_org_licenses_on_change();

DROP TRIGGER IF EXISTS organizations_grant_platform_org_licenses ON public.organizations;
CREATE TRIGGER organizations_grant_platform_org_licenses
    AFTER INSERT OR UPDATE OF is_platform ON public.organizations
    FOR EACH ROW WHEN (NEW.is_platform)
    EXECUTE FUNCTION public.platform_org_licenses_on_change();

-- 4. the "always" guarantee -----------------------------------------------------
CREATE OR REPLACE FUNCTION public.licenses_platform_org_guard()
  RETURNS trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'public'
AS $$
DECLARE
  v_platform boolean;
BEGIN
  IF OLD.status IS DISTINCT FROM 'active' THEN
    RETURN COALESCE(NEW, OLD);
  END IF;
  SELECT o.is_platform INTO v_platform
    FROM public.organizations o WHERE o.id = OLD.org_id;
  IF NOT COALESCE(v_platform, false) THEN
    -- Not the platform org — or the org row is already gone (cascade).
    RETURN COALESCE(NEW, OLD);
  END IF;
  IF TG_OP = 'DELETE' THEN
    IF NOT EXISTS (SELECT 1 FROM public.products p WHERE p.id = OLD.product_id) THEN
      RETURN OLD;  -- the product itself was deleted (ON DELETE CASCADE)
    END IF;
    RAISE EXCEPTION 'licenses_platform_org_guard: a licença ativa da organização da plataforma não pode ser excluída (ela mantém acesso a todos os produtos)'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.status IS DISTINCT FROM 'active'
     OR NEW.fim IS NOT NULL
     OR NEW.org_id IS DISTINCT FROM OLD.org_id
     OR NEW.product_id IS DISTINCT FROM OLD.product_id THEN
    RAISE EXCEPTION 'licenses_platform_org_guard: a licença da organização da plataforma não pode ser revogada, expirada nem transferida (ela mantém acesso a todos os produtos)'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.licenses_platform_org_guard() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS licenses_platform_org_guard ON public.licenses;
CREATE TRIGGER licenses_platform_org_guard
    BEFORE UPDATE OR DELETE ON public.licenses
    FOR EACH ROW EXECUTE FUNCTION public.licenses_platform_org_guard();

-- 5. backfill -------------------------------------------------------------------
SELECT public.grant_platform_org_licenses();
