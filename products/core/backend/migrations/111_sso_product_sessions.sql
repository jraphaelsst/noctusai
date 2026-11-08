-- Migration 111: public.sso_product_sessions -- the product-session registry (SSO lifecycle slice S2).
-- Design: project-history/plans/sso-session-lifecycle-2026-11.md section B (B1), table F row S2.
-- Schema: public
--
-- EXPAND-ONLY and backward-compatible with the previous image: a new table nothing in N-1 reads.
-- `/api/sso/session` (`_generate_session`) writes one row per minted product session; the seed auth
-- dependency resolves `session_id -> product_slug` so core can tell a product-born session from a
-- core-born one (observe mode logs, S8 enforces). Sessions minted before this table are unregistered
-- and look like core sessions -- the S8 sweep handles them.
--
-- FK to auth.sessions? DECIDED: NO FK; a PURGE FUNCTION instead.
--   * auth.sessions is GoTrue-owned. The migration replay (PGlite, run twice pre-commit) does not stub
--     it, so a REFERENCES clause would fail the chain replay.
--   * The project's precedent for binding to a GoTrue session is by VALUE with a lazy EXISTS check
--     (070 `platform_org_selections.auth_session_id`, 072/073/078) -- never an FK into `auth.sessions`.
--     (FKs to auth.users exist, 079, because that table is the stable identity root.)
--   * A GoTrue upgrade that recreates `auth.sessions` must not cascade into a security registry.
--   Cost of no-FK: orphan rows after logout/expiry. `sso_product_sessions_purge()` deletes rows whose
--   session no longer exists (never by age alone: an age purge would un-register a LIVE session, and
--   an unregistered product session looks like a core session = fail-open at S8). The body reads
--   auth.sessions lazily (plpgsql), so replay is unaffected. Scheduling it rides the jobs organ.
--   NOC-REMEDIATE[sso-registry-purge-job]: schedule `sso_product_sessions_purge()` via the jobs organ
--   (dedupe_key, lease) before S8 enforce; rows are tiny and the registry lookup is a PK read, so
--   growth is harmless until then. -- 2026-11-08

SET search_path = public, public;

CREATE TABLE IF NOT EXISTS public.sso_product_sessions (
    session_id   uuid        PRIMARY KEY,           -- the access token's `session_id` claim (= auth.sessions.id)
    user_id      uuid        NOT NULL,
    product_slug text        NOT NULL,
    jti          text,                              -- the SSO token redeemed to mint this session (audit)
    minted_at    timestamptz NOT NULL DEFAULT now()
);

-- Per-user lookups (S6 "revoke this user's product sessions") and the purge scan.
CREATE INDEX IF NOT EXISTS idx_sso_product_sessions_user ON public.sso_product_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sso_product_sessions_minted_at ON public.sso_product_sessions (minted_at);

-- SERVICE-ROLE ONLY: RLS on, NO policies, no browser grant (access-tiers: Platform IP).
ALTER TABLE public.sso_product_sessions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sso_product_sessions FROM PUBLIC, anon, authenticated;
COMMENT ON TABLE public.sso_product_sessions IS 'tier:service';

CREATE OR REPLACE FUNCTION public.sso_product_sessions_purge()
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth, pg_temp
AS $$
DECLARE
  v_deleted bigint;
BEGIN
  DELETE FROM public.sso_product_sessions r
   WHERE NOT EXISTS (SELECT 1 FROM auth.sessions s WHERE s.id = r.session_id);
  GET DIAGNOSTICS v_deleted = ROW_COUNT;
  RETURN v_deleted;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.sso_product_sessions_purge() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.sso_product_sessions_purge() TO service_role;
