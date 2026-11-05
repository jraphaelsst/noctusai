-- ============================================================================
-- Migration 323 -- social_wiring: Julia's ALLOWLIST ("lista de permitidos") + its on/off switch (owner 2026-11-05)
-- ============================================================================
-- WHY: owner, verbatim: "add the allowlist with a switch on/off, so I can set my own number so she only replies to me at first.
-- The list, when empty, answers all numbers." Sits next to the blocklist (migration 298).
--
-- WHAT
--   1. julia_permitidos: the per-org allowlist (number as canonical phone digits, optional label, who/when). Unique per (org, number).
--   2. julia_protecao_config.permitidos_ativo (default false): the switch. ON + a non-empty list => only listed numbers are Julia's;
--      OFF or an empty list => nobody is filtered.
--
-- FORWARD-ONLY, IDEMPOTENT, additive (the previous image ignores the new column and table). No SECURITY DEFINER.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.julia_protecao_config') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.julia_protecao_config (migration 298)';
  END IF;
END
$guard$;

ALTER TABLE social_wiring.julia_protecao_config
    ADD COLUMN IF NOT EXISTS permitidos_ativo boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS social_wiring.julia_permitidos (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     uuid        NOT NULL,
    numero     text        NOT NULL CHECK (numero ~ '^[0-9]{10,15}$'),
    rotulo     text        CHECK (rotulo IS NULL OR char_length(btrim(rotulo)) BETWEEN 1 AND 120),
    criado_por uuid,
    criado_em  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT julia_permitidos_org_numero_uk UNIQUE (org_id, numero)
);

COMMENT ON TABLE social_wiring.julia_permitidos IS
    'Per-org allowlist (migration 323): with julia_protecao_config.permitidos_ativo ON and the list non-empty, only these numbers are '
    'Julia''s; a listed number bypasses the 11.1 snapshot / previous-chat rules (an explicit opt-in). Backend-only.';

DO $rls$
BEGIN
  ALTER TABLE social_wiring.julia_permitidos ENABLE ROW LEVEL SECURITY;
  DROP POLICY IF EXISTS julia_permitidos_service_role ON social_wiring.julia_permitidos;
  CREATE POLICY julia_permitidos_service_role ON social_wiring.julia_permitidos FOR ALL TO service_role USING (true) WITH CHECK (true);
  REVOKE ALL ON social_wiring.julia_permitidos FROM PUBLIC, anon, authenticated;
END
$rls$;
