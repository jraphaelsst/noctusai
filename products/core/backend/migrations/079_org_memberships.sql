-- Migration: org memberships — one user ↔ many orgs (multi-org S1)
-- Schema: public (core)
-- Roadmap: project-history/roadmaps/multi-org-membership-2026-10.md
--
-- EXPAND-ONLY. Nothing the running image reads changes behaviour:
--   * org_memberships is a NEW service-role-only table (+ a self-read policy) -- no reader yet;
--   * noctus_users.org_id / org_role stay the source every current reader uses. From S2 on they
--     are DEMOTED to "home / last-active org" (a mirror), never the membership list;
--   * a trigger keeps the mirror honest in the expand window: every noctus_users insert, or an
--     org_id / org_role change, upserts the matching ACTIVE membership. It never ends one --
--     ending is S4's explicit remove-member path, not an implicit side effect of a home switch.
--
-- Why: a user could belong to exactly one org (noctus_users.org_id NOT NULL), so
-- accept-invite answered 409 "Você já pertence a outra organização" and an owner could not run
-- a company org, a personal-brand org and a second company at once (motange@gmail.com,
-- 2026-10-12). The org picker (070) already carries a chosen org into the resolver + RLS for
-- staff; S2/S3 widen its WHO from "staff" to "staff OR active member of the target org".
SET search_path = public, public;

-- 1. Table ---------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.org_memberships (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    org_id         uuid        NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    -- Free text on purpose: same vocabulary as noctus_users.org_role (owner, admin, member,
    -- corretor, juridico, membro, ...) which carries no CHECK either; roles stay per product.
    org_role       text        NOT NULL DEFAULT 'member',
    status         text        NOT NULL DEFAULT 'active'
                               CHECK (status IN ('invited', 'active', 'suspended', 'removed')),
    invited_by     uuid        REFERENCES auth.users(id) ON DELETE SET NULL,
    invitation_id  uuid        REFERENCES public.invitations(id) ON DELETE SET NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    ended_at       timestamptz,
    CONSTRAINT org_memberships_user_org_key UNIQUE (user_id, org_id),
    CONSTRAINT org_memberships_ended_iff_removed CHECK ((status = 'removed') = (ended_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS org_memberships_org_active_idx
    ON public.org_memberships (org_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS org_memberships_user_active_idx
    ON public.org_memberships (user_id) WHERE status = 'active';

COMMENT ON TABLE public.org_memberships IS
    'Which orgs a user belongs to, with the role IN THAT ORG. The authoritative membership list '
    '(multi-org, 2026-10). noctus_users.org_id/org_role = the home / last-active org mirror only. '
    'Role reads for an org MUST come from here, never from the home row (privilege-leak guard).';

-- 2. Access: service role writes; a user may read only their own memberships -----------------
ALTER TABLE public.org_memberships ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.org_memberships FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.org_memberships TO authenticated;
GRANT ALL ON public.org_memberships TO service_role;

DROP POLICY IF EXISTS org_memberships_self_read ON public.org_memberships;
CREATE POLICY org_memberships_self_read ON public.org_memberships
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

-- 3. updated_at -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.org_memberships_touch()
RETURNS trigger LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS org_memberships_touch ON public.org_memberships;
CREATE TRIGGER org_memberships_touch BEFORE UPDATE ON public.org_memberships
    FOR EACH ROW EXECUTE FUNCTION public.org_memberships_touch();

-- 4. Mirror sync: a home-org write always has a matching ACTIVE membership -------------------
CREATE OR REPLACE FUNCTION public.org_memberships_sync_from_home()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    INSERT INTO public.org_memberships (user_id, org_id, org_role, status)
    VALUES (NEW.id, NEW.org_id, COALESCE(NEW.org_role, 'member'), 'active')
    ON CONFLICT (user_id, org_id) DO UPDATE
        SET org_role = EXCLUDED.org_role,
            status   = 'active',
            ended_at = NULL;
    RETURN NEW;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.org_memberships_sync_from_home() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS org_memberships_sync_from_home ON public.noctus_users;
CREATE TRIGGER org_memberships_sync_from_home
    AFTER INSERT OR UPDATE OF org_id, org_role ON public.noctus_users
    FOR EACH ROW EXECUTE FUNCTION public.org_memberships_sync_from_home();

-- 5. Backfill: one ACTIVE membership per existing profile -----------------------------------
INSERT INTO public.org_memberships (user_id, org_id, org_role, status, created_at)
SELECT nu.id, nu.org_id, COALESCE(nu.org_role, 'member'), 'active', COALESCE(nu.created_at, now())
  FROM public.noctus_users nu
  JOIN auth.users au ON au.id = nu.id
ON CONFLICT (user_id, org_id) DO NOTHING;

-- Loud parity check: every profile whose auth user exists must now have its home membership.
DO $$
DECLARE missing int;
BEGIN
    SELECT count(*) INTO missing
      FROM public.noctus_users nu
      JOIN auth.users au ON au.id = nu.id
     WHERE NOT EXISTS (SELECT 1 FROM public.org_memberships m
                        WHERE m.user_id = nu.id AND m.org_id = nu.org_id AND m.status = 'active');
    IF missing > 0 THEN
        RAISE EXCEPTION 'org_memberships backfill: % profile(s) without a home membership', missing;
    END IF;
END;
$$;
