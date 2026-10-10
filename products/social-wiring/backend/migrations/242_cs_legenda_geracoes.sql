-- ============================================================================
-- Migration 242 · social_wiring: cs_legenda_geracoes -- the durable counter behind the Esteira
-- AI-caption daily cap (legendas_dia_usuario)
-- ============================================================================
-- WHY
-- ---
-- Contract: projects/core-studio/specs/esteira-contract.md section 5.3 (cap 40/day/user) and 9.
-- The caption is RETURNED, never saved, so a generation leaves no row anywhere: without this log the
-- cap could only be counted in process memory (per worker, lost on restart). One row is written by
-- the service each time the model was actually reached; the cap is the count of the user's rows in
-- the last 24 h.
--
-- * post_id is ON DELETE SET NULL: deleting a post must not hand the user their quota back.
-- * Written by the backend (service role). Authenticated users may only READ their org's rows.
-- * No CHECK / UNIQUE / trigger: there is no domain rule to guard beyond NOT NULLs and the FKs, so
--   there is nothing for a GuardProbe to prove (the keeper check_migration_guard_has_probe only
--   registers trigger / CHECK / UNIQUE guards).
--
-- FORWARD-ONLY, IDEMPOTENT. Requires 241 (cs_posts).
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.cs_posts') IS NULL THEN
    RAISE EXCEPTION 'Migration 242 requires social_wiring.cs_posts (migration 241) -- apply 241 first';
  END IF;
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'Migration 242 requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
END
$guard$;

CREATE TABLE IF NOT EXISTS social_wiring.cs_legenda_geracoes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    user_id     UUID NOT NULL,
    post_id     UUID REFERENCES social_wiring.cs_posts (id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE social_wiring.cs_legenda_geracoes IS
    'Migration 242 - one row per AI caption generation (model reached); counted over a rolling 24 h window for legendas_dia_usuario.';

-- The rolling-window count: WHERE org_id = ? AND user_id = ? AND created_at >= now() - 24h.
CREATE INDEX IF NOT EXISTS cs_legenda_geracoes_janela_idx
    ON social_wiring.cs_legenda_geracoes (org_id, user_id, created_at DESC);

ALTER TABLE social_wiring.cs_legenda_geracoes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_legenda_geracoes_select_own_org" ON social_wiring.cs_legenda_geracoes;
CREATE POLICY "cs_legenda_geracoes_select_own_org"
    ON social_wiring.cs_legenda_geracoes
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_legenda_geracoes_service_role" ON social_wiring.cs_legenda_geracoes;
CREATE POLICY "cs_legenda_geracoes_service_role"
    ON social_wiring.cs_legenda_geracoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);
