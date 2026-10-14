-- Migration: 084_owner_grant_and_block_rules
-- Schema: public (core)
-- Roadmap: project-history/roadmaps/multi-org-membership-2026-10.md (Phase 2, S5b)
-- Owner decisions 2026-10-14 (P1-P5), implemented exactly:
--   P1 granting the role `owner` in an org is allowed ONLY to platform staff (NoctusAI owner +
--      admins, platform_staff_role owner|admin) -- through the role change AND the move target
--      role. An org owner may no longer grant it: team_membership:owner_grant_forbidden.
--   P2 D5 blocks survive removal + re-invite (they hang off the membership row): no change.
--   P3 NoctusAI staff can never be blocked: team_membership:cannot_block_staff.
--   P4 manager scope unchanged.
--   P5 block / unblock only by the org's OWNER, or platform staff (org_manager_role = 'owner');
--      an org ADMIN is refused team_membership:forbidden.
--
-- WHAT (CREATE OR REPLACE only, idempotent; 083's text otherwise verbatim):
--  1. org_member_product_access_set -- P5 authority + P3 refusal.
--  2. team_member_set_role(org, user, role, actor) -- P1 (the 3-arg 083 wrapper passes actor NULL,
--     so it can never grant owner either).
--  3. team_member_move -- P1 (before 083's role_above_actor cap, which stays as the general rule).
-- Refusal codes added: owner_grant_forbidden, cannot_block_staff.
-- ROLLBACK = re-run these three functions from 083_member_access_rules.sql.
-- KB § PATTERNS/backend/tenancy-license-gate.md § Members
SET search_path = public, public;

-- 1. block / unblock (D5 + P3 + P5) -------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.org_member_product_access_set(
    p_actor_id uuid, p_org_id uuid, p_user_id uuid, p_product_slug text, p_blocked boolean
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $f$
DECLARE
  v_pid     uuid;
  v_status  text;
  v_changed integer := 0;
BEGIN
  IF p_blocked IS NULL THEN
    RAISE EXCEPTION 'team_membership:invalid_request';
  END IF;
  -- P5: only the org's OWNER (or platform staff, who manage any org as owner) blocks/unblocks;
  -- an org ADMIN no longer may.
  IF public.org_manager_role(p_actor_id, p_org_id) IS DISTINCT FROM 'owner' THEN
    RAISE EXCEPTION 'team_membership:forbidden';
  END IF;
  SELECT p.id INTO v_pid FROM public.products p WHERE p.slug = p_product_slug;
  IF v_pid IS NULL THEN
    RAISE EXCEPTION 'team_membership:product_not_found';
  END IF;
  -- P3: NoctusAI staff can never be blocked (unblocking an old row stays allowed).
  IF p_blocked AND public.platform_staff_role(p_user_id) IS NOT NULL THEN
    RAISE EXCEPTION 'team_membership:cannot_block_staff';
  END IF;
  -- serialise per (user, org): the membership row is the lock
  SELECT m.status INTO v_status FROM public.org_memberships m
   WHERE m.user_id = p_user_id AND m.org_id = p_org_id FOR UPDATE;

  IF p_blocked THEN
    IF v_status IS DISTINCT FROM 'active' THEN
      RAISE EXCEPTION 'team_membership:not_a_member';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.licenses l
                    WHERE l.org_id = p_org_id AND l.product_id = v_pid
                      AND l.status = 'active' AND (l.fim IS NULL OR l.fim > now())) THEN
      RAISE EXCEPTION 'team_membership:not_licensed';
    END IF;
    INSERT INTO public.org_member_product_access (user_id, org_id, product_id, blocked_by)
    SELECT p_user_id, p_org_id, v_pid, au.id
      FROM (SELECT p_actor_id AS id) a LEFT JOIN auth.users au ON au.id = a.id
    ON CONFLICT (user_id, org_id, product_id) WHERE unblocked_at IS NULL DO NOTHING;
    GET DIAGNOSTICS v_changed = ROW_COUNT;
    -- a live pick of the now-blocked org ends at once (the helpers re-check anyway)
    UPDATE public.platform_org_selections
       SET ended_at = now(), ended_by = 'revoked'
     WHERE user_id = p_user_id AND product_id = v_pid AND target_org_id = p_org_id
       AND ended_at IS NULL;
  ELSE
    IF v_status IS NULL THEN
      RAISE EXCEPTION 'team_membership:not_a_member';
    END IF;
    UPDATE public.org_member_product_access
       SET unblocked_at = now(),
           unblocked_by = (SELECT au.id FROM auth.users au WHERE au.id = p_actor_id)
     WHERE user_id = p_user_id AND org_id = p_org_id AND product_id = v_pid
       AND unblocked_at IS NULL;
    GET DIAGNOSTICS v_changed = ROW_COUNT;
  END IF;

  RETURN jsonb_build_object('user_id', p_user_id, 'org_id', p_org_id, 'product_id', v_pid,
                            'product_slug', p_product_slug, 'blocked', p_blocked,
                            'changed', v_changed > 0);
END;
$f$;

-- 2. change a member's role in ONE org (D2 override + P1) -----------------------------------------
CREATE OR REPLACE FUNCTION public.team_member_set_role(
    p_org_id uuid, p_user_id uuid, p_role text, p_actor_id uuid
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $f$
DECLARE
  v_role        text;
  v_profile_org uuid;
BEGIN
  IF p_role IS NULL OR btrim(p_role) = '' THEN
    RAISE EXCEPTION 'team_membership:invalid_role';
  END IF;
  PERFORM 1 FROM public.organizations o WHERE o.id = p_org_id FOR UPDATE;

  SELECT m.org_role INTO v_role
    FROM public.org_memberships m
   WHERE m.user_id = p_user_id AND m.org_id = p_org_id AND m.status = 'active'
     FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'team_membership:not_a_member';
  END IF;

  -- P1: granting `owner` is for platform staff only (from the ACTOR, never a caller flag).
  IF p_role = 'owner' AND v_role IS DISTINCT FROM 'owner'
     AND public.platform_staff_role(p_actor_id) IS NULL THEN
    RAISE EXCEPTION 'team_membership:owner_grant_forbidden';
  END IF;

  IF v_role = 'owner' AND p_role <> 'owner' AND NOT EXISTS (
       SELECT 1 FROM public.org_memberships o
        WHERE o.org_id = p_org_id AND o.status = 'active' AND o.org_role = 'owner'
          AND o.user_id <> p_user_id)
     AND public.platform_staff_role(p_actor_id) IS DISTINCT FROM 'owner' THEN
    RAISE EXCEPTION 'team_membership:last_owner';
  END IF;

  UPDATE public.org_memberships SET org_role = p_role
   WHERE user_id = p_user_id AND org_id = p_org_id;

  -- the profile mirrors the role of its OWN org only; another org's role must never leak into it
  SELECT u.org_id INTO v_profile_org FROM public.noctus_users u WHERE u.id = p_user_id;
  IF v_profile_org = p_org_id THEN
    UPDATE public.noctus_users SET org_role = p_role WHERE id = p_user_id;
  END IF;

  RETURN jsonb_build_object('user_id', p_user_id, 'org_id', p_org_id, 'org_role', p_role,
                            'previous_org_role', v_role);
END;
$f$;

-- 3. move a user between orgs (D3 + P1) -------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.team_member_move(
    p_actor_id uuid, p_user_id uuid, p_source_org_id uuid, p_target_org_id uuid,
    p_role text, p_mode text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $f$
DECLARE
  v_src_mgr     text;
  v_tgt_mgr     text;
  v_src_role    text;
  v_tgt_status  text;
  v_profile_org uuid;
  v_inviter     uuid;
  v_done        integer;
  v_moved       boolean := false;
  v_ended_sel   integer := 0;
BEGIN
  IF p_mode IS NULL OR p_mode NOT IN ('transfer', 'add') THEN
    RAISE EXCEPTION 'team_membership:invalid_mode';
  END IF;
  IF p_role IS NULL OR btrim(p_role) = '' THEN
    RAISE EXCEPTION 'team_membership:invalid_role';
  END IF;
  IF p_source_org_id IS NULL OR p_target_org_id IS NULL OR p_source_org_id = p_target_org_id THEN
    RAISE EXCEPTION 'team_membership:same_org';
  END IF;
  -- serialise on both orgs, always in the same order (no deadlock between two opposite moves)
  PERFORM 1 FROM public.organizations o
   WHERE o.id IN (p_source_org_id, p_target_org_id) ORDER BY o.id FOR UPDATE;
  IF (SELECT count(*) FROM public.organizations o
       WHERE o.id IN (p_source_org_id, p_target_org_id)) <> 2 THEN
    RAISE EXCEPTION 'team_membership:org_not_found';
  END IF;

  v_src_mgr := public.org_manager_role(p_actor_id, p_source_org_id);
  v_tgt_mgr := public.org_manager_role(p_actor_id, p_target_org_id);
  IF v_src_mgr IS NULL OR v_tgt_mgr IS NULL THEN
    RAISE EXCEPTION 'team_membership:forbidden';
  END IF;
  -- P1: granting `owner` is for platform staff only (from the ACTOR, never a caller flag).
  IF p_role = 'owner' AND public.platform_staff_role(p_actor_id) IS NULL THEN
    RAISE EXCEPTION 'team_membership:owner_grant_forbidden';
  END IF;
  -- never above the actor's own role in the target (owner > admin > every other role)
  IF p_role = 'owner' AND v_tgt_mgr <> 'owner' THEN
    RAISE EXCEPTION 'team_membership:role_above_actor';
  END IF;

  SELECT m.org_role INTO v_src_role
    FROM public.org_memberships m
   WHERE m.user_id = p_user_id AND m.org_id = p_source_org_id AND m.status = 'active'
     FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'team_membership:not_a_member';
  END IF;

  SELECT m.status INTO v_tgt_status
    FROM public.org_memberships m
   WHERE m.user_id = p_user_id AND m.org_id = p_target_org_id
     FOR UPDATE;
  IF v_tgt_status = 'active' THEN
    RAISE EXCEPTION 'team_membership:already_member';
  ELSIF v_tgt_status = 'suspended' THEN
    RAISE EXCEPTION 'team_membership:membership_suspended';
  END IF;

  IF p_mode = 'transfer' AND v_src_role = 'owner' AND NOT EXISTS (
       SELECT 1 FROM public.org_memberships o
        WHERE o.org_id = p_source_org_id AND o.status = 'active' AND o.org_role = 'owner'
          AND o.user_id <> p_user_id)
     AND public.platform_staff_role(p_actor_id) IS DISTINCT FROM 'owner' THEN
    RAISE EXCEPTION 'team_membership:last_owner';
  END IF;

  SELECT au.id INTO v_inviter FROM auth.users au WHERE au.id = p_actor_id;
  INSERT INTO public.org_memberships (user_id, org_id, org_role, status, invited_by)
  VALUES (p_user_id, p_target_org_id, p_role, 'active', v_inviter)
  ON CONFLICT (user_id, org_id) DO UPDATE
     SET org_role      = EXCLUDED.org_role,
         status        = 'active',
         ended_at      = NULL,
         invited_by    = EXCLUDED.invited_by,
         invitation_id = NULL
   WHERE public.org_memberships.status IN ('removed', 'invited');
  GET DIAGNOSTICS v_done = ROW_COUNT;
  IF v_done = 0 THEN
    RAISE EXCEPTION 'team_membership:already_member';
  END IF;

  IF p_mode = 'transfer' THEN
    UPDATE public.org_memberships
       SET status = 'removed', ended_at = now()
     WHERE user_id = p_user_id AND org_id = p_source_org_id;
    SELECT u.org_id INTO v_profile_org FROM public.noctus_users u WHERE u.id = p_user_id FOR UPDATE;
    IF v_profile_org = p_source_org_id THEN
      UPDATE public.noctus_users SET org_id = p_target_org_id, org_role = p_role WHERE id = p_user_id;
      v_moved := true;
    END IF;
    UPDATE public.platform_org_selections
       SET ended_at = now(), ended_by = 'revoked'
     WHERE user_id = p_user_id AND target_org_id = p_source_org_id AND ended_at IS NULL;
    GET DIAGNOSTICS v_ended_sel = ROW_COUNT;
  END IF;

  RETURN jsonb_build_object(
    'user_id', p_user_id, 'source_org_id', p_source_org_id, 'target_org_id', p_target_org_id,
    'org_role', p_role, 'mode', p_mode, 'previous_org_role', v_src_role,
    'source_ended', p_mode = 'transfer', 'profile_moved', v_moved,
    'reactivated', COALESCE(v_tgt_status IN ('removed', 'invited'), false),
    'selections_ended', v_ended_sel
  );
END;
$f$;

REVOKE EXECUTE ON FUNCTION public.org_member_product_access_set(uuid, uuid, uuid, text, boolean) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.team_member_set_role(uuid, uuid, text, uuid) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.team_member_move(uuid, uuid, uuid, uuid, text, text) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.org_member_product_access_set(uuid, uuid, uuid, text, boolean) TO service_role;
GRANT  EXECUTE ON FUNCTION public.team_member_set_role(uuid, uuid, text, uuid) TO service_role;
GRANT  EXECUTE ON FUNCTION public.team_member_move(uuid, uuid, uuid, uuid, text, text) TO service_role;
