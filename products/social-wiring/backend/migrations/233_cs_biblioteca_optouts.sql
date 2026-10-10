-- ============================================================================
-- Migration 233 · social_wiring: Biblioteca de virais opt-out / deletion registry
-- ============================================================================
-- WHY: the Biblioteca monitors third-party Instagram creators under LGPD legal basis
-- Art. 7 IX (legitimate interest). That basis requires an opt-out / deletion path, and the Meta
-- Platform Terms require deleting data on request. A creator's opt-out applies to EVERY org, so
-- the registry is platform-wide (handle is UNIQUE, not org-scoped). Service role only: no
-- client ever reads or writes it (platform-admin endpoints go through the backend).
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.cs_biblioteca_optouts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- normalized (lowercase, no @, as in cs_perfis_monitorados.handle)
    handle         TEXT NOT NULL CHECK (handle ~ '^[a-z0-9._]{1,30}$'),
    motivo         TEXT CHECK (motivo IS NULL OR char_length(motivo) <= 1000),
    origem         TEXT NOT NULL CHECK (origem IN ('email', 'dpo', 'admin')),
    solicitado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
    registrado_por UUID,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE social_wiring.cs_biblioteca_optouts IS
    'Migration 233 - Biblioteca opt-out registry: a monitored creator asked not to be monitored; platform-wide, service role only.';

CREATE UNIQUE INDEX IF NOT EXISTS cs_biblioteca_optouts_handle_uq
    ON social_wiring.cs_biblioteca_optouts (handle);

ALTER TABLE social_wiring.cs_biblioteca_optouts ENABLE ROW LEVEL SECURITY;
-- No policies on purpose: only the service role (bypasses RLS) reaches this table.
REVOKE ALL ON social_wiring.cs_biblioteca_optouts FROM authenticated, anon;

DROP POLICY IF EXISTS "cs_biblioteca_optouts_service_role" ON social_wiring.cs_biblioteca_optouts;
CREATE POLICY "cs_biblioteca_optouts_service_role"
    ON social_wiring.cs_biblioteca_optouts
    FOR ALL TO service_role USING (true) WITH CHECK (true);
