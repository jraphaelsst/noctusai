-- ============================================================================
-- Migration 315 · social_wiring: imovel_notas — our own notes on an imóvel
-- ============================================================================
-- OWNER DIRECTIVE (2026-11-03): the imóvel UI is a mirror of Vista's data PLUS
-- what we add over time, with full CRUD on what is ours. An internal note
-- ("o proprietário só atende à tarde", "chave com o porteiro") is ours by
-- definition: Vista has no such field and a sync must never touch it.
--
-- One row per note, keyed to `imovel_registry` (NOT the `imoveis` mirror) for
-- the reason migration 076 gives: a property leaves the Vista catalog when it
-- is sold, exactly when its paperwork is being handled. Written only by
-- `imovel_hub.notas_service`; never by a sync.
--
-- FORWARD-ONLY, IDEMPOTENT. MIGRATION FILE ONLY — not applied by this change
-- (see `migrations/APPLIED.md`).
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.imovel_notas (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    codigo      TEXT NOT NULL,
    texto       TEXT NOT NULL,
    created_by  UUID,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by  UUID,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Blank / over-long text is refused by notas_service (400) — no CHECK here:
    -- a DB guard needs a behaviour probe in verify_db_guards (not warranted for
    -- free text), and the single writer is the service.
    CONSTRAINT imovel_notas_imovel_fk
        FOREIGN KEY (org_id, codigo)
        REFERENCES social_wiring.imovel_registry (org_id, codigo_canonical) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS imovel_notas_org_codigo_idx
    ON social_wiring.imovel_notas (org_id, codigo, created_at DESC);

COMMENT ON TABLE social_wiring.imovel_notas IS
    'Internal free-text notes on an imóvel (migration 315). Owned data: never '
    'written by the Vista sync. CRUD via imovel_hub.notas_service.';

ALTER TABLE social_wiring.imovel_notas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imovel_notas_select_own_org" ON social_wiring.imovel_notas;
CREATE POLICY "imovel_notas_select_own_org"
    ON social_wiring.imovel_notas
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "imovel_notas_service_role" ON social_wiring.imovel_notas;
CREATE POLICY "imovel_notas_service_role"
    ON social_wiring.imovel_notas
    FOR ALL TO service_role USING (true) WITH CHECK (true);
