-- Editorial roles for Nos no Limiar (OWNER DECISION 2026-10-05, nnl-editorial-roles = split).
--
--   Monica Tangerino : editorial review + publish   -> editorial:editar, editorial:revisar, editorial:publicar
--   Joao             : safety / source review       -> editorial:revisar_seguranca
--   Claude           : drafts only, as the machine identity "Claude (rascunho)"
--                      (app.stores.knowledge_editorial.CLAUDE_DRAFT_AUTHOR_ID) — it holds NO grant and
--                      no user account, so a human can always approve its drafts.
--   Nobody approves their own work: enforced in code AND in the DB (editorial_transition re-checks
--   it), not by this file.
--
-- This is grant ASSIGNMENT (data), not schema: `public.user_permission_grants` is the user-global
-- permissions organ (core 046). It is NOT part of migration 018 because it depends on which
-- accounts exist. Idempotent (ON CONFLICT DO NOTHING); a person with no account yet is SKIPPED
-- with a NOTICE — never an invented user id. Re-run it once the account exists.
--
-- HOW: set the two emails below (exactly as the accounts sign in), then run this script through
-- the Supabase SQL runner. To read what it did: SELECT u.email, g.permission
--   FROM public.user_permission_grants g JOIN auth.users u ON u.id = g.user_id
--  WHERE g.permission LIKE 'editorial:%' ORDER BY 1, 2;
--
-- The grants are USER-GLOBAL: the editorial router additionally requires an org membership and an
-- item/org match, and the editors must be org admins/owners (the agents router is admin-gated, so
-- the admin MFA policy applies to them).

DO $roles$
DECLARE
    v_monica_email TEXT := NULL;  -- <- Monica's sign-in email (no account yet? leave NULL: skipped)
    v_joao_email   TEXT := NULL;  -- <- Joao's sign-in email
    v_assign CONSTANT TEXT[][] := ARRAY[
        ARRAY['monica', 'editorial:editar'],
        ARRAY['monica', 'editorial:revisar'],
        ARRAY['monica', 'editorial:publicar'],
        ARRAY['joao',   'editorial:revisar_seguranca']
    ];
    v_who TEXT;
    v_email TEXT;
    v_uid UUID;
    i INT;
BEGIN
    FOR i IN 1 .. array_length(v_assign, 1) LOOP
        v_who := v_assign[i][1];
        v_email := CASE v_who WHEN 'monica' THEN v_monica_email ELSE v_joao_email END;
        IF v_email IS NULL OR btrim(v_email) = '' THEN
            RAISE NOTICE 'skipped % for %: email not provided', v_assign[i][2], v_who;
            CONTINUE;
        END IF;
        SELECT id INTO v_uid FROM auth.users WHERE lower(email) = lower(btrim(v_email));
        IF v_uid IS NULL THEN
            RAISE NOTICE 'skipped % for %: no account with that email yet', v_assign[i][2], v_who;
            CONTINUE;
        END IF;
        INSERT INTO public.user_permission_grants (user_id, permission)
        VALUES (v_uid, v_assign[i][2])
        ON CONFLICT (user_id, permission) DO NOTHING;
    END LOOP;
END
$roles$;
