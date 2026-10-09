-- Migration: platform org picker (staff enter a customer org per product, per login)
-- Schema: public (core)
-- Contract: projects/org-picker/CONTRACT.md (owner-confirmed 2026-10-08)
--
-- EXPAND-ONLY. Nothing the running image reads or writes changes behaviour:
--   * products gains two columns (db_schema, org_picker_ready=false) -- nothing reads them yet;
--   * platform_org_selections is a NEW service-role-only table -- nothing writes it yet;
--   * the RPCs / triggers / current_org_id_for() are NEW objects. current_org_id() and
--     current_user_org_id() are UNCHANGED (HOME-ONLY forever: public tables, storage and
--     realtime never act). A product's policies opt in by calling
--     (SELECT public.current_org_id_for('<schema>')) -- a policy literal, never a header.
--
-- WHO (staff): noctus_users.role = 'admin' AND the user's home org is_platform=true.
-- WHEN: one live selection per (user, product); bound to the Supabase auth session_id
--   (a new login never inherits it); aal2 is required for the helper to honour it.
-- ENDS (ended_by): replaced | new_session | exit | logout | revoked. The set RPC tags the
--   superseded row 'new_session' when it belonged to another login, else 'replaced'.
--
-- A product sets org_picker_ready = true only once EVERY policy in its schema is converted
-- (keeper check_org_picker_ready_policies).
-- KB § PATTERNS/backend/tenancy-license-gate.md § Platform org picker
SET search_path = public, public;

-- 1. products.db_schema + org_picker_ready -------------------------------------------
ALTER TABLE public.products ADD COLUMN IF NOT EXISTS db_schema text;
ALTER TABLE public.products ADD COLUMN IF NOT EXISTS org_picker_ready boolean NOT NULL DEFAULT false;
CREATE UNIQUE INDEX IF NOT EXISTS products_db_schema_key ON public.products (db_schema);

COMMENT ON COLUMN public.products.db_schema IS
    'The Postgres/PostgREST schema this product''s data lives in = its create_product_app(schema=...) '
    'declaration. current_org_id_for(p_schema) resolves the product from it.';
COMMENT ON COLUMN public.products.org_picker_ready IS
    'true once every RLS policy in db_schema uses current_org_id_for() (keeper-enforced). '
    'Only then may platform staff pick an org for the product.';

-- Backfill: derived from each product's create_product_app(schema=...) in
-- products/*/backend/app/main.py (test_migration_070 pins this list to the tree).
UPDATE public.products p
   SET db_schema = v.db_schema
  FROM (VALUES
    ('academia-de-reciclagem', 'academia_de_reciclagem'),
    ('adconnect', 'adconnect'),
    ('agents', 'agents'),
    ('community', 'community'),
    ('daily-life', 'daily_life'),
    ('dev-team', 'dev_team'),
    ('erp-imobiliario', 'erp'),
    ('igig', 'igig'),
    ('knowledge-extractor', 'knowledge_extractor'),
    ('orbity', 'orbity'),
    ('p-studio', 'p_studio'),
    ('personal-finance', 'personal-finance'),
    ('seed', 'seed'),
    ('social-wiring', 'social_wiring'),
    ('store', 'store'),
    ('therapy-platform', 'therapy')
  ) AS v(slug, db_schema)
 WHERE p.slug = v.slug AND p.db_schema IS DISTINCT FROM v.db_schema;

DO $$
DECLARE
  v_missing text;
BEGIN
  SELECT string_agg(slug, ', ' ORDER BY slug) INTO v_missing
    FROM public.products WHERE ativo IS NOT FALSE AND db_schema IS NULL;
  IF v_missing IS NOT NULL THEN
    RAISE NOTICE 'org picker: active product(s) without db_schema (not pickable until mapped): %', v_missing;
  END IF;
END
$$;

-- A ready product MUST name its schema (expand-safe: org_picker_ready defaults false).
ALTER TABLE public.products DROP CONSTRAINT IF EXISTS products_org_picker_ready_needs_schema;
ALTER TABLE public.products ADD CONSTRAINT products_org_picker_ready_needs_schema
    CHECK (NOT org_picker_ready OR db_schema IS NOT NULL);

-- 2. platform_org_selections ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.platform_org_selections (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES public.noctus_users(id) ON DELETE CASCADE,
    product_id      uuid NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    target_org_id   uuid NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    home_org_id     uuid NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    auth_session_id uuid NOT NULL,
    started_at      timestamptz NOT NULL DEFAULT now(),
    ended_at        timestamptz,
    ended_by        text CHECK (ended_by IN ('replaced', 'exit', 'logout', 'new_session', 'revoked')),
    CONSTRAINT platform_org_selections_ended_pair CHECK ((ended_at IS NULL) = (ended_by IS NULL))
);

-- At most one LIVE selection per (user, product).
CREATE UNIQUE INDEX IF NOT EXISTS platform_org_selections_one_live
    ON public.platform_org_selections (user_id, product_id) WHERE ended_at IS NULL;
-- The helper's lookup (live row bound to this login).
CREATE INDEX IF NOT EXISTS platform_org_selections_live_lookup
    ON public.platform_org_selections (user_id, product_id, auth_session_id) WHERE ended_at IS NULL;
CREATE INDEX IF NOT EXISTS platform_org_selections_target
    ON public.platform_org_selections (target_org_id, product_id) WHERE ended_at IS NULL;

ALTER TABLE public.platform_org_selections ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.platform_org_selections FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.platform_org_selections TO service_role;

COMMENT ON TABLE public.platform_org_selections IS
    'Platform-staff org picker: which org a staff user entered, per product, per login. '
    'Service-role only (RLS on, no policy); read by current_org_id_for() (SECURITY DEFINER).';

-- 3. RPCs (service_role only) ----------------------------------------------------------
CREATE OR REPLACE FUNCTION public.platform_org_selection_set(
    p_user_id         uuid,
    p_product_slug    text,
    p_target_org_id   uuid,
    p_auth_session_id uuid
) RETURNS uuid
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'public'
AS $$
DECLARE
  v_home       uuid;
  v_product_id uuid;
  v_id         uuid;
BEGIN
  SELECT u.org_id INTO v_home
    FROM public.noctus_users u
    JOIN public.organizations o ON o.id = u.org_id
   WHERE u.id = p_user_id
     AND u.role = 'admin'
     AND o.is_platform
     AND COALESCE(u.org_role, '') <> ALL (ARRAY['membro']);
  IF v_home IS NULL THEN
    RAISE EXCEPTION 'platform_org_selection:not_platform_staff';
  END IF;

  SELECT p.id INTO v_product_id
    FROM public.products p
   WHERE p.slug = p_product_slug AND p.org_picker_ready AND p.db_schema IS NOT NULL;
  IF v_product_id IS NULL THEN
    RAISE EXCEPTION 'platform_org_selection:product_not_ready';
  END IF;

  IF p_target_org_id IS NULL OR p_auth_session_id IS NULL OR NOT EXISTS (
       SELECT 1 FROM public.licenses l
        WHERE l.org_id = p_target_org_id AND l.product_id = v_product_id
          AND l.status = 'active' AND (l.fim IS NULL OR l.fim > now())) THEN
    RAISE EXCEPTION 'platform_org_selection:target_not_licensed';
  END IF;

  UPDATE public.platform_org_selections
     SET ended_at = now(),
         ended_by = CASE WHEN auth_session_id IS DISTINCT FROM p_auth_session_id
                         THEN 'new_session' ELSE 'replaced' END
   WHERE user_id = p_user_id AND product_id = v_product_id AND ended_at IS NULL;

  INSERT INTO public.platform_org_selections
         (user_id, product_id, target_org_id, home_org_id, auth_session_id)
  VALUES (p_user_id, v_product_id, p_target_org_id, v_home, p_auth_session_id)
  RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;

-- p_product_slug NULL = every product. Returns how many live selections it ended.
CREATE OR REPLACE FUNCTION public.platform_org_selection_end(
    p_user_id      uuid,
    p_product_slug text DEFAULT NULL,
    p_reason       text DEFAULT 'exit'
) RETURNS integer
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'public'
AS $$
DECLARE
  v_count integer;
BEGIN
  IF p_reason IS NULL OR p_reason NOT IN ('replaced', 'exit', 'logout', 'new_session', 'revoked') THEN
    RAISE EXCEPTION 'platform_org_selection:bad_reason';
  END IF;
  UPDATE public.platform_org_selections s
     SET ended_at = now(), ended_by = p_reason
   WHERE s.user_id = p_user_id
     AND s.ended_at IS NULL
     AND (p_product_slug IS NULL
          OR s.product_id IN (SELECT p.id FROM public.products p WHERE p.slug = p_product_slug));
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.platform_org_selection_set(uuid, text, uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.platform_org_selection_set(uuid, text, uuid, uuid) TO service_role;
REVOKE EXECUTE ON FUNCTION public.platform_org_selection_end(uuid, text, text) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.platform_org_selection_end(uuid, text, text) TO service_role;

-- 4. Revocation triggers (a live selection dies the moment its premise does) ------------
CREATE OR REPLACE FUNCTION public.platform_org_selection_revoke_user()
  RETURNS trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'public'
AS $$
BEGIN
  UPDATE public.platform_org_selections
     SET ended_at = now(), ended_by = 'revoked'
   WHERE user_id = NEW.id AND ended_at IS NULL;
  RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION public.platform_org_selection_revoke_home_org()
  RETURNS trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'public'
AS $$
BEGIN
  UPDATE public.platform_org_selections
     SET ended_at = now(), ended_by = 'revoked'
   WHERE home_org_id = NEW.id AND ended_at IS NULL;
  RETURN NULL;
END;
$$;

-- Ends the selection of the OLD (org, product) pair unless a valid active license
-- remains for it (a second active row, or a still-future fim, keeps it alive).
CREATE OR REPLACE FUNCTION public.platform_org_selection_revoke_license()
  RETURNS trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'public'
AS $$
BEGIN
  IF NOT EXISTS (
       SELECT 1 FROM public.licenses l
        WHERE l.org_id = OLD.org_id AND l.product_id = OLD.product_id
          AND l.status = 'active' AND (l.fim IS NULL OR l.fim > now())) THEN
    UPDATE public.platform_org_selections
       SET ended_at = now(), ended_by = 'revoked'
     WHERE target_org_id = OLD.org_id AND product_id = OLD.product_id AND ended_at IS NULL;
  END IF;
  RETURN NULL;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.platform_org_selection_revoke_user() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.platform_org_selection_revoke_home_org() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.platform_org_selection_revoke_license() FROM PUBLIC, anon, authenticated;

-- noctus_users DELETE needs no trigger: platform_org_selections.user_id is ON DELETE CASCADE.
DROP TRIGGER IF EXISTS noctus_users_revoke_org_selection ON public.noctus_users;
CREATE TRIGGER noctus_users_revoke_org_selection
    AFTER UPDATE OF org_id, org_role, role ON public.noctus_users
    FOR EACH ROW
    WHEN (OLD.org_id IS DISTINCT FROM NEW.org_id
          OR OLD.org_role IS DISTINCT FROM NEW.org_role
          OR OLD.role IS DISTINCT FROM NEW.role)
    EXECUTE FUNCTION public.platform_org_selection_revoke_user();

DROP TRIGGER IF EXISTS organizations_revoke_org_selection ON public.organizations;
CREATE TRIGGER organizations_revoke_org_selection
    AFTER UPDATE OF is_platform ON public.organizations
    FOR EACH ROW
    WHEN (OLD.is_platform IS DISTINCT FROM NEW.is_platform)
    EXECUTE FUNCTION public.platform_org_selection_revoke_home_org();

DROP TRIGGER IF EXISTS licenses_revoke_org_selection ON public.licenses;
CREATE TRIGGER licenses_revoke_org_selection
    AFTER UPDATE OF status, fim, org_id, product_id OR DELETE ON public.licenses
    FOR EACH ROW
    EXECUTE FUNCTION public.platform_org_selection_revoke_license();

-- 5. The RLS helper (canonical rendering: sql_templates.org_identity_function_sql) -------
-- secdef-execute-ok: rls-helper policies call current_org_id_for() as the caller (EXECUTE must stay)
CREATE OR REPLACE FUNCTION public.current_org_id_for(p_schema text)
  RETURNS uuid
  LANGUAGE plpgsql
  STABLE SECURITY DEFINER
  SET search_path TO 'public'
AS $f$
DECLARE
  v_uid      uuid := auth.uid();
  v_claims   jsonb := auth.jwt();
  v_home     uuid;
  v_org_role text;
  v_role     text;
  v_target   uuid;
  v_hdr      text;
BEGIN
  SELECT u.org_id, u.org_role, u.role INTO v_home, v_org_role, v_role
    FROM public.noctus_users u WHERE u.id = v_uid;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;
  IF COALESCE(v_org_role, '') = ANY (ARRAY['membro']) THEN
    RETURN NULL;
  END IF;
  IF v_role = 'admin' AND p_schema IS NOT NULL
     AND EXISTS (SELECT 1 FROM public.organizations o WHERE o.id = v_home AND o.is_platform)
  THEN
    SELECT s.target_org_id INTO v_target
      FROM public.products p
      JOIN public.platform_org_selections s
        ON s.product_id = p.id AND s.user_id = v_uid AND s.ended_at IS NULL
     WHERE p.db_schema = p_schema
       AND s.auth_session_id = NULLIF(v_claims ->> 'session_id', '')::uuid
       AND v_claims ->> 'aal' = 'aal2'
       AND EXISTS (
         SELECT 1 FROM public.licenses l
          WHERE l.org_id = s.target_org_id AND l.product_id = p.id
            AND l.status = 'active' AND (l.fim IS NULL OR l.fim > now()));
    IF FOUND THEN
      BEGIN
        v_hdr := NULLIF(btrim(NULLIF(current_setting('request.headers', true), '')::json
                              ->> 'x-noctus-acting-org'), '');
      EXCEPTION WHEN OTHERS THEN
        v_hdr := NULL;
      END;
      IF v_hdr IS NULL OR lower(v_hdr) = v_target::text THEN
        RETURN v_target;
      END IF;
    END IF;
  END IF;
  RETURN v_home;
END;
$f$;

COMMENT ON FUNCTION public.current_org_id_for(text) IS
    'Org picker RLS helper: the live-selection target for platform staff (aal2, this login, still '
    'licensed, optional x-noctus-acting-org narrowing), else the HOME rule (customers NULL). '
    'Product policies opt in with (SELECT public.current_org_id_for(''<schema>'')).';
