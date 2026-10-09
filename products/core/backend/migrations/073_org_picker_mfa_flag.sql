-- Migration: 073_org_picker_mfa_flag
-- Schema: public (core)
-- Contract: projects/org-picker/CONTRACT.md -- decision 5 revised (owner, 2026-10-09)
--
-- WHY: the picker required an aal2 (2FA) session (decision 5, 2026-10-08). On 2026-10-09 the
-- owner could not enroll 2FA (core /api/auth/mfa/status 500'd -- fixed in seed mfa_router) and
-- chose: drop the requirement now, restore it later ("do it so we can move on").
--
-- WHAT: products.org_picker_requires_mfa (default true = the 2026-10-08 rule) is the ONE switch
-- every layer reads -- this helper, the seed resolver (resolve_effective_org) and the picker
-- endpoints (me_router). It is set false for every product now.
-- RESTORE (the revisit trigger: the owner has enrolled 2FA):
--   UPDATE public.products SET org_picker_requires_mfa = true;
-- A live selection made from an aal1 session then simply stops resolving (helper + resolver
-- fall back to home) until the staff member steps up to aal2 -- no migration needed.
-- KB § PATTERNS/backend/tenancy-license-gate.md § Platform org picker
SET search_path = public, public;

ALTER TABLE public.products
    ADD COLUMN IF NOT EXISTS org_picker_requires_mfa boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN public.products.org_picker_requires_mfa IS
    'true = platform staff need an aal2 (2FA) session to act in another org through this product''s '
    'org picker (core 070 decision 5). Owner set false fleet-wide on 2026-10-09 (core 073); restore '
    'with UPDATE ... SET org_picker_requires_mfa = true.';

UPDATE public.products SET org_picker_requires_mfa = false;

-- canonical rendering: noctusai_lib.domain.sql_templates.org_identity_function_sql('current_org_id_for')
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
  IF v_role = 'admin' AND p_schema IS NOT NULL AND v_org_role IN ('owner', 'admin')
     AND EXISTS (SELECT 1 FROM public.organizations o WHERE o.id = v_home AND o.is_platform)
  THEN
    BEGIN
      v_hdr := NULLIF(btrim(NULLIF(current_setting('request.headers', true), '')::json
                            ->> 'x-noctus-acting-org'), '');
    EXCEPTION WHEN OTHERS THEN
      v_hdr := NULL;
    END;
    SELECT s.target_org_id INTO v_target
      FROM public.products p
      JOIN public.platform_org_selections s
        ON s.product_id = p.id AND s.user_id = v_uid AND s.ended_at IS NULL
     WHERE p.db_schema = p_schema AND p.org_picker_ready
       AND s.auth_session_id = NULLIF(v_claims ->> 'session_id', '')::uuid
       AND (NOT p.org_picker_requires_mfa OR v_claims ->> 'aal' = 'aal2')
       AND EXISTS (SELECT 1 FROM auth.sessions se WHERE se.id = s.auth_session_id)
       AND EXISTS (
         SELECT 1 FROM public.licenses l
          WHERE l.org_id = s.target_org_id AND l.product_id = p.id
            AND l.status = 'active' AND (l.fim IS NULL OR l.fim > now()));
    IF FOUND THEN
      IF v_hdr IS NULL OR lower(v_hdr) = v_target::text THEN
        RETURN v_target;
      END IF;
      RETURN NULL;
    END IF;
    IF v_hdr IS NOT NULL AND lower(v_hdr) <> v_home::text THEN
      RETURN NULL;
    END IF;
  END IF;
  RETURN v_home;
END;
$f$;

COMMENT ON FUNCTION public.current_org_id_for(text) IS
    'Org picker RLS helper: the live-selection target for platform staff (aal2 when the product''s '
    'org_picker_requires_mfa, this login with an existing auth session, product ready, still licensed); '
    'a present x-noctus-acting-org that differs from the result DENIES (NULL); else the HOME rule '
    '(customers NULL). Product policies opt in with (SELECT public.current_org_id_for(''<schema>'')).';
