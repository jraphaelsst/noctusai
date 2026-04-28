-- Migration 006: Concurrent session cap function
--
-- Creates a PostgreSQL function that enforces a maximum number of concurrent
-- sessions per user by deleting the oldest sessions when the cap is exceeded.
-- Called from the login endpoint after successful authentication.

CREATE OR REPLACE FUNCTION public.enforce_session_cap(p_user_id UUID, p_max_sessions INT DEFAULT 5)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, auth
AS $$
DECLARE
  session_count INT;
BEGIN
  SELECT COUNT(*) INTO session_count FROM auth.sessions WHERE user_id = p_user_id;
  IF session_count > p_max_sessions THEN
    DELETE FROM auth.sessions
    WHERE id IN (
      SELECT id FROM auth.sessions
      WHERE user_id = p_user_id
      ORDER BY created_at ASC
      LIMIT (session_count - p_max_sessions)
    );
  END IF;
END;
$$;
