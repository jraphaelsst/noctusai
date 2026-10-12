-- Migration: 078_org_picker_postgrest_entry
-- Schema: public (core)
-- Contract: projects/org-picker/CONTRACT.md -- "every entry is a choice" (owner, 2026-10-12)
--   closes the org-picker-postgrest-entry remediation marker (sql_templates.py)
--
-- WHY: since 2026-10-12 the seed resolver (noctusai_lib.api.auth.effective_org.resolve_effective_org)
-- refuses platform staff on an org_picker_ready product with no valid live selection
-- (409 org_selection_required) instead of resolving their HOME org -- every entry into a
-- product is a choice. Direct PostgREST reads still went through current_org_id_for(), whose
-- staff branch fell through to `RETURN v_home`, so the browser could read home-org rows the
-- API now refuses.
--
-- WHAT: current_org_id_for(p_schema) re-declared with ONE added branch, mirroring the resolver:
--   staff (role='admin', home org_role owner/admin, home org is_platform)
--   AND the product owning p_schema is org_picker_ready
--   AND the token passes the product's MFA rule (NOT org_picker_requires_mfa OR aal = 'aal2')
--   AND no valid live selection (this login, auth session alive, target licensed)
--   => NULL (RLS: no rows; writes refused).
-- Unchanged: non-staff -> home rule; product not ready / not a product schema -> home;
-- valid selection -> target; aal1 on a product that requires 2FA -> home (the resolver's
-- mfa_required path); x-noctus-acting-org stays narrowing-only (a mismatch -> NULL).
--
-- CALLERS (audited 2026-10-12): RLS policies (the intended effect: staff see nothing until they
-- pick); core 072 audit_acting_write (NULL target = "not acting" -> no audit row, as for home);
-- social-wiring 239 ai_outputs/ai_feedback `org_id DEFAULT current_org_id_for(...)` (a staff
-- insert without a selection now fails NOT NULL instead of landing in the home org -- the
-- write is refused either way; the FastAPI writer is gated by the 409 first);
-- social_wiring.fotos_lote_visivel (keeps its separate is_platform_admin() branch).
--
-- Function-only; no data change. Idempotent (CREATE OR REPLACE). Rollback = re-run core 073's
-- declaration.
-- KB § PATTERNS/backend/tenancy-license-gate.md § Platform org picker
SET search_path = public, public;

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
    IF EXISTS (SELECT 1 FROM public.products p
                WHERE p.db_schema = p_schema AND p.org_picker_ready
                  AND (NOT p.org_picker_requires_mfa OR v_claims ->> 'aal' = 'aal2')) THEN
      RETURN NULL;
    END IF;
  END IF;
  RETURN v_home;
END;
$f$;

COMMENT ON FUNCTION public.current_org_id_for(text) IS
    'Org picker RLS helper: the live-selection target for platform staff (aal2 when the product''s '
    'org_picker_requires_mfa, this login with an existing auth session, product ready, still licensed); '
    'staff on a ready product with NO valid selection (MFA rule satisfied) get NULL -- every entry is a '
    'choice (core 078); a present x-noctus-acting-org that differs from the result DENIES (NULL); else '
    'the HOME rule (customers NULL). Product policies opt in with (SELECT public.current_org_id_for(''<schema>'')).';
