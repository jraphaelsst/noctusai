-- Migration: sso_promotion_probe_guard
-- Schema: public
--
-- WHY (SSO identity hardening P2.1, roadmap sso-identity-hardening-2026-10).
-- Promoting a product to deploy_scope='live' makes its SSO regime STRICT
-- (fragment launch + mandatory product_slug). POST /api/products/{id}/deploy-scope
-- therefore probes the served bundle for SSO_CALLBACK_MARKER and refuses (409)
-- on the old callback. Any OTHER writer (hand SQL, a migration, a future job)
-- skipped that probe. A trigger cannot do HTTP, so the API records the probe's
-- verdict in the row (sso_callback_verified_at) and this trigger refuses a
-- transition INTO 'live' that does not carry it. Resolves
-- NOC-REMEDIATE[sso-promotion-sql-bypass].
--
-- Leaving 'live' clears the stamp: a later rebuild could regress the bundle,
-- so every re-promotion must be re-verified. The stamp can only exist on a
-- live row, so it must be set in the SAME statement as the promotion.
-- Residual: a human can still write the column by hand -- a deliberate act.
SET search_path = public, public;

ALTER TABLE public.products
  ADD COLUMN IF NOT EXISTS sso_callback_verified_at timestamptz;

-- Backfill: every product already live was verified on the new callback in
-- prod (2026-10-09). Idempotent (only fills NULLs); orbity/p-studio are 'dev'
-- and stay NULL.
UPDATE public.products
   SET sso_callback_verified_at = now()
 WHERE deploy_scope = 'live'
   AND sso_callback_verified_at IS NULL;

CREATE OR REPLACE FUNCTION public.enforce_sso_promotion_probe()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
  IF NEW.deploy_scope IS DISTINCT FROM 'live' THEN
    NEW.sso_callback_verified_at := NULL;
  ELSIF (TG_OP = 'INSERT' OR OLD.deploy_scope IS DISTINCT FROM 'live')
        AND NEW.sso_callback_verified_at IS NULL THEN
    RAISE EXCEPTION
      'product % cannot be promoted to live without a passing SSO callback probe; use POST /api/products/{id}/deploy-scope (sets sso_callback_verified_at)',
      NEW.slug
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sso_promotion_probe ON public.products;
CREATE TRIGGER trg_sso_promotion_probe
  BEFORE INSERT OR UPDATE ON public.products
  FOR EACH ROW EXECUTE FUNCTION public.enforce_sso_promotion_probe();
