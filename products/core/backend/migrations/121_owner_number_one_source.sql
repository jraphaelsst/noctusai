-- Migration: 121_owner_number_one_source
-- Schema: public (core)
-- Project: owner-kept-ideas-2026-11 (W1-D, idea r17: the owner number is set ONCE, in core).
--
-- WHAT: core `public.notification_owner_recipients` (118) is the platform's ONE list of owner numbers. Agents used to
-- keep its own copy (`agents.runtime_settings` key 'numero_fallback_atendimento', 074) for the hand-off notice, so prod
-- had a number in agents and ZERO active recipients in core (the owner's WhatsApp notices had nobody to go to).
-- This copies the existing agents number into core as an ACTIVE recipient, straight from that row (no number in code
-- or in this file). Agents' own code now reads core; the old agents row stays untouched (a later cleanup drops it).
--
-- The row is attributed to the nil UUID = "migration" (the events table refuses a change with no actor).
-- Guarded: a database without the agents schema/table (core replay, fresh environments) is a no-op; a missing or
-- malformed agents value is a no-op (nothing to copy); a number already in core is left exactly as the owner set it.
-- Re-runnable.
SET search_path = public, public;
SET lock_timeout = '5s';

DO $$
DECLARE
    v_numero TEXT;
BEGIN
    IF to_regclass('agents.runtime_settings') IS NULL THEN
        RETURN;
    END IF;
    EXECUTE $q$SELECT value #>> '{}' FROM agents.runtime_settings WHERE key = 'numero_fallback_atendimento'$q$
        INTO v_numero;
    IF v_numero IS NULL OR v_numero !~ '^\+[1-9][0-9]{7,14}$' THEN
        RETURN;
    END IF;
    INSERT INTO public.notification_owner_recipients (numero, nome, ativo, alterado_por, alterado_em)
    VALUES (v_numero, 'Número de atendimento (copiado do agents)', true,
            '00000000-0000-0000-0000-000000000000'::uuid, now())
    ON CONFLICT (numero) DO NOTHING;
END $$;
