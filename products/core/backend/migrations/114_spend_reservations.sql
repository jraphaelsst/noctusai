-- Migration: 114_spend_reservations
-- Schema: public (core)
-- WHAT: the shared rolling-window spend ceiling (owner decision 2026-11-09: $10 per org per rolling 24h, ONE ceiling
--   shared by every mechanism that spends on an org's behalf: eval runs, mecanismo runs, later the improver loop).
--   public.spend_reservations  - one row per reserved run; reserved_usd is the cap while the run is unfinished,
--                                actual_usd (set by spend_settle) replaces it once the cost is known.
--   public.spend_reserve(...)  - the ONLY admission path: advisory-locked per (ceiling_key, org), sums the window,
--                                refuses (allowed=false) when spent + amount would cross the ceiling, else inserts.
--                                One RPC = one transaction, so two concurrent starts cannot both slip under.
--   public.spend_settle(...)   - records the actual cost of a reservation.
-- Seed side: noctusai_lib/integrations/llm/spend_ceiling.py (Protocol + Fake + Real + factory).
-- Backward-compatible with the previous image (new objects only). Service-role only: no authenticated/anon grant.
-- Re-runnable: IF NOT EXISTS / OR REPLACE.
SET search_path = public, public;

CREATE TABLE IF NOT EXISTS public.spend_reservations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ceiling_key  TEXT NOT NULL CHECK (length(ceiling_key) BETWEEN 1 AND 80),
    kind         TEXT NOT NULL CHECK (length(kind) BETWEEN 1 AND 80),
    org_id       UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    ref          TEXT NOT NULL CHECK (length(ref) BETWEEN 1 AND 200),
    reserved_usd NUMERIC(12, 6) NOT NULL CHECK (reserved_usd >= 0),
    actual_usd   NUMERIC(12, 6) CHECK (actual_usd IS NULL OR actual_usd >= 0),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    settled_at   TIMESTAMPTZ,
    CONSTRAINT spend_reservations_ref_unique UNIQUE (ceiling_key, kind, ref)
);
CREATE INDEX IF NOT EXISTS spend_reservations_window_idx
    ON public.spend_reservations (ceiling_key, org_id, created_at DESC);
-- Rolling-window spend ceiling ledger (one row per reserved run; actual_usd replaces reserved_usd once settled).
COMMENT ON TABLE public.spend_reservations IS 'tier:service';

ALTER TABLE public.spend_reservations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.spend_reservations FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.spend_reservations TO service_role;
DROP POLICY IF EXISTS "service_role_bypass" ON public.spend_reservations;
CREATE POLICY "service_role_bypass" ON public.spend_reservations FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE FUNCTION public.spend_reserve(
    p_ceiling_key  TEXT,
    p_kind         TEXT,
    p_org_id       UUID,
    p_ref          TEXT,
    p_amount_usd   NUMERIC,
    p_ceiling_usd  NUMERIC,
    p_window_hours INTEGER DEFAULT 24
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_spent NUMERIC;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_ceiling_key || ':' || p_org_id::text, 0));
    SELECT COALESCE(SUM(COALESCE(actual_usd, reserved_usd)), 0) INTO v_spent
      FROM public.spend_reservations
     WHERE ceiling_key = p_ceiling_key AND org_id = p_org_id
       AND created_at > now() - make_interval(hours => p_window_hours);
    -- Idempotent retry of the same run: already reserved, never double-counted.
    IF EXISTS (SELECT 1 FROM public.spend_reservations
                WHERE ceiling_key = p_ceiling_key AND kind = p_kind AND ref = p_ref) THEN
        RETURN jsonb_build_object('allowed', true, 'spent_usd', v_spent);
    END IF;
    IF v_spent + p_amount_usd > p_ceiling_usd THEN
        RETURN jsonb_build_object('allowed', false, 'spent_usd', v_spent);
    END IF;
    INSERT INTO public.spend_reservations (ceiling_key, kind, org_id, ref, reserved_usd)
    VALUES (p_ceiling_key, p_kind, p_org_id, p_ref, p_amount_usd);
    RETURN jsonb_build_object('allowed', true, 'spent_usd', v_spent);
END;
$$;
REVOKE ALL ON FUNCTION public.spend_reserve(TEXT, TEXT, UUID, TEXT, NUMERIC, NUMERIC, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.spend_reserve(TEXT, TEXT, UUID, TEXT, NUMERIC, NUMERIC, INTEGER) TO service_role;

CREATE OR REPLACE FUNCTION public.spend_settle(
    p_ceiling_key TEXT,
    p_kind        TEXT,
    p_ref         TEXT,
    p_actual_usd  NUMERIC
) RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_n INTEGER;
BEGIN
    UPDATE public.spend_reservations
       SET actual_usd = p_actual_usd, settled_at = now()
     WHERE ceiling_key = p_ceiling_key AND kind = p_kind AND ref = p_ref;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n > 0;
END;
$$;
REVOKE ALL ON FUNCTION public.spend_settle(TEXT, TEXT, TEXT, NUMERIC) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.spend_settle(TEXT, TEXT, TEXT, NUMERIC) TO service_role;
