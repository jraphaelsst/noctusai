-- Migration: 081_org_member_selection
-- Schema: public (core)
-- Roadmap: project-history/roadmaps/multi-org-membership-2026-10.md (Phase 2, S2+S3)
-- Owner decisions 2026-10-13 (Q1-Q3): members switch orgs through the EXISTING platform org
-- picker (no second mechanism); aal2 only for staff; a multi-org user chooses only when the
-- last-active org is not licensed for the product; noctus_users.org_id/org_role = the
-- last-active org and FOLLOW the member's selection.
--
-- WHAT (function-only; no table/column change; idempotent -- CREATE OR REPLACE):
--  1. platform_org_selection_set(): WHO may select widens from "staff" to "staff OR an ACTIVE
--     member of the target org". A non-staff caller must hold an ACTIVE org_memberships row for
--     the target (else platform_org_selection:not_a_member). Staff behaviour is unchanged (same
--     refusals, same codes, profile untouched). For a member the profile mirror
--     (noctus_users.org_id/org_role) is moved to the target IN THE SAME TRANSACTION, BEFORE the
--     selection row is written: org_role is the MEMBERSHIP role in the target (never the previous
--     home role, never a promotion beyond the membership), and the 079 mirror trigger upserts
--     the SAME membership values -- it can neither end nor downgrade one. The 070 revocation
--     trigger ends the member's other live selections when the mirror moves (the "last-active
--     org" is one value), so the INSERT below is the only live row.
--  2. current_org_id_for(): a member's selection resolves ONLY while the membership is still
--     ACTIVE (re-checked on every call, revocation-by-recheck; nothing in the JWT), the login
--     is the one that chose, the auth session lives, the target is licensed. No aal2 for
--     members. The pin header only narrows (mismatch -> NULL). A removed member's selection
--     stops resolving on the next query and the home fall-back itself requires an ACTIVE
--     membership in the home org, so it never falls back to the org they were removed from.
--
-- ROLLBACK = re-run core 070's declaration of platform_org_selection_set (staff-only) and core
-- 078's declaration of current_org_id_for.
-- KB § PATTERNS/backend/tenancy-license-gate.md § Platform org picker
SET search_path = public, public;

-- 1. the selection RPC (service_role only) -----------------------------------------------------
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
  v_staff      boolean := false;
  v_mrole      text;
BEGIN
  SELECT u.org_id INTO v_home
    FROM public.noctus_users u
    JOIN public.organizations o ON o.id = u.org_id
   WHERE u.id = p_user_id
     AND u.role = 'admin'
     AND o.is_platform
     AND u.org_role IN ('owner', 'admin');
  v_staff := v_home IS NOT NULL;

  IF NOT v_staff THEN
    -- Member path: an ACTIVE membership in the target, locked so a concurrent removal waits.
    SELECT u.org_id INTO v_home FROM public.noctus_users u WHERE u.id = p_user_id;
    SELECT m.org_role INTO v_mrole
      FROM public.org_memberships m
     WHERE m.user_id = p_user_id AND m.org_id = p_target_org_id AND m.status = 'active'
       FOR SHARE;
    IF v_home IS NULL OR v_mrole IS NULL THEN
      RAISE EXCEPTION 'platform_org_selection:not_a_member';
    END IF;
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

  IF NOT v_staff THEN
    -- Q3: the profile follows the selection (last-active org). Only a CHANGE writes, so the
    -- 070 revocation trigger fires only when the mirror really moves.
    UPDATE public.noctus_users
       SET org_id = p_target_org_id, org_role = v_mrole
     WHERE id = p_user_id
       AND (org_id IS DISTINCT FROM p_target_org_id OR org_role IS DISTINCT FROM v_mrole);
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

-- CREATE OR REPLACE keeps the 070 grants; restated so the file is self-evidently lockdown-safe.
REVOKE EXECUTE ON FUNCTION public.platform_org_selection_set(uuid, text, uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.platform_org_selection_set(uuid, text, uuid, uuid) TO service_role;

-- 2. the RLS helper ---------------------------------------------------------------------------
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
  v_mrole    text;
  v_hdr      text;
BEGIN
  SELECT u.org_id, u.org_role, u.role INTO v_home, v_org_role, v_role
    FROM public.noctus_users u WHERE u.id = v_uid;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;
  BEGIN
    v_hdr := NULLIF(btrim(NULLIF(current_setting('request.headers', true), '')::json
                          ->> 'x-noctus-acting-org'), '');
  EXCEPTION WHEN OTHERS THEN
    v_hdr := NULL;
  END;
  IF v_role = 'admin' AND p_schema IS NOT NULL AND v_org_role IN ('owner', 'admin')
     AND EXISTS (SELECT 1 FROM public.organizations o WHERE o.id = v_home AND o.is_platform)
  THEN
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
  ELSIF p_schema IS NOT NULL THEN
    SELECT s.target_org_id, m.org_role INTO v_target, v_mrole
      FROM public.products p
      JOIN public.platform_org_selections s
        ON s.product_id = p.id AND s.user_id = v_uid AND s.ended_at IS NULL
      JOIN public.org_memberships m
        ON m.user_id = v_uid AND m.org_id = s.target_org_id AND m.status = 'active'
     WHERE p.db_schema = p_schema AND p.org_picker_ready
       AND s.auth_session_id = NULLIF(v_claims ->> 'session_id', '')::uuid
       AND EXISTS (SELECT 1 FROM auth.sessions se WHERE se.id = s.auth_session_id)
       AND EXISTS (
         SELECT 1 FROM public.licenses l
          WHERE l.org_id = s.target_org_id AND l.product_id = p.id
            AND l.status = 'active' AND (l.fim IS NULL OR l.fim > now()));
    IF FOUND THEN
      IF COALESCE(v_mrole, '') = ANY (ARRAY['membro']) THEN
        RETURN NULL;
      END IF;
      IF v_hdr IS NULL OR lower(v_hdr) = v_target::text THEN
        RETURN v_target;
      END IF;
      RETURN NULL;
    END IF;
  END IF;
  IF COALESCE(v_org_role, '') = ANY (ARRAY['membro']) THEN
    RETURN NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.org_memberships m
                  WHERE m.user_id = v_uid AND m.org_id = v_home AND m.status = 'active') THEN
    RETURN NULL;
  END IF;
  RETURN v_home;
END;
$f$;

COMMENT ON FUNCTION public.current_org_id_for(text) IS
    'Org picker RLS helper: staff -> the live-selection target (aal2 when the product''s '
    'org_picker_requires_mfa, this login, auth session alive, still licensed); staff on a ready '
    'product with no valid selection -> NULL (core 078); MEMBERS (multi-org S3) -> the live-selection '
    'target only while the org_memberships row is ACTIVE (re-checked every call, no aal2); a present '
    'x-noctus-acting-org that differs from the result DENIES; else the HOME rule (customers NULL, '
    'home must be an ACTIVE membership). Product policies opt in with '
    '(SELECT public.current_org_id_for(''<schema>'')).';
