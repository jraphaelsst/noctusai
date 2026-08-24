-- ============================================================================
-- Migration 069 -- social_wiring: sync_leases, a cross-process run lock
--
-- WHY NOT `pg_advisory_lock`
-- --------------------------
-- The obvious answer to "stop two processes running the same job" is a
-- Postgres advisory lock. It does not work here, and the reason is worth
-- writing down so nobody re-proposes it.
--
-- Advisory locks are SESSION-scoped. Every call from this backend goes
-- through PostgREST over HTTP, which pools connections — the session that
-- takes the lock is returned to the pool the moment the request ends, and
-- the lock is released with it. `pg_try_advisory_lock` over PostgREST
-- would return true to two callers in a row and protect nothing.
--
-- So the lock is a LEASE ROW with an expiry instead: state that outlives
-- the connection, which is exactly the property advisory locks lack here.
--
-- WHY AN EXPIRY RATHER THAN AN EXPLICIT RELEASE
-- ---------------------------------------------
-- The holder releases on the way out, but a holder that is SIGKILLed, or
-- whose machine sleeps mid-run (the 2026-08-22 incident: a laptop froze
-- mid-sync during a macOS DarkWake and never came back), never releases
-- anything. Without a TTL that job is wedged forever and the failure is
-- invisible — the nightly sync would simply stop, silently, and the
-- registry would drift.
--
-- The TTL is the recovery mechanism, not a nicety. It is the caller's
-- job to pick one comfortably longer than the work: the imóveis sync
-- measures 403s, and the caller asks for 1800s.
--
-- ATOMICITY
-- ---------
-- Acquisition is ONE statement — `INSERT ... ON CONFLICT DO UPDATE ...
-- WHERE expires_at < now()`. Two processes racing both execute it; the
-- row lock inside `ON CONFLICT` serialises them, and the second sees a
-- non-expired `expires_at` so its `WHERE` matches nothing and it returns
-- no row. A read-then-write (`SELECT` then `INSERT`) would have a window
-- between the two and would be exactly wrong.
--
-- PREREQUISITE: 011_rls_current_org_id.sql.
-- Forward-only + idempotent.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.sync_leases (
    -- The job name. One row per job, forever — rows are updated in place,
    -- never accumulated, so this table stays at ~the number of jobs.
    name        TEXT        PRIMARY KEY,
    -- Who holds it. Host + pid, for diagnosis: "which box is running this"
    -- is the first question when a lease looks stuck.
    holder      TEXT        NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);

ALTER TABLE social_wiring.sync_leases ENABLE ROW LEVEL SECURITY;

-- service_role only. Deliberately NO `authenticated` SELECT policy: this is
-- backend coordination state, not tenant data, and it is not org-scoped —
-- the jobs it guards are fleet-level. Granting a tenant read access would
-- leak the shape of our infrastructure for no product benefit.
DROP POLICY IF EXISTS "sync_leases_service_role" ON social_wiring.sync_leases;
CREATE POLICY "sync_leases_service_role" ON social_wiring.sync_leases
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── Acquire ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION social_wiring.try_acquire_sync_lease(
    p_name TEXT,
    p_holder TEXT,
    p_ttl_seconds INTEGER DEFAULT 1800
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SET search_path TO 'social_wiring', 'public'
AS $$
DECLARE
    v_got BOOLEAN := FALSE;
BEGIN
    IF p_ttl_seconds IS NULL OR p_ttl_seconds <= 0 THEN
        RAISE EXCEPTION
            'try_acquire_sync_lease: p_ttl_seconds must be > 0 (got %). A '
            'zero or negative TTL creates a lease that is already expired, '
            'which is a lock that never locks.', p_ttl_seconds
            USING ERRCODE = 'raise_exception';
    END IF;

    INSERT INTO social_wiring.sync_leases (name, holder, acquired_at, expires_at)
    VALUES (p_name, p_holder, now(), now() + make_interval(secs => p_ttl_seconds))
    ON CONFLICT (name) DO UPDATE
       SET holder      = EXCLUDED.holder,
           acquired_at = EXCLUDED.acquired_at,
           expires_at  = EXCLUDED.expires_at
     -- The whole lock, in one predicate: take it over only if the
     -- incumbent lease has expired. A live lease matches nothing, no row
     -- is returned, and the caller learns it lost.
     WHERE social_wiring.sync_leases.expires_at < now()
    RETURNING TRUE INTO v_got;

    RETURN COALESCE(v_got, FALSE);
END;
$$;

-- ── Release ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION social_wiring.release_sync_lease(
    p_name TEXT,
    p_holder TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SET search_path TO 'social_wiring', 'public'
AS $$
DECLARE
    v_deleted INTEGER := 0;
BEGIN
    -- Holder-scoped on purpose. If our lease already expired and another
    -- process legitimately took over, releasing "ours" must NOT delete
    -- theirs — that would hand the job to a third process while the second
    -- is still running, which is the exact overlap this table prevents.
    DELETE FROM social_wiring.sync_leases
     WHERE name = p_name AND holder = p_holder;
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted > 0;
END;
$$;
