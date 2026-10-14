-- Migration: 083_member_access_rules
-- Schema: public (core)
-- Roadmap: project-history/roadmaps/multi-org-membership-2026-10.md (Phase 2, S4b)
-- Owner decisions 2026-10-14 (D1-D5), implemented exactly:
--   D1 a NON-staff member chooses the org on EVERY entry into a product iff they hold >=2
--      ELIGIBLE orgs for it (ACTIVE, non-customer membership; org licensed for the product; not
--      blocked by D5). Exactly one eligible org -> land there silently. Replaces Q2 (2026-10-13).
--   D2 NoctusAI owner + admins (platform staff) manage ANY org's team; ONLY the NoctusAI owner
--      may override "never remove/demote an org's last owner".
--   D3 moving a user between orgs (mode transfer | add), platform staff anywhere, an org
--      owner/admin only between orgs where they are owner/admin in BOTH; target role never above
--      the actor's role in the target; last-owner rule on transfer (D2 override only).
--   D4 removing a user whose ONLY active membership is this org keeps the profile: it moves to a
--      personal org of their own (created by the caller through the signup org path, validated
--      here) in the same transaction. First-time invitees get invited_by/invitation_id linked.
--   D5 per-user product access: an org owner/admin (or platform staff) may BLOCK a member from a
--      product inside the org, and unblock. Default (no live row) = access.
--
-- WHAT (expand-only, idempotent):
--  0. organizations.is_personal claimed by core (ADD COLUMN IF NOT EXISTS; personal-finance 008
--     added it first -- same definition).
--  1. platform_staff_role(user) / org_manager_role(actor, org): the ONE SQL definition of
--     "platform staff" (noctus_users.role='admin' AND home org_role owner/admin AND home org
--     is_platform -- the resolver's rule) and of "may manage this org" (staff, or an ACTIVE
--     owner/admin membership). Internal helpers, EXECUTE revoked from API roles.
--  2. public.org_member_product_access: one row per BLOCK (append-only history: a block is
--     ended by stamping unblocked_at/unblocked_by, never deleted or rewritten). Why a table and
--     not a blocked-products column on org_memberships: (a) a product id array cannot carry an FK
--     to products; (b) who blocked/unblocked and when is the audit, per entry; (c) writing the
--     membership row would re-fire the 079 mirror + 081 invariant triggers and bump updated_at,
--     which team_member_remove uses to pick the profile's next org.
--  3. org_member_product_access_set(actor, org, user, product_slug, blocked) -- D5 write RPC.
--  4. team_member_remove / team_member_set_role gain an actor (D2 override) and remove gains the
--     personal org (D4): new 4-arg implementations; the 082 signatures stay as thin wrappers
--     (actor NULL = no override; a sole membership without a personal org is refused
--     personal_org_required -- the profile is never deleted any more).
--  5. team_member_move(actor, user, source, target, role, mode) -- D3.
--  6. team_invitation_accept(inv, user, nome) -- also creates a FIRST-TIME invitee's profile and
--     links invited_by/invitation_id on the membership (D4), one transaction; the 2-arg 082
--     signature is a wrapper.
--  7. platform_org_selection_set: a member may not select an org they are blocked in for the
--     product (platform_org_selection:product_blocked). Staff path unchanged.
--  8. current_org_id_for: D1 + D5 (canonical text: sql_templates.org_identity_function_sql).
--
-- Refusal codes: team_membership:<code> (not_a_member, last_owner, invalid_role, invalid_mode,
-- same_org, org_not_found, forbidden, role_above_actor, already_member, membership_suspended,
-- personal_org_required, personal_org_invalid, product_not_found, not_licensed, ...).
-- ROLLBACK = re-run 082's three functions and 081's two; DROP the new functions + table.
-- KB § PATTERNS/backend/tenancy-license-gate.md § Members
SET search_path = public, public;

-- 0. organizations.is_personal (core claims it) ------------------------------------------------
ALTER TABLE public.organizations
    ADD COLUMN IF NOT EXISTS is_personal boolean NOT NULL DEFAULT false;

-- 1. who is platform staff / who may manage an org ---------------------------------------------
CREATE OR REPLACE FUNCTION public.platform_staff_role(p_user_id uuid)
RETURNS text
LANGUAGE sql
STABLE SECURITY DEFINER
SET search_path = public
AS $f$
  SELECT u.org_role
    FROM public.noctus_users u
    JOIN public.organizations o ON o.id = u.org_id
   WHERE u.id = p_user_id AND u.role = 'admin' AND o.is_platform
     AND u.org_role IN ('owner', 'admin');
$f$;

COMMENT ON FUNCTION public.platform_staff_role(uuid) IS
    'owner | admin for NoctusAI platform staff (noctus_users.role=admin AND home org_role owner/admin '
    'AND home org is_platform -- the resolver''s staff rule), else NULL. owner = the NoctusAI owner '
    '(D2: the only one who may override the last-owner rule).';

CREATE OR REPLACE FUNCTION public.org_manager_role(p_actor_id uuid, p_org_id uuid)
RETURNS text
LANGUAGE sql
STABLE SECURITY DEFINER
SET search_path = public
AS $f$
  SELECT CASE
           WHEN public.platform_staff_role(p_actor_id) IS NOT NULL THEN 'owner'
           ELSE (SELECT m.org_role FROM public.org_memberships m
                  WHERE m.user_id = p_actor_id AND m.org_id = p_org_id AND m.status = 'active'
                    AND m.org_role IN ('owner', 'admin'))
         END;
$f$;

COMMENT ON FUNCTION public.org_manager_role(uuid, uuid) IS
    'The role an actor manages org p_org_id with: owner for platform staff (any org, D2), else their '
    'ACTIVE owner/admin membership role there, else NULL (may not manage it: D3/D5).';

REVOKE EXECUTE ON FUNCTION public.platform_staff_role(uuid) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.org_manager_role(uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.platform_staff_role(uuid) TO service_role;
GRANT  EXECUTE ON FUNCTION public.org_manager_role(uuid, uuid) TO service_role;

-- 2. per-member product blocks (D5) -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.org_member_product_access (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid        NOT NULL,
    org_id        uuid        NOT NULL,
    product_id    uuid        NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    blocked_by    uuid        REFERENCES auth.users(id) ON DELETE SET NULL,
    blocked_at    timestamptz NOT NULL DEFAULT now(),
    unblocked_by  uuid        REFERENCES auth.users(id) ON DELETE SET NULL,
    unblocked_at  timestamptz,
    CONSTRAINT org_member_product_access_membership_fkey
        FOREIGN KEY (user_id, org_id) REFERENCES public.org_memberships (user_id, org_id) ON DELETE CASCADE,
    CONSTRAINT org_member_product_access_unblocked_by_needs_at
        CHECK (unblocked_by IS NULL OR unblocked_at IS NOT NULL)
);

-- at most ONE live block per (user, org, product)
CREATE UNIQUE INDEX IF NOT EXISTS org_member_product_access_one_live
    ON public.org_member_product_access (user_id, org_id, product_id) WHERE unblocked_at IS NULL;
CREATE INDEX IF NOT EXISTS org_member_product_access_org_idx
    ON public.org_member_product_access (org_id) WHERE unblocked_at IS NULL;

COMMENT ON TABLE public.org_member_product_access IS
    'D5 (owner, 2026-10-14): a LIVE row (unblocked_at IS NULL) blocks user x org x product -- that org is '
    'then not an eligible choice for the user in the product, SSO does not admit through it and '
    'current_org_id_for/resolve_effective_org never resolve to it. No live row = access. Append-only '
    'history: unblocking stamps unblocked_at/unblocked_by. Written only by org_member_product_access_set.';

ALTER TABLE public.org_member_product_access ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.org_member_product_access FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.org_member_product_access TO authenticated;
GRANT ALL ON public.org_member_product_access TO service_role;
DROP POLICY IF EXISTS org_member_product_access_self_read ON public.org_member_product_access;
CREATE POLICY org_member_product_access_self_read ON public.org_member_product_access
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

-- append-only: identity and blocked_at never change; a block is closed once (unblocked_at set);
-- the only other change allowed is an FK ON DELETE SET NULL of blocked_by/unblocked_by.
CREATE OR REPLACE FUNCTION public.org_member_product_access_append_only()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public
AS $f$
BEGIN
  IF NEW.id IS DISTINCT FROM OLD.id
     OR NEW.user_id IS DISTINCT FROM OLD.user_id
     OR NEW.org_id IS DISTINCT FROM OLD.org_id
     OR NEW.product_id IS DISTINCT FROM OLD.product_id
     OR NEW.blocked_at IS DISTINCT FROM OLD.blocked_at
     OR (OLD.unblocked_at IS NOT NULL AND NEW.unblocked_at IS DISTINCT FROM OLD.unblocked_at)
     OR (NEW.blocked_by IS DISTINCT FROM OLD.blocked_by AND NEW.blocked_by IS NOT NULL)
     OR (OLD.unblocked_at IS NOT NULL AND NEW.unblocked_by IS DISTINCT FROM OLD.unblocked_by
         AND NEW.unblocked_by IS NOT NULL) THEN
    RAISE EXCEPTION 'org_member_product_access_append_only: a block row is history; only closing a live block (unblocked_at/unblocked_by) is allowed'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$f$;

REVOKE EXECUTE ON FUNCTION public.org_member_product_access_append_only() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS org_member_product_access_append_only ON public.org_member_product_access;
CREATE TRIGGER org_member_product_access_append_only
    BEFORE UPDATE ON public.org_member_product_access
    FOR EACH ROW EXECUTE FUNCTION public.org_member_product_access_append_only();

-- 3. block / unblock (D5) -----------------------------------------------------------------------
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
  IF public.org_manager_role(p_actor_id, p_org_id) IS NULL THEN
    RAISE EXCEPTION 'team_membership:forbidden';
  END IF;
  SELECT p.id INTO v_pid FROM public.products p WHERE p.slug = p_product_slug;
  IF v_pid IS NULL THEN
    RAISE EXCEPTION 'team_membership:product_not_found';
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

REVOKE EXECUTE ON FUNCTION public.org_member_product_access_set(uuid, uuid, uuid, text, boolean) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.org_member_product_access_set(uuid, uuid, uuid, text, boolean) TO service_role;

-- 4a. remove a member from ONE org (D2 override + D4 personal org) ----------------------------------
CREATE OR REPLACE FUNCTION public.team_member_remove(
    p_org_id uuid, p_user_id uuid, p_actor_id uuid, p_personal_org_id uuid
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $f$
DECLARE
  v_role        text;
  v_profile_org uuid;
  v_next_org    uuid;
  v_next_role   text;
  v_personal    uuid;
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
          AND o.user_id <> p_user_id)
     AND public.platform_staff_role(p_actor_id) IS DISTINCT FROM 'owner' THEN
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
      -- D4: the profile (and its append-only audit history) stays; it moves to a personal org of
      -- the user's own, created by the caller through the signup org path and validated here.
      IF p_personal_org_id IS NULL THEN
        RAISE EXCEPTION 'team_membership:personal_org_required';
      END IF;
      SELECT o.id INTO v_personal
        FROM public.organizations o
       WHERE o.id = p_personal_org_id AND o.owner_id = p_user_id AND o.is_personal
         AND NOT EXISTS (SELECT 1 FROM public.org_memberships x WHERE x.org_id = o.id)
         FOR UPDATE;
      IF v_personal IS NULL THEN
        RAISE EXCEPTION 'team_membership:personal_org_invalid';
      END IF;
      -- the 079 mirror trigger creates the ACTIVE owner membership of the personal org
      UPDATE public.noctus_users SET org_id = v_personal, org_role = 'owner' WHERE id = p_user_id;
    END IF;
  END IF;

  UPDATE public.platform_org_selections
     SET ended_at = now(), ended_by = 'revoked'
   WHERE user_id = p_user_id AND target_org_id = p_org_id AND ended_at IS NULL;
  GET DIAGNOSTICS v_ended_sel = ROW_COUNT;

  RETURN jsonb_build_object(
    'user_id', p_user_id,
    'org_id', p_org_id,
    'profile_moved_to', COALESCE(v_next_org, v_personal),
    'personal_org_id', v_personal,
    'profile_deleted', false,
    'selections_ended', v_ended_sel
  );
END;
$f$;

-- the 082 signature: no actor (no last-owner override), no personal org (sole membership refused)
CREATE OR REPLACE FUNCTION public.team_member_remove(p_org_id uuid, p_user_id uuid)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $f$
  SELECT public.team_member_remove(p_org_id, p_user_id, NULL::uuid, NULL::uuid);
$f$;

-- 4b. change a member's role in ONE org (D2 override) ----------------------------------------------
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

CREATE OR REPLACE FUNCTION public.team_member_set_role(p_org_id uuid, p_user_id uuid, p_role text)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $f$
  SELECT public.team_member_set_role(p_org_id, p_user_id, p_role, NULL::uuid);
$f$;

-- 5. move a user between orgs (D3) ------------------------------------------------------------------
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

-- 6. accept an invitation (existing user OR first-time invitee) ------------------------------------
CREATE OR REPLACE FUNCTION public.team_invitation_accept(p_invitation_id uuid, p_user_id uuid, p_nome text)
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
  v_new_user  boolean;
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
  v_new_user := NOT EXISTS (SELECT 1 FROM public.noctus_users u WHERE u.id = p_user_id);

  IF v_new_user THEN
    -- first-time invitee: the profile is created in the inviting org (the 079 trigger mirrors the
    -- ACTIVE membership), then the membership is linked to the invitation -- D4, same transaction.
    INSERT INTO public.noctus_users (id, email, nome, org_id, org_role, role)
    VALUES (p_user_id, v_email, COALESCE(NULLIF(btrim(p_nome), ''), v_email),
            v_inv.org_id, v_inv.role, 'user');
    UPDATE public.org_memberships
       SET invited_by = v_inviter, invitation_id = v_inv.id
     WHERE user_id = p_user_id AND org_id = v_inv.org_id AND status = 'active';
    GET DIAGNOSTICS v_activated = ROW_COUNT;
  ELSE
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
  END IF;
  IF v_activated = 0 THEN
    -- lost a race with a concurrent activation/suspension
    RAISE EXCEPTION 'team_membership:already_member';
  END IF;

  UPDATE public.invitations SET status = 'accepted' WHERE id = v_inv.id;

  RETURN jsonb_build_object('user_id', p_user_id, 'org_id', v_inv.org_id, 'org_role', v_inv.role,
                            'invitation_id', v_inv.id, 'new_user', v_new_user,
                            'reactivated', COALESCE(v_status = 'removed', false));
END;
$f$;

CREATE OR REPLACE FUNCTION public.team_invitation_accept(p_invitation_id uuid, p_user_id uuid)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $f$
  SELECT public.team_invitation_accept(p_invitation_id, p_user_id, NULL::text);
$f$;

-- lockdown: service_role only (new + restated) ------------------------------------------------------
REVOKE EXECUTE ON FUNCTION public.team_member_remove(uuid, uuid, uuid, uuid) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.team_member_remove(uuid, uuid) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.team_member_set_role(uuid, uuid, text, uuid) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.team_member_set_role(uuid, uuid, text) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.team_member_move(uuid, uuid, uuid, uuid, text, text) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.team_invitation_accept(uuid, uuid, text) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.team_invitation_accept(uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.team_member_remove(uuid, uuid, uuid, uuid) TO service_role;
GRANT  EXECUTE ON FUNCTION public.team_member_remove(uuid, uuid) TO service_role;
GRANT  EXECUTE ON FUNCTION public.team_member_set_role(uuid, uuid, text, uuid) TO service_role;
GRANT  EXECUTE ON FUNCTION public.team_member_set_role(uuid, uuid, text) TO service_role;
GRANT  EXECUTE ON FUNCTION public.team_member_move(uuid, uuid, uuid, uuid, text, text) TO service_role;
GRANT  EXECUTE ON FUNCTION public.team_invitation_accept(uuid, uuid, text) TO service_role;
GRANT  EXECUTE ON FUNCTION public.team_invitation_accept(uuid, uuid) TO service_role;

-- 7. the selection RPC: a member may not pick an org they are blocked in (D5) -------------------------
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

  IF NOT v_staff AND EXISTS (
       SELECT 1 FROM public.org_member_product_access a
        WHERE a.user_id = p_user_id AND a.org_id = p_target_org_id
          AND a.product_id = v_product_id AND a.unblocked_at IS NULL) THEN
    -- D5: blocked from this product in that org -- not an eligible choice
    RAISE EXCEPTION 'platform_org_selection:product_blocked';
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

REVOKE EXECUTE ON FUNCTION public.platform_org_selection_set(uuid, text, uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.platform_org_selection_set(uuid, text, uuid, uuid) TO service_role;

-- 8. the RLS helper (D1 + D5) -------------------------------------------------------------------
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
  v_pid      uuid;
  v_n        integer;
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
  ELSIF p_schema IS NOT NULL AND COALESCE(v_org_role, '') <> ALL (ARRAY['membro']) THEN
    SELECT p.id INTO v_pid FROM public.products p
     WHERE p.db_schema = p_schema AND p.org_picker_ready;
    IF FOUND THEN
      SELECT s.target_org_id INTO v_target
        FROM public.platform_org_selections s
        JOIN public.org_memberships m
          ON m.user_id = v_uid AND m.org_id = s.target_org_id AND m.status = 'active'
       WHERE s.product_id = v_pid AND s.user_id = v_uid AND s.ended_at IS NULL
         AND s.auth_session_id = NULLIF(v_claims ->> 'session_id', '')::uuid
         AND COALESCE(m.org_role, '') <> ALL (ARRAY['membro'])
         AND EXISTS (SELECT 1 FROM auth.sessions se WHERE se.id = s.auth_session_id)
         AND EXISTS (
           SELECT 1 FROM public.licenses l
            WHERE l.org_id = s.target_org_id AND l.product_id = v_pid
              AND l.status = 'active' AND (l.fim IS NULL OR l.fim > now()))
         AND NOT EXISTS (
           SELECT 1 FROM public.org_member_product_access a
            WHERE a.user_id = v_uid AND a.org_id = s.target_org_id
              AND a.product_id = v_pid AND a.unblocked_at IS NULL);
      IF NOT FOUND THEN
        SELECT count(*), (array_agg(m.org_id))[1] INTO v_n, v_target
          FROM public.org_memberships m
         WHERE m.user_id = v_uid AND m.status = 'active'
           AND COALESCE(m.org_role, '') <> ALL (ARRAY['membro'])
           AND EXISTS (
             SELECT 1 FROM public.licenses l
              WHERE l.org_id = m.org_id AND l.product_id = v_pid
                AND l.status = 'active' AND (l.fim IS NULL OR l.fim > now()))
           AND NOT EXISTS (
             SELECT 1 FROM public.org_member_product_access a
              WHERE a.user_id = v_uid AND a.org_id = m.org_id
                AND a.product_id = v_pid AND a.unblocked_at IS NULL);
        IF v_n >= 2 THEN
          RETURN NULL;
        END IF;
        IF v_n = 0 THEN
          v_target := NULL;
        END IF;
      END IF;
      IF v_target IS NOT NULL THEN
        IF v_hdr IS NULL OR lower(v_hdr) = v_target::text THEN
          RETURN v_target;
        END IF;
        RETURN NULL;
      END IF;
    END IF;
  END IF;
  IF COALESCE(v_org_role, '') = ANY (ARRAY['membro']) THEN
    RETURN NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.org_memberships m
                  WHERE m.user_id = v_uid AND m.org_id = v_home AND m.status = 'active') THEN
    RETURN NULL;
  END IF;
  IF p_schema IS NOT NULL AND EXISTS (
       SELECT 1 FROM public.org_member_product_access a
         JOIN public.products p ON p.id = a.product_id
        WHERE a.user_id = v_uid AND a.org_id = v_home
          AND p.db_schema = p_schema AND a.unblocked_at IS NULL) THEN
    RETURN NULL;
  END IF;
  RETURN v_home;
END;
$f$;

COMMENT ON FUNCTION public.current_org_id_for(text) IS
    'Org picker RLS helper: staff -> the live-selection target (aal2 when the product''s '
    'org_picker_requires_mfa, this login, auth session alive, still licensed); staff on a ready '
    'product with no valid selection -> NULL (core 078); MEMBERS on a ready product (D1/D5, core 083) -> '
    'a valid live selection of an ELIGIBLE org (active non-customer membership, licensed, not blocked), '
    'else NULL with >=2 eligible orgs, the only eligible org with exactly 1, else the home rule; a '
    'present x-noctus-acting-org that differs from the result DENIES; the HOME rule excludes customers, '
    'needs an ACTIVE home membership and is never served to a user blocked from the product there.';
