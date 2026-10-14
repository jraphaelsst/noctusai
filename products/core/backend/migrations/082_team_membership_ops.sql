-- Migration: 082_team_membership_ops
-- Schema: public (core)
-- Roadmap: project-history/roadmaps/multi-org-membership-2026-10.md (Phase 2, S4 / P2.3)
--
-- The team router (accept-invite / remove-member / change-role) used to act on noctus_users
-- (one org per user). With multi-org memberships (core 079) those three operations become
-- MEMBERSHIP operations, and each one is several writes that must succeed or fail together --
-- PostgREST call sequences are not transactional, and the deferred constraint trigger from core
-- 081 (`org_memberships_profile_org_active`) refuses at COMMIT any transaction that ends the
-- membership a profile still points at. So each operation is ONE function (service_role only):
--
--   team_member_remove(org, user)          end the membership; if it was the user's profile org,
--                                          move the profile to their most recently updated other
--                                          ACTIVE membership (org_id + that membership's role) or,
--                                          with none, delete the profile (the pre-multi-org
--                                          behaviour); end their live org selections for the org.
--   team_member_set_role(org, user, role)  membership role (+ the profile mirror when this org is
--                                          the profile org) in one statement group.
--   team_invitation_accept(inv, user)      an EXISTING user accepts into another org: activate or
--                                          create the ACTIVE membership with the invited role, link
--                                          invited_by/invitation_id, mark the invitation accepted.
--                                          The profile does NOT move (last-active org stays put; the
--                                          new org is reached through the platform picker).
--
-- Refusals are `team_membership:<code>`; the router maps each code to a strict HTTP status.
-- "Last owner": ending or demoting the only ACTIVE owner of an org is refused here, serialised on
-- the organizations row so two concurrent owner removals cannot both pass the check.
--
-- EXPAND-ONLY: three new functions, nothing replaced, no table/column change. Rollback = DROP FUNCTION.
-- KB § PATTERNS/backend/tenancy-license-gate.md § Members
SET search_path = public, public;

-- 1. remove a member from ONE org --------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.team_member_remove(p_org_id uuid, p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $f$
DECLARE
  v_role        text;
  v_profile_org uuid;
  v_next_org    uuid;
  v_next_role   text;
  v_deleted     boolean := false;
  v_ended_sel   integer;
BEGIN
  -- serialise per org: the last-owner check below reads other rows
  PERFORM 1 FROM public.organizations o WHERE o.id = p_org_id FOR UPDATE;

  SELECT m.org_role INTO v_role
    FROM public.org_memberships m
   WHERE m.user_id = p_user_id AND m.org_id = p_org_id AND m.status = 'active'
     FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'team_membership:not_a_member';
  END IF;

  IF v_role = 'owner' AND NOT EXISTS (
       SELECT 1 FROM public.org_memberships o
        WHERE o.org_id = p_org_id AND o.status = 'active' AND o.org_role = 'owner'
          AND o.user_id <> p_user_id) THEN
    RAISE EXCEPTION 'team_membership:last_owner';
  END IF;

  UPDATE public.org_memberships
     SET status = 'removed', ended_at = now()
   WHERE user_id = p_user_id AND org_id = p_org_id;

  SELECT u.org_id INTO v_profile_org FROM public.noctus_users u WHERE u.id = p_user_id FOR UPDATE;
  IF v_profile_org = p_org_id THEN
    SELECT m.org_id, m.org_role INTO v_next_org, v_next_role
      FROM public.org_memberships m
     WHERE m.user_id = p_user_id AND m.org_id <> p_org_id AND m.status = 'active'
     ORDER BY m.updated_at DESC, m.created_at DESC
     LIMIT 1;
    IF FOUND THEN
      UPDATE public.noctus_users SET org_id = v_next_org, org_role = v_next_role WHERE id = p_user_id;
    ELSE
      BEGIN
        DELETE FROM public.noctus_users WHERE id = p_user_id;
      EXCEPTION WHEN foreign_key_violation THEN
        -- invitations.invited_by / api_keys.created_by / audit_logs.user_id reference the profile
        -- without a cascade (pre-multi-org behaviour: the old PostgREST delete failed the same
        -- way, as a bare 500). Typed refusal; the whole transaction rolls back, the membership stays.
        RAISE EXCEPTION 'team_membership:profile_in_use';
      END;
      v_deleted := true;
    END IF;
  END IF;

  UPDATE public.platform_org_selections
     SET ended_at = now(), ended_by = 'revoked'
   WHERE user_id = p_user_id AND target_org_id = p_org_id AND ended_at IS NULL;
  GET DIAGNOSTICS v_ended_sel = ROW_COUNT;

  RETURN jsonb_build_object(
    'user_id', p_user_id,
    'org_id', p_org_id,
    'profile_moved_to', v_next_org,
    'profile_deleted', v_deleted,
    'selections_ended', v_ended_sel
  );
END;
$f$;

-- 2. change a member's role in ONE org ----------------------------------------------------------
CREATE OR REPLACE FUNCTION public.team_member_set_role(p_org_id uuid, p_user_id uuid, p_role text)
RETURNS jsonb
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

  IF v_role = 'owner' AND p_role <> 'owner' AND NOT EXISTS (
       SELECT 1 FROM public.org_memberships o
        WHERE o.org_id = p_org_id AND o.status = 'active' AND o.org_role = 'owner'
          AND o.user_id <> p_user_id) THEN
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

-- 3. an existing user accepts an invitation into ANOTHER org -----------------------------------------
CREATE OR REPLACE FUNCTION public.team_invitation_accept(p_invitation_id uuid, p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $f$
DECLARE
  v_inv       public.invitations%ROWTYPE;
  v_email     text;
  v_status    text;
  v_inviter   uuid;
  v_activated integer;
BEGIN
  SELECT * INTO v_inv FROM public.invitations i WHERE i.id = p_invitation_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'team_membership:invitation_not_found';
  END IF;
  IF v_inv.status <> 'pending' THEN
    RAISE EXCEPTION 'team_membership:invitation_not_pending';
  END IF;
  IF v_inv.expires_at IS NOT NULL AND v_inv.expires_at < now() THEN
    RAISE EXCEPTION 'team_membership:invitation_expired';
  END IF;

  SELECT au.email INTO v_email FROM auth.users au WHERE au.id = p_user_id;
  IF v_email IS NULL OR lower(btrim(v_email)) <> lower(btrim(v_inv.email)) THEN
    RAISE EXCEPTION 'team_membership:email_mismatch';
  END IF;

  SELECT m.status INTO v_status
    FROM public.org_memberships m
   WHERE m.user_id = p_user_id AND m.org_id = v_inv.org_id
     FOR UPDATE;
  IF v_status = 'active' THEN
    RAISE EXCEPTION 'team_membership:already_member';
  ELSIF v_status = 'suspended' THEN
    -- a suspension is an org decision; accepting an invitation must not lift it
    RAISE EXCEPTION 'team_membership:membership_suspended';
  END IF;

  SELECT au.id INTO v_inviter FROM auth.users au WHERE au.id = v_inv.invited_by;

  INSERT INTO public.org_memberships (user_id, org_id, org_role, status, invited_by, invitation_id)
  VALUES (p_user_id, v_inv.org_id, v_inv.role, 'active', v_inviter, v_inv.id)
  ON CONFLICT (user_id, org_id) DO UPDATE
     SET org_role      = EXCLUDED.org_role,
         status        = 'active',
         ended_at      = NULL,
         invited_by    = EXCLUDED.invited_by,
         invitation_id = EXCLUDED.invitation_id
   WHERE public.org_memberships.status IN ('removed', 'invited');
  GET DIAGNOSTICS v_activated = ROW_COUNT;
  IF v_activated = 0 THEN
    -- lost a race with a concurrent activation/suspension
    RAISE EXCEPTION 'team_membership:already_member';
  END IF;

  UPDATE public.invitations SET status = 'accepted' WHERE id = v_inv.id;

  RETURN jsonb_build_object('user_id', p_user_id, 'org_id', v_inv.org_id, 'org_role', v_inv.role,
                            'invitation_id', v_inv.id, 'reactivated', COALESCE(v_status = 'removed', false));
END;
$f$;

-- 4. lockdown: service_role only ------------------------------------------------------------------
REVOKE EXECUTE ON FUNCTION public.team_member_remove(uuid, uuid) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.team_member_set_role(uuid, uuid, text) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.team_invitation_accept(uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.team_member_remove(uuid, uuid) TO service_role;
GRANT  EXECUTE ON FUNCTION public.team_member_set_role(uuid, uuid, text) TO service_role;
GRANT  EXECUTE ON FUNCTION public.team_invitation_accept(uuid, uuid) TO service_role;
